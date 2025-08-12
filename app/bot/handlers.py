from datetime import datetime
from pathlib import Path

from aiogram import Bot, Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, func

import app.texts as texts
from app.avatars import save_avatar, _emoji_avatar, _sticker_avatar
from app.models import User, StepOption, Idea, IdeaVote, McqAnswer
from app.settings import settings
from app.web import hub
from .context import get_ctx
from .keyboards import mcq_kb, idea_vote_kb
from .prompts import send_prompt

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    session, user, state, step = await get_ctx(str(message.from_user.id))
    try:
        await save_avatar(bot, user)
        user.waiting_for_name = True
        await session.commit()
        if user.name:
            await message.answer(texts.CURRENT_NAME.format(name=user.name))
        else:
            await message.answer(texts.ENTER_NAME)
    finally:
        await session.close()


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, bot: Bot):
    session, user, state, step = await get_ctx(str(message.from_user.id))
    try:
        user.waiting_for_name = False
        await session.commit()
        await send_prompt(bot, user, step, state.phase, prefix=texts.NAME_UNCHANGED)
    finally:
        await session.close()


@router.message(F.text & ~F.via_bot)
async def on_text(message: Message, bot: Bot):
    session, user, state, step = await get_ctx(str(message.from_user.id))
    try:
        if user.waiting_for_avatar:
            emoji = message.text.strip()
            if not emoji:
                await message.answer(texts.ASK_AVATAR)
                return
            path = Path(settings.AVATAR_DIR)
            path.mkdir(exist_ok=True)
            _emoji_avatar(path, user, emoji[0])
            user.waiting_for_avatar = False
            await session.commit()
            await hub.broadcast({"type": "reload"})
            await send_prompt(bot, user, step, state.phase, prefix=texts.NAME_SAVED)
            return

        if user.waiting_for_name:
            new_name = message.text.strip()[:120]
            if not new_name:
                await message.answer(texts.NAME_EMPTY)
                return
            was_new = user.name == ""
            user.name = new_name
            user.waiting_for_name = False
            await session.commit()
            saved = await save_avatar(bot, user)
            if was_new and not saved:
                user.waiting_for_avatar = True
                await session.commit()
                await message.answer(texts.ASK_AVATAR)
            else:
                await hub.broadcast({"type": "reload"})
                await send_prompt(bot, user, step, state.phase, prefix=texts.NAME_SAVED)
            return

        if step.type == "open" and state.phase == 0:
            existing = (
                await session.execute(
                    select(Idea).where(Idea.step_id == step.id, Idea.user_id == user.id)
                )
            ).scalar_one_or_none()
            now = datetime.utcnow()
            delta_ms = int((now - state.step_started_at).total_seconds() * 1000)
            delta_ms = max(0, delta_ms)
            if existing:
                old_delta = int(
                    (existing.submitted_at - state.step_started_at).total_seconds() * 1000
                )
                existing.text = message.text.strip()
                existing.submitted_at = now
                user.total_answer_ms += delta_ms - old_delta
                user.open_answer_ms += delta_ms - old_delta
            else:
                session.add(
                    Idea(
                        step_id=step.id,
                        user_id=user.id,
                        text=message.text.strip(),
                        submitted_at=now,
                    )
                )
                user.total_answer_ms += delta_ms
                user.open_answer_ms += delta_ms
                user.open_answer_count += 1
            await session.commit()
            await message.answer(texts.IDEA_ACCEPTED, parse_mode="HTML")
            count = await session.scalar(
                select(func.count(Idea.id)).where(Idea.step_id == step.id)
            )
            total = await session.scalar(
                select(func.count(User.id)).where(User.name != "")
            )
            last_at = await session.scalar(
                select(func.max(Idea.submitted_at)).where(Idea.step_id == step.id)
            )
            last_ago = None
            if last_at:
                last_ago = int((datetime.utcnow() - last_at).total_seconds())
            await hub.broadcast(
                {"type": "idea_progress", "count": int(count or 0), "total": int(total or 0), "last": last_ago}
            )
        else:
            await message.answer(texts.TEXT_NOT_ACCEPTED)
    finally:
        await session.close()


@router.message(F.sticker)
async def on_sticker(message: Message, bot: Bot):
    session, user, state, step = await get_ctx(str(message.from_user.id))
    try:
        if user.waiting_for_avatar:
            await _sticker_avatar(bot, user, message.sticker)
            user.waiting_for_avatar = False
            await session.commit()
            await hub.broadcast({"type": "reload"})
            await send_prompt(bot, user, step, state.phase, prefix=texts.NAME_SAVED)
    finally:
        await session.close()


@router.callback_query(F.data.startswith("mcq:"))
async def cb_mcq(cb: CallbackQuery, bot: Bot):
    choice_idx = int(cb.data.split(":")[1])
    session, user, state, step = await get_ctx(str(cb.from_user.id))
    try:
        if step.type != "quiz" or state.phase != 0:
            await cb.answer(texts.NOT_ANSWER_PHASE, show_alert=True)
            return
        existing = (
            await session.execute(
                select(McqAnswer).where(
                    McqAnswer.step_id == step.id, McqAnswer.user_id == user.id
                )
            )
        ).scalar_one_or_none()
        now = datetime.utcnow()
        delta_ms = int((now - state.step_started_at).total_seconds() * 1000)
        delta_ms = max(0, delta_ms)
        if existing and existing.choice_idx == choice_idx:
            await cb.answer(texts.ANSWER_UNCHANGED)
            return
        if existing:
            old_delta = int(
                (existing.answered_at - state.step_started_at).total_seconds() * 1000
            )
            existing.choice_idx = choice_idx
            existing.answered_at = now
            user.total_answer_ms += delta_ms - old_delta
            user.quiz_answer_ms += delta_ms - old_delta
        else:
            session.add(
                McqAnswer(
                    step_id=step.id,
                    user_id=user.id,
                    choice_idx=choice_idx,
                    answered_at=now,
                )
            )
            user.total_answer_ms += delta_ms
            user.quiz_answer_ms += delta_ms
            user.quiz_answer_count += 1
        await session.commit()
        await cb.answer(texts.ANSWER_SAVED)
        options = [
            o.text
            for o in (
                await session.execute(
                    select(StepOption).where(StepOption.step_id == step.id).order_by(StepOption.idx)
                )
            ).scalars().all()
        ]
        await cb.message.edit_reply_markup(reply_markup=mcq_kb(options, selected=choice_idx))
        count = await session.scalar(select(func.count(McqAnswer.id)).where(McqAnswer.step_id == step.id))
        total = await session.scalar(select(func.count(User.id)).where(User.name != ""))
        last_at = await session.scalar(
            select(func.max(McqAnswer.answered_at)).where(McqAnswer.step_id == step.id)
        )
        last_ago = None
        if last_at:
            last_ago = int((datetime.utcnow() - last_at).total_seconds())
        await hub.broadcast(
            {"type": "mcq_progress", "count": int(count or 0), "total": int(total or 0), "last": last_ago}
        )
    finally:
        await session.close()


@router.callback_query(F.data.startswith("vote:"))
async def cb_vote(cb: CallbackQuery, bot: Bot):
    idea_id = int(cb.data.split(":")[1])
    session, user, state, step = await get_ctx(str(cb.from_user.id))
    try:
        if step.type != "open" or state.phase != 1:
            await cb.answer(texts.NOT_VOTE_PHASE, show_alert=True)
            return
        existing = (
            await session.execute(
                select(IdeaVote).where(
                    IdeaVote.step_id == step.id,
                    IdeaVote.idea_id == idea_id,
                    IdeaVote.voter_id == user.id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            await session.delete(existing)
            await session.commit()
            await cb.answer(texts.VOTE_REMOVED)
        else:
            session.add(IdeaVote(step_id=step.id, idea_id=idea_id, voter_id=user.id))
            await session.commit()
            await cb.answer(texts.VOTE_COUNTED)
        kb = await idea_vote_kb(session, step, user)
        await cb.message.edit_reply_markup(reply_markup=kb)
        voters = (
            await session.execute(
                select(IdeaVote.voter_id)
                .where(IdeaVote.step_id == step.id)
                .group_by(IdeaVote.voter_id)
            )
        ).all()
        last_vote_at = await session.scalar(
            select(func.max(IdeaVote.created_at)).where(IdeaVote.step_id == step.id)
        )
        last_ago = None
        if last_vote_at:
            last_ago = int((datetime.utcnow() - last_vote_at).total_seconds())
        await hub.broadcast(
            {"type": "vote_progress", "count": len(voters), "last": last_ago}
        )
    finally:
        await session.close()

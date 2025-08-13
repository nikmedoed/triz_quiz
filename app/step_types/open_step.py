# Open step type.
from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any, Dict

from aiogram import Bot
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

import app.texts as texts
from app.db import AsyncSessionLocal
from app.hub import hub
from app.models import Step, GlobalState, Idea, IdeaVote, User
from app.public_context import open_context
from app.scoring import add_vote_points
from . import StepType, register


async def open_phases(session: AsyncSession, step: Step) -> int:
    ideas_count = await session.scalar(
        select(func.count(Idea.id)).where(Idea.step_id == step.id)
    )
    return 3 if ideas_count else 2


async def open_on_enter(session: AsyncSession, step: Step, phase: int) -> None:
    if phase == 2:
        await add_vote_points(session, step.id)


async def open_load_item(
        session: AsyncSession, add_step, item: Dict[str, Any]
) -> None:
    add_step(
        "open",
        title=item.get("title", texts.TITLE_OPEN),
        text=item.get("description") or item.get("text"),
    )


async def open_bot_prompts(
        user: User, step: Step, phase: int
) -> list[tuple[str, dict]]:
    from app.bot.keyboards import idea_vote_kb

    msgs: list[tuple[str, dict]] = []
    if phase == 0:
        header = texts.OPEN_HEADER
        title = escape(step.title)
        body = escape(step.text or "")
        instr = texts.OPEN_INSTR
        text = (
            f"<b>{header}</b>\n\n"
            f"{title}\n\n"
            f"{body}\n\n\n"
            f"<i>{instr}</i>"
        ).strip()
        msgs.append((text, {"parse_mode": "HTML"}))
    elif phase == 1:
        async with AsyncSessionLocal() as s:
            kb = await idea_vote_kb(s, step, user)
            if kb:
                msgs.append((texts.VOTE_START, {"parse_mode": "HTML", "reply_markup": kb}))
            else:
                msgs.append((texts.VOTE_NO_OPTIONS, {}))
    elif phase == 2:
        async with AsyncSessionLocal() as s:
            points = await s.scalar(
                select(func.count(IdeaVote.id))
                .join(Idea, Idea.id == IdeaVote.idea_id)
                .where(Idea.step_id == step.id, Idea.user_id == user.id)
            )
        msgs.append((texts.VOTE_FINISHED.format(points=int(points or 0)), {}))
    return msgs


async def open_on_text(
        message: Message,
        bot: Bot,
        session: AsyncSession,
        user: User,
        state: GlobalState,
        step: Step,
) -> bool:
    if state.phase != 0:
        return False
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
    count = await session.scalar(select(func.count(Idea.id)).where(Idea.step_id == step.id))
    total = await session.scalar(select(func.count(User.id)).where(User.name != ""))
    last_at = await session.scalar(
        select(func.max(Idea.submitted_at)).where(Idea.step_id == step.id)
    )
    last_ago = None
    if last_at:
        last_ago = int((datetime.utcnow() - last_at).total_seconds())
    await hub.broadcast(
        {
            "type": "idea_progress",
            "count": int(count or 0),
            "total": int(total or 0),
            "last": last_ago,
        }
    )
    return True


async def open_on_callback(
        cb: CallbackQuery,
        bot: Bot,
        session: AsyncSession,
        user: User,
        state: GlobalState,
        step: Step,
        payload: str,
) -> None:
    from app.bot.keyboards import idea_vote_kb
    if state.phase != 1:
        await cb.answer(texts.NOT_VOTE_PHASE, show_alert=True)
        return
    idea_id = int(payload)
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
    await hub.broadcast({"type": "vote_progress", "count": len(voters), "last": last_ago})


async def open_prompt_pre(bot: Bot, user: User, step: Step, phase: int) -> None:
    if phase == 2 and user.last_vote_msg_id:
        try:
            await bot.edit_message_reply_markup(
                user.id, user.last_vote_msg_id, reply_markup=None
            )
        except Exception:
            pass
        async with AsyncSessionLocal() as s:
            u = await s.get(User, user.id)
            if u:
                u.last_vote_msg_id = None
                await s.commit()


async def open_prompt_post(
        bot: Bot, user: User, step: Step, phase: int, msg: Message
) -> None:
    if phase == 1 and msg.reply_markup:
        async with AsyncSessionLocal() as s:
            u = await s.get(User, user.id)
            if u:
                u.last_vote_msg_id = msg.message_id
                await s.commit()


register(
    "open",
    StepType(
        open_context,
        open_phases,
        on_enter_phase=open_on_enter,
        load_item=open_load_item,
        build_bot_prompts=open_bot_prompts,
        on_text=open_on_text,
        callback_prefix="vote",
        on_callback=open_on_callback,
        callback_error=texts.NOT_VOTE_PHASE,
        on_prompt_pre=open_prompt_pre,
        on_prompt_post=open_prompt_post,
    ),
)

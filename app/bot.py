# aiogram 3 bot handlers — blocks with internal phases
from __future__ import annotations
from datetime import datetime
from typing import Optional, List

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.models import User, GlobalState, Step, StepOption, Idea, IdeaVote, McqAnswer
from app.scoring import add_mcq_points

router = Router()

async def get_ctx(tg_id: str):
    session = AsyncSessionLocal()
    try:
        user = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
        if not user:
            user = User(telegram_id=tg_id, name="")
            session.add(user)
            await session.commit()
            await session.refresh(user)
        state = await session.get(GlobalState, 1)
        step = await session.get(Step, state.current_step_id)
        return session, user, state, step
    except Exception:
        await session.close()
        raise

# Keyboards

def mcq_kb(options: List[str], selected: Optional[int]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for i, _ in enumerate(options):
        label = f"{i+1}"
        if selected == i:
            label = "✅ " + label
        kb.button(text=label, callback_data=f"mcq:{i}")
    kb.adjust(2)
    return kb.as_markup()

async def idea_vote_kb(session: AsyncSession, open_step: Step, voter: User):
    ideas = (await session.execute(select(Idea).where(Idea.step_id == open_step.id).order_by(Idea.submitted_at.asc()))).scalars().all()
    voted_ids = set(x for (x,) in (await session.execute(select(IdeaVote.idea_id).where(IdeaVote.step_id == open_step.id, IdeaVote.voter_id == voter.id))).all())
    rows = []
    for idx, idea in enumerate(ideas, start=1):
        if idea.user_id == voter.id:
            continue
        text = idea.text[:40].replace("\n", " ")
        prefix = "✅ " if idea.id in voted_ids else ""
        rows.append([InlineKeyboardButton(text=prefix + f"{idx}. {text}", callback_data=f"vote:{idea.id}")])
    if not rows:
        rows = [[InlineKeyboardButton(text="Нет идей для голосования", callback_data="noop")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)

# /start and name capture

@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    session, user, state, step = await get_ctx(str(message.from_user.id))
    try:
        if not user.name:
            await message.answer("Введите имя для участия (отправьте одним сообщением).")
            return
        await message.answer(f"Текущее имя: {user.name}\nЕсли хотите изменить — отправьте новое сейчас.")
        await send_prompt(bot, user, step, state.phase)
    finally:
        await session.close()

@router.message(F.text & ~F.via_bot)
async def on_text(message: Message, bot: Bot):
    session, user, state, step = await get_ctx(str(message.from_user.id))
    try:
        if not user.name:
            user.name = message.text.strip()[:120]
            await session.commit()
            await message.answer("Имя сохранено. Готово к участию.")
            await send_prompt(bot, user, step, state.phase)
            return
        # Open ideas only in phase 0
        if step.type == "open" and state.phase == 0:
            await session.execute(delete(Idea).where(Idea.step_id == step.id, Idea.user_id == user.id))
            session.add(Idea(step_id=step.id, user_id=user.id, text=message.text.strip()))
            await session.commit()
            # time-to-first-answer is measured when MCQ pressed; for open we count at submission time
            delta_ms = int((datetime.utcnow() - state.step_started_at).total_seconds() * 1000)
            user.total_answer_ms += max(0, delta_ms)
            await session.commit()
            await message.answer("Идея принята. Можно отправить новое сообщение, чтобы заменить.")
        else:
            await message.answer("Сейчас текстовые ответы не принимаются. Дождитесь команды модератора.")
    finally:
        await session.close()

@router.callback_query(F.data.startswith("mcq:"))
async def cb_mcq(cb: CallbackQuery, bot: Bot):
    choice_idx = int(cb.data.split(":")[1])
    session, user, state, step = await get_ctx(str(cb.from_user.id))
    try:
        if step.type != "quiz" or state.phase != 0:
            await cb.answer("Сейчас не этап ответов.", show_alert=True)
            return
        existing = (await session.execute(select(McqAnswer).where(McqAnswer.step_id == step.id, McqAnswer.user_id == user.id))).scalar_one_or_none()
        if existing:
            existing.choice_idx = choice_idx
        else:
            session.add(McqAnswer(step_id=step.id, user_id=user.id, choice_idx=choice_idx))
            delta_ms = int((datetime.utcnow() - state.step_started_at).total_seconds() * 1000)
            user.total_answer_ms += max(0, delta_ms)
        await session.commit()
        await cb.answer("Ответ сохранён.")
        options = [o.text for o in (await session.execute(select(StepOption).where(StepOption.step_id == step.id).order_by(StepOption.idx))).scalars().all()]
        await cb.message.edit_reply_markup(reply_markup=mcq_kb(options, selected=choice_idx))
    finally:
        await session.close()

@router.callback_query(F.data.startswith("vote:"))
async def cb_vote(cb: CallbackQuery, bot: Bot):
    idea_id = int(cb.data.split(":")[1])
    session, user, state, step = await get_ctx(str(cb.from_user.id))
    try:
        if step.type != "open" or state.phase != 2:
            await cb.answer("Сейчас не этап голосования.", show_alert=True)
            return
        existing = (await session.execute(select(IdeaVote).where(IdeaVote.step_id == step.id, IdeaVote.idea_id == idea_id, IdeaVote.voter_id == user.id))).scalar_one_or_none()
        if existing:
            await session.delete(existing)
            await session.commit()
            await cb.answer("Голос снят.")
        else:
            session.add(IdeaVote(step_id=step.id, idea_id=idea_id, voter_id=user.id))
            await session.commit()
            await cb.answer("Голос засчитан.")
        kb = await idea_vote_kb(session, step, user)
        await cb.message.edit_reply_markup(reply_markup=kb)
    finally:
        await session.close()

async def send_prompt(bot: Bot, user: User, step: Step, phase: int):
    if step.type == "registration":
        await bot.send_message(user.telegram_id, "Ждём начала. Вы на экране регистрации.")
    elif step.type == "open":
        if phase == 0:
            await bot.send_message(user.telegram_id, (step.text or "Отправьте идею одним сообщением."))
        elif phase == 1:
            await bot.send_message(user.telegram_id, "Приём идей завершён. Смотрите общий экран.")
        elif phase == 2:
            await bot.send_message(user.telegram_id, "Начато голосование за идеи. Можно выбрать несколько.")
            async with AsyncSessionLocal() as s:
                kb = await idea_vote_kb(s, step, user)
            await bot.send_message(user.telegram_id, "Выберите идеи:", reply_markup=kb)
        elif phase == 3:
            await bot.send_message(user.telegram_id, "Голосование завершено. Смотрите общий экран.")
    elif step.type == "quiz":
        if phase == 0:
            async with AsyncSessionLocal() as s:
                options = [o.text for o in (await s.execute(select(StepOption).where(StepOption.step_id == step.id).order_by(StepOption.idx))).scalars().all()]
            await bot.send_message(user.telegram_id, (step.text or "Выберите вариант ответа:") + "\n\n" + "\n".join([f"{i+1}. {t}" for i,t in enumerate(options)]), reply_markup=mcq_kb(options, selected=None))
        else:
            await bot.send_message(user.telegram_id, "Ответы закрыты. Смотрите общий экран.")
    elif step.type == "leaderboard":
        await bot.send_message(user.telegram_id, "Финальные результаты на общем экране.")

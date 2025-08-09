# aiogram 3 bot handlers — blocks with internal phases
from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from pathlib import Path

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from html import escape

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.models import User, GlobalState, Step, StepOption, Idea, IdeaVote, McqAnswer
from app.scoring import add_mcq_points
from app.web import hub
from app.settings import settings

router = Router()


async def save_avatar(bot: Bot, user: User):
    path = Path(settings.AVATAR_DIR)
    path.mkdir(exist_ok=True)
    photos = await bot.get_user_profile_photos(user.telegram_id, limit=1)
    if photos.total_count:
        file_id = photos.photos[0][-1].file_id
        await bot.download(file_id, destination=path / f"{user.telegram_id}.jpg")
        user.avatar_file_id = file_id

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
    """Inline keyboard with options as button labels."""
    kb = InlineKeyboardBuilder()
    for i, text in enumerate(options):
        label = f"{i + 1}. {text}"
        if selected == i:
            label = "✅ " + label
        kb.button(text=label, callback_data=f"mcq:{i}")
    kb.adjust(1)
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

@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    session, user, state, step = await get_ctx(str(message.from_user.id))
    try:
        user.waiting_for_name = True
        await session.commit()
        if user.name:
            await message.answer(f"Текущее имя: {user.name}\nОтправьте новое имя одним сообщением.\nИли /cancel — оставить как есть.")
        else:
            await message.answer("Введите имя для участия (одним сообщением).")
    finally:
        await session.close()

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, bot: Bot):
    session, user, state, step = await get_ctx(str(message.from_user.id))
    try:
        user.waiting_for_name = False
        await session.commit()
        await send_prompt(bot, user, step, state.phase, prefix="Ок, имя не меняем.")
    finally:
        await session.close()

@router.message(F.text & ~F.via_bot)
async def on_text(message: Message, bot: Bot):
    session, user, state, step = await get_ctx(str(message.from_user.id))
    try:
        # 1) режим ввода имени работает ТОЛЬКО если он активирован /start
        if user.waiting_for_name:
            new_name = message.text.strip()[:120]
            if not new_name:
                await message.answer("Имя пустое. Введите заново или /cancel.")
                return
            user.name = new_name
            user.waiting_for_name = False
            await session.commit()
            await save_avatar(bot, user)
            await session.commit()
            await hub.broadcast({"type": "reload"})  # появится на экране регистрации
            await send_prompt(bot, user, step, state.phase, prefix="Имя сохранено. Готово к участию.")
            return

        # 2) обычные текстовые ответы принимаем только в open:collect
        if step.type == "open" and state.phase == 0:
            await session.execute(delete(Idea).where(Idea.step_id == step.id, Idea.user_id == user.id))
            session.add(Idea(step_id=step.id, user_id=user.id, text=message.text.strip()))
            await session.commit()
            delta_ms = int((datetime.utcnow() - state.step_started_at).total_seconds() * 1000)
            delta_ms = max(0, delta_ms)
            user.total_answer_ms += delta_ms
            user.open_answer_ms += delta_ms
            user.open_answer_count += 1
            await session.commit()
            await message.answer(
                "Идея принята!\n\n<i>Вы можете изменить ответ, отправив новое сообщение.\nРедактирование сообщений не поддерживается, скопируйте, измените и пришлите новое.</i>",
                parse_mode="HTML",
            )
            count = await session.scalar(select(func.count(Idea.id)).where(Idea.step_id == step.id))
            total = await session.scalar(select(func.count(User.id)).where(User.name != ""))
            last_at = await session.scalar(select(func.max(Idea.submitted_at)).where(Idea.step_id == step.id))
            last_ago = None
            if last_at:
                last_ago = int((datetime.utcnow() - last_at).total_seconds())
            await hub.broadcast({"type": "idea_progress", "count": int(count or 0), "total": int(total or 0), "last": last_ago})
        else:
            await message.answer("Сейчас текстовые ответы не принимаются. Дождитесь команды модератора.\nЧтобы изменить имя: /start")
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
        if existing and existing.choice_idx == choice_idx:
            await cb.answer("Ответ не изменён.")
            return
        if existing:
            existing.choice_idx = choice_idx
            existing.answered_at = datetime.utcnow()
        else:
            session.add(McqAnswer(step_id=step.id, user_id=user.id, choice_idx=choice_idx))
            delta_ms = int((datetime.utcnow() - state.step_started_at).total_seconds() * 1000)
            delta_ms = max(0, delta_ms)
            user.total_answer_ms += delta_ms
            user.quiz_answer_ms += delta_ms
            user.quiz_answer_count += 1
        await session.commit()
        await cb.answer("Ответ сохранён.")
        options = [o.text for o in (await session.execute(select(StepOption).where(StepOption.step_id == step.id).order_by(StepOption.idx))).scalars().all()]
        await cb.message.edit_reply_markup(reply_markup=mcq_kb(options, selected=choice_idx))
        count = await session.scalar(select(func.count(McqAnswer.id)).where(McqAnswer.step_id == step.id))
        total = await session.scalar(select(func.count(User.id)).where(User.name != ""))
        last_at = await session.scalar(
            select(func.max(McqAnswer.answered_at)).where(McqAnswer.step_id == step.id)
        )
        last_ago = None
        if last_at:
            last_ago = int((datetime.utcnow() - last_at).total_seconds())
        await hub.broadcast({"type": "mcq_progress", "count": int(count or 0), "total": int(total or 0), "last": last_ago})
    finally:
        await session.close()

@router.callback_query(F.data.startswith("vote:"))
async def cb_vote(cb: CallbackQuery, bot: Bot):
    idea_id = int(cb.data.split(":")[1])
    session, user, state, step = await get_ctx(str(cb.from_user.id))
    try:
        if step.type != "open" or state.phase != 1:
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
        # обновить прогресс на общем экране (voters_count, last_vote_at)
        voters = (await session.execute(
            select(IdeaVote.voter_id)
            .where(IdeaVote.step_id == step.id)
            .group_by(IdeaVote.voter_id)
        )).all()
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

async def build_prompt_messages(user: User, step: Step, phase: int):
    msgs = []
    if step.type == "registration":
        msgs.append(("Ждём начала. Вы на экране регистрации.", {}))
    elif step.type == "open":
        if phase == 0:
            header = "Предложите идею решения проблемной ситуации (открытый ответ)"
            title = escape(step.title)
            body = escape(step.text or "")
            instr = (
                "Пришлите ваш ответ в этот чат.\n"
                "- Учитывается один последний ответ\n"
                "- В свободной форме\n"
                "- Лаконично, важна скорость\n"
                "- Укажите логику решения, использванные приёмы, методы, обоснуйте"
            )
            text = (
                f"<b>{header}</b>\n\n"
                f"{title}\n\n"
                f"{body}\n\n\n"
                f"<i>{instr}</i>"
            ).strip()
            msgs.append((text, {"parse_mode": "HTML"}))
        elif phase == 1:
            async with AsyncSessionLocal() as s:
                count = await s.scalar(select(func.count(Idea.id)).where(Idea.step_id == step.id))
                if count:
                    kb = await idea_vote_kb(s, step, user)
                    text = (
                        "Ответы более не принимаются.\n\n"
                        "<b>Начато голосование за идеи.</b>\n\n"
                        "Выберите номера, которые считаете достойным и методологически обоснованным решением описанной проблемы.\n\n"
                        "<i>Можно выбрать несколько, или ничего не выбирать.</i>"
                    )
                    msgs.append((text, {"parse_mode": "HTML", "reply_markup": kb}))
                else:
                    msgs.append(("Начато голосование за идеи. Для вас нет вариантов, ожидайте.", {}))
        elif phase == 2:
            async with AsyncSessionLocal() as s:
                points = await s.scalar(
                    select(func.count(IdeaVote.id))
                    .join(Idea, Idea.id == IdeaVote.idea_id)
                    .where(Idea.step_id == step.id, Idea.user_id == user.id)
                )
            text = (
                "Голосование завершено.\n"
                "Результаты на экране.\n"
                f"Вы набрали {int(points or 0)} балл(ов)."
            )
            msgs.append((text, {}))
    elif step.type == "quiz":
        if phase == 0:
            async with AsyncSessionLocal() as s:
                options = [
                    o.text
                    for o in (
                        await s.execute(
                            select(StepOption)
                            .where(StepOption.step_id == step.id)
                            .order_by(StepOption.idx)
                        )
                    ).scalars().all()
                ]
            header = "Выберите один вариант ответа"
            title = escape(step.title)
            instr = (
                "Выберите\n"
                "- Наиболее подходящий вариант\n"
                "- Быстро, пока есть время\n"
                "- Можно изменить выбор"
            )
            text = f"<b>{header}</b>\n\n{title}\n\n<i>{instr}</i>"
            msgs.append((text, {"parse_mode": "HTML", "reply_markup": mcq_kb(options, selected=None)}))
        else:
            async with AsyncSessionLocal() as s:
                ans = (
                    await s.execute(
                        select(McqAnswer).where(
                            McqAnswer.step_id == step.id, McqAnswer.user_id == user.id
                        )
                    )
                ).scalar_one_or_none()
            if not ans:
                text = (
                    "Вы не ответили.\n\n"
                    "Ответы более не принимаются, вернитесь в общий зал."
                )
            elif step.correct_index is not None and ans.choice_idx == step.correct_index:
                points = step.points_correct or 0
                text = (
                    f"Верно! Вы получили {points} балл(ов).\n\n"
                    "Ответы более не принимаются, вернитесь в общий зал."
                )
            else:
                text = (
                    "Вы ответили неверно.\n\n"
                    "Ответы более не принимаются, вернитесь в общий зал."
                )
            msgs.append((text, {}))
    elif step.type == "leaderboard":
        async with AsyncSessionLocal() as s:
            users = (await s.execute(select(User))).scalars().all()
        users.sort(key=lambda u: (-u.total_score, u.total_answer_ms, u.joined_at))
        place = next(i for i, u in enumerate(users, start=1) if u.id == user.id)
        open_avg = (
            user.open_answer_ms / user.open_answer_count / 1000
            if user.open_answer_count
            else 0
        )
        quiz_avg = (
            user.quiz_answer_ms / user.quiz_answer_count / 1000
            if user.quiz_answer_count
            else 0
        )
        text = (
            "Викторина завершена.\n\n"
            f"Набрано баллов: {user.total_score}.\n"
            f"Ваше место: {place}.\n\n"
            "Среднее время ответа:\n"
            f"{open_avg:.1f} c - открытый вопрос\n"
            f"{quiz_avg:.1f} c - выбор варианта"
        )
        msgs.append((text, {}))
    return msgs


async def send_prompt(bot: Bot, user: User, step: Step, phase: int, prefix: str | None = None):
    if step.type == "open" and phase == 2 and user.last_vote_msg_id:
        try:
            await bot.edit_message_reply_markup(user.telegram_id, user.last_vote_msg_id, reply_markup=None)
        except Exception:
            pass
        async with AsyncSessionLocal() as s:
            u = await s.get(User, user.id)
            if u:
                u.last_vote_msg_id = None
                await s.commit()
    msgs = await build_prompt_messages(user, step, phase)
    if prefix:
        if msgs:
            text, kwargs = msgs[0]
            sep = "\n\n" if text else ""
            msgs[0] = (f"{prefix}{sep}{text}", kwargs)
        else:
            msgs.insert(0, (prefix, {}))
    for text, kwargs in msgs:
        msg = await bot.send_message(user.telegram_id, text, **kwargs)
        if step.type == "open" and phase == 1 and kwargs.get("reply_markup"):
            async with AsyncSessionLocal() as s:
                u = await s.get(User, user.id)
                if u:
                    u.last_vote_msg_id = msg.message_id
                    await s.commit()

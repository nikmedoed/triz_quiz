"""Registry of step types with hooks for public screen and Telegram."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape
from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import Bot
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

import app.texts as texts
from app.db import AsyncSessionLocal
from app.hub import hub
from app.models import (
    Step,
    GlobalState,
    Idea,
    IdeaVote,
    McqAnswer,
    StepOption,
    User,
)
from app.public_context import (
    registration_context,
    open_context,
    quiz_context,
    leaderboard_context,
)
from app.scoring import add_vote_points, add_mcq_points, get_leaderboard_users

ContextBuilder = Callable[[AsyncSession, Step, GlobalState, Dict[str, Any]], Awaitable[None]]
TotalPhasesFn = Callable[[AsyncSession, Step], Awaitable[int]]
PhaseHook = Callable[[AsyncSession, Step, int], Awaitable[None]]
ScenarioLoader = Callable[[AsyncSession, Callable[..., Step], Dict[str, Any]], Awaitable[None]]
BotPromptBuilder = Callable[[User, Step, int], Awaitable[list[tuple[str, dict]]]]
MessageHandler = Callable[[Message, Bot, AsyncSession, User, GlobalState, Step], Awaitable[bool]]
CallbackHandler = Callable[
    [CallbackQuery, Bot, AsyncSession, User, GlobalState, Step, str], Awaitable[None]
]
PromptPreHook = Callable[[Bot, User, Step, int], Awaitable[None]]
PromptPostHook = Callable[[Bot, User, Step, int, Message], Awaitable[None]]


@dataclass
class StepType:
    """Metadata and helpers for a quiz step type."""

    build_context: ContextBuilder
    total_phases: TotalPhasesFn
    on_enter_phase: Optional[PhaseHook] = None
    load_item: Optional[ScenarioLoader] = None
    build_bot_prompts: Optional[BotPromptBuilder] = None
    on_text: Optional[MessageHandler] = None
    callback_prefix: Optional[str] = None
    on_callback: Optional[CallbackHandler] = None
    callback_error: str = texts.NOT_VOTE_PHASE
    on_prompt_pre: Optional[PromptPreHook] = None
    on_prompt_post: Optional[PromptPostHook] = None


async def registration_phases(session: AsyncSession, step: Step) -> int:
    return 1


async def open_phases(session: AsyncSession, step: Step) -> int:
    ideas_count = await session.scalar(
        select(func.count(Idea.id)).where(Idea.step_id == step.id)
    )
    return 3 if ideas_count else 2


async def quiz_phases(session: AsyncSession, step: Step) -> int:
    return 2


async def leaderboard_phases(session: AsyncSession, step: Step) -> int:
    return 1


async def open_on_enter(session: AsyncSession, step: Step, phase: int) -> None:
    if phase == 2:
        await add_vote_points(session, step.id)


async def quiz_on_enter(session: AsyncSession, step: Step, phase: int) -> None:
    if phase == 1:
        await add_mcq_points(session, step)


# Scenario loading helpers
async def open_load_item(
    session: AsyncSession, add_step: Callable[..., Step], item: Dict[str, Any]
) -> None:
    add_step(
        "open",
        title=item.get("title", texts.TITLE_OPEN),
        text=item.get("description") or item.get("text"),
    )


async def quiz_load_item(
    session: AsyncSession, add_step: Callable[..., Step], item: Dict[str, Any]
) -> None:
    time_val = item.get("time")
    timer_ms = None
    if isinstance(time_val, str) and time_val.isdigit():
        timer_ms = int(time_val) * 1000
    elif isinstance(time_val, (int, float)):
        timer_ms = int(time_val) * 1000
    s = add_step(
        "quiz",
        title=item.get("title", texts.TITLE_QUIZ),
        text=item.get("description") or item.get("text"),
        timer_ms=timer_ms,
    )
    await session.flush()
    opts = item.get("options", [])
    for idx, text in enumerate(opts):
        session.add(StepOption(step_id=s.id, idx=idx, text=text))
    correct = item.get("correct")
    if isinstance(correct, str) and correct.isdigit():
        s.correct_index = int(correct) - 1
    elif isinstance(correct, int):
        s.correct_index = correct
    s.points_correct = item.get("points")


# Bot prompt builders
async def registration_bot_prompts(
    user: User, step: Step, phase: int
) -> list[tuple[str, dict]]:
    return [(texts.REGISTRATION_WAIT, {})]


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


async def quiz_bot_prompts(
    user: User, step: Step, phase: int
) -> list[tuple[str, dict]]:
    from app.bot.keyboards import mcq_kb

    msgs: list[tuple[str, dict]] = []
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
        header = texts.QUIZ_HEADER
        title = escape(step.title)
        body = escape(step.text or "")
        instr = texts.QUIZ_INSTR
        parts = [f"<b>{header}</b>", title]
        if body:
            parts.append(body)
        parts.append(f"<i>{instr}</i>")
        text = "\n\n".join(parts)
        msgs.append(
            (
                text,
                {"parse_mode": "HTML", "reply_markup": mcq_kb(options, selected=None)},
            )
        )
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
            text = texts.NO_ANSWER + texts.RESPONSES_CLOSED
        elif step.correct_index is not None and ans.choice_idx == step.correct_index:
            points = step.points_correct or 0
            text = texts.CORRECT_PREFIX.format(points=points) + texts.RESPONSES_CLOSED
        else:
            text = texts.WRONG_ANSWER + texts.RESPONSES_CLOSED
        msgs.append((text, {}))
    return msgs


async def leaderboard_bot_prompts(
    user: User, step: Step, phase: int
) -> list[tuple[str, dict]]:
    async with AsyncSessionLocal() as s:
        users = await get_leaderboard_users(s)
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
    text = texts.LEADERBOARD.format(
        score=user.total_score, place=place, open_avg=open_avg, quiz_avg=quiz_avg
    )
    return [(text, {})]


# Message handlers
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
    await hub.broadcast(
        {"type": "vote_progress", "count": len(voters), "last": last_ago}
    )


async def quiz_on_callback(
    cb: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: GlobalState,
    step: Step,
    payload: str,
) -> None:
    from app.bot.keyboards import mcq_kb
    if state.phase != 0:
        await cb.answer(texts.NOT_ANSWER_PHASE, show_alert=True)
        return
    choice_idx = int(payload)
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
                select(StepOption)
                .where(StepOption.step_id == step.id)
                .order_by(StepOption.idx)
            )
        ).scalars().all()
    ]
    await cb.message.edit_reply_markup(
        reply_markup=mcq_kb(options, selected=choice_idx)
    )
    count = await session.scalar(
        select(func.count(McqAnswer.id)).where(McqAnswer.step_id == step.id)
    )
    total = await session.scalar(
        select(func.count(User.id)).where(User.name != "")
    )
    last_at = await session.scalar(
        select(func.max(McqAnswer.answered_at)).where(McqAnswer.step_id == step.id)
    )
    last_ago = None
    if last_at:
        last_ago = int((datetime.utcnow() - last_at).total_seconds())
    await hub.broadcast(
        {
            "type": "mcq_progress",
            "count": int(count or 0),
            "total": int(total or 0),
            "last": last_ago,
        }
    )


# Prompt hooks
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


STEP_TYPES: Dict[str, StepType] = {
    "registration": StepType(
        registration_context,
        registration_phases,
        build_bot_prompts=registration_bot_prompts,
    ),
    "open": StepType(
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
    "quiz": StepType(
        quiz_context,
        quiz_phases,
        on_enter_phase=quiz_on_enter,
        load_item=quiz_load_item,
        build_bot_prompts=quiz_bot_prompts,
        callback_prefix="mcq",
        on_callback=quiz_on_callback,
        callback_error=texts.NOT_ANSWER_PHASE,
    ),
    "leaderboard": StepType(
        leaderboard_context,
        leaderboard_phases,
        build_bot_prompts=leaderboard_bot_prompts,
    ),
}


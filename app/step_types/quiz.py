# Quiz step type.
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from aiogram import Bot
from aiogram.types import CallbackQuery
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

import app.texts as texts
from app.db import AsyncSessionLocal
from app.hub import hub
from app.models import Step, GlobalState, McqAnswer, StepOption, User
from app.public_context import quiz_context
from app.scoring import add_mcq_points
from . import StepType, register


async def quiz_phases(session: AsyncSession, step: Step) -> int:
    return 2


async def quiz_on_enter(session: AsyncSession, step: Step, phase: int) -> None:
    if phase == 1:
        await add_mcq_points(session, step)


async def quiz_load_item(
        session: AsyncSession, add_step, item: Dict[str, Any]
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
        title = step.title
        body = step.text or ""
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


register(
    "quiz",
    StepType(
        quiz_context,
        quiz_phases,
        on_enter_phase=quiz_on_enter,
        load_item=quiz_load_item,
        build_bot_prompts=quiz_bot_prompts,
        callback_prefix="mcq",
        on_callback=quiz_on_callback,
        callback_error=texts.NOT_ANSWER_PHASE,
    ),
)

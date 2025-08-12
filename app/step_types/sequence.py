# Sequence step type.
from __future__ import annotations

import json
import random
from datetime import datetime
from typing import Any, Dict

from aiogram import Bot
from aiogram.types import CallbackQuery
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.hub import hub
import app.texts as texts
from app.db import AsyncSessionLocal
from app.models import Step, GlobalState, SequenceAnswer, StepOption, User
from app.public_context import sequence_context
from app.scoring import add_sequence_points

from . import StepType, register


async def sequence_phases(session: AsyncSession, step: Step) -> int:
    return 2


async def sequence_on_enter(session: AsyncSession, step: Step, phase: int) -> None:
    if phase == 1:
        await add_sequence_points(session, step)


async def sequence_load_item(
    session: AsyncSession, add_step, item: Dict[str, Any]
) -> None:
    time_val = item.get("time")
    timer_ms = None
    if isinstance(time_val, str) and time_val.isdigit():
        timer_ms = int(time_val) * 1000
    elif isinstance(time_val, (int, float)):
        timer_ms = int(time_val) * 1000
    s = add_step(
        "sequence",
        title=item.get("title", texts.TITLE_SEQUENCE),
        text=item.get("description") or item.get("text"),
        timer_ms=timer_ms,
    )
    await session.flush()
    opts = item.get("options", [])
    for idx, text in enumerate(opts):
        session.add(StepOption(step_id=s.id, idx=idx, text=text))
    pts_val = item.get("points")
    if isinstance(pts_val, str) and pts_val.isdigit():
        s.points_correct = int(pts_val)
    elif isinstance(pts_val, (int, float)):
        s.points_correct = int(pts_val)
    else:
        s.points_correct = 3


async def sequence_bot_prompts(
    user: User, step: Step, phase: int
) -> list[tuple[str, dict]]:
    from app.bot.keyboards import sequence_kb

    msgs: list[tuple[str, dict]] = []
    async with AsyncSessionLocal() as s:
        options = [
            (o.idx, o.text)
            for o in (
                await s.execute(
                    select(StepOption)
                    .where(StepOption.step_id == step.id)
                    .order_by(StepOption.idx)
                )
            ).scalars().all()
        ]
        rng = random.Random(step.id)
        rng.shuffle(options)
        ans = (
            await s.execute(
                select(SequenceAnswer).where(
                    SequenceAnswer.step_id == step.id,
                    SequenceAnswer.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        selected = json.loads(ans.order_json) if ans else []
    if phase == 0:
        header = texts.SEQUENCE_HEADER
        title = step.title
        body = step.text or ""
        instr = texts.SEQUENCE_INSTR
        parts = [f"<b>{header}</b>", title]
        if body:
            parts.append(body)
        parts.append(f"<i>{instr}</i>")
        text = "\n\n".join(parts)
        msgs.append(
            (
                text,
                {
                    "parse_mode": "HTML",
                    "reply_markup": sequence_kb(options, selected),
                },
            )
        )
    else:
        async with AsyncSessionLocal() as s:
            ans = (
                await s.execute(
                    select(SequenceAnswer).where(
                        SequenceAnswer.step_id == step.id,
                        SequenceAnswer.user_id == user.id,
                    )
                )
            ).scalar_one_or_none()
        if not ans:
            text = texts.NO_ANSWER + texts.RESPONSES_CLOSED
        else:
            correct_order = [idx for idx, _ in sorted(options, key=lambda x: x[0])]
            order = json.loads(ans.order_json)
            if len(order) != len(correct_order):
                text = texts.NO_ANSWER + texts.RESPONSES_CLOSED
            elif order == correct_order:
                points = step.points_correct or 0
                text = (
                    texts.CORRECT_PREFIX.format(points=points)
                    + texts.RESPONSES_CLOSED
                )
            else:
                text = texts.WRONG_SEQUENCE + texts.RESPONSES_CLOSED
        msgs.append((text, {}))
    return msgs


async def sequence_on_callback(
    cb: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    user: User,
    state: GlobalState,
    step: Step,
    payload: str,
) -> None:
    from app.bot.keyboards import sequence_kb

    if state.phase != 0:
        await cb.answer(texts.NOT_ANSWER_PHASE, show_alert=True)
        return
    options = [
        (o.idx, o.text)
        for o in (
            await session.execute(
                select(StepOption)
                .where(StepOption.step_id == step.id)
                .order_by(StepOption.idx)
            )
        ).scalars().all()
    ]
    rng = random.Random(step.id)
    rng.shuffle(options)
    existing = (
        await session.execute(
            select(SequenceAnswer).where(
                SequenceAnswer.step_id == step.id,
                SequenceAnswer.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    now = datetime.utcnow()
    delta_ms = int((now - state.step_started_at).total_seconds() * 1000)
    delta_ms = max(0, delta_ms)
    options_count = len(options)
    if payload == "reset":
        if existing:
            old_order = json.loads(existing.order_json)
            was_full = len(old_order) == options_count
            old_delta = (
                int((existing.answered_at - state.step_started_at).total_seconds() * 1000)
                if was_full
                else 0
            )
            await session.delete(existing)
            if was_full:
                user.total_answer_ms -= old_delta
                user.quiz_answer_ms -= old_delta
                if user.quiz_answer_count:
                    user.quiz_answer_count -= 1
            await session.commit()
        await cb.answer(texts.ANSWER_SAVED)
        await cb.message.edit_reply_markup(reply_markup=sequence_kb(options, []))
    else:
        idx = int(payload)
        existing_order = json.loads(existing.order_json) if existing else []
        order = list(existing_order)
        if idx in order:
            order.remove(idx)
        else:
            order.append(idx)
        was_full = len(existing_order) == options_count
        old_delta = (
            int((existing.answered_at - state.step_started_at).total_seconds() * 1000)
            if existing and was_full
            else 0
        )
        is_full = len(order) == options_count
        if existing:
            if order:
                existing.order_json = json.dumps(order)
                existing.answered_at = now
            else:
                await session.delete(existing)
        elif order:
            session.add(
                SequenceAnswer(
                    step_id=step.id,
                    user_id=user.id,
                    order_json=json.dumps(order),
                    answered_at=now,
                )
            )
        if was_full:
            user.total_answer_ms -= old_delta
            user.quiz_answer_ms -= old_delta
            if user.quiz_answer_count:
                user.quiz_answer_count -= 1
        if is_full:
            user.total_answer_ms += delta_ms
            user.quiz_answer_ms += delta_ms
            user.quiz_answer_count += 1
        await session.commit()
        await cb.answer(texts.ANSWER_SAVED)
        await cb.message.edit_reply_markup(
            reply_markup=sequence_kb(options, order)
        )
    count = await session.scalar(
        select(func.count(SequenceAnswer.id)).where(
            SequenceAnswer.step_id == step.id,
            func.json_array_length(SequenceAnswer.order_json) == options_count,
        )
    )
    total = await session.scalar(
        select(func.count(User.id)).where(User.name != "")
    )
    last_at = await session.scalar(
        select(func.max(SequenceAnswer.answered_at)).where(SequenceAnswer.step_id == step.id)
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
    "sequence",
    StepType(
        sequence_context,
        sequence_phases,
        on_enter_phase=sequence_on_enter,
        load_item=sequence_load_item,
        build_bot_prompts=sequence_bot_prompts,
        callback_prefix="seq",
        on_callback=sequence_on_callback,
        callback_error=texts.NOT_ANSWER_PHASE,
    ),
)

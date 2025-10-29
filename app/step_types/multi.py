# Multiple choice step type.
from __future__ import annotations

import random
from datetime import datetime
from typing import Any, Dict

from aiogram import Bot
from aiogram.types import CallbackQuery
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

import app.texts as texts
from app.db import AsyncSessionLocal
from app.hub import hub
from app.models import Step, GlobalState, MultiAnswer, StepOption, User
from app.public_context import multi_context
from app.scoring import add_multi_points
from . import StepType, register


async def multi_phases(session: AsyncSession, step: Step) -> int:
    return 2


async def multi_on_enter(session: AsyncSession, step: Step, phase: int) -> None:
    if phase == 1:
        await add_multi_points(session, step)


async def multi_load_item(
        session: AsyncSession, add_step, item: Dict[str, Any]
) -> None:
    time_val = item.get("time")
    timer_ms = None
    if isinstance(time_val, str) and time_val.isdigit():
        timer_ms = int(time_val) * 1000
    elif isinstance(time_val, (int, float)):
        timer_ms = int(time_val) * 1000
    def _as_str_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(x) for x in value if str(x)]
        return [str(value)]

    def _is_digit_like(value: Any) -> bool:
        if isinstance(value, int):
            return True
        if isinstance(value, str):
            return value.isdigit()
        return False

    correct_multi_indices: list[int] = []
    options_payload: list[str]

    explicit_correct = _as_str_list(item.get("correct_options"))
    if not explicit_correct:
        raw_correct = item.get("correct")
        if isinstance(raw_correct, list) and any(
            not _is_digit_like(c) for c in raw_correct
        ):
            explicit_correct = [str(c) for c in raw_correct if str(c)]

    if explicit_correct:
        wrong_sources = (
            _as_str_list(item.get("incorrect_options"))
            or _as_str_list(item.get("wrong_options"))
            or _as_str_list(item.get("other_options"))
        )
        fallback_options = _as_str_list(item.get("options"))
        if not wrong_sources and fallback_options:
            wrong_sources = [
                opt for opt in fallback_options if opt not in explicit_correct
            ]
        combined: list[tuple[str, bool]] = []
        seen: set[str] = set()
        for text in explicit_correct:
            if text in seen:
                continue
            combined.append((text, True))
            seen.add(text)
        for text in wrong_sources:
            if text in seen:
                continue
            combined.append((text, False))
            seen.add(text)
        for text in fallback_options:
            if text in seen:
                continue
            combined.append((text, False))
            seen.add(text)
        if not combined:
            combined = [(text, True) for text in explicit_correct]
        rng = random.Random()
        rng.shuffle(combined)
        options_payload = [text for text, _ in combined]
        correct_multi_indices = [
            idx for idx, (_, is_correct) in enumerate(combined) if is_correct
        ]
    else:
        options_payload = _as_str_list(item.get("options"))
        raw_correct = item.get("correct")
        if isinstance(raw_correct, list):
            for c in raw_correct:
                if isinstance(c, str) and c.isdigit():
                    correct_multi_indices.append(int(c) - 1)
                elif isinstance(c, int):
                    correct_multi_indices.append(int(c))
        options_payload = [text for text in options_payload]

    s = add_step(
        "multi",
        title=item.get("title", texts.TITLE_MULTI),
        text=item.get("description") or item.get("text"),
        timer_ms=timer_ms,
        correct_multi=",".join(str(idx) for idx in sorted(set(correct_multi_indices)))
        if correct_multi_indices
        else None,
    )
    await session.flush()
    for idx, text in enumerate(options_payload):
        session.add(StepOption(step_id=s.id, idx=idx, text=text))
    s.points_correct = item.get("points")


async def multi_bot_prompts(
        user: User, step: Step, phase: int
) -> list[tuple[str, dict]]:
    from app.bot.keyboards import multi_kb

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
        header = texts.MULTI_HEADER
        title = step.title
        body = step.text or ""
        instr = texts.MULTI_INSTR
        parts = [f"<b>{header}</b>", title]
        if body:
            parts.append(body)
        parts.append(f"<i>{instr}</i>")
        text = "\n\n".join(parts)
        msgs.append(
            (
                text,
                {"parse_mode": "HTML", "reply_markup": multi_kb(options, selected=set())},
            )
        )
    else:
        async with AsyncSessionLocal() as s:
            ans = (
                await s.execute(
                    select(MultiAnswer).where(
                        MultiAnswer.step_id == step.id, MultiAnswer.user_id == user.id
                    )
                )
            ).scalar_one_or_none()
        if not ans:
            text = texts.NO_ANSWER + texts.RESPONSES_CLOSED
        else:
            correct_set = {
                int(x)
                for x in (step.correct_multi or "").split(",")
                if x.strip().isdigit()
            }
            chosen = {
                int(x)
                for x in ans.choice_idxs.split(",")
                if x.strip().isdigit()
            }
            if not chosen.issubset(correct_set):
                text = texts.WRONG_ANSWER + texts.RESPONSES_CLOSED
            else:
                share = (step.points_correct or 0) / len(correct_set) if correct_set else 0
                points = int(share * len(chosen))
                text = texts.CORRECT_PREFIX.format(points=points) + texts.RESPONSES_CLOSED
        msgs.append((text, {}))
    return msgs


async def multi_on_callback(
        cb: CallbackQuery,
        bot: Bot,
        session: AsyncSession,
        user: User,
        state: GlobalState,
        step: Step,
        payload: str,
) -> None:
    from app.bot.keyboards import multi_kb

    if state.phase != 0:
        await cb.answer(texts.NOT_ANSWER_PHASE, show_alert=True)
        return
    choice_idx = int(payload)
    existing = (
        await session.execute(
            select(MultiAnswer).where(
                MultiAnswer.step_id == step.id, MultiAnswer.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    now = datetime.utcnow()
    delta_ms = int((now - state.step_started_at).total_seconds() * 1000)
    delta_ms = max(0, delta_ms)
    if existing:
        selected = {int(x) for x in existing.choice_idxs.split(",") if x}
        old_delta = int(
            (existing.answered_at - state.step_started_at).total_seconds() * 1000
        )
    else:
        selected: set[int] = set()
        old_delta = 0
        existing = MultiAnswer(
            step_id=step.id,
            user_id=user.id,
            choice_idxs="",
            answered_at=now,
        )
        session.add(existing)
        user.quiz_answer_count += 1
    if choice_idx in selected:
        selected.remove(choice_idx)
    else:
        selected.add(choice_idx)
    existing.choice_idxs = ",".join(str(x) for x in sorted(selected))
    existing.answered_at = now
    user.total_answer_ms += delta_ms - old_delta
    user.quiz_answer_ms += delta_ms - old_delta
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
        reply_markup=multi_kb(options, selected=selected)
    )
    count = await session.scalar(
        select(func.count(MultiAnswer.id)).where(MultiAnswer.step_id == step.id)
    )
    total = await session.scalar(
        select(func.count(User.id)).where(User.name != "")
    )
    last_at = await session.scalar(
        select(func.max(MultiAnswer.answered_at)).where(MultiAnswer.step_id == step.id)
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
    "multi",
    StepType(
        multi_context,
        multi_phases,
        on_enter_phase=multi_on_enter,
        load_item=multi_load_item,
        build_bot_prompts=multi_bot_prompts,
        callback_prefix="multi",
        on_callback=multi_on_callback,
        callback_error=texts.NOT_ANSWER_PHASE,
    ),
)

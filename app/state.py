"""State machine helpers for advancing steps and notifying users."""
from __future__ import annotations

import asyncio
from datetime import datetime

from aiogram import Bot
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    GlobalState,
    Step,
    Idea,
    User,
)
from app.scoring import add_vote_points, add_mcq_points
from app.settings import settings


async def notify_all(session: AsyncSession) -> None:
    """Send current prompt to all users via Telegram bot."""
    from app.bot import send_prompt

    gs = await session.get(GlobalState, 1)
    step = await session.get(Step, gs.current_step_id)
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    users = (await session.execute(select(User))).scalars().all()
    for u in users:
        try:
            await send_prompt(bot, u, step, gs.phase)
            await asyncio.sleep(settings.TELEGRAM_SEND_DELAY)
        except Exception:
            pass
    await bot.session.close()


async def advance(session: AsyncSession, forward: bool) -> None:
    """Advance to the next phase or block and notify all participants."""
    gs = await session.get(GlobalState, 1)
    step = await session.get(Step, gs.current_step_id)

    async def commit_and_notify() -> None:
        await session.commit()
        await notify_all(session)

    if forward:
        if step.type == "open":
            ideas_count = await session.scalar(select(func.count(Idea.id)).where(Idea.step_id == step.id))
            total_phases = 3 if ideas_count else 2
            if gs.phase + 1 < total_phases:
                gs.phase += 1
                gs.phase_started_at = datetime.utcnow()
                if ideas_count and gs.phase == 2:
                    await add_vote_points(session, step.id)
                await commit_and_notify()
            else:
                await move_to_block(session, step.order_index + 1)
                await commit_and_notify()
        elif step.type == "quiz":
            if gs.phase == 0:
                gs.phase = 1
                gs.phase_started_at = datetime.utcnow()
                await add_mcq_points(session, step)
                await commit_and_notify()
            else:
                await move_to_block(session, step.order_index + 1)
                await commit_and_notify()
        else:
            await move_to_block(session, step.order_index + 1)
            await commit_and_notify()
    else:
        if step.type in ("open", "quiz") and gs.phase > 0:
            gs.phase -= 1
            gs.phase_started_at = datetime.utcnow()
            await commit_and_notify()
        else:
            await move_to_block(session, step.order_index - 1, to_last_phase=True)
            await commit_and_notify()


async def move_to_block(
    session: AsyncSession, target_order_index: int, to_last_phase: bool = False
) -> None:
    """Switch global state to another block and optionally jump to its last phase."""
    target = await session.scalar(select(Step).where(Step.order_index == target_order_index))
    if not target:
        return
    gs = await session.get(GlobalState, 1)
    gs.current_step_id = target.id
    now = datetime.utcnow()
    gs.step_started_at = now
    gs.phase_started_at = now
    if to_last_phase and target.type == "open":
        ideas_count = await session.scalar(select(func.count(Idea.id)).where(Idea.step_id == target.id))
        gs.phase = 2 if ideas_count else 1
    elif to_last_phase and target.type == "quiz":
        gs.phase = 1
    else:
        gs.phase = 0
    await session.commit()

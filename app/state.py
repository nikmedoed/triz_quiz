"""State machine helpers for advancing steps and notifying users."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    GlobalState,
    Step,
    User,
)
from app.settings import settings
from app.step_types import STEP_TYPES
from app.db import AsyncSessionLocal


async def notify_all(session: AsyncSession | None = None) -> None:
    """Send current prompt to all users via Telegram bot."""
    from app.bot import send_prompt

    logger = logging.getLogger(__name__)

    async def _send_with(session_obj: AsyncSession) -> None:
        gs = await session_obj.get(GlobalState, 1)
        step = await session_obj.get(Step, gs.current_step_id)
        bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        try:
            users = (await session_obj.execute(select(User))).scalars().all()
            for u in users:
                try:
                    await send_prompt(bot, u, step, gs.phase)
                    await asyncio.sleep(settings.TELEGRAM_SEND_DELAY)
                except Exception:
                    logger.exception(
                        "Telegram prompt send failed: user_id=%s step_id=%s step_type=%s phase=%s",
                        getattr(u, "id", None),
                        getattr(step, "id", None),
                        getattr(step, "type", None),
                        getattr(gs, "phase", None),
                    )
        finally:
            await bot.session.close()

    if session is None:
        try:
            async with AsyncSessionLocal() as new_session:
                await _send_with(new_session)
        except Exception:
            logger.exception("notify_all failed")
        return

    try:
        await _send_with(session)
    except Exception:
        logger.exception("notify_all failed")


async def advance(session: AsyncSession, forward: bool) -> None:
    """Advance to the next phase or block and notify all participants."""
    gs = await session.get(GlobalState, 1)
    step = await session.get(Step, gs.current_step_id)

    async def commit_and_notify() -> None:
        await session.commit()
        asyncio.create_task(notify_all())

    handler = STEP_TYPES.get(step.type)
    total_phases = 1
    if handler:
        total_phases = await handler.total_phases(session, step)

    if forward:
        if gs.phase + 1 < total_phases:
            gs.phase += 1
            gs.phase_started_at = datetime.utcnow()
            if handler and handler.on_enter_phase:
                await handler.on_enter_phase(session, step, gs.phase)
            await commit_and_notify()
        else:
            await move_to_block(session, step.order_index + 1)
            await commit_and_notify()
    else:
        if gs.phase > 0:
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
    if to_last_phase:
        handler = STEP_TYPES.get(target.type)
        if handler:
            phases = await handler.total_phases(session, target)
            gs.phase = max(0, phases - 1)
        else:
            gs.phase = 0
    else:
        gs.phase = 0
    await session.commit()

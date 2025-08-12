"""Registry of step types with phase counts and hooks."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Step, GlobalState, Idea
from app.scoring import add_vote_points, add_mcq_points
from app.public_context import (
    registration_context,
    open_context,
    quiz_context,
    leaderboard_context,
)

ContextBuilder = Callable[[AsyncSession, Step, GlobalState, Dict[str, Any]], Awaitable[None]]
TotalPhasesFn = Callable[[AsyncSession, Step], Awaitable[int]]
PhaseHook = Callable[[AsyncSession, Step, int], Awaitable[None]]


@dataclass
class StepType:
    """Metadata and helpers for a quiz step type."""

    build_context: ContextBuilder
    total_phases: TotalPhasesFn
    on_enter_phase: Optional[PhaseHook] = None


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


STEP_TYPES: Dict[str, StepType] = {
    "registration": StepType(registration_context, registration_phases),
    "open": StepType(open_context, open_phases, open_on_enter),
    "quiz": StepType(quiz_context, quiz_phases, quiz_on_enter),
    "leaderboard": StepType(leaderboard_context, leaderboard_phases),
}

# Leaderboard step type.
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

import app.texts as texts
from app.db import AsyncSessionLocal
from app.models import Step, User
from app.public_context import leaderboard_context
from app.scoring import get_leaderboard_users

from . import StepType, register


async def leaderboard_phases(session: AsyncSession, step: Step) -> int:
    return 1


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


register(
    "leaderboard",
    StepType(
        leaderboard_context,
        leaderboard_phases,
        build_bot_prompts=leaderboard_bot_prompts,
    ),
)

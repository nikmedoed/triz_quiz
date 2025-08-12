# Registration step type.
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

import app.texts as texts
from app.models import Step, User
from app.public_context import registration_context

from . import StepType, register


async def registration_phases(session: AsyncSession, step: Step) -> int:
    return 1


async def registration_bot_prompts(user: User, step: Step, phase: int) -> list[tuple[str, dict]]:
    return [(texts.REGISTRATION_WAIT, {})]


register(
    "registration",
    StepType(
        registration_context,
        registration_phases,
        build_bot_prompts=registration_bot_prompts,
    ),
)

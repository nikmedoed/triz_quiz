# Load scenario (JSON or YAML list). Auto-prepend registration and append leaderboard.
import json
import os
import yaml

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.texts as texts
from app.models import Step, GlobalState
from app.step_types import STEP_TYPES

IGNORED = {"vote", "vote_results"}


async def load_if_empty(session: AsyncSession, path: str) -> None:
    existing = await session.execute(select(Step.id))
    if existing.first():
        return
    # Prefer explicit path; else try both yaml/json
    data = None
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = yaml.safe_load(text)
    else:
        return
    if isinstance(data, dict) and "quiz" in data:
        # Legacy format: {quiz: {steps: [...]}}
        items = data["quiz"].get("steps", [])
    elif isinstance(data, list):
        items = data
    else:
        raise ValueError("Scenario must be a list of blocks or legacy dict format")

    order = 0

    def add_step(_type: str, title: str = "", text: str | None = None, options: list[str] | None = None,
                 correct_index: int | None = None, points: int | None = None, timer_ms: int | None = None):
        nonlocal order
        s = Step(order_index=order, type=_type, title=title or _type.title(), text=text, correct_index=correct_index,
                 points_correct=points, timer_ms=timer_ms)
        session.add(s)
        order += 1
        return s

    # Registration (implicit)
    add_step("registration", title=texts.TITLE_REGISTRATION)

    # Normalize items
    for item in items:
        t = (item.get("type") or "").strip().lower()
        if t in IGNORED:
            continue
        handler = STEP_TYPES.get(t)
        if not handler:
            continue
        if handler.load_item:
            await handler.load_item(session, add_step, item)
        else:
            add_step(
                t,
                title=item.get("title", t.title()),
                text=item.get("description") or item.get("text"),
            )

    # Leaderboard (implicit)
    add_step("leaderboard", title=texts.TITLE_LEADERBOARD)

    # Global state
    first_step_id = await session.scalar(select(Step.id).order_by(Step.order_index.asc()))
    session.add(GlobalState(current_step_id=first_step_id))
    await session.commit()

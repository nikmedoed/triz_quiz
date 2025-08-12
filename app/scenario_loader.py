# Load scenario (JSON or YAML list). Auto-prepend registration and append leaderboard.
import json
import os
import yaml

from typing import Any, Awaitable, Callable, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.texts as texts
from app.models import Step, StepOption, GlobalState


# Step loader callback type. Each loader receives the current DB session,
# an ``add_step`` helper to create the ``Step`` row, and the raw scenario item.
StepLoader = Callable[[AsyncSession, Callable[..., Step], Dict[str, Any]], Awaitable[None]]


async def _load_open(session: AsyncSession, add_step: Callable[..., Step], item: Dict[str, Any]) -> None:
    """Persist an ``open`` step from scenario data."""
    add_step(
        "open",
        title=item.get("title", texts.TITLE_OPEN),
        text=item.get("description") or item.get("text"),
    )


async def _load_quiz(session: AsyncSession, add_step: Callable[..., Step], item: Dict[str, Any]) -> None:
    """Persist a ``quiz`` step with options and correct answer."""
    s = add_step(
        "quiz",
        title=item.get("title", texts.TITLE_QUIZ),
        text=item.get("description") or item.get("text"),
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


# Registry of known step loaders. New mechanics can register here without
# modifying ``load_if_empty`` logic.
STEP_LOADERS: Dict[str, StepLoader] = {
    "open": _load_open,
    "quiz": _load_quiz,
}


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
                 correct_index: int | None = None, points: int | None = None):
        nonlocal order
        s = Step(order_index=order, type=_type, title=title or _type.title(), text=text, correct_index=correct_index,
                 points_correct=points)
        session.add(s)
        order += 1
        return s

    # Registration (implicit)
    add_step("registration", title=texts.TITLE_REGISTRATION)

    # Normalize items
    for item in items:
        t = (item.get("type") or "").strip().lower()
        if t in {"vote", "vote_results"}:
            continue
        loader = STEP_LOADERS.get(t)
        if loader:
            await loader(session, add_step, item)
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

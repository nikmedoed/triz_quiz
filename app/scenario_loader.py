# Load scenario (JSON or YAML list). Auto-prepend registration and append leaderboard.
import json
import os
import yaml

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.texts as texts
from app.models import Step, StepOption, GlobalState

SUPPORTED = {"open", "quiz", "vote", "vote_results"}


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
        if t not in SUPPORTED:
            continue
        if t == "open":
            add_step(
                "open",
                title=item.get("title", texts.TITLE_OPEN),
                text=item.get("description") or item.get("text"),
            )
        elif t == "quiz":
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
            elif isinstance(correct, (int,)):
                s.correct_index = correct
            s.points_correct = item.get("points")
        # vote/vote_results are ignored (implicit in `open`)

    # Leaderboard (implicit)
    add_step("leaderboard", title=texts.TITLE_LEADERBOARD)

    # Global state
    first_step_id = await session.scalar(select(Step.id).order_by(Step.order_index.asc()))
    session.add(GlobalState(current_step_id=first_step_id))
    await session.commit()

# Load scenario (JSON or YAML list). Auto-prepend registration and append leaderboard.
import json
import os
import random
from dataclasses import dataclass
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.texts as texts
from app.models import Step, GlobalState
from app.step_types import STEP_TYPES
from app.step_types.multi import build_multi_payload_seeded

IGNORED = {"vote", "vote_results"}


@dataclass
class PreviewOption:
    idx: int
    text: str


@dataclass
class PreviewStep:
    step: Step
    options: list[PreviewOption]


def _normalize_text(val: str | list[str] | None) -> str | None:
    if isinstance(val, list):
        return "\n".join(str(x) for x in val)
    return val


def _parse_timer_ms(time_val: Any) -> int | None:
    if isinstance(time_val, str) and time_val.isdigit():
        return int(time_val) * 1000
    if isinstance(time_val, (int, float)):
        return int(time_val) * 1000
    return None


def _resolve_path(path: str | None) -> str | None:
    if path and os.path.exists(path):
        return path
    for candidate in ("scenario.yaml", "scenario.json"):
        if os.path.exists(candidate):
            return candidate
    return None


def _read_scenario_items(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = yaml.safe_load(text)
    if isinstance(data, dict) and "quiz" in data:
        items = data["quiz"].get("steps", [])
    elif isinstance(data, list):
        items = data
    else:
        raise ValueError("Scenario must be a list of blocks or legacy dict format")
    normalized: list[dict] = []
    for item in items:
        copy = dict(item)
        copy["description"] = _normalize_text(copy.get("description"))
        copy["text"] = _normalize_text(copy.get("text"))
        normalized.append(copy)
    return normalized


def _parse_correct_index(val: Any) -> int | None:
    if isinstance(val, str) and val.isdigit():
        return int(val) - 1
    if isinstance(val, int):
        return val
    return None


async def load_if_empty(session: AsyncSession, path: str) -> None:
    existing = await session.execute(select(Step.id))
    if existing.first():
        return
    resolved = _resolve_path(path)
    if not resolved:
        return
    items = _read_scenario_items(resolved)
    order = 0

    def add_step(
            _type: str,
            title: str = "",
            text: str | None = None,
            options: list[str] | None = None,
            correct_index: int | None = None,
            correct_multi: str | None = None,
            points: int | None = None,
            timer_ms: int | None = None,
    ):
        nonlocal order
        s = Step(
            order_index=order,
            type=_type,
            title=title or _type.title(),
            text=text,
            correct_index=correct_index,
            correct_multi=correct_multi,
            points_correct=points,
            timer_ms=timer_ms,
        )
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


def load_preview_steps(path: str | None = None) -> list[PreviewStep]:
    """Read scenario file without touching DB and return steps for preview."""
    resolved = _resolve_path(path)
    if not resolved:
        return []
    items = _read_scenario_items(resolved)
    steps: list[PreviewStep] = []
    order = 0
    for item in items:
        t = (item.get("type") or "").strip().lower()
        if not t or t in IGNORED:
            continue
        if t == "open":
            step = Step(
                id=order + 1,
                order_index=order,
                type="open",
                title=item.get("title", texts.TITLE_OPEN),
                text=item.get("description") or item.get("text"),
                timer_ms=_parse_timer_ms(item.get("time")),
            )
            steps.append(PreviewStep(step=step, options=[]))
            order += 1
            continue
        if t == "quiz":
            opts = [str(opt) for opt in item.get("options", [])]
            correct_index = _parse_correct_index(item.get("correct"))
            combined: list[tuple[str, bool]] = [
                (text, idx == correct_index) for idx, text in enumerate(opts)
            ]
            rng = random.Random(order + 1)  # order+1 matches DB order_index (registration is implicit at 0)
            rng.shuffle(combined)
            shuffled_correct: int | None = None
            shuffled_opts: list[str] = []
            for idx, (text, is_correct) in enumerate(combined):
                shuffled_opts.append(text)
                if is_correct:
                    shuffled_correct = idx
            step = Step(
                id=order + 1,
                order_index=order,
                type="quiz",
                title=item.get("title", texts.TITLE_QUIZ),
                text=item.get("description") or item.get("text"),
                correct_index=shuffled_correct,
                points_correct=item.get("points"),
                timer_ms=_parse_timer_ms(item.get("time")),
            )
            options = [
                PreviewOption(idx=i, text=text) for i, text in enumerate(shuffled_opts)
            ]
            steps.append(PreviewStep(step=step, options=options))
            order += 1
            continue
        if t == "multi":
            options_payload, correct_multi_indices = build_multi_payload_seeded(
                item, seed=order + 1  # order+1 matches DB order_index (registration is implicit at 0)
            )
            step = Step(
                id=order + 1,
                order_index=order,
                type="multi",
                title=item.get("title", texts.TITLE_MULTI),
                text=item.get("description") or item.get("text"),
                correct_multi=",".join(str(idx) for idx in sorted(set(correct_multi_indices)))
                if correct_multi_indices
                else None,
                points_correct=item.get("points"),
                timer_ms=_parse_timer_ms(item.get("time")),
            )
            options = [
                PreviewOption(idx=i, text=text) for i, text in enumerate(options_payload)
            ]
            steps.append(PreviewStep(step=step, options=options))
            order += 1
            continue
        if t == "sequence":
            opts = [str(opt) for opt in item.get("options", [])]
            pts_val = item.get("points")
            default_points = None
            if isinstance(pts_val, str) and pts_val.isdigit():
                default_points = int(pts_val)
            elif isinstance(pts_val, (int, float)):
                default_points = int(pts_val)
            else:
                default_points = 3
            step = Step(
                id=order + 1,
                order_index=order,
                type="sequence",
                title=item.get("title", texts.TITLE_SEQUENCE),
                text=item.get("description") or item.get("text"),
                points_correct=default_points,
                timer_ms=_parse_timer_ms(item.get("time")),
            )
            options = [PreviewOption(idx=i, text=text) for i, text in enumerate(opts)]
            steps.append(PreviewStep(step=step, options=options))
            order += 1
            continue
    return steps

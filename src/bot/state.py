"""Application state and persistence helpers."""

import json
import time

from ..config import settings
from ..db import Database
from ..resources import load_scenario

PROJECTOR_URL = settings.projector_url

db = Database(settings.db_file, settings.avatar_dir)
SCENARIO = load_scenario()

step_idx = -1  # текущий шаг сценария
participants: dict[int, dict] = {}
answers_current: dict[int, dict] = {}
votes_current: dict[int, set[int]] = {}
ideas: list[dict] = []  # текущие идеи для голосования
vote_gains: dict[int, int] = {}  # очки, полученные на последнем голосовании
ADMIN_ID = settings.admin_id  # ведущий
pending_names: set[int] = set()
last_answer_ts = 0.0
step_start_ts = 0.0


def current_step():
    return SCENARIO[step_idx] if 0 <= step_idx < len(SCENARIO) else None


def _parse_answers(raw: dict[int, str]) -> dict[int, dict]:
    return {
        uid: json.loads(val) if val.startswith("{") else {"text": val, "time": 0}
        for uid, val in raw.items()
    }


def load_state() -> None:
    """Load quiz state from the database."""
    global step_idx, participants, answers_current, votes_current, ideas, vote_gains, pending_names, last_answer_ts, step_start_ts
    step_idx = db.get_step()
    step_start_ts = db.get_step_start_ts()
    last_answer_ts = db.get_last_answer_ts()
    if step_start_ts == 0:
        step_start_ts = last_answer_ts = time.time()
    participants = {
        row["id"]: {"name": row["name"], "score": row["score"]}
        for row in db.get_participants()
    }
    answers_current = _parse_answers(db.get_responses(step_idx, "open"))
    answers_current.update(_parse_answers(db.get_responses(step_idx, "quiz")))
    votes_raw = db.get_responses(step_idx, "vote")
    votes_current = {
        uid: set(json.loads(v)) if v.startswith("[") else set()
        for uid, v in votes_raw.items()
    }
    vote_gains = db.get_vote_gains()
    pending_names = set(db.get_pending_names())
    if current_step() and current_step().get("type") == "vote":
        ideas = db.get_ideas(step_idx - 1)


def reset_state() -> None:
    """Clear in-memory state and reset the database."""
    global step_idx, participants, answers_current, votes_current, ideas, vote_gains, pending_names, last_answer_ts, step_start_ts
    step_idx = -1
    participants.clear()
    answers_current.clear()
    votes_current.clear()
    ideas = []
    vote_gains = {}
    pending_names.clear()
    now = time.time()
    last_answer_ts = now
    step_start_ts = now
    db.reset()
    db.set_step_start_ts(now)
    db.set_last_answer_ts(now)
    db.set_vote_gains({})
    db.set_pending_names([])


def record_answer(uid: int, kind: str, text: str) -> None:
    """Store answer in memory and database."""
    global last_answer_ts
    now = time.time()
    delta = now - step_start_ts
    answers_current[uid] = {"text": text, "time": delta}
    db.record_response(uid, step_idx, kind, json.dumps({"text": text, "time": delta}))
    last_answer_ts = now
    db.set_last_answer_ts(now)

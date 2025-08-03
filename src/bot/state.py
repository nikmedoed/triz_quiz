"""Application state and persistence helpers."""

import json
import time

from ..config import settings
from ..db import Database
from ..resources import load_scenario

PROJECTOR_URL = settings.projector_url

db = Database(settings.db_file, settings.avatar_dir)
SCENARIO = load_scenario()
vote_gains: dict[int, int] = {}  # очки, полученные на последнем голосовании
ADMIN_ID = settings.admin_id  # ведущий
pending_names: set[int] = set()
last_answer_ts = time.time()
step_start_ts = time.time()


def current_step():
    idx = db.get_step()
    return SCENARIO[idx] if 0 <= idx < len(SCENARIO) else None


def load_state() -> None:
    """Compatibility placeholder."""
    return None


def record_answer(uid: int, kind: str, text: str) -> None:
    """Store answer in the database."""
    global last_answer_ts
    step_idx = db.get_step()
    delta = time.time() - step_start_ts
    db.record_response(uid, step_idx, kind, json.dumps({"text": text, "time": delta}))
    last_answer_ts = time.time()

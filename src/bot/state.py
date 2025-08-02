"""Application state and persistence helpers."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from ..config import settings
from ..db import Database
from ..resources import load_scenario


db = Database(settings.db_file)
SCENARIO = load_scenario()


@dataclass
class BotState:
    """Container for mutable bot state."""

    db: Database
    projector_url: str = settings.projector_url
    admin_id: int = settings.admin_id
    step_idx: int = -1
    participants: dict[int, dict] = field(default_factory=dict)
    answers_current: dict[int, dict] = field(default_factory=dict)
    votes_current: dict[int, set[int]] = field(default_factory=dict)
    ideas: list[dict] = field(default_factory=list)
    vote_gains: dict[int, int] = field(default_factory=dict)
    pending_names: set[int] = field(default_factory=set)
    last_answer_ts: float = field(default_factory=time.time)
    step_start_ts: float = field(default_factory=time.time)

    # ------------------------------------------------------------------
    def current_step(self):
        return SCENARIO[self.step_idx] if 0 <= self.step_idx < len(SCENARIO) else None

    # ------------------------------------------------------------------
    def _parse_answers(self, raw: dict[int, str]) -> dict[int, dict]:
        return {
            uid: json.loads(val) if val.startswith("{") else {"text": val, "time": 0}
            for uid, val in raw.items()
        }

    # ------------------------------------------------------------------
    def load(self) -> None:
        """Load quiz state from the database."""
        self.step_idx = self.db.get_step()
        self.participants = {
            row["id"]: {"name": row["name"], "score": row["score"]}
            for row in self.db.get_participants()
        }
        self.answers_current = self._parse_answers(self.db.get_responses(self.step_idx, "open"))
        self.answers_current.update(
            self._parse_answers(self.db.get_responses(self.step_idx, "quiz"))
        )
        votes_raw = self.db.get_responses(self.step_idx, "vote")
        self.votes_current = {
            uid: set(json.loads(v)) if v.startswith("[") else set()
            for uid, v in votes_raw.items()
        }
        if self.current_step() and self.current_step().get("type") == "vote":
            self.ideas = self.db.get_ideas(self.step_idx - 1)

    # ------------------------------------------------------------------
    def reset(self) -> None:
        """Clear in-memory state without touching the database."""
        self.step_idx = -1
        self.participants.clear()
        self.answers_current.clear()
        self.votes_current.clear()
        self.ideas = []
        self.vote_gains = {}
        self.pending_names.clear()
        self.last_answer_ts = time.time()
        self.step_start_ts = time.time()

    # ------------------------------------------------------------------
    def record_answer(self, uid: int, kind: str, text: str) -> None:
        """Store answer in memory and database."""
        delta = time.time() - self.step_start_ts
        self.answers_current[uid] = {"text": text, "time": delta}
        self.db.record_response(
            uid, self.step_idx, kind, json.dumps({"text": text, "time": delta})
        )
        self.last_answer_ts = time.time()


state = BotState(db)


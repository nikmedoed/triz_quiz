import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple


class Database:
    """Lightweight SQLite wrapper for storing quiz data."""

    def __init__(self, path: str, avatar_dir: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.avatar_dir = Path(avatar_dir)
        self.avatar_dir.mkdir(parents=True, exist_ok=True)
        self._apply_migrations()

    def _apply_migrations(self) -> None:
        """Apply pending schema migrations in order."""
        cur = self.conn.cursor()
        migrations = [self._migration_initial]
        cur.execute("PRAGMA user_version")
        version = cur.fetchone()[0]
        for idx in range(version, len(migrations)):
            migrations[idx](cur)
            cur.execute(f"PRAGMA user_version = {idx + 1}")
            self.conn.commit()

    def _migration_initial(self, cur: sqlite3.Cursor) -> None:
        """Create base tables if they do not exist."""
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS participants (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                score INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS responses (
                user_id INTEGER,
                step INTEGER,
                kind TEXT,
                value TEXT,
                PRIMARY KEY(user_id, step, kind)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )

    def add_participant(
            self, user_id: int, name: str, avatar: bytes | None = None
    ) -> None:
        """Insert or update a participant without resetting their score."""
        cur = self.conn.cursor()
        cur.execute(
            (
                "INSERT INTO participants (id, name) VALUES (?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "name=excluded.name"
            ),
            (user_id, name),
        )
        self.conn.commit()
        if avatar:
            (self.avatar_dir / f"{user_id}.jpg").write_bytes(avatar)

    def update_score(self, user_id: int, delta: int) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE participants SET score = score + ? WHERE id = ?",
            (delta, user_id),
        )
        self.conn.commit()

    def record_response(self, user_id: int, step: int, kind: str, value: str) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "REPLACE INTO responses (user_id, step, kind, value) VALUES (?, ?, ?, ?)",
            (user_id, step, kind, value),
        )
        self.conn.commit()

    def get_rating(self) -> List[Tuple[str, int]]:
        cur = self.conn.cursor()
        cur.execute("SELECT name, score FROM participants ORDER BY score DESC")
        return [(row["name"], row["score"]) for row in cur.fetchall()]

    def get_participants(self) -> List[sqlite3.Row]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM participants")
        return cur.fetchall()

    def get_avatar(self, user_id: int) -> bytes | None:
        path = self.avatar_dir / f"{user_id}.jpg"
        return path.read_bytes() if path.exists() else None

    def get_responses(self, step: int, kind: str) -> Dict[int, str]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT user_id, value FROM responses WHERE step = ? AND kind = ?",
            (step, kind),
        )
        return {row["user_id"]: row["value"] for row in cur.fetchall()}

    def get_open_answers(self, step: int) -> List[dict]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT r.user_id, r.value, p.name
            FROM responses r JOIN participants p ON r.user_id = p.id
            WHERE r.step = ? AND r.kind = 'open'
            """,
            (step,),
        )
        rows = []
        for row in cur.fetchall():
            try:
                data = json.loads(row["value"])
                text = data.get("text", "")
                ts = data.get("time", 0)
            except Exception:
                text = row["value"]
                ts = 0
            rows.append(
                {
                    "user_id": row["user_id"],
                    "name": row["name"],
                    "text": text,
                    "time": ts,
                }
            )
        return rows

    def get_ideas(self, step: int) -> List[dict]:
        """Return open answers of a step formatted for voting."""
        answers = self.get_open_answers(step)
        answers.sort(key=lambda a: a["time"])
        return [
            {
                "id": i + 1,
                "user_id": a["user_id"],
                "text": a["text"],
                "time": a["time"],
            }
            for i, a in enumerate(answers)
        ]

    def get_votes(self, step: int) -> Dict[int, List[int]]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT user_id, value FROM responses WHERE step = ? AND kind = 'vote'",
            (step,),
        )
        votes: Dict[int, List[int]] = {}
        for row in cur.fetchall():
            try:
                votes[row["user_id"]] = json.loads(row["value"])
            except Exception:
                votes[row["user_id"]] = []
        return votes

    def get_times_by_user(self) -> Dict[int, Dict[str, List[float]]]:
        """Collect response times for each user grouped by question kind."""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT user_id, kind, value FROM responses WHERE kind IN ('open','quiz')"
        )
        stats: Dict[int, Dict[str, List[float]]] = {}
        for row in cur.fetchall():
            try:
                data = json.loads(row["value"])
                t = data.get("time", 0)
            except Exception:
                t = 0
            stats.setdefault(row["user_id"], {}).setdefault(row["kind"], []).append(t)
        return stats

    def get_leaderboard(self) -> List[dict]:
        """Return participants ordered by score and response speed."""
        cur = self.conn.cursor()
        cur.execute("SELECT id, name, score FROM participants")
        people = {
            row["id"]: {"name": row["name"], "score": row["score"]}
            for row in cur.fetchall()
        }
        times = self.get_times_by_user()
        board = []
        for uid, p in people.items():
            total = sum(times.get(uid, {}).get("open", [])) + sum(
                times.get(uid, {}).get("quiz", [])
            )
            board.append({
                "id": uid,
                "name": p["name"],
                "score": p["score"],
                "time": total,
            })
        board.sort(key=lambda r: (-r["score"], r["time"]))
        for i, row in enumerate(board, start=1):
            row["place"] = i
        return board

    def _get_state(self, key: str, default: int) -> int:
        cur = self.conn.cursor()
        cur.execute("SELECT value FROM state WHERE key = ?", (key,))
        row = cur.fetchone()
        return int(row["value"]) if row else default

    def _set_state(self, key: str, value: int) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "REPLACE INTO state (key, value) VALUES (?, ?)", (key, str(value))
        )
        self.conn.commit()

    def get_step(self) -> int:
        return self._get_state("step", -1)

    def set_step(self, step: int) -> None:
        self._set_state("step", step)

    def get_stage(self) -> int:
        return self._get_state("stage", 1)

    def set_stage(self, stage: int) -> None:
        self._set_state("stage", stage)

    def reset(self) -> None:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM participants")
        cur.execute("DELETE FROM responses")
        cur.execute("DELETE FROM state")
        self.conn.commit()
        for file in self.avatar_dir.glob("*"):
            try:
                file.unlink()
            except FileNotFoundError:
                pass
        self.set_stage(1)
        self.set_step(-1)

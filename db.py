import sqlite3
from typing import List, Tuple

class Database:
    """Lightweight SQLite wrapper for storing quiz data."""

    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS participants (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                score INTEGER NOT NULL DEFAULT 0
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS responses (
                user_id INTEGER,
                step INTEGER,
                kind TEXT,
                value TEXT,
                PRIMARY KEY(user_id, step, kind)
            )
        """)
        self.conn.commit()

    def add_participant(self, user_id: int, name: str, score: int = 0) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO participants (id, name, score) VALUES (?, ?, ?)",
            (user_id, name, score),
        )
        self.conn.commit()

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

    def reset(self) -> None:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM participants")
        cur.execute("DELETE FROM responses")
        self.conn.commit()

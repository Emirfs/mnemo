"""Human-labelled bridge interactions for eval and future fine-tuning."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS interactions (
    task_id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    provider TEXT NOT NULL,
    project TEXT,
    objective TEXT NOT NULL,
    output TEXT NOT NULL,
    created_at TEXT NOT NULL,
    rating TEXT,
    note TEXT
);
"""


class FeedbackStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(self.path))
        self.con.row_factory = sqlite3.Row
        self.con.executescript(_SCHEMA)

    def close(self):
        self.con.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def record(self, *, task_id, user_id, provider, project, objective, output) -> None:
        self.con.execute(
            """INSERT OR REPLACE INTO interactions
               (task_id,user_id,provider,project,objective,output,created_at,rating,note)
               VALUES (?,?,?,?,?,?,?,NULL,NULL)""",
            (
                task_id, int(user_id), provider, project, objective[:20_000],
                output[:20_000], dt.datetime.now(dt.timezone.utc).isoformat(),
            ),
        )
        self.con.commit()

    def rate(self, task_id: str, user_id: int, rating: str, note: str = "") -> None:
        if rating not in {"good", "bad"}:
            raise ValueError("feedback rating must be good or bad")
        cur = self.con.execute(
            "UPDATE interactions SET rating = ?, note = ? WHERE task_id = ? AND user_id = ?",
            (rating, note[:2_000], task_id, int(user_id)),
        )
        self.con.commit()
        if cur.rowcount != 1:
            raise ValueError("feedback task not found for this user")

    def stats(self) -> dict:
        row = self.con.execute(
            """SELECT COUNT(*) AS total,
                      SUM(CASE WHEN rating='good' THEN 1 ELSE 0 END) AS good,
                      SUM(CASE WHEN rating='bad' THEN 1 ELSE 0 END) AS bad,
                      SUM(CASE WHEN rating IS NULL THEN 1 ELSE 0 END) AS unrated
               FROM interactions"""
        ).fetchone()
        return {key: int(row[key] or 0) for key in ("total", "good", "bad", "unrated")}

    def export(self, path: str | Path) -> int:
        rows = self.con.execute(
            "SELECT * FROM interactions WHERE rating IS NOT NULL ORDER BY created_at"
        ).fetchall()
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "".join(json.dumps(dict(row), ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )
        return len(rows)

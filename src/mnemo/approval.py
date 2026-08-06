"""Persistent, one-time approval records for remote write operations."""

from __future__ import annotations

import datetime as dt
import secrets
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    provider TEXT NOT NULL,
    objective TEXT NOT NULL,
    repo TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    worktree TEXT,
    result TEXT
);
"""


@dataclass
class Approval:
    id: str
    user_id: int
    provider: str
    objective: str
    repo: str
    status: str
    created_at: str
    expires_at: str
    worktree: str | None = None
    result: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class ApprovalStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(self.path))
        self.con.row_factory = sqlite3.Row
        self.con.executescript(_SCHEMA)

    def close(self) -> None:
        self.con.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def create(
        self,
        *,
        user_id: int,
        provider: str,
        objective: str,
        repo: str | Path,
        ttl_minutes: int = 15,
    ) -> Approval:
        provider = provider.strip().lower()
        objective = objective.strip()
        repo = str(Path(repo).resolve())
        if provider != "codex":
            raise ValueError("write proposals currently support only codex")
        if not objective or len(objective) > 8_000:
            raise ValueError("proposal objective must contain 1..8000 characters")
        if ttl_minutes < 1 or ttl_minutes > 60:
            raise ValueError("approval TTL must be between 1 and 60 minutes")
        now = dt.datetime.now(dt.timezone.utc)
        approval = Approval(
            id=secrets.token_urlsafe(9),
            user_id=int(user_id),
            provider=provider,
            objective=objective,
            repo=repo,
            status="pending",
            created_at=now.isoformat(),
            expires_at=(now + dt.timedelta(minutes=ttl_minutes)).isoformat(),
        )
        self.con.execute(
            "INSERT INTO approvals VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                approval.id,
                approval.user_id,
                approval.provider,
                approval.objective,
                approval.repo,
                approval.status,
                approval.created_at,
                approval.expires_at,
                approval.worktree,
                approval.result,
            ),
        )
        self.con.commit()
        return approval

    def get(self, approval_id: str) -> Approval | None:
        row = self.con.execute(
            "SELECT * FROM approvals WHERE id = ?", (approval_id,)
        ).fetchone()
        return Approval(**dict(row)) if row else None

    def claim(self, approval_id: str, user_id: int) -> Approval:
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        cur = self.con.execute(
            "UPDATE approvals SET status = 'running' "
            "WHERE id = ? AND user_id = ? AND status = 'pending' AND expires_at > ?",
            (approval_id, int(user_id), now),
        )
        self.con.commit()
        if cur.rowcount != 1:
            raise ValueError("approval is missing, expired, already used, or belongs to another user")
        return self.get(approval_id)

    def reject(self, approval_id: str, user_id: int) -> Approval:
        cur = self.con.execute(
            "UPDATE approvals SET status = 'rejected' "
            "WHERE id = ? AND user_id = ? AND status = 'pending'",
            (approval_id, int(user_id)),
        )
        self.con.commit()
        if cur.rowcount != 1:
            raise ValueError("approval cannot be rejected")
        return self.get(approval_id)

    def finish(
        self,
        approval_id: str,
        *,
        success: bool,
        worktree: str | Path | None = None,
        result: str = "",
    ) -> Approval:
        status = "completed" if success else "failed"
        cur = self.con.execute(
            "UPDATE approvals SET status = ?, worktree = ?, result = ? "
            "WHERE id = ? AND status = 'running'",
            (status, str(worktree) if worktree else None, result[:20_000], approval_id),
        )
        self.con.commit()
        if cur.rowcount != 1:
            raise ValueError("approval is not running")
        return self.get(approval_id)

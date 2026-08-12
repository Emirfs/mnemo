from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from mnemo.approval import ApprovalStore


def test_approval_is_one_time_and_user_bound(tmp_path: Path):
    with ApprovalStore(tmp_path / "approvals.sqlite") as store:
        approval = store.create(
            user_id=12,
            provider="codex",
            objective="Change one file",
            repo=tmp_path,
        )
        with pytest.raises(ValueError, match="another user"):
            store.claim(approval.id, 99)

        claimed = store.claim(approval.id, 12)
        assert claimed.status == "running"

        with pytest.raises(ValueError, match="already used"):
            store.claim(approval.id, 12)


def test_expired_approval_cannot_be_claimed(tmp_path: Path):
    with ApprovalStore(tmp_path / "approvals.sqlite") as store:
        approval = store.create(
            user_id=12,
            provider="codex",
            objective="Task",
            repo=tmp_path,
        )
        expired = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)).isoformat()
        store.con.execute(
            "UPDATE approvals SET expires_at = ? WHERE id = ?", (expired, approval.id)
        )
        store.con.commit()
        with pytest.raises(ValueError, match="expired"):
            store.claim(approval.id, 12)


def test_rejected_approval_cannot_run(tmp_path: Path):
    with ApprovalStore(tmp_path / "approvals.sqlite") as store:
        approval = store.create(
            user_id=12,
            provider="codex",
            objective="Task",
            repo=tmp_path,
        )
        assert store.reject(approval.id, 12).status == "rejected"
        with pytest.raises(ValueError):
            store.claim(approval.id, 12)


def test_finish_records_bounded_result(tmp_path: Path):
    with ApprovalStore(tmp_path / "approvals.sqlite") as store:
        approval = store.create(
            user_id=12,
            provider="codex",
            objective="Task",
            repo=tmp_path,
        )
        store.claim(approval.id, 12)
        finished = store.finish(
            approval.id,
            success=True,
            worktree=tmp_path / "worktree",
            result="x" * 30_000,
        )
        assert finished.status == "completed"
        assert len(finished.result) == 20_000


def test_only_codex_write_proposals_are_allowed(tmp_path: Path):
    with ApprovalStore(tmp_path / "approvals.sqlite") as store:
        with pytest.raises(ValueError, match="only codex"):
            store.create(
                user_id=12,
                provider="claude",
                objective="Task",
                repo=tmp_path,
            )


def test_merge_approval_requires_target(tmp_path: Path):
    with ApprovalStore(tmp_path / "approvals.sqlite") as store:
        with pytest.raises(ValueError, match="target id"):
            store.create(
                user_id=12,
                provider="git",
                objective="Merge",
                repo=tmp_path,
                operation="merge",
            )
        approval = store.create(
            user_id=12,
            provider="git",
            objective="Merge",
            repo=tmp_path,
            operation="merge",
            target_id="source-1",
        )
        assert approval.operation == "merge"
        assert approval.target_id == "source-1"

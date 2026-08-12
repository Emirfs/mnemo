from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest

from mnemo.approval import ApprovalStore
from mnemo.executor import CodexWorktreeExecutor, MergeExecutor


def _git(repo: Path, *args: str):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    (repo / "file.txt").write_text("before\n", encoding="utf-8")
    _git(repo, "add", "file.txt")
    _git(
        repo,
        "-c",
        "user.name=Mnemo Test",
        "-c",
        "user.email=mnemo@example.invalid",
        "commit",
        "-m",
        "initial",
    )
    return repo.resolve()


def _claimed(tmp_path: Path, repo: Path):
    store = ApprovalStore(tmp_path / "approvals.sqlite")
    approval = store.create(
        user_id=12, provider="codex", objective="Change file.txt", repo=repo
    )
    return store, store.claim(approval.id, 12)


def test_executor_creates_isolated_worktree(monkeypatch, tmp_path: Path):
    repo = _repo(tmp_path)
    store, approval = _claimed(tmp_path, repo)
    executor = CodexWorktreeExecutor(tmp_path / "worktrees")

    def fake_codex(worktree, prompt):
        (worktree / "file.txt").write_text("after\n", encoding="utf-8")
        assert "Do not access paths outside" in prompt
        return subprocess.CompletedProcess([], 0, stdout="implemented", stderr="")

    monkeypatch.setattr(executor, "_codex", fake_codex)
    result = executor.execute(approval)
    store.close()

    assert result.success is True
    assert "file.txt" in result.status
    assert "file.txt" in result.diff_stat
    assert "+after" in result.diff
    assert (repo / "file.txt").read_text(encoding="utf-8") == "before\n"
    assert (Path(result.worktree) / "file.txt").read_text(encoding="utf-8") == "after\n"


def test_executor_refuses_dirty_repository(tmp_path: Path):
    repo = _repo(tmp_path)
    (repo / "file.txt").write_text("dirty\n", encoding="utf-8")
    store, approval = _claimed(tmp_path, repo)
    executor = CodexWorktreeExecutor(tmp_path / "worktrees")
    with pytest.raises(ValueError, match="must be clean"):
        executor.execute(approval)
    store.close()


def test_executor_requires_claimed_approval(tmp_path: Path):
    repo = _repo(tmp_path)
    with ApprovalStore(tmp_path / "approvals.sqlite") as store:
        approval = store.create(
            user_id=12, provider="codex", objective="Task", repo=repo
        )
        executor = CodexWorktreeExecutor(tmp_path / "worktrees")
        with pytest.raises(ValueError, match="running Codex approval"):
            executor.execute(approval)


def test_merge_executor_applies_worktree_patch(monkeypatch, tmp_path: Path):
    repo = _repo(tmp_path)
    store, source = _claimed(tmp_path, repo)
    executor = CodexWorktreeExecutor(Path(tempfile.gettempdir()) / "mnemo-worktrees")

    def fake_codex(worktree, prompt):
        (worktree / "file.txt").write_text("after\n", encoding="utf-8")
        return subprocess.CompletedProcess([], 0, stdout="implemented", stderr="")

    monkeypatch.setattr(executor, "_codex", fake_codex)
    result = executor.execute(source)
    source = store.finish(source.id, success=True, worktree=result.worktree)
    merge = store.create(
        user_id=12,
        provider="git",
        objective="Apply patch",
        repo=repo,
        operation="merge",
        target_id=source.id,
    )
    merge = store.claim(merge.id, 12)

    message = MergeExecutor().execute(merge, source)
    store.close()

    assert "uncommitted" in message
    assert (repo / "file.txt").read_text(encoding="utf-8") == "after\n"

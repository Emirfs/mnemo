from __future__ import annotations

from pathlib import Path

import pytest

from mnemo.approval import ApprovalStore
from mnemo.bridge import BridgeResult
from mnemo.executor import ExecutionResult
from mnemo.telegram import (
    TelegramClient,
    TelegramReply,
    RepoRoute,
    TelegramService,
    chunks,
    parse_users,
)


def _write_note(vault: Path):
    path = vault / "projects" / "p" / "decision.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        """---
id: safe-decision
type: decision
title: Safe decision
project: p
summary: anchor memory
---
body
""",
        encoding="utf-8",
    )


def test_parse_users_requires_allowlist():
    assert parse_users("12, 34") == {12, 34}
    with pytest.raises(ValueError, match="allowlist is empty"):
        parse_users("")


def test_unauthorized_user_gets_no_response(tmp_path: Path):
    service = TelegramService(tmp_path, "p", {12})
    assert service.handle(99, "/status") is None


def test_status_exposes_read_only_mode(tmp_path: Path):
    service = TelegramService(tmp_path, "p", {12})
    response = service.handle(12, "/status")
    assert "Mode: read-only" in response
    assert "Project: p" in response


def test_recall_returns_scoped_context(tmp_path: Path):
    _write_note(tmp_path)
    service = TelegramService(tmp_path, "p", {12})
    response = service.handle(12, "/recall anchor")
    assert "safe-decision" in response
    assert "anchor memory" in response


def test_ask_uses_isolated_bridge(monkeypatch, tmp_path: Path):
    _write_note(tmp_path)
    captured = {}

    def fake_bridge(provider, envelope, workdir):
        captured.update(provider=provider, envelope=envelope, workdir=workdir)
        return BridgeResult(provider=provider, success=True, output="reviewed")

    monkeypatch.setattr("mnemo.telegram.run_bridge", fake_bridge)
    service = TelegramService(tmp_path, "p", {12})
    response = service.handle(12, "/ask claude inspect decision")

    assert isinstance(response, TelegramReply)
    assert "reviewed" in response.text
    assert "untrusted AI analysis" in response.text
    assert response.buttons[0][0]["callback_data"].startswith("feedback:good:")
    assert captured["provider"] == "claude"
    assert captured["envelope"].project == "p"
    assert captured["workdir"].name == "mnemo-bridge"


def test_bot_has_no_write_commands(tmp_path: Path):
    service = TelegramService(tmp_path, "p", {12})
    response = service.handle(12, "/delete everything")
    assert "one-time /approve" in response


def test_client_chunks_long_messages(monkeypatch):
    client = TelegramClient("secret")
    calls = []
    monkeypatch.setattr(client, "_call", lambda method, data: calls.append((method, data)))
    client.send(12, "x" * 8000)
    assert len(calls) == len(chunks("x" * 8000)) == 3
    assert all(call[0] == "sendMessage" for call in calls)


def test_client_error_does_not_expose_token(monkeypatch):
    client = TelegramClient("top-secret-token")
    monkeypatch.setattr(
        "mnemo.telegram.urllib.request.urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("network down")),
    )
    with pytest.raises(RuntimeError) as exc:
        client.updates(None)
    assert "top-secret-token" not in str(exc.value)


def test_proposal_requires_second_approval(monkeypatch, tmp_path: Path):
    service = TelegramService(tmp_path / "vault", "p", {12}, repo=tmp_path)
    proposal = service.handle(12, "/propose codex Change one file")
    assert isinstance(proposal, TelegramReply)
    approval_id = proposal.text.splitlines()[0].split(": ", 1)[1]
    assert f"/approve {approval_id}" in proposal.text
    assert proposal.buttons[0][0]["callback_data"] == f"approve:{approval_id}"

    called = []

    class FakeExecutor:
        def execute(self, approval):
            called.append(approval)
            return ExecutionResult(
                success=True,
                worktree="C:/temp/worktree",
                branch=f"mnemo/task-{approval.id}",
                output="implemented",
                status=" M file.txt",
                diff_stat="file.txt | 1 +",
                diff="-before\n+after",
            )

    monkeypatch.setattr("mnemo.telegram.CodexWorktreeExecutor", FakeExecutor)
    monkeypatch.setattr(
        service,
        "_review_and_distill",
        lambda approval, execution: ("reviewed", "draft memory-1"),
    )
    response = service.handle(12, f"/approve {approval_id}")
    assert "completed" in response
    assert "file.txt" in response
    assert len(called) == 1

    second = service.handle(12, f"/approve {approval_id}")
    assert "failed safely" in second


def test_proposal_can_be_rejected(tmp_path: Path):
    service = TelegramService(tmp_path / "vault", "p", {12}, repo=tmp_path)
    proposal = service.handle(12, "/propose codex Task")
    approval_id = proposal.text.splitlines()[0].split(": ", 1)[1]
    assert "rejected" in service.handle(12, f"/reject {approval_id}")
    assert "Status: rejected" in service.handle(12, f"/proposal {approval_id}")


def test_flow_analyzes_before_creating_proposal(monkeypatch, tmp_path: Path):
    service = TelegramService(tmp_path / "vault", "p", {12}, repo=tmp_path)
    monkeypatch.setattr(
        "mnemo.telegram.run_bridge",
        lambda provider, envelope, workdir: BridgeResult(
            provider=provider, success=True, output="safe implementation plan"
        ),
    )

    response = service.handle(12, "/flow add a safe feature")

    assert isinstance(response, TelegramReply)
    assert "Claude analysis" in response.text
    assert "safe implementation plan" in response.text
    assert "/approve" in response.text


def test_telegram_distill_writes_only_draft(monkeypatch, tmp_path: Path):
    service = TelegramService(tmp_path / "vault", "p", {12})
    monkeypatch.setattr(
        "mnemo.telegram.distill",
        lambda text: {
            "remember": True,
            "type": "decision",
            "title": "Remote decision",
            "summary": "Draft only.",
            "body": "",
            "tags": ["telegram"],
            "supersedes": [],
            "reason": "durable",
        },
    )
    response = service.handle(12, "/distill remember this decision")
    assert "Qwen draft" in response
    note = next((tmp_path / "vault").rglob("*.md")).read_text(encoding="utf-8")
    assert "status: draft" in note
    assert "verification: inferred" in note


def test_patch_rejects_untrusted_worktree_path(tmp_path: Path):
    service = TelegramService(tmp_path / "vault", "p", {12}, repo=tmp_path)
    proposal = service.handle(12, "/propose codex Task")
    approval_id = proposal.text.splitlines()[0].split(": ", 1)[1]
    with ApprovalStore(service.approvals_path) as store:
        store.claim(approval_id, 12)
        store.finish(approval_id, success=True, worktree=tmp_path / "outside")
    response = service.handle(12, f"/patch {approval_id}")
    assert "failed safety validation" in response


def test_multi_repo_routes_scope_recall(tmp_path: Path):
    vault = tmp_path / "vault"
    _write_note(vault)
    routes = {
        "alpha": RepoRoute("alpha", "p", tmp_path / "alpha"),
        "beta": RepoRoute("beta", "other", tmp_path / "beta"),
    }
    service = TelegramService(vault, "fallback", {12}, routes=routes)

    assert "alpha" in service.handle(12, "/status")
    assert "safe-decision" in service.handle(12, "/recall anchor")
    assert "Route selected: beta" in service.handle(12, "/use beta")
    assert "safe-decision" not in service.handle(12, "/recall anchor")
    assert "alpha" in service.handle(12, "/repos")

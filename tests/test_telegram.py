from __future__ import annotations

from pathlib import Path

import pytest

from mnemo.bridge import BridgeResult
from mnemo.telegram import TelegramClient, TelegramService, chunks, parse_users


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

    assert "reviewed" in response
    assert captured["provider"] == "claude"
    assert captured["envelope"].project == "p"
    assert captured["workdir"].name == "mnemo-bridge"


def test_bot_has_no_write_commands(tmp_path: Path):
    service = TelegramService(tmp_path, "p", {12})
    response = service.handle(12, "/delete everything")
    assert "No file-write" in response


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

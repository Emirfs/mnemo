from __future__ import annotations

from pathlib import Path

from mnemo import autostart


def test_autostart_contains_no_secrets(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(autostart.os, "name", "nt")
    target = autostart.install(
        tmp_path / "vault",
        project="mnemo",
        repo=tmp_path / "repo",
        repos=tmp_path / "routes.json",
        appdata=tmp_path / "appdata",
    )
    text = target.read_text(encoding="utf-8")
    assert "mnemo.cli" in text
    assert "telegram" in text
    assert "MNEMO_TELEGRAM_TOKEN" not in text
    assert autostart.status(tmp_path / "appdata")["installed"] is True
    assert autostart.uninstall(tmp_path / "appdata") is True
    assert autostart.uninstall(tmp_path / "appdata") is False

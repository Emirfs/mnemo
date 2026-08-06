"""User-level hidden Windows startup launcher for the Telegram bot."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_NAME = "mnemo-telegram.vbs"


def startup_path(appdata: str | Path | None = None) -> Path:
    root = Path(appdata or os.environ.get("APPDATA", ""))
    if not str(root):
        raise RuntimeError("APPDATA is unavailable")
    return root / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / _NAME


def install(
    vault: str | Path,
    *,
    project: str,
    repo: str | Path | None = None,
    repos: str | Path | None = None,
    appdata: str | Path | None = None,
) -> Path:
    if os.name != "nt":
        raise RuntimeError("Telegram autostart is currently Windows-only")
    args = [
        sys.executable,
        "-m",
        "mnemo.cli",
        "--vault",
        str(Path(vault).resolve()),
        "telegram",
        "--project",
        project,
    ]
    if repo:
        args.extend(["--repo", str(Path(repo).resolve())])
    if repos:
        args.extend(["--repos", str(Path(repos).resolve())])
    command = subprocess.list2cmdline(args).replace('"', '""')
    script = f'Set shell = CreateObject("WScript.Shell")\n\nshell.Run "{command}", 0, False\n'
    target = startup_path(appdata)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(script, encoding="utf-8")
    return target


def uninstall(appdata: str | Path | None = None) -> bool:
    target = startup_path(appdata)
    if not target.exists():
        return False
    target.unlink()
    return True


def status(appdata: str | Path | None = None) -> dict:
    target = startup_path(appdata)
    return {"installed": target.exists(), "path": str(target)}

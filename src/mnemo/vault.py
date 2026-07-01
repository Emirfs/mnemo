"""Vault scanning + project detection."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

IGNORE_DIRS = {".git", ".mnemo", ".obsidian", ".venv", "node_modules", "__pycache__", ".trash"}


def iter_note_files(vault: Path) -> Iterator[Path]:
    """Yield every indexable markdown file under the vault."""
    vault = Path(vault)
    for p in sorted(vault.rglob("*.md")):
        rel_parts = p.relative_to(vault).parts
        if any(part in IGNORE_DIRS for part in rel_parts):
            continue
        yield p


MARKER = ".mnemo-project"


def _read_marker(start: Path) -> str | None:
    """Walk up from `start` looking for a `.mnemo-project` file; its first
    non-empty line is the project name. Stops at the git root."""
    cur = Path(start).resolve()
    while True:
        f = cur / MARKER
        if f.is_file():
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    return line.strip()
            return None
        if (cur / ".git").exists() or cur.parent == cur:
            return None
        cur = cur.parent


def detect_project(start: str | Path) -> str | None:
    """Identify the project for a working directory.

    Order: ``.mnemo-project`` marker → git ``origin`` remote slug → folder name.
    The marker lets several repos (different git remotes) share one logical
    project, so their memory is pooled.
    """
    start = Path(start)
    marker = _read_marker(start)
    if marker:
        return marker
    try:
        out = subprocess.run(
            ["git", "-C", str(start), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        url = out.stdout.strip()
        if out.returncode == 0 and url:
            slug = url.rstrip("/").split("/")[-1]
            if slug.endswith(".git"):
                slug = slug[:-4]
            if slug:
                return slug
    except (OSError, subprocess.SubprocessError):
        pass
    return start.name or None

"""Vault scanning + project detection."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

IGNORE_DIRS = {".git", ".mnemo", ".obsidian", "node_modules", "__pycache__", ".trash"}


def iter_note_files(vault: Path) -> Iterator[Path]:
    """Yield every indexable markdown file under the vault."""
    vault = Path(vault)
    for p in sorted(vault.rglob("*.md")):
        rel_parts = p.relative_to(vault).parts
        if any(part in IGNORE_DIRS for part in rel_parts):
            continue
        yield p


def detect_project(start: str | Path) -> str | None:
    """Identify the project for a working directory.

    Order: git ``origin`` remote slug → folder name fallback.
    """
    start = Path(start)
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

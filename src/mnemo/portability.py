"""Portability: the vault is a private git repo of markdown; the index is
derived and rebuildable. Move machines = sync/clone the vault, then reindex.

- init   : scaffold the vault folder + .gitignore + git repo (+ optional remote)
- sync   : commit local changes, pull --rebase, push
- clone  : git clone a vault onto a new machine, then reindex ("pull memory")
- export : zip the markdown (for Drive/one-shot transfer), excluding the index
- import : unzip into a vault, then reindex
"""

from __future__ import annotations

import datetime as _dt
import subprocess
import zipfile
from pathlib import Path

from .index import Index
from .vault import IGNORE_DIRS

VAULT_DIRS = ["daily", "projects", "lessons", "reference", "notes"]

VAULT_GITIGNORE = """\
# mnemo derived index — never commit (rebuildable)
.mnemo/
*.sqlite
*.sqlite-*
.cache/
"""

_EXCLUDE = IGNORE_DIRS | {".git"}


def _git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r


def _has_remote(vault: Path) -> bool:
    return bool(_git(["remote"], vault, check=False).stdout.strip())


def _reindex(vault: Path) -> dict:
    idx = Index(vault / ".mnemo" / "index.sqlite")
    try:
        return idx.reindex(vault)
    finally:
        idx.close()


def init_vault(vault: Path, remote: str | None = None) -> dict:
    vault = Path(vault)
    vault.mkdir(parents=True, exist_ok=True)
    for d in VAULT_DIRS:
        p = vault / d
        p.mkdir(exist_ok=True)
        keep = p / ".gitkeep"
        if not keep.exists():
            keep.write_text("", encoding="utf-8")
    gi = vault / ".gitignore"
    if not gi.exists():
        gi.write_text(VAULT_GITIGNORE, encoding="utf-8")

    git_init = False
    if not (vault / ".git").exists():
        _git(["init"], vault)
        git_init = True
    if remote and not _has_remote(vault):
        _git(["remote", "add", "origin", remote], vault)

    _git(["add", "-A"], vault, check=False)
    committed = False
    if _git(["status", "--porcelain"], vault, check=False).stdout.strip():
        _git(["commit", "-m", "mnemo: init vault"], vault, check=False)
        committed = True
    return {"vault": str(vault), "git_init": git_init, "remote": remote, "committed": committed}


def sync_vault(vault: Path, message: str | None = None) -> dict:
    vault = Path(vault)
    if not (vault / ".git").exists():
        raise RuntimeError("vault is not a git repo; run `mnemo init` first")
    msg = message or f"mnemo sync {_dt.datetime.now():%Y-%m-%d %H:%M}"
    _git(["add", "-A"], vault, check=False)
    committed = False
    if _git(["status", "--porcelain"], vault, check=False).stdout.strip():
        _git(["commit", "-m", msg], vault, check=False)
        committed = True
    pulled = pushed = False
    has_remote = _has_remote(vault)
    if has_remote:
        pulled = _git(["pull", "--rebase"], vault, check=False).returncode == 0
        pushed = _git(["push"], vault, check=False).returncode == 0
    return {"committed": committed, "pulled": pulled, "pushed": pushed, "remote": has_remote}


def clone_vault(url: str, dest: Path) -> dict:
    dest = Path(dest)
    _git(["clone", url, str(dest)], Path.cwd())
    return {"dest": str(dest), "index": _reindex(dest)}


def export_vault(vault: Path, out_file: Path) -> dict:
    vault = Path(vault)
    out = Path(out_file)
    out.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(vault.rglob("*")):
            rel = f.relative_to(vault)
            if any(part in _EXCLUDE for part in rel.parts):
                continue
            if f.is_file():
                z.write(f, str(rel))
                count += 1
    return {"out": str(out), "files": count}


def import_vault(archive: Path, vault: Path) -> dict:
    vault = Path(vault)
    vault.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        z.extractall(vault)
    return {"vault": str(vault), "index": _reindex(vault)}

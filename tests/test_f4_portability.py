"""F4 tests: init / export-import round-trip / sync (no remote) / clone (local)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mnemo.config import Config
from mnemo.index import Index
from mnemo.portability import (
    clone_vault,
    export_vault,
    import_vault,
    init_vault,
    sync_vault,
)
from mnemo.search import Search
from mnemo.writer import write_note


def _git_ok() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _git_ok(), reason="git not available")


def _seed(vault: Path) -> None:
    cfg = Config(vault)
    idx = Index(cfg.index_path)
    write_note(cfg, idx, type="decision", title="Karar bir", summary="s1", project="p")
    write_note(cfg, idx, type="lesson", title="Ders bir", summary="s2")
    idx.close()


def test_init_scaffolds_repo(tmp_path: Path):
    vault = tmp_path / "mem"
    res = init_vault(vault)
    assert res["git_init"] is True
    assert (vault / ".git").exists()
    assert (vault / "projects").is_dir()
    assert (vault / ".gitignore").exists()
    assert ".mnemo/" in (vault / ".gitignore").read_text(encoding="utf-8")


def test_sync_without_remote_commits(tmp_path: Path):
    vault = tmp_path / "mem"
    init_vault(vault)
    _seed(vault)
    res = sync_vault(vault)
    assert res["remote"] is False
    assert res["pushed"] is False
    # nothing left uncommitted
    out = subprocess.run(
        ["git", "status", "--porcelain"], cwd=str(vault), capture_output=True, text=True
    ).stdout.strip()
    assert out == ""


def test_export_import_roundtrip(tmp_path: Path):
    src = tmp_path / "src"
    _seed(src)
    archive = tmp_path / "backup.zip"
    exp = export_vault(src, archive)
    assert exp["files"] >= 2
    assert archive.exists()

    dest = tmp_path / "restored"
    imp = import_vault(archive, dest)
    assert imp["index"]["added"] >= 2
    idx = Index(Config(dest).index_path)
    assert Search(idx).get("does-not-exist") is None
    hits = Search(idx).search("karar")
    assert hits and hits[0]["title"] == "Karar bir"
    idx.close()


def test_export_excludes_index(tmp_path: Path):
    import zipfile

    src = tmp_path / "src"
    _seed(src)  # creates .mnemo/index.sqlite
    archive = tmp_path / "b.zip"
    export_vault(src, archive)
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
    assert not any(".mnemo" in n or n.endswith(".sqlite") for n in names)


def test_clone_local(tmp_path: Path):
    origin = tmp_path / "origin"
    init_vault(origin)
    _seed(origin)
    sync_vault(origin)  # commit notes into git history

    dest = tmp_path / "clone"
    res = clone_vault(str(origin), dest)
    assert (dest / ".git").exists()
    assert res["index"]["added"] >= 2
    idx = Index(Config(dest).index_path)
    assert Search(idx).search("ders")
    idx.close()

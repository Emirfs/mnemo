"""F5 tests: daily journaling (fast) + semantic search & dedup (needs embed)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mnemo.config import Config
from mnemo.daily import append_daily
from mnemo.index import Index
from mnemo.search import Search
from mnemo.writer import write_note


def make(tmp_path: Path, embedder=None):
    cfg = Config(tmp_path)
    return cfg, Index(cfg.index_path, embedder=embedder)


# ----------------------------------------------------------------- daily (fast)
def test_daily_creates_and_appends(tmp_path: Path):
    cfg, idx = make(tmp_path)
    r1 = append_daily(cfg, idx, "mnemo F5 baslangic")
    p = tmp_path / r1["path"]
    assert p.exists()
    r2 = append_daily(cfg, idx, "semantic arama eklendi")
    assert r1["path"] == r2["path"]  # same day -> same file
    text = p.read_text(encoding="utf-8")
    assert "mnemo F5 baslangic" in text and "semantic arama eklendi" in text
    # searchable as a daily note
    assert Search(idx).search("semantic", type="daily")
    idx.close()


# ------------------------------------------------------------- semantic (heavy)
embed = pytest.importorskip("fastembed")  # noqa: F841
pytest.importorskip("sqlite_vec")

from mnemo.embed import Embedder  # noqa: E402


def test_semantic_finds_paraphrase(tmp_path: Path):
    """Vector recall catches a paraphrase that shares no keywords with FTS."""
    cfg, idx = make(tmp_path, embedder=Embedder())
    write_note(
        cfg, idx, type="decision", project="rf",
        title="RF guncelleme sirali yapilir",
        summary="Cihazlar tek tek guncellenir, esamanli degil.",
    )
    query = "ardisik firmware yukleme yontemi"  # no shared tokens
    # FTS-only misses it...
    cfg2, fts_only = make(tmp_path / "fts", embedder=None)
    write_note(cfg2, fts_only, type="decision", project="rf",
               title="RF guncelleme sirali yapilir",
               summary="Cihazlar tek tek guncellenir, esamanli degil.")
    assert fts_only.fts_ids(query, 10) == []
    fts_only.close()
    # ...but hybrid (semantic) finds it
    hits = Search(idx).search(query, project="rf")
    assert any(h["title"].startswith("RF guncelleme") for h in hits)
    idx.close()


def test_semantic_dedup_merges_identical_body(tmp_path: Path):
    cfg, idx = make(tmp_path, embedder=Embedder())
    body = "Tamamen ayni icerik: sirali guncelleme mantigi burada anlatiliyor."
    a = write_note(cfg, idx, type="decision", project="rf",
                   title="Baslik bir", summary="x", body=body)
    assert a["action"] == "created"
    # different title (title-dedup misses) but identical body -> semantic merge
    b = write_note(cfg, idx, type="decision", project="rf",
                   title="Tamamen farkli baslik", summary="x", body=body)
    assert b["action"] == "updated"
    assert idx.count() == 1
    idx.close()

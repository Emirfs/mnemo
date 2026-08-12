"""F2 tests: write (create/update/dedup) and recall block."""

from __future__ import annotations

import json
from pathlib import Path

from mnemo.config import Config
from mnemo.index import Index
from mnemo.recall import build_recall
from mnemo.search import Search
from mnemo.writer import write_note


def make(tmp_path: Path):
    cfg = Config(tmp_path)
    return cfg, Index(cfg.index_path)


def test_write_creates_and_indexes(tmp_path: Path):
    cfg, idx = make(tmp_path)
    res = write_note(
        cfg, idx,
        type="decision",
        title="RF guncelleme sirali",
        summary="Cihazlar tek tek guncellenir.",
        body="id1 biter id2 baslar.",
        project="stm32-rf-ota",
        tags=["rf", "stm32"],
    )
    assert res["action"] == "created"
    # file written under projects/<project-slug>/
    assert (tmp_path / res["path"]).exists()
    assert res["path"].startswith("projects")
    # searchable immediately
    hits = Search(idx).search("sirali", project="stm32-rf-ota")
    assert hits and hits[0]["id"] == res["id"]
    idx.close()


def test_write_dedup_updates(tmp_path: Path):
    cfg, idx = make(tmp_path)
    first = write_note(
        cfg, idx, type="decision", title="UID kimligi",
        summary="ilk", project="p", tags=["a"],
    )
    assert first["action"] == "created"
    assert idx.count() == 1
    # same type/project + equivalent title (case/space) -> update, not duplicate
    second = write_note(
        cfg, idx, type="decision", title="  uid   KIMLIGI ",
        summary="guncel", project="p", tags=["b"],
    )
    assert second["action"] == "updated"
    assert second["id"] == first["id"]
    assert idx.count() == 1
    note = Search(idx).get(first["id"])
    assert note["summary"] == "guncel"
    assert set(json.loads(note["tags"])) == {"a", "b"}  # tags merged
    idx.close()


def test_write_different_title_creates_second(tmp_path: Path):
    cfg, idx = make(tmp_path)
    write_note(cfg, idx, type="lesson", title="Hata A", summary="s")
    write_note(cfg, idx, type="lesson", title="Hata B", summary="s")
    assert idx.count() == 2
    idx.close()


def test_recall_block(tmp_path: Path):
    cfg, idx = make(tmp_path)
    write_note(
        cfg, idx, type="project", title="STM32 RF OTA — MOC", project="stm32-rf-ota",
        summary="RF OTA sistemi haritasi.", body="Bilesenler: sender, uploader, alicilar.",
    )
    write_note(
        cfg, idx, type="decision", title="Sirali guncelleme", project="stm32-rf-ota",
        summary="Tek tek guncelle.",
    )
    write_note(
        cfg, idx, type="lesson", title="RF cakismasi", project="stm32-rf-ota",
        summary="Esamanli TX carpisir; backoff sart.",
    )
    block = build_recall(idx, "stm32-rf-ota")
    assert "mnemo recall" in block
    assert "Map: STM32 RF OTA" in block
    assert "Sirali guncelleme" in block
    assert "RF cakismasi" in block
    assert "mnemo get" in block  # tells the model how to expand
    idx.close()


def test_recall_empty_when_no_notes(tmp_path: Path):
    cfg, idx = make(tmp_path)
    assert build_recall(idx, "nothing") == ""
    idx.close()


def test_recall_uses_latest_project_map(tmp_path: Path):
    cfg, idx = make(tmp_path)
    write_note(
        cfg, idx, type="project", title="Old map", project="p",
        summary="Old state.", id="20260101-old",
    )
    write_note(
        cfg, idx, type="project", title="Current map", project="p",
        summary="Current state.", id="20260102-current",
    )
    idx.con.execute(
        "UPDATE notes SET created = '2026-01-01', updated = '2026-01-01' WHERE id = ?",
        ("20260101-old",),
    )
    idx.con.execute(
        "UPDATE notes SET created = '2026-01-02', updated = '2026-01-02' WHERE id = ?",
        ("20260102-current",),
    )
    idx.con.commit()

    block = build_recall(idx, "p")

    assert "Map: Current map" in block
    assert "Map: Old map" not in block
    idx.close()

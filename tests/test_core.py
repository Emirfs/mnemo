"""F1 core tests: parse, incremental reindex, FTS5 search, filters, deletion."""

from __future__ import annotations

import os
import time
from pathlib import Path

from mnemo.config import Config
from mnemo.index import Index
from mnemo.note import Note
from mnemo.search import Search


def write_note(vault: Path, rel: str, frontmatter_block: str, body: str) -> Path:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{frontmatter_block.strip()}\n---\n{body}\n", encoding="utf-8")
    return p


def seed_vault(vault: Path) -> None:
    write_note(
        vault,
        "projects/rf/uid-sequential.md",
        """
id: rf-uid-sequential
type: decision
title: RF guncellemesi sirali yapilir
project: stm32-rf-ota
tags: [rf, protocol, stm32]
summary: Cihazlar tek tek guncellenir; esamanli degil, sistem kilitlenmesini onler.
""",
        "Sirali guncelleme: id1 biter, id2 baslar. Tum cihazlar ayni anda bootloader'a dusmez.",
    )
    write_note(
        vault,
        "projects/rf/uid-identity.md",
        """
id: rf-uid-identity
type: decision
title: Cihaz kimligi 96-bit STM32 UID
project: stm32-rf-ota
tags: [rf, uid, stm32]
summary: Kimlik = STM32 fabrika UID; hash veya kisaltma yok, cakisma riski olmasin.
""",
        "HAL_GetUIDw0/1/2 ile 12 byte okunur. Header'a girmez, sadece discovery payload.",
    )
    write_note(
        vault,
        "daily/2026-06-23.md",
        """
type: daily
title: 2026-06-23
tags: [journal]
summary: Hafiza sistemi tasarimi; mnemo F1 cekirdek.
""",
        "Bugun mnemo mimarisi kilitlendi: vault=kaynak, push>pull, GitHub portability.",
    )


def make(tmp_path: Path) -> tuple[Config, Index]:
    cfg = Config(tmp_path)
    return cfg, Index(cfg.index_path)


def test_parse_note(tmp_path: Path):
    p = write_note(
        tmp_path,
        "n.md",
        "id: x1\ntype: lesson\ntitle: T\ntags: [a, b]\nsummary: S",
        "body here",
    )
    n = Note.from_file(p)
    assert n.id == "x1"
    assert n.type == "lesson"
    assert n.title == "T"
    assert n.tags == ["a", "b"]
    assert n.summary == "S"
    assert "body here" in n.body


def test_reindex_and_count(tmp_path: Path):
    cfg, idx = make(tmp_path)
    seed_vault(tmp_path)
    stats = idx.reindex(cfg.vault)
    assert stats["added"] == 3
    assert idx.count() == 3
    idx.close()


def test_incremental_skip(tmp_path: Path):
    cfg, idx = make(tmp_path)
    seed_vault(tmp_path)
    idx.reindex(cfg.vault)
    stats = idx.reindex(cfg.vault)  # nothing changed
    assert stats["added"] == 0 and stats["updated"] == 0
    assert stats["skipped"] == 3
    idx.close()


def test_update_detected(tmp_path: Path):
    cfg, idx = make(tmp_path)
    seed_vault(tmp_path)
    idx.reindex(cfg.vault)
    target = tmp_path / "daily" / "2026-06-23.md"
    time.sleep(0.01)
    os.utime(target, None)  # bump mtime
    target.write_text(
        target.read_text(encoding="utf-8") + "\nEk satir.\n", encoding="utf-8"
    )
    stats = idx.reindex(cfg.vault)
    assert stats["updated"] == 1
    assert stats["skipped"] == 2
    idx.close()


def test_search_finds_note(tmp_path: Path):
    cfg, idx = make(tmp_path)
    seed_vault(tmp_path)
    idx.reindex(cfg.vault)
    res = Search(idx).search("sirali guncelleme")
    assert res, "expected a match"
    assert res[0]["id"] == "rf-uid-sequential"
    # summaries returned, bodies not
    assert "summary" in res[0] and "body" not in res[0]
    idx.close()


def test_search_type_filter(tmp_path: Path):
    cfg, idx = make(tmp_path)
    seed_vault(tmp_path)
    idx.reindex(cfg.vault)
    res = Search(idx).search("mnemo", type="decision")
    assert all(r["type"] == "decision" for r in res)
    res2 = Search(idx).search("hafiza", type="daily")
    assert any(r["type"] == "daily" for r in res2)
    idx.close()


def test_search_project_and_tags(tmp_path: Path):
    cfg, idx = make(tmp_path)
    seed_vault(tmp_path)
    idx.reindex(cfg.vault)
    res = Search(idx).search("stm32", project="stm32-rf-ota")
    assert res and all(r["project"] == "stm32-rf-ota" for r in res)
    res_tags = Search(idx).search("uid", tags=["uid"])
    assert res_tags and all("uid" in r["tags"] for r in res_tags)
    idx.close()


def test_search_filters_before_candidate_limit(tmp_path: Path):
    cfg, idx = make(tmp_path)
    for i in range(15):
        write_note(
            tmp_path,
            f"projects/noisy/n-{i}.md",
            f"""
id: noisy-{i}
type: decision
title: Exact anchor {i}
project: noisy
summary: exact anchor repeated repeated repeated {i}
""",
            "exact anchor repeated repeated repeated",
        )
    write_note(
        tmp_path,
        "projects/target/wanted.md",
        """
id: wanted
type: lesson
title: Anchor lesson
project: target
tags: [wanted]
summary: anchor
""",
        "anchor",
    )
    idx.reindex(cfg.vault)

    hits = Search(idx).search(
        "anchor", type="lesson", project="target", tags=["wanted"], k=1
    )

    assert [hit["id"] for hit in hits] == ["wanted"]
    idx.close()


def test_long_query_drops_single_generic_term_match(tmp_path: Path):
    cfg, idx = make(tmp_path)
    write_note(
        tmp_path,
        "lessons/relevant.md",
        """
id: relevant
type: lesson
title: SI4432 OTA transfer stall
project: rf
summary: SI4432 OTA packets stall when RX loses synchronization.
""",
        "Radio packet transfer stops during the update.",
    )
    write_note(
        tmp_path,
        "lessons/weak.md",
        """
id: weak
type: lesson
title: General OTA release checklist
project: rf
summary: Record the firmware version before release.
""",
        "Archive build artifacts after publishing.",
    )
    idx.reindex(cfg.vault)

    hits = Search(idx).search(
        "si4432 ota packet transfer neden takiliyor", type="lesson", project="rf"
    )

    assert [hit["id"] for hit in hits] == ["relevant"]
    idx.close()


def test_deletion_removed(tmp_path: Path):
    cfg, idx = make(tmp_path)
    seed_vault(tmp_path)
    idx.reindex(cfg.vault)
    (tmp_path / "daily" / "2026-06-23.md").unlink()
    stats = idx.reindex(cfg.vault)
    assert stats["removed"] == 1
    assert idx.count() == 2
    assert Search(idx).get("2026-06-23") is None
    idx.close()


def test_get_returns_full_body(tmp_path: Path):
    cfg, idx = make(tmp_path)
    seed_vault(tmp_path)
    idx.reindex(cfg.vault)
    note = Search(idx).get("rf-uid-identity")
    assert note is not None
    assert "HAL_GetUIDw0" in note["body"]
    idx.close()

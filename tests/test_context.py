from __future__ import annotations

import json
from pathlib import Path

from mnemo.cli import main
from mnemo.config import Config
from mnemo.context import build_context
from mnemo.embed import Embedder
from mnemo.index import Index


def write_note(vault: Path, rel: str, frontmatter_block: str, body: str) -> Path:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{frontmatter_block.strip()}\n---\n{body}\n", encoding="utf-8")
    return p


def seed_context_vault(vault: Path) -> None:
    write_note(
        vault,
        "projects/proj-a/map.md",
        """
id: proj-a-moc
type: project
title: Project A Map
project: proj-a
summary: Compact project map summary with anchor.
""",
        "Full MOC body must not appear in context output.",
    )
    write_note(
        vault,
        "projects/proj-a/decision.md",
        """
id: a-decision
type: decision
title: Keep CLI local
project: proj-a
summary: anchor decision summary for local-only context packs.
""",
        "Decision body is intentionally longer and private.",
    )
    write_note(
        vault,
        "projects/proj-a/reference.md",
        """
id: a-reference
type: reference
title: Broad Reference
project: proj-a
summary: anchor reference summary with reusable implementation detail.
""",
        "Reference body must not be emitted.",
    )
    write_note(
        vault,
        "projects/proj-a/note.md",
        """
id: a-note
type: note
title: Working Note
project: proj-a
summary: anchor note summary for active work.
""",
        "Note body must not be emitted.",
    )
    write_note(
        vault,
        "projects/proj-b/decision.md",
        """
id: b-decision
type: decision
title: Other Project Decision
project: proj-b
summary: anchor decision summary from another project.
""",
        "Other project body.",
    )


def make_index(vault: Path) -> Index:
    cfg = Config(vault)
    idx = Index(cfg.index_path)
    idx.reindex(cfg.vault)
    return idx


def test_context_cli_detects_project_and_scopes_results(
    tmp_path: Path, capsys, monkeypatch
):
    vault = tmp_path / "vault"
    work = tmp_path / "work"
    vault.mkdir()
    work.mkdir()
    (work / ".mnemo-project").write_text("proj-a\n", encoding="utf-8")
    seed_context_vault(vault)
    monkeypatch.setattr(Embedder, "is_available", staticmethod(lambda: False))

    assert main(
        [
            "--vault",
            str(vault),
            "context",
            "anchor",
            "--project-dir",
            str(work),
            "--reindex",
            "--json",
        ]
    ) == 0

    pack = json.loads(capsys.readouterr().out)
    ids = [item["id"] for item in pack["items"]]
    assert pack["project"] == "proj-a"
    assert "proj-a-moc" in ids
    assert "b-decision" not in ids


def test_build_context_includes_reference_result(tmp_path: Path):
    seed_context_vault(tmp_path)
    idx = make_index(tmp_path)
    try:
        pack = build_context(idx, "reference anchor", project="proj-a", k=5)
    finally:
        idx.close()

    assert any(
        item["type"] == "reference" and item["id"] == "a-reference"
        for item in pack["items"]
    )
    assert "Reference body" not in pack["markdown"]


def test_build_context_puts_project_moc_first_and_uses_summary(tmp_path: Path):
    seed_context_vault(tmp_path)
    idx = make_index(tmp_path)
    try:
        pack = build_context(idx, "anchor", project="proj-a", k=5)
    finally:
        idx.close()

    assert pack["items"][0]["id"] == "proj-a-moc"
    assert "Compact project map summary" in pack["markdown"]
    assert "Full MOC body" not in pack["markdown"]


def test_context_budget_drops_extra_items(tmp_path: Path):
    seed_context_vault(tmp_path)
    idx = make_index(tmp_path)
    try:
        full = build_context(idx, "anchor", project="proj-a", k=5, budget=2400)
        tight = build_context(idx, "anchor", project="proj-a", k=5, budget=260)
    finally:
        idx.close()

    assert len(tight["items"]) < len(full["items"])
    assert len(tight["markdown"]) <= 260
    assert "Hint: summaries only" in tight["markdown"]


def test_context_pack_is_json_friendly_summary_shape(tmp_path: Path):
    seed_context_vault(tmp_path)
    idx = make_index(tmp_path)
    try:
        pack = build_context(idx, "anchor", project="proj-a", k=2)
    finally:
        idx.close()

    json.dumps(pack, ensure_ascii=False)
    assert set(pack) == {"project", "query", "items", "markdown"}
    assert pack["items"]
    assert set(pack["items"][0]) == {
        "id", "type", "title", "summary", "path", "verification", "sources", "score"
    }
    assert "body" not in pack["items"][0]

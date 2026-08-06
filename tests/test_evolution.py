"""Tests for the supermemory-derived evolution: bench harness, recency
weighting, profile injection, temporal supersession, ephemeral expiry."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from mnemo.bench import evaluate, load_cases
from mnemo.config import Config
from mnemo.context import build_context
from mnemo.index import Index
from mnemo.recall import build_recall
from mnemo.search import Search
from mnemo.writer import verify_note, write_note


def write_md(vault: Path, rel: str, fm: str, body: str = "body") -> Path:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{fm.strip()}\n---\n{body}\n", encoding="utf-8")
    return p


def make_index(vault: Path) -> Index:
    cfg = Config(vault)
    idx = Index(cfg.index_path)
    idx.reindex(cfg.vault)
    return idx


def _days_ago(n: int) -> str:
    return (_dt.date.today() - _dt.timedelta(days=n)).isoformat()


# --------------------------------------------------------------------- bench
def test_bench_evaluate_reports_hits(tmp_path: Path):
    vault = tmp_path / "v"
    write_md(
        vault, "projects/proj-a/d.md",
        "id: a-dec\ntype: decision\ntitle: Keep CLI local\nproject: proj-a\n"
        "summary: anchor decision summary",
    )
    idx = make_index(vault)
    try:
        report = evaluate(
            idx,
            [{"query": "anchor decision", "project": "proj-a", "expected": ["a-dec"]}],
        )
    finally:
        idx.close()

    assert report["summary"]["cases"] == 1
    assert report["summary"]["hit_rate"] == 1.0
    assert report["results"][0]["hit"] is True


def test_load_cases_supports_json_and_jsonl(tmp_path: Path):
    j = tmp_path / "c.json"
    j.write_text('[{"query": "x", "expected": ["a"]}]', encoding="utf-8")
    jl = tmp_path / "c.jsonl"
    jl.write_text('{"query": "x", "expected": ["a"]}\n', encoding="utf-8")
    assert load_cases(j) == load_cases(jl)


# ------------------------------------------------------------------ recency
def test_recency_breaks_ties_toward_recent(tmp_path: Path):
    vault = tmp_path / "v"
    write_md(
        vault, "projects/proj-a/old.md",
        f"id: old-dec\ntype: decision\ntitle: Old choice\nproject: proj-a\n"
        f"summary: shared anchor relevance\ncreated: {_days_ago(900)}\n"
        f"updated: {_days_ago(900)}",
    )
    write_md(
        vault, "projects/proj-a/new.md",
        f"id: new-dec\ntype: decision\ntitle: New choice\nproject: proj-a\n"
        f"summary: shared anchor relevance\ncreated: {_days_ago(1)}\n"
        f"updated: {_days_ago(1)}",
    )
    idx = make_index(vault)
    try:
        pack = build_context(idx, "shared anchor relevance", project="proj-a", k=5)
    finally:
        idx.close()

    ids = [i["id"] for i in pack["items"]]
    assert ids.index("new-dec") < ids.index("old-dec")


# ------------------------------------------------------------------ profile
def test_profile_is_injected_into_context_and_recall(tmp_path: Path):
    vault = tmp_path / "v"
    write_md(
        vault, "profile/me.md",
        "id: prof-me\ntype: profile\ntitle: Prefers caveman replies\n"
        "summary: terse fragments, no filler",
    )
    write_md(
        vault, "projects/proj-a/d.md",
        "id: a-dec\ntype: decision\ntitle: Keep CLI local\nproject: proj-a\n"
        "summary: anchor decision summary",
    )
    idx = make_index(vault)
    try:
        pack = build_context(idx, "anchor", project="proj-a", k=5)
        block = build_recall(idx, "proj-a")
    finally:
        idx.close()

    ids = [i["id"] for i in pack["items"]]
    assert "prof-me" in ids
    # profile (pinned) precedes query-matched notes
    assert ids.index("prof-me") < ids.index("a-dec")
    assert "Profile / static facts" in block
    assert "prof-me" in block


# ------------------------------------------------------------- supersession
def test_write_supersedes_hides_old_note(tmp_path: Path):
    vault = tmp_path / "v"
    vault.mkdir()
    cfg = Config(vault)
    idx = Index(cfg.index_path)
    try:
        write_note(
            cfg, idx, type="decision", title="Old way",
            summary="anchor approach", project="proj-a", id="old-dec",
        )
        res = write_note(
            cfg, idx, type="decision", title="New way",
            summary="anchor approach", project="proj-a", supersedes=["old-dec"],
        )
        assert "old-dec" in res["superseded"]

        old = Search(idx).get("old-dec")
        assert old["status"] == "superseded"

        pack = build_context(idx, "anchor approach", project="proj-a", k=5)
        ids = [i["id"] for i in pack["items"]]
        assert "old-dec" not in ids
        assert res["id"] in ids

        # superseded note also stays out of plain search
        assert all(r["id"] != "old-dec" for r in Search(idx).search("anchor", k=10))
    finally:
        idx.close()


# ----------------------------------------------------------------- expiry
def test_ephemeral_note_expires_from_context(tmp_path: Path):
    vault = tmp_path / "v"
    write_md(
        vault, "notes/old.md",
        f"id: old-note\ntype: note\ntitle: Stale scratch\nproject: proj-a\n"
        f"summary: anchor scratch detail\ncreated: {_days_ago(200)}\n"
        f"updated: {_days_ago(200)}",
    )
    write_md(
        vault, "notes/fresh.md",
        f"id: fresh-note\ntype: note\ntitle: Fresh scratch\nproject: proj-a\n"
        f"summary: anchor scratch detail\ncreated: {_days_ago(2)}\n"
        f"updated: {_days_ago(2)}",
    )
    idx = make_index(vault)
    try:
        pack = build_context(idx, "anchor scratch detail", project="proj-a", k=5)
    finally:
        idx.close()

    ids = [i["id"] for i in pack["items"]]
    assert "fresh-note" in ids
    assert "old-note" not in ids


def test_draft_requires_evidence_before_retrieval(tmp_path: Path):
    vault = tmp_path / "v"
    vault.mkdir()
    cfg = Config(vault)
    idx = Index(cfg.index_path)
    try:
        draft = write_note(
            cfg,
            idx,
            type="lesson",
            title="AI inferred lesson",
            summary="anchor candidate",
            project="proj-a",
            status="draft",
            verification="inferred",
        )
        assert Search(idx).search("anchor", project="proj-a") == []

        verified = verify_note(
            cfg, idx, draft["id"], ["commit:abc123", "test:pytest"]
        )

        assert verified["status"] == "active"
        assert verified["verification"] == "verified"
        hits = Search(idx).search("anchor", project="proj-a")
        assert [hit["id"] for hit in hits] == [draft["id"]]
        assert hits[0]["sources"] == ["commit:abc123", "test:pytest"]
    finally:
        idx.close()


def test_verified_write_requires_source(tmp_path: Path):
    cfg = Config(tmp_path)
    idx = Index(cfg.index_path)
    try:
        try:
            write_note(
                cfg,
                idx,
                type="decision",
                title="Unsupported claim",
                verification="verified",
            )
        except ValueError as exc:
            assert "require at least one source" in str(exc)
        else:
            raise AssertionError("verified write accepted without evidence")
    finally:
        idx.close()


def test_draft_defers_supersession_until_verified(tmp_path: Path):
    cfg = Config(tmp_path)
    idx = Index(cfg.index_path)
    try:
        old = write_note(
            cfg, idx, type="decision", title="Old fact",
            summary="active anchor", id="old-fact",
        )
        draft = write_note(
            cfg, idx, type="decision", title="Replacement fact",
            summary="replacement anchor", status="draft",
            verification="inferred", supersedes=[old["id"]],
        )

        assert Search(idx).get(old["id"])["status"] == "active"
        assert draft["pending_supersedes"] == [old["id"]]

        result = verify_note(cfg, idx, draft["id"], ["test:confirmed"])

        assert result["superseded"] == [old["id"]]
        assert Search(idx).get(old["id"])["status"] == "superseded"
    finally:
        idx.close()


def test_draft_cannot_overwrite_active_note_during_dedup(tmp_path: Path):
    cfg = Config(tmp_path)
    idx = Index(cfg.index_path)
    try:
        active = write_note(
            cfg, idx, type="decision", title="Stable decision",
            summary="verified behavior", id="stable",
        )
        draft = write_note(
            cfg, idx, type="decision", title="Stable decision",
            summary="AI proposes different behavior", status="draft",
            verification="inferred",
        )

        assert draft["id"] != active["id"]
        assert Search(idx).get(active["id"])["status"] == "active"
        assert Search(idx).get(active["id"])["summary"] == "verified behavior"
        assert Search(idx).get(draft["id"])["status"] == "draft"
    finally:
        idx.close()

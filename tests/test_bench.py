from __future__ import annotations

from pathlib import Path

from mnemo.bench import evaluate
from mnemo.config import Config
from mnemo.index import Index


def _write_note(vault: Path, note_id: str, project: str, title: str, summary: str) -> None:
    path = vault / "projects" / project / f"{note_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""---
id: {note_id}
type: decision
title: {title}
project: {project}
summary: {summary}
---
{summary}
""",
        encoding="utf-8",
    )


def test_evaluate_reports_retrieval_baseline(tmp_path: Path):
    _write_note(
        tmp_path,
        "sequential-update",
        "rf",
        "RF updates are sequential",
        "Update one device at a time to avoid radio collisions.",
    )
    _write_note(
        tmp_path,
        "short-tokens",
        "auth",
        "Access tokens expire quickly",
        "Use short-lived access tokens with refresh tokens.",
    )
    cfg = Config(tmp_path)
    idx = Index(cfg.index_path)
    idx.reindex(cfg.vault)
    try:
        report = evaluate(
            idx,
            [
                {
                    "query": "sequential radio update",
                    "project": "rf",
                    "expected": ["sequential-update"],
                },
                {
                    "query": "short lived access token",
                    "project": "auth",
                    "expected": ["short-tokens"],
                },
            ],
        )
    finally:
        idx.close()

    assert report["summary"] == {
        "cases": 2,
        "hit_rate": 1.0,
        "mrr": 1.0,
        "mean_recall": 1.0,
    }

"""Retrieval eval harness — measure recall quality before/after changes.

Storage was never the hard part; retrieval is. So we measure it. A *cases*
file lists realistic queries with the note ids that *should* surface; the
harness runs each through :func:`mnemo.context.build_context` and reports
hit-rate, MRR, and mean recall@k. Run it before a change to get a baseline,
then after to prove the change helped (and didn't regress).

Cases file is JSON (a list) or JSONL (one object per line). Each case::

    {"query": "rf update order", "project": "stm32-rf-ota",
     "expected": ["20260623-rf-uid-sequential"], "k": 5}

``project`` and ``k`` are optional (``k`` falls back to the run default).
"""

from __future__ import annotations

import json
from pathlib import Path

from .context import build_context


def load_cases(path: str | Path) -> list[dict]:
    text = Path(path).read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text[0] == "[":
        return json.loads(text)
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _eval_case(index, case: dict, k: int) -> dict:
    expected = set(case.get("expected") or [])
    ck = int(case.get("k", k))
    pack = build_context(index, case["query"], project=case.get("project"), k=ck)
    got = [item["id"] for item in pack["items"]]
    ranks = [i for i, gid in enumerate(got) if gid in expected]
    recall = (len(expected & set(got)) / len(expected)) if expected else 0.0
    rr = (1.0 / (ranks[0] + 1)) if ranks else 0.0
    return {
        "query": case["query"],
        "project": case.get("project"),
        "expected": sorted(expected),
        "got": got,
        "hit": bool(ranks),
        "recall": round(recall, 3),
        "rr": round(rr, 3),
    }


def evaluate(index, cases: list[dict], k: int = 5) -> dict:
    """Run every case; return per-case results plus an aggregate summary."""
    results = [_eval_case(index, c, k) for c in cases]
    n = len(results) or 1
    summary = {
        "cases": len(results),
        "hit_rate": round(sum(r["hit"] for r in results) / n, 3),
        "mrr": round(sum(r["rr"] for r in results) / n, 3),
        "mean_recall": round(sum(r["recall"] for r in results) / n, 3),
    }
    return {"summary": summary, "results": results}


def format_report(report: dict) -> str:
    s = report["summary"]
    lines = [
        f"cases {s['cases']} · hit-rate {s['hit_rate']} · "
        f"MRR {s['mrr']} · mean recall {s['mean_recall']}",
        "",
    ]
    for r in report["results"]:
        mark = "✓" if r["hit"] else "✗"
        lines.append(f"{mark} {r['query']}  (recall {r['recall']}, rr {r['rr']})")
        if not r["hit"]:
            lines.append(f"    expected {r['expected']}")
            lines.append(f"    got      {r['got']}")
    return "\n".join(lines)

"""Build compact query context packs over indexed mnemo summaries.

Ranking blends relevance with **recency** (a recent note beats an equally
relevant stale one) and the pack always leads with durable context: the
project MOC and any *profile* notes (static facts about the user/stack).
Ephemeral notes past their shelf life are dropped. All of this is pure
retrieval — no LLM on the hot path.
"""

from __future__ import annotations

import datetime as _dt
import json

from .search import Search

_TARGET_TYPES = ("decision", "lesson", "reference", "note", "project")

# Recency decay: a note's relevance score is scaled by a factor in
# [_RECENCY_FLOOR, 1.0] that halves every _HALF_LIFE_DAYS. Relevance still
# dominates; recency only breaks ties and gently demotes stale notes.
_HALF_LIFE_DAYS = 120.0
_RECENCY_FLOOR = 0.5

# Ephemeral types get a hard shelf life: past this age they leave the context
# pack entirely (they still live in the vault and in `search`). 0 disables.
_EPHEMERAL_TYPES = {"note", "daily"}
_EXPIRE_DAYS = 90

# How many static-fact profile notes to surface, at most.
_MAX_PROFILES = 3


def _age_days(item: dict, *, today: _dt.date | None = None) -> float | None:
    raw = item.get("updated") or item.get("created")
    if not raw:
        return None
    try:
        when = _dt.date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None
    today = today or _dt.date.today()
    return max((today - when).days, 0)


def _recency_factor(item: dict, *, today: _dt.date | None = None) -> float:
    age = _age_days(item, today=today)
    if age is None:
        return 1.0  # undated notes are not penalised
    decay = 0.5 ** (age / _HALF_LIFE_DAYS)
    return _RECENCY_FLOOR + (1.0 - _RECENCY_FLOOR) * decay


def _expired(item: dict, *, today: _dt.date | None = None) -> bool:
    if _EXPIRE_DAYS <= 0 or item["type"] not in _EPHEMERAL_TYPES:
        return False
    age = _age_days(item, today=today)
    return age is not None and age > _EXPIRE_DAYS


def _item(row: dict, *, score: float | None = None) -> dict:
    return {
        "id": row["id"],
        "type": row["type"],
        "title": row["title"],
        "summary": row["summary"] or "",
        "path": row["path"],
        "created": row.get("created"),
        "updated": row.get("updated"),
        "verification": row.get("verification") or "unknown",
        "sources": row.get("sources") or [],
        "score": row.get("score") if score is None else score,
    }


def _public(item: dict) -> dict:
    """The JSON-facing shape: drop the internal date fields used for ranking."""
    return {
        k: item[k]
        for k in (
            "id", "type", "title", "summary", "path", "verification", "sources", "score"
        )
    }


def _project_moc(index, project: str | None) -> dict | None:
    if not project:
        return None
    row = index.con.execute(
        "SELECT id, type, title, summary, path, created, updated, "
        "verification, sources FROM notes "
        "WHERE type = 'project' AND project = ? "
        "AND COALESCE(status,'active') = 'active' "
        "ORDER BY COALESCE(updated, created, '') DESC, id DESC LIMIT 1",
        (project,),
    ).fetchone()
    if not row:
        return None
    data = dict(row)
    data["sources"] = json.loads(data["sources"] or "[]")
    return _item(data, score=1.0)


def _profiles(index, project: str | None) -> list[dict]:
    """Static facts about the user/stack — always surfaced, query-independent.

    Global profiles (no project) plus any scoped to the current project.
    """
    rows = index.con.execute(
        "SELECT id, type, title, summary, path, created, updated, "
        "verification, sources FROM notes "
        "WHERE type = 'profile' AND COALESCE(status,'active') = 'active' "
        "AND (project IS NULL OR project = ?) "
        "ORDER BY COALESCE(updated, created, '') DESC, id DESC LIMIT ?",
        (project, _MAX_PROFILES),
    ).fetchall()
    items = []
    for row in rows:
        data = dict(row)
        data["sources"] = json.loads(data["sources"] or "[]")
        items.append(_item(data, score=1.0))
    return items


def _render_item(item: dict) -> str:
    score = item["score"]
    score_text = "" if score is None else f", score {score}"
    summary = item["summary"] or "(no summary)"
    trust = item["verification"]
    source_text = ""
    if item["sources"]:
        source_text = f"\n  Sources: {', '.join(item['sources'])}"
    return (
        f"- [{item['id']}] {item['title']} "
        f"({item['type']}, verification {trust}{score_text})\n"
        f"  {summary}\n"
        f"  {item['path']}{source_text}"
    )


def _render_markdown(
    *, project: str | None, query: str, items: list[dict], budget: int
) -> tuple[str, list[dict]]:
    header = [
        f"## mnemo context — project: {project or '(unknown)'}",
        f"Query: {query}",
        "Hint: summaries only; expand details with `mnemo get <id>`.",
        "Trust: unknown/reported/inferred memories are leads, not verified facts.",
    ]
    kept: list[dict] = []
    lines = header[:]

    for item in items:
        candidate_lines = [*lines, "", _render_item(item)]
        candidate = "\n".join(candidate_lines).strip()
        if budget > 0 and len(candidate) > budget:
            break
        lines = candidate_lines
        kept.append(item)

    if not kept:
        lines = [*header, "", "(no matches)"]

    return "\n".join(lines).strip(), kept


def build_context(
    index,
    query: str,
    project: str | None = None,
    k: int = 5,
    budget: int = 2400,
) -> dict:
    """Return a compact context pack for ``query`` using summaries only."""
    search = Search(index)
    today = _dt.date.today()
    seen: set[str] = set()
    pinned: list[dict] = []  # MOC + profiles, always first, in order

    moc = _project_moc(index, project)
    if moc:
        pinned.append(moc)
        seen.add(moc["id"])
    for prof in _profiles(index, project):
        if prof["id"] not in seen:
            pinned.append(prof)
            seen.add(prof["id"])

    limit = max(int(k), 0)
    hits: list[tuple[float, int, dict]] = []
    for type_order, type_ in enumerate(_TARGET_TYPES):
        for row in search.search(query, type=type_, project=project, k=limit):
            if row["id"] in seen:
                continue
            item = _item(row)
            if _expired(item, today=today):
                continue
            seen.add(row["id"])
            combined = (item["score"] or 0) * _recency_factor(item, today=today)
            hits.append((combined, type_order, item))

    hits.sort(key=lambda h: (-h[0], h[1], h[2]["id"]))
    items = pinned + [item for _, _, item in hits[:limit]]

    markdown, kept = _render_markdown(
        project=project, query=query, items=items, budget=max(int(budget), 0)
    )
    return {
        "project": project,
        "query": query,
        "items": [_public(i) for i in kept],
        "markdown": markdown,
    }

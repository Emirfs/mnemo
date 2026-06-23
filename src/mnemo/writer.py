"""Write notes into the vault with simple dedup (search-before-write).

F2 dedup is title-based: if a note of the same type/project with an equivalent
normalized title already exists, it is updated in place rather than duplicated.
Semantic (embedding) dedup lands in F5.
"""

from __future__ import annotations

import datetime as _dt
import math
from pathlib import Path

import frontmatter

from .note import slugify
from .search import Search


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0

_FOLDER = {
    "decision": "projects",
    "project": "projects",
    "lesson": "lessons",
    "daily": "daily",
    "reference": "reference",
    "note": "notes",
}


def _norm_title(t: str) -> str:
    return " ".join(t.lower().split())


def _target_path(vault: Path, type_: str, project: str | None, fid: str) -> Path:
    base = _FOLDER.get(type_, "notes")
    if type_ in ("decision", "project") and project:
        folder = vault / base / slugify(project)
    else:
        folder = vault / base
    return folder / f"{fid}.md"


def write_note(
    cfg,
    index,
    *,
    type: str,
    title: str,
    summary: str = "",
    body: str = "",
    project: str | None = None,
    tags: list[str] | None = None,
    links: list[str] | None = None,
    id: str | None = None,
) -> dict:
    vault = cfg.vault
    tags = tags or []
    links = links or []
    today = _dt.date.today().isoformat()

    # --- dedup: same type/project + equivalent title -> update in place ---
    existing = None
    for r in Search(index).search(f"{title} {summary}", type=type, project=project, k=5):
        if _norm_title(r["title"]) == _norm_title(title):
            existing = r
            break

    # semantic dedup: near-identical *content* (summary+body) of the same
    # type/project, regardless of title. High cosine threshold avoids false
    # merges (paraphrases of distinct ideas are NOT merged).
    if existing is None and getattr(index, "vectors", False):
        emb = index.embedder
        new_vec = emb.encode_one(f"{summary}\n{body}".strip() or title)
        for nid, _dist in index.vec_search(f"{title} {summary} {body}", 5) or []:
            cand = Search(index).get(nid)
            if not cand or cand["type"] != type or cand["project"] != project:
                continue
            cand_vec = emb.encode_one(f"{cand['summary']}\n{cand['body']}".strip() or cand["title"])
            if _cosine(new_vec, cand_vec) >= 0.95:
                existing = {"path": cand["path"], "title": cand["title"]}
                break

    if existing:
        path = vault / existing["path"]
        post = frontmatter.load(str(path))
        meta = post.metadata
        meta["title"] = title
        if summary:
            meta["summary"] = summary
        if tags:
            meta["tags"] = sorted(set(meta.get("tags", []) or []) | set(tags))
        if links:
            meta["links"] = sorted(set(meta.get("links", []) or []) | set(links))
        meta["updated"] = today
        if body:
            post.content = body
        fid = str(meta.get("id") or path.stem)
        action = "updated"
    else:
        fid = id or f"{_dt.date.today():%Y%m%d}-{slugify(title)}"
        path = _target_path(vault, type, project, fid)
        n = 2
        while path.exists():
            path = path.with_name(f"{fid}-{n}.md")
            n += 1
        fid = path.stem
        meta = {"id": fid, "type": type, "title": title, "created": today, "updated": today}
        if summary:
            meta["summary"] = summary
        if project:
            meta["project"] = project
        if tags:
            meta["tags"] = tags
        if links:
            meta["links"] = links
        post = frontmatter.Post(body or "", **meta)
        action = "created"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    index.reindex(vault)
    return {"action": action, "id": fid, "path": str(path.relative_to(vault))}

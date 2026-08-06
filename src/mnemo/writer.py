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

from .note import NOTE_STATES, NOTE_VERIFICATIONS, slugify
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
    "profile": "profile",
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


def _mark_superseded(vault: Path, index, old_ids: list[str], new_id: str, today: str) -> list[str]:
    """Flag each old note as superseded by ``new_id`` (kept on disk, hidden
    from retrieval). Returns the ids actually updated."""
    done: list[str] = []
    for oid in old_ids:
        row = Search(index).get(oid)
        if not row or oid == new_id:
            continue
        path = vault / row["path"]
        post = frontmatter.load(str(path))
        meta = post.metadata
        meta["status"] = "superseded"
        prev = meta.get("superseded_by") or []
        if isinstance(prev, str):
            prev = [prev]
        meta["superseded_by"] = sorted(set(prev) | {new_id})
        meta["updated"] = today
        path.write_text(frontmatter.dumps(post), encoding="utf-8")
        done.append(oid)
    return done


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
    supersedes: list[str] | None = None,
    status: str = "active",
    verification: str = "unknown",
    sources: list[str] | None = None,
    id: str | None = None,
) -> dict:
    vault = cfg.vault
    tags = tags or []
    links = links or []
    supersedes = supersedes or []
    sources = sources or []
    if status not in NOTE_STATES:
        raise ValueError(f"invalid note status: {status}")
    if verification not in NOTE_VERIFICATIONS:
        raise ValueError(f"invalid verification: {verification}")
    if verification == "verified" and not sources:
        raise ValueError("verified notes require at least one source")
    if verification == "verified" and status != "active":
        raise ValueError("verified notes must be active")
    today = _dt.date.today().isoformat()

    # --- dedup: same type/project + equivalent title -> update in place ---
    existing = None
    allowed_statuses = ("draft",) if status == "draft" else ("active", "draft")
    placeholders = ",".join("?" for _ in allowed_statuses)
    rows = index.con.execute(
        "SELECT id, path, title FROM notes WHERE type = ? AND project IS ? "
        f"AND COALESCE(status, 'active') IN ({placeholders})",
        (type, project, *allowed_statuses),
    ).fetchall()
    for r in rows:
        if _norm_title(r["title"]) == _norm_title(title):
            existing = dict(r)
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
            if status == "draft" and cand["status"] != "draft":
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
        if supersedes:
            meta["supersedes"] = sorted(set(meta.get("supersedes", []) or []) | set(supersedes))
        if sources:
            meta["sources"] = sorted(set(meta.get("sources", []) or []) | set(sources))
        meta["status"] = status
        meta["verification"] = verification
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
        if supersedes:
            meta["supersedes"] = supersedes
        meta["status"] = status
        meta["verification"] = verification
        if sources:
            meta["sources"] = sources
        post = frontmatter.Post(body or "", **meta)
        action = "created"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    index.reindex(vault)  # so _mark_superseded can resolve old note paths
    superseded = (
        _mark_superseded(vault, index, supersedes, fid, today)
        if supersedes and status == "active"
        else []
    )
    if superseded:
        index.reindex(vault)
    result = {
        "action": action,
        "id": fid,
        "path": str(path.relative_to(vault)),
        "status": status,
        "verification": verification,
    }
    if superseded:
        result["superseded"] = superseded
    elif supersedes and status == "draft":
        result["pending_supersedes"] = supersedes
    return result


def verify_note(cfg, index, note_id: str, sources: list[str]) -> dict:
    sources = [source.strip() for source in sources if source.strip()]
    if not sources:
        raise ValueError("verification requires at least one source")
    row = Search(index).get(note_id)
    if not row:
        raise ValueError(f"note not found: {note_id}")
    path = cfg.vault / row["path"]
    post = frontmatter.load(str(path))
    previous = post.metadata.get("sources") or []
    if isinstance(previous, str):
        previous = [previous]
    post.metadata["sources"] = sorted(set(previous) | set(sources))
    post.metadata["status"] = "active"
    post.metadata["verification"] = "verified"
    post.metadata["updated"] = _dt.date.today().isoformat()
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    index.reindex(cfg.vault)
    supersedes = post.metadata.get("supersedes") or []
    if isinstance(supersedes, str):
        supersedes = [supersedes]
    superseded = _mark_superseded(
        cfg.vault, index, supersedes, note_id, post.metadata["updated"]
    )
    if superseded:
        index.reindex(cfg.vault)
    result = {
        "id": note_id,
        "path": row["path"],
        "status": "active",
        "verification": "verified",
        "sources": post.metadata["sources"],
    }
    if superseded:
        result["superseded"] = superseded
    return result

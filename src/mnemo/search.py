"""Search over the index.

Hybrid when a vector store is present (FTS5 + semantic, fused with Reciprocal
Rank Fusion); FTS-only otherwise. Returns *summaries + paths*, never full
bodies — the token-discipline contract. Fetch a body with ``get`` on demand.
"""

from __future__ import annotations

import json

_RRF_K = 60


def _rrf(ranked_lists: list[list[str]], k0: int = _RRF_K) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion across one or more ranked id lists."""
    scores: dict[str, float] = {}
    for ids in ranked_lists:
        for rank, nid in enumerate(ids):
            scores[nid] = scores.get(nid, 0.0) + 1.0 / (k0 + rank + 1)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


class Search:
    def __init__(self, index):
        self.index = index
        self.con = index.con

    def search(
        self,
        query: str,
        type: str | None = None,
        project: str | None = None,
        tags: list[str] | None = None,
        k: int = 5,
    ) -> list[dict]:
        pool = max(k * 4, 10)
        lists = [self.index.fts_ids(query, pool)]
        vec = self.index.vec_ids(query, pool)
        if vec is not None:
            lists.append(vec)
        fused = _rrf(lists)

        results: list[dict] = []
        for nid, score in fused:
            n = self.con.execute(
                "SELECT id, type, project, title, summary, path, tags, "
                "created, updated, status FROM notes WHERE id = ?",
                (nid,),
            ).fetchone()
            if n is None:
                continue
            if (n["status"] or "active") != "active":
                continue  # superseded / expired notes stay out of retrieval
            if type and n["type"] != type:
                continue
            if project and n["project"] != project:
                continue
            ntags = json.loads(n["tags"] or "[]")
            if tags and not (set(tags) & set(ntags)):
                continue
            results.append(
                {
                    "id": n["id"],
                    "type": n["type"],
                    "project": n["project"],
                    "title": n["title"],
                    "summary": n["summary"],
                    "path": n["path"],
                    "tags": ntags,
                    "created": n["created"],
                    "updated": n["updated"],
                    "score": round(score, 5),
                }
            )
            if len(results) >= k:
                break
        return results

    def get(self, note_id: str) -> dict | None:
        n = self.con.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        return dict(n) if n else None

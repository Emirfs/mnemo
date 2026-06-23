"""Search over the index.

Returns *summaries + paths*, never full bodies — this is the token-discipline
contract ("map then expand"). Callers fetch a full note with ``get`` only when
they actually need it.
"""

from __future__ import annotations

import json
import re

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _fts_query(text: str) -> str:
    """Build a safe FTS5 query: prefix-matched terms joined by OR."""
    terms = _WORD_RE.findall(text)
    if not terms:
        return '""'
    return " OR ".join(f'"{t}"*' for t in terms)


class Search:
    def __init__(self, index):
        self.con = index.con

    def search(
        self,
        query: str,
        type: str | None = None,
        project: str | None = None,
        tags: list[str] | None = None,
        k: int = 5,
    ) -> list[dict]:
        match = _fts_query(query)
        # Over-fetch, then apply metadata filters and trim to k.
        rows = self.con.execute(
            """SELECT id, bm25(notes_fts) AS rank
               FROM notes_fts
               WHERE notes_fts MATCH ?
               ORDER BY rank
               LIMIT ?""",
            (match, max(k * 4, k)),
        ).fetchall()

        results: list[dict] = []
        for r in rows:
            n = self.con.execute(
                "SELECT id, type, project, title, summary, path, tags "
                "FROM notes WHERE id = ?",
                (r["id"],),
            ).fetchone()
            if n is None:
                continue
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
                    "score": round(-r["rank"], 4),  # higher = better
                }
            )
            if len(results) >= k:
                break
        return results

    def get(self, note_id: str) -> dict | None:
        n = self.con.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        return dict(n) if n else None

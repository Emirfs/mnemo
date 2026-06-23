"""SQLite index: `notes` metadata + FTS5 full-text + optional vector store.

The index is derived from the vault and fully rebuildable. Reindexing is
incremental (a file is re-parsed only when its mtime changed). When an
``Embedder`` is supplied and sqlite-vec is available, a cosine vector table is
maintained alongside FTS for hybrid search; otherwise everything works on FTS5.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

from .note import Note
from .vault import iter_note_files

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id       TEXT PRIMARY KEY,
    path     TEXT UNIQUE,
    mtime    REAL,
    hash     TEXT,
    type     TEXT,
    project  TEXT,
    title    TEXT,
    summary  TEXT,
    tags     TEXT,
    created  TEXT,
    updated  TEXT,
    body     TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    id UNINDEXED,
    title,
    summary,
    body,
    tags,
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE INDEX IF NOT EXISTS idx_notes_type ON notes(type);
CREATE INDEX IF NOT EXISTS idx_notes_project ON notes(project);
"""

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fts_query(text: str) -> str:
    """Build a safe FTS5 query: prefix-matched terms joined by OR."""
    terms = _WORD_RE.findall(text)
    if not terms:
        return '""'
    return " OR ".join(f'"{t}"*' for t in terms)


class Index:
    def __init__(self, db_path: str | Path, embedder=None):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(self.db_path))
        self.con.row_factory = sqlite3.Row
        self.embedder = embedder
        self.vectors = False
        self._vec = None
        if embedder is not None:
            self._enable_vectors()
        self.con.executescript(SCHEMA)
        if self.vectors:
            self.con.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS vec_notes USING vec0("
                f"note_id TEXT, embedding float[{embedder.dim}] distance_metric=cosine)"
            )

    def _enable_vectors(self) -> None:
        try:
            import sqlite_vec

            self.con.enable_load_extension(True)
            sqlite_vec.load(self.con)
            self.con.enable_load_extension(False)
            self._vec = sqlite_vec
            self.vectors = True
        except Exception:
            self.vectors = False

    def close(self) -> None:
        self.con.close()

    def __enter__(self) -> "Index":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------------ write
    def _vec_delete(self, note_id: str) -> None:
        if self.vectors:
            self.con.execute("DELETE FROM vec_notes WHERE note_id = ?", (note_id,))

    def _vec_insert(self, note: Note) -> None:
        if not self.vectors:
            return
        vec = self.embedder.encode_one(note.search_text())
        self.con.execute(
            "INSERT INTO vec_notes(note_id, embedding) VALUES (?, ?)",
            (note.id, self._vec.serialize_float32(vec)),
        )

    def _upsert(self, note: Note, mtime: float, h: str) -> None:
        rel = str(note.path)
        old = self.con.execute("SELECT id FROM notes WHERE path = ?", (rel,)).fetchone()
        if old:
            self.con.execute("DELETE FROM notes_fts WHERE id = ?", (old["id"],))
            self._vec_delete(old["id"])
        self.con.execute("DELETE FROM notes_fts WHERE id = ?", (note.id,))
        self._vec_delete(note.id)
        self.con.execute("DELETE FROM notes WHERE id = ? OR path = ?", (note.id, rel))
        self.con.execute(
            """INSERT INTO notes
               (id, path, mtime, hash, type, project, title, summary, tags,
                created, updated, body)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                note.id, rel, mtime, h, note.type, note.project, note.title,
                note.summary, json.dumps(note.tags, ensure_ascii=False),
                note.created, note.updated, note.body,
            ),
        )
        self.con.execute(
            "INSERT INTO notes_fts (id, title, summary, body, tags) VALUES (?,?,?,?,?)",
            (note.id, note.title, note.summary, note.body, " ".join(note.tags)),
        )
        self._vec_insert(note)

    def reindex(self, vault: str | Path, full: bool = False) -> dict[str, int]:
        """Incrementally sync the index with the vault. Returns stats."""
        vault = Path(vault)
        existing = {
            row["path"]: (row["mtime"], row["id"])
            for row in self.con.execute("SELECT path, mtime, id FROM notes")
        }
        seen: set[str] = set()
        added = updated = skipped = 0

        for f in iter_note_files(vault):
            rel = str(f.relative_to(vault))
            seen.add(rel)
            mtime = f.stat().st_mtime
            if not full and rel in existing and abs(existing[rel][0] - mtime) < 1e-6:
                skipped += 1
                continue
            note = Note.from_file(f)
            note.path = Path(rel)
            self._upsert(note, mtime, _hash(note.search_text()))
            updated += 1 if rel in existing else 0
            added += 0 if rel in existing else 1

        removed = 0
        for path, (_, nid) in existing.items():
            if path not in seen:
                self.con.execute("DELETE FROM notes WHERE path = ?", (path,))
                self.con.execute("DELETE FROM notes_fts WHERE id = ?", (nid,))
                self._vec_delete(nid)
                removed += 1

        self.con.commit()
        return {"added": added, "updated": updated, "skipped": skipped, "removed": removed}

    # ------------------------------------------------------------------- read
    def count(self) -> int:
        return self.con.execute("SELECT COUNT(*) FROM notes").fetchone()[0]

    def fts_ids(self, query: str, limit: int) -> list[str]:
        rows = self.con.execute(
            """SELECT id, bm25(notes_fts) AS rank
               FROM notes_fts WHERE notes_fts MATCH ?
               ORDER BY rank LIMIT ?""",
            (fts_query(query), limit),
        ).fetchall()
        return [r["id"] for r in rows]

    def vec_search(self, query: str, limit: int) -> list[tuple[str, float]] | None:
        """KNN over the vector store. Returns (id, cosine_distance) or None
        when semantic search is unavailable."""
        if not self.vectors:
            return None
        q = self.embedder.encode_one(query)
        rows = self.con.execute(
            """SELECT note_id, distance FROM vec_notes
               WHERE embedding MATCH ? AND k = ? ORDER BY distance""",
            (self._vec.serialize_float32(q), limit),
        ).fetchall()
        return [(r["note_id"], r["distance"]) for r in rows]

    def vec_ids(self, query: str, limit: int) -> list[str] | None:
        hits = self.vec_search(query, limit)
        return None if hits is None else [h[0] for h in hits]

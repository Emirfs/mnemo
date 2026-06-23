"""SQLite index: a `notes` metadata table + an FTS5 full-text table.

The index is *derived* from the vault and fully rebuildable. Reindexing is
incremental: a file is re-parsed only when its mtime changed.
"""

from __future__ import annotations

import hashlib
import json
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


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Index:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(self.db_path))
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA)

    def close(self) -> None:
        self.con.close()

    def __enter__(self) -> "Index":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------------ write
    def _upsert(self, note: Note, mtime: float, h: str) -> None:
        rel = str(note.path)
        # Drop any prior FTS row for this path (its id may have changed) and
        # for the incoming id, then replace the metadata row.
        old = self.con.execute("SELECT id FROM notes WHERE path = ?", (rel,)).fetchone()
        if old:
            self.con.execute("DELETE FROM notes_fts WHERE id = ?", (old["id"],))
        self.con.execute("DELETE FROM notes_fts WHERE id = ?", (note.id,))
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
            note.path = Path(rel)  # store vault-relative path
            self._upsert(note, mtime, _hash(note.search_text()))
            updated += 1 if rel in existing else 0
            added += 0 if rel in existing else 1

        removed = 0
        for path, (_, nid) in existing.items():
            if path not in seen:
                self.con.execute("DELETE FROM notes WHERE path = ?", (path,))
                self.con.execute("DELETE FROM notes_fts WHERE id = ?", (nid,))
                removed += 1

        self.con.commit()
        return {"added": added, "updated": updated, "skipped": skipped, "removed": removed}

    # ------------------------------------------------------------------- read
    def count(self) -> int:
        return self.con.execute("SELECT COUNT(*) FROM notes").fetchone()[0]

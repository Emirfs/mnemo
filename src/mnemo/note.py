"""Note model — markdown + YAML frontmatter parsing/serialization."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import frontmatter

NOTE_TYPES = {"decision", "lesson", "daily", "project", "reference", "note", "profile"}

# Lifecycle states. 'active' is the default; 'superseded' / 'expired' notes are
# kept on disk (history) but hidden from retrieval.
NOTE_STATES = {"active", "superseded", "expired"}

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    s = _SLUG_RE.sub("-", text.lower()).strip("-")
    return s or "note"


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return [str(v).strip() for v in value if str(v).strip()]


@dataclass
class Note:
    """One atomic memory: a decision, lesson, daily entry, reference, etc."""

    id: str
    type: str
    title: str
    body: str = ""
    summary: str = ""
    project: str | None = None
    tags: list[str] = field(default_factory=list)
    created: str | None = None
    updated: str | None = None
    links: list[str] = field(default_factory=list)
    status: str = "active"
    supersedes: list[str] = field(default_factory=list)
    superseded_by: list[str] = field(default_factory=list)
    path: Path | None = None

    @classmethod
    def from_post(cls, post: "frontmatter.Post", path: Path | None = None) -> "Note":
        meta = post.metadata or {}
        stem = path.stem if path else ""
        title = str(meta.get("title") or stem).strip()
        ntype = str(meta.get("type") or "note").strip()
        nid = str(meta.get("id") or stem or slugify(title))
        project = meta.get("project")
        status = str(meta.get("status") or "active").strip().lower()
        return cls(
            id=nid,
            type=ntype,
            title=title,
            body=(post.content or "").strip(),
            summary=str(meta.get("summary") or "").strip(),
            project=str(project).strip() if project else None,
            tags=_as_list(meta.get("tags")),
            created=str(meta["created"]) if meta.get("created") else None,
            updated=str(meta["updated"]) if meta.get("updated") else None,
            links=_as_list(meta.get("links")),
            status=status if status in NOTE_STATES else "active",
            supersedes=_as_list(meta.get("supersedes")),
            superseded_by=_as_list(meta.get("superseded_by")),
            path=Path(path) if path else None,
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "Note":
        path = Path(path)
        post = frontmatter.load(str(path))
        return cls.from_post(post, path)

    def search_text(self) -> str:
        """Concatenated text used for indexing / hashing."""
        return "\n".join(p for p in (self.title, self.summary, self.body) if p)

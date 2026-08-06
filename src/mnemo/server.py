"""MCP server front-end (F3) — the PULL side, for any MCP-capable AI.

Exposes the same core (search / get / moc / write) as MCP tools over stdio.
The ``mcp`` dependency is imported lazily so the base install stays light.

A fresh SQLite connection is opened per call (cheap incremental reindex picks
up external Obsidian edits and avoids cross-thread connection issues).
"""

from __future__ import annotations

from .config import Config
from .index import Index
from .recall import build_recall
from .search import Search
from .writer import write_note


def build_server(vault: str | None = None, project: str | None = None):
    from mcp.server.fastmcp import FastMCP

    cfg = Config(vault)
    server = FastMCP("mnemo")
    default_project = project

    from .embed import Embedder
    _embedder = Embedder() if Embedder.is_available() else None

    def _open() -> Index:
        idx = Index(cfg.index_path, embedder=_embedder)
        idx.reindex(cfg.vault)  # incremental: pick up vault edits / git pulls
        return idx

    def _project(requested: str | None) -> str | None:
        if default_project and requested and requested != default_project:
            raise ValueError(
                f"MCP server is scoped to project {default_project!r}; "
                f"requested {requested!r}"
            )
        return default_project or requested

    @server.tool()
    def memory_search(
        query: str,
        type: str | None = None,
        project: str | None = None,
        k: int = 5,
    ) -> list[dict]:
        """Search memory. Returns summaries + ids + paths, NOT full bodies.
        Expand a specific result with memory_get(id)."""
        idx = _open()
        try:
            return Search(idx).search(
                query, type=type, project=_project(project), k=k
            )
        finally:
            idx.close()

    @server.tool()
    def memory_get(id: str) -> dict | None:
        """Fetch one full note (including body) by its id."""
        idx = _open()
        try:
            return Search(idx).get(id)
        finally:
            idx.close()

    @server.tool()
    def memory_moc(project: str | None = None) -> str:
        """Return the recall map for a project: its MOC plus recent decisions
        and lessons (summaries only). Uses the server's default project when
        omitted. Good first call when starting work."""
        idx = _open()
        try:
            return build_recall(idx, _project(project))
        finally:
            idx.close()

    @server.tool()
    def memory_write(
        type: str,
        title: str,
        summary: str = "",
        body: str = "",
        project: str | None = None,
        tags: list[str] | None = None,
        links: list[str] | None = None,
        supersedes: list[str] | None = None,
    ) -> dict:
        """Add or update a memory note. Deduped by title within the same
        type/project (an equivalent title updates in place, not a duplicate).
        type: decision | lesson | daily | project | reference | note | profile.
        Pass `supersedes` with ids this note replaces — those are marked stale
        and drop out of recall, so newer facts win over older contradictory ones."""
        idx = _open()
        try:
            return write_note(
                cfg, idx,
                type=type, title=title, summary=summary, body=body,
                project=_project(project),
                tags=tags, links=links, supersedes=supersedes,
            )
        finally:
            idx.close()

    return server


def run(vault: str | None = None, project: str | None = None) -> None:
    build_server(vault, project=project).run(transport="stdio")

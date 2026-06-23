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


def build_server(vault: str | None = None):
    from mcp.server.fastmcp import FastMCP

    cfg = Config(vault)
    server = FastMCP("mnemo")

    def _open() -> Index:
        idx = Index(cfg.index_path)
        idx.reindex(cfg.vault)  # incremental: pick up vault edits / git pulls
        return idx

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
            return Search(idx).search(query, type=type, project=project, k=k)
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
    def memory_moc(project: str) -> str:
        """Return the recall map for a project: its MOC plus recent decisions
        and lessons (summaries only). Good first call when starting work."""
        idx = _open()
        try:
            return build_recall(idx, project)
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
    ) -> dict:
        """Add or update a memory note. Deduped by title within the same
        type/project (an equivalent title updates in place, not a duplicate).
        type: decision | lesson | daily | project | reference | note."""
        idx = _open()
        try:
            return write_note(
                cfg, idx,
                type=type, title=title, summary=summary, body=body,
                project=project, tags=tags, links=links,
            )
        finally:
            idx.close()

    return server


def run(vault: str | None = None) -> None:
    build_server(vault).run(transport="stdio")

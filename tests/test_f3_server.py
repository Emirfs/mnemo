"""F3 tests: MCP server builds and registers the expected tools."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mnemo.server import build_server  # noqa: E402


def test_server_registers_tools(tmp_path: Path):
    server = build_server(str(tmp_path))
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert {"memory_search", "memory_get", "memory_moc", "memory_write"} <= names


def test_tool_schema_has_query(tmp_path: Path):
    server = build_server(str(tmp_path))
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    schema = tools["memory_search"].inputSchema
    assert "query" in schema.get("properties", {})


def test_moc_project_is_optional_for_scoped_server(tmp_path: Path):
    server = build_server(str(tmp_path), project="shared")
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    schema = tools["memory_moc"].inputSchema
    assert "project" not in schema.get("required", [])


def test_scoped_server_applies_default_project_to_write(tmp_path: Path):
    server = build_server(str(tmp_path), project="shared")

    asyncio.run(
        server.call_tool(
            "memory_write",
            {
                "type": "decision",
                "title": "Shared decision",
                "summary": "Stored under the server scope.",
            },
        )
    )

    note = next(tmp_path.rglob("*.md")).read_text(encoding="utf-8")
    assert "project: shared" in note
    assert "status: draft" in note
    assert "verification: inferred" in note


def test_scoped_server_rejects_conflicting_project(tmp_path: Path):
    server = build_server(str(tmp_path), project="shared")

    with pytest.raises(Exception, match="scoped to project 'shared'"):
        asyncio.run(
            server.call_tool(
                "memory_write",
                {
                    "type": "decision",
                    "title": "Wrong scope",
                    "project": "other",
                },
            )
        )

    assert not list(tmp_path.rglob("*.md"))

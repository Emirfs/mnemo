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

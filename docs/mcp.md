# mnemo MCP server (cross-AI, pull)

The MCP server exposes the same vault to **any MCP-capable AI** (Claude Code,
Cursor, …) as callable tools. This is the *pull* side; the SessionStart hook
(see `hooks/`) is the *push* side. Both read the same vault — use both.

## Tools

| Tool | Returns |
|------|---------|
| `memory_search(query, type?, project?, k=5)` | summaries + ids + paths (no bodies) |
| `memory_get(id)` | one full note (with body) |
| `memory_moc(project)` | the recall map: MOC + recent decisions/lessons |
| `memory_write(type, title, summary?, body?, project?, tags?, links?)` | create/update draft (deduped) |

`memory_search` deliberately omits bodies — the model expands only what it needs
with `memory_get`, keeping token cost flat as the vault grows.

`memory_write` is intentionally draft-only. AI-created notes are stored with
`status: draft` and `verification: inferred`, so they cannot enter retrieval as
facts. A human promotes one with `mnemo verify <id> --sources <evidence>`.

## Install (requires the `mcp` extra)

```bash
uv tool install "mnemofish[mcp]"     # or: pipx install "mnemofish[mcp]"
```

## Register with Claude Code

`.mcp.json` in your project (or via `claude mcp add`):

```json
{
  "mcpServers": {
    "mnemo": {
      "command": "mnemo",
      "args": ["--vault", "C:/Users/you/my-memory", "serve", "--project", "my-app"]
    }
  }
}
```

## Register with Cursor

`~/.cursor/mcp.json` (or project `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "mnemo": {
      "command": "mnemo",
      "args": ["--vault", "C:/Users/you/my-memory", "serve", "--project", "my-app"]
    }
  }
}
```

The server runs over stdio and reindexes incrementally on each call, so edits
made in Obsidian (or pulled via git) are picked up automatically.

`--project` scopes every search, MOC, and write to that project. A conflicting
project from the AI is rejected instead of silently splitting memory. Use the
same value as the repo's `.mnemo-project` marker. Omit it only when you want a
global, cross-project MCP server.

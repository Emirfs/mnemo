# mnemo

Persistent, portable, cross-AI memory over a plain **markdown vault** — with
**push-based auto-recall** so the model knows your past work *without being asked*.

> Storage was never the hard part. **Retrieval** is. Most memory tools save notes
> the model never reads back. mnemo closes that loop: a hook injects the relevant
> notes into context at session start (push), and an MCP server lets any
> MCP-capable AI search the same vault (pull).

## Core ideas

- **Vault = source of truth.** Plain markdown + frontmatter. The index
  (SQLite FTS5 + vectors) is derived and rebuildable — never committed.
- **Map then expand.** Search returns summaries + paths, not full bodies, so
  token cost stays flat as the vault grows.
- **Push > pull.** Auto-recall via editor hooks; search via MCP for every AI.
- **Portable.** Your vault is a private git repo. Move machines:
  `mnemo clone <url>` → reindex → the AI knows everything.

## Status

Working. F1–F5 implemented (24 tests passing). See [`DESIGN.md`](./DESIGN.md)
for architecture and roadmap.

- **F1** core: markdown/frontmatter parse, FTS5, incremental index
- **F2** `recall` + `write` + SessionStart hook (push auto-recall) — [`hooks/`](./hooks)
- **F3** MCP server (`memory_search/get/moc/write`) — [`docs/mcp.md`](./docs/mcp.md)
- **F4** portability: `init` / `sync` / `clone` / `export` / `import`
- **F5** semantic hybrid search (fastembed + sqlite-vec, RRF), content dedup,
  `daily` journaling

## Quick start (dev)

```bash
uv venv
uv pip install -e ".[dev]"            # core (FTS5 only)
uv pip install -e ".[dev,embed,mcp]"  # + semantic search + MCP server

uv run mnemo --vault ./my-vault init
uv run mnemo --vault ./my-vault write --type decision --title "..." --summary "..."
uv run mnemo --vault ./my-vault search "your query"
uv run mnemo --vault ./my-vault daily "what I did today"
```

## Commands

| Command | What |
|---------|------|
| `init` / `sync` / `clone` | manage the vault as a private git repo |
| `write` / `daily` | add notes (deduped) / journal entries |
| `search` / `get` | hybrid search (summaries) / fetch a full note |
| `recall --hook` | emit the SessionStart recall block (push) |
| `serve` | run the MCP server (pull, cross-AI) |
| `export` / `import` | zip the vault for one-shot transfer |

## License

MIT

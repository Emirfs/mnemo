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

Early development. See [`DESIGN.md`](./DESIGN.md) for the full architecture and
roadmap. F1 (core: parse + FTS5 + incremental index) is implemented.

## Quick start (dev)

```bash
uv venv
uv pip install -e ".[dev]"
uv run mnemo --vault ./my-vault reindex
uv run mnemo --vault ./my-vault search "your query"
```

## License

MIT

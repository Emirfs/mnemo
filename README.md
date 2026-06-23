<div align="center">

<img src="./docs/assets/logo.svg" alt="mnemo logo" width="140" height="140" />

# mnemo

### Your AI keeps losing Nemo. mnemo finds him — *every session.*

**Persistent, portable, cross-AI memory** over a plain markdown vault —
with **push-based auto-recall** so the model remembers your past work *without being asked.*

[![Python](https://img.shields.io/badge/python-3.10+-3776ab?logo=python&logoColor=white)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-compatible-7c3aed)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/license-MIT-22c55e.svg)](#license)
[![Tests](https://img.shields.io/badge/tests-28%20passing-22c55e.svg)](#status)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-ff8a3d.svg)](#contributing)

*Just keep swimming.* 🐠

</div>

---

## 🌊 The problem

Every new chat, your AI gets amnesia. It forgets the decision you made yesterday,
the bug you already fixed, the contract two repos share. So you re-explain. Forever.

Most "memory" tools only solve **storage** — they save notes the model never reads back.
That's like writing Nemo's address on a fridge he can't reach. The real bottleneck is
**retrieval**: getting the *right* memory into context at the *right* moment.

> Storage was never the hard part. **Retrieval is.**

## 🐠 How mnemo finds Nemo

mnemo closes the loop with **two currents**:

- **Push (the rescue).** A `SessionStart` hook injects the relevant notes into context
  *before you type a word*. The AI starts every session already knowing your past work.
- **Pull (the net).** An MCP server lets any MCP-capable AI (Claude Code, Cursor, …)
  search the same vault mid-conversation.

Same vault, two ways in. Nemo never stays lost.

## ✨ Why it's different

- **Vault = source of truth.** Plain markdown + YAML frontmatter. Edit it in Obsidian,
  in your editor, by hand. The index (SQLite FTS5 + vectors) is *derived* and rebuildable —
  never committed.
- **Map, then expand.** Search returns *summaries + paths*, not full bodies. Token cost
  stays **flat** as your vault grows from 10 notes to 10,000.
- **Store only what can't be re-derived.** File trees and function signatures? The AI can
  find those. Decisions, gotchas, contracts, intent? Those get saved.
- **Hybrid search.** Keyword (FTS5) + semantic (local embeddings, RRF-fused) — catches
  paraphrases that keyword search misses. Embeddings run **locally**: offline, private, no API.
- **Portable.** Your vault is a private git repo. New machine, new AI:
  `mnemo clone <url>` → reindex → it knows everything.
- **Shared across repos.** Drop a `.mnemo-project` marker so multiple repos feed one project memory.

## 🚀 Quick start

```bash
uv venv
uv pip install -e ".[dev]"            # core (FTS5 keyword search)
uv pip install -e ".[dev,embed,mcp]"  # + semantic search + MCP server

uv run mnemo --vault ./my-vault init
uv run mnemo --vault ./my-vault write \
  --type decision --title "RF update is sequential" \
  --summary "Devices update one at a time, not concurrently — prevents system lockup."
uv run mnemo --vault ./my-vault search "rf update order"
uv run mnemo --vault ./my-vault daily "what I shipped today"
```

## 🪝 Auto-recall in 30 seconds

Wire the `SessionStart` hook (see [`hooks/`](./hooks)) and your AI greets you with the
relevant Map of Content + recent decisions — automatically:

```jsonc
// .claude/settings.json  (full example: hooks/settings.example.json)
{
  "hooks": {
    "SessionStart": [
      { "matcher": "startup", "hooks": [{
        "type": "command",
        "command": "mnemo --vault \"/path/to/my-memory\" recall --hook --reindex --project-dir \"$CLAUDE_PROJECT_DIR\""
      }]}
    ]
  }
}
```

For MCP clients, run the server and point your client at it:

```bash
uv run mnemo --vault ./my-vault serve   # exposes memory_search / get / moc / write
```

## 🧭 How it works

```
        ┌──────────────────────────────────────────┐
        │  Vault (markdown + frontmatter)          │  ← single source of truth (Obsidian-friendly)
        └───────────────────┬──────────────────────┘
                            │ parse (incremental: mtime/hash)
                 ┌──────────▼───────────┐
                 │   CORE LIBRARY       │   index.sqlite (FTS5 + vectors)
                 │  parse / index /     │   ← derived, .gitignored, rebuildable
                 │  search / write      │
                 └─────┬───────────┬────┘
          ┌────────────▼──┐    ┌───▼─────────────────┐
          │  CLI + hook    │    │   MCP server         │
          │  (PUSH)        │    │   (PULL)             │
          │  session-start │    │   any MCP-capable AI │
          │  auto-recall   │    │   in-chat tool calls │
          └────────────────┘    └─────────────────────┘
```

A task = **1 MOC + a few atomic notes**, no matter how big the vault gets.

## 📓 A note looks like this

```markdown
---
id: 20260623-rf-uid-sequential
type: decision           # decision | lesson | daily | project | reference | note
title: RF update is sequential
project: stm32-rf-ota
tags: [rf, protocol, stm32]
summary: Devices update one at a time, not concurrently — prevents system lockup.
links: [20260623-rf-uid-identity]
---

Sequential update: id1 finishes, id2 begins. All devices don't drop into the
bootloader at once, so the system stays alive...
```

`summary` is required and short — the index shows *that*, not the body. That's where the
token discipline comes from.

## 🛠️ Commands

| Command | What it does |
|---|---|
| `init` / `sync` / `clone` | manage the vault as a private git repo |
| `write` / `daily` | add notes (deduped) / append journal entries |
| `search` / `get` | hybrid search (summaries) / fetch one full note |
| `reindex` | rebuild the derived index from scratch |
| `recall --hook` | emit the SessionStart recall block (push) |
| `serve` | run the MCP server (pull, cross-AI) |
| `export` / `import` | zip the vault for one-shot transfer (Drive, etc.) |

## 📊 Status

Working. **F1–F6 implemented, 28 tests passing.** See [`DESIGN.md`](./DESIGN.md) for
architecture and roadmap.

- **F1** — core: markdown/frontmatter parse, FTS5, incremental index
- **F2** — `recall` + `write` + SessionStart hook (push auto-recall) — [`hooks/`](./hooks)
- **F3** — MCP server (`memory_search/get/moc/write`) — [`docs/mcp.md`](./docs/mcp.md)
- **F4** — portability: `init` / `sync` / `clone` / `export` / `import`
- **F5** — semantic hybrid search (fastembed + sqlite-vec, RRF), content dedup, `daily` journaling
- **F6** — `.mnemo-project` marker for shared cross-repo project memory

## 🔒 Privacy

Two repos, never mixed: the **public** one is this software (generic, zero personal data);
your **private** one is your vault. Embeddings run locally, so your notes never leave your
machine (API embeddings are opt-in only).

## 🤝 Contributing

PRs and issues welcome. The codebase is small Python — `core library + two frontends`.
Run the suite with `pytest`, keep notes atomic, and *just keep swimming.*

## License

[MIT](#license) © Emir Furkan Sarı

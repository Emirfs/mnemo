<div align="center">

<img src="https://raw.githubusercontent.com/Emirfs/mnemo/master/docs/assets/logo.svg" alt="mnemo pixel-art clownfish" width="220" />

# mnemo

### Your AI has goldfish memory. 🐠 mnemo gives it an elephant's. 🐘

**Persistent, portable, cross-AI memory** over a plain markdown vault —
with **push-based auto-recall** so the model remembers your past work *without being asked.*

[![Python](https://img.shields.io/badge/python-3.10+-3776ab?logo=python&logoColor=white)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-compatible-7c3aed)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/license-MIT-22c55e.svg)](#license)
[![Tests](https://img.shields.io/badge/tests-28%20passing-22c55e.svg)](#status)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-ff8a3d.svg)](#contributing)
[![Vibe](https://img.shields.io/badge/just%20keep-swimming-1e90ff.svg)](#)

</div>

> [!NOTE]
> **P. Sherman, 42 Wallaby Way, Sydney.**
> Dory could *say* the address. She just couldn't *recall* it when it mattered.
> That's your AI. That's every memory tool that only does storage. mnemo is the one that remembers at the right moment.

---

## 🫧 The problem (you've lived this)

```
You:  "remember we decided X yesterday"
AI:   "i have no memory of that, what is X"
You:  *re-explains the entire project for the 9th time*
```

New chat → instant amnesia. The decision from yesterday? Gone. The bug you already
killed? It's back, baby. The contract two repos share? Never heard of her.

Most "memory" tools only solve **storage** — they save notes the model never reads back.
Cool, you wrote down Nemo's address on a fridge he can't reach. 🧲 The actual hard part
is **retrieval**: getting the *right* memory into context at the *right* moment.

> Storage was never the hard part. **Retrieval is.** 🎯

## 🐠 How mnemo keeps finding Nemo

Two currents. Same ocean.

| | | |
|---|---|---|
| **🌊 PUSH — the rescue** | a `SessionStart` hook injects the relevant notes into context *before you type a word* | the AI starts every session already knowing your history |
| **🪝 PULL — the net** | an MCP server lets any MCP-capable AI search the same vault mid-chat | Claude Code, Cursor, whatever — same brain |

Nemo never stays lost. *He just keeps swimming back.*

## ✨ Why it actually slaps

- **🗂️ Vault = source of truth.** Plain markdown + YAML frontmatter. Edit it in Obsidian,
  your editor, or a cave with a stick. The index (SQLite FTS5 + vectors) is *derived* and
  rebuildable — never committed.
- **🧮 Map, then expand.** Search returns *summaries + paths*, not full bodies. Token cost
  stays **flat** whether your vault has 10 notes or 10,000. Your context window stays unbothered.
- **🧠 Store only what can't be re-derived.** File trees and function signatures? The AI can
  find those itself. Decisions, gotchas, contracts, *why-the-hell-did-we-do-it-this-way*? Saved.
- **🔍 Hybrid search.** Keyword (FTS5) **+** semantic (local embeddings, RRF-fused) — catches
  the paraphrase keyword search fumbles. Runs **100% local**: offline, private, zero API spend.
- **🚚 Portable AF.** Your vault is a private git repo. New machine, new AI?
  `mnemo clone <url>` → reindex → it knows everything. Memory that survives a laptop death.
- **🔗 Shared across repos.** Drop a `.mnemo-project` marker and many repos feed one project brain.

## 🚀 Quick start

```bash
# zero-install run (recommended)
uvx mnemovault --vault ./my-vault init

# or install it (ships the `mnemo` command)
pip install "mnemovault[embed,mcp]"   # everything: semantic search + MCP server
pip install mnemovault                 # core only (FTS5 keyword search)
```

> 📦 PyPI package is **`mnemovault`**; the CLI command is **`mnemo`** (the alias `mnemovault` also works).

<details>
<summary>From source (dev)</summary>

```bash
uv venv
uv pip install -e ".[dev]"            # core (FTS5 keyword search)
uv pip install -e ".[dev,embed,mcp]"  # + semantic search + MCP server
```
</details>

```bash
uv run mnemo --vault ./my-vault init
uv run mnemo --vault ./my-vault write \
  --type decision --title "RF update is sequential" \
  --summary "Devices update one at a time, not concurrently — prevents system lockup."
uv run mnemo --vault ./my-vault search "rf update order"
uv run mnemo --vault ./my-vault daily "what I shipped today"
```

## 🪝 Auto-recall in 30 seconds

Wire the `SessionStart` hook and your AI greets you with the relevant Map of Content +
recent decisions — *automatically, every time.*

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

A task = **1 MOC + a few atomic notes**, no matter how big the vault gets. Flat tokens. 📉

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
token discipline comes from. (No `summary` = bad note. The fish judges you. 🐠)

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

Working. **F1–F6 shipped, 28 tests green.** ✅ See [`DESIGN.md`](./DESIGN.md) for
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
machine. 🏠 (API embeddings are opt-in only.)

## 🤝 Contributing

PRs and issues welcome. Small Python codebase — `core library + two frontends`.
Run the suite with `pytest`, keep notes atomic, and *just keep swimming.* 🐠

## License

[MIT](#license) © Emir Furkan Sarı

<div align="center"><sub><i>mnemo /ˈniːmoʊ/ — from Mnemosyne (memory) ⋅ also a small orange fish who refuses to be forgotten.</i></sub></div>

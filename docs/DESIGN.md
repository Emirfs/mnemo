# mnemo — Design Document

> Working title: **mnemo** (Mnemosyne — memory). Subject to change.
> Status: DRAFT v0.1 — scope freeze phase.

Personal, cross-project, cross-AI **persistent memory** system.
Running over a markdown vault: **MCP memory server** + **CLI** + **Claude Code hooks**.

---

## 1. Problem

Existing memory tools (e.g. claude-mem) solve **storage** but fail to solve **retrieval**.

> Common scenario: "Save this" is executed, notes are saved — but the AI never **reads** the right memory at the right time.

The real bottleneck is not writing information, but **automatically injecting the relevant subset into the model's context at the right moment.**

Second problem: As information grows, token consumption and noise increase. Loading everything is unsustainable.

---

## 2. Core Principles

1. **Retrieval-first.** The system is designed around "auto-recalling the right memory", not "writing".
2. **Push > Pull.** MCP tool (pull) waits for the model to invoke it — where claude-mem breaks. Real automation happens via **hooks** (push): relevant notes are injected into context before the AI asks.
3. **Vault = single source of truth.** Markdown files are canonical. Index (sqlite/embedding) is derived and can be destroyed and rebuilt at any time.
4. **Store only non-re-derivable content.** File trees/function signatures can be discovered by the AI → do not store. Decisions, relationships, contracts, bugs, intent → store.
5. **Map first, node second.** To keep token cost flat: small index (MOC) is loaded first, expanding only the relevant atomic note. Never load "everything".
6. **Atomic notes.** One note = one decision/fact/bug. Small → cheap individual loading, minimal conflicts, no chunking needed.

### Derivable vs Non-Derivable

| AI can discover itself (DO NOT STORE) | AI cannot discover (STORE) |
|---|---|
| File tree (`glob`) | Topology: what talks to what |
| Vendor code (HAL/CMSIS, node_modules) | Shared protocols/contracts |
| Function signatures | Why a decision was made |
| Which files exist | Current activity / gotchas / bugs |

---

## 3. Architecture

**Core library + two front-ends.** This separation is key — it enables auto-recall.

```
            ┌──────────────────────────────────────────┐
            │  Vault (markdown + frontmatter)          │  ← single source, editable in Obsidian
            └───────────────────┬──────────────────────┘
                                │ parse (incremental, mtime/hash)
                     ┌──────────▼───────────┐
                     │  CORE LIB            │  index.sqlite (FTS5 + vectors)
                     │  parse / index /     │  ← derived, gitignored, rebuildable
                     │  search / write      │
                     └─────┬───────────┬────┘
              ┌────────────▼──┐    ┌───▼─────────────────┐
              │  CLI front-end │    │  MCP front-end       │
              │  (PUSH)        │    │  (PULL)              │
              │  Claude hook   │    │  any MCP-capable AI  │
              │  session-start │    │  in-chat tool calls  │
              │  inject recall │    │                      │
              └────────────────┘    └─────────────────────┘
```

- **Core lib:** parse + index + search + write. Single business logic.
- **CLI front-end:** Called by hooks (push). Prints relevant MOC + top-N notes at session start into context. `mnemo search/write/init/sync/...`.
- **MCP front-end:** Exposes core as MCP tools → Claude Code, Cursor, and other MCP clients use the same search interface.

---

## 4. Vault Structure

The vault is a flat folder (= private GitHub repo). Recommended layout:

```
my-memory/                    ← private repo
├── daily/                    daily notes, todos, "what I did today"
│   └── 2026-06-23.md
├── projects/
│   └── <project>/
│       ├── _moc.md           project map (Map of Content) — index note
│       └── <atomic>.md       single decision/fact
├── lessons/                  bugs, lessons learned (retrieved by tag)
├── protocol/                 technical contracts (e.g. RF v2)
├── reference/                durable information (URLs, dashboards, tickets)
├── .gitignore                excludes index.sqlite + .cache
└── .mnemo/                   (gitignored) index.sqlite, embedding cache
```

`projects/`, `lessons/` etc. are **not fixed** — users can define their taxonomy; the system operates on `type` frontmatter, not directory names.

---

## 5. Note Schema (Frontmatter)

Every note = markdown + YAML frontmatter:

```markdown
---
id: 20260623-rf-uid-sequential        # stable identifier (date-slug)
type: decision                         # decision | lesson | daily | project | reference | note
title: RF updates are performed sequentially
project: stm32-rf-ota                  # optional
tags: [rf, protocol, stm32]
created: 2026-06-23
updated: 2026-06-23
summary: Devices are updated one by one; non-concurrent — prevents system lockup.
links: [20260623-rf-uid-identity]      # [[wikilink]] supported
---

Sequential update: id1 completes, id2 starts. Advantage: all devices do not drop to bootloader simultaneously...
```

- `summary` is required and **short** → index/MOC displays this, not the body. Enables token discipline.
- `type` provides retrieval filtering (keeps `daily` notes from clogging technical queries).
- `links` builds relationship graph (MOC + backlink + AI traversal).

---

## 6. MOC (Map of Content)

`_moc.md` = **map** of a project or topic. Links to atomic notes + single-line summary.

```markdown
---
type: project
title: STM32 RF OTA — MOC
project: stm32-rf-ota
---
# STM32 RF OTA

## Decisions
- [[20260623-rf-uid-identity]] — identity = 96-bit STM32 UID, no hash
- [[20260623-rf-uid-sequential]] — updates sequential, non-concurrent

## Components
- Sender STM32 (RF gateway), PC Uploader (Python/Qt), MobileUploader (Flutter)
- Receivers: stpm, stpm_fc (bootloader) + apps

## Open Tasks
- [ ] DISCOVER_ACK 7→18 byte (UID) transition
```

Recall flow: **MOC loaded first** → AI sees relevant link → opens only that atomic note with `get`. Even if vault grows to 10,000 notes, one task = 1 MOC + a few atomic notes.

---

## 7. Index Layer

- **Store:** vault markdown. **Index:** `.mnemo/index.sqlite` (disposable).
- **Lexical:** SQLite **FTS5** (keyword/tag search, deterministic, no model required).
- **Semantic:** local embedding (sentence-transformers/fastembed) → vector search via `sqlite-vec` (catches paraphrases/synonyms).
- **Hybrid:** FTS5 + vector results fused (rerank via RRF).
- **Incremental:** per-file mtime/hash → re-parse+embed only modified files. No full vault reprocessing.
- **Local Embedding:** no API calls, offline, private.

---

## 8. Retrieval (Token Discipline)

`search` returns **summary + path + score**, **not full body.** Map-then-expand contract embedded at interface level.

```
search("rf update sequence", type=decision, k=5)
  → [{id, title, summary, path, score}, ...]   # ~5 lines, cheap
get(path)                                        # full body only if needed
```

Context token cost remains **flat** per task as vault grows.

---

## 9. MCP Tool API

| Tool | Input | Output | Note |
|---|---|---|---|
| `memory_search` | query, type?, project?, tags?, k=5 | summary+path+score list | does NOT return body |
| `memory_get` | path/id | full note | on-demand |
| `memory_moc` | project | project map | map |
| `memory_write` | type, title, body, tags, links | new/updated note | **search-before-write** (dedup) |
| `memory_link` | id_a, id_b | — | connect nodes |

---

## 10. CLI Commands

| Command | Action |
|---|---|
| `mnemo init [--remote <github-url>]` | initialize vault as git repo |
| `mnemo reindex` | rebuild index from scratch |
| `mnemo search <query> [--type --project -k]` | hook/manual search |
| `mnemo write ...` | add note (deduped) |
| `mnemo recall [--project]` | generate session-start injection block (used by hook) |
| `mnemo sync` | git pull + push |
| `mnemo clone <github-url>` | new machine: clone + reindex |
| `mnemo export <file>` / `import <file>` | single-file transfer |
| `mnemo compact` | dedup / decay cleanup |

---

## 11. Hook Flow (Claude Code — PUSH)

Enables auto-recall. `settings.json` hooks:

- **SessionStart:** `mnemo recall --project <cwd>` → relevant MOC + recent decisions/lessons injected into context. AI starts knowing history **without asking**.
- **UserPromptSubmit (optional):** keyword/embedding from prompt → top-N notes injected (task-specific recall).
- **Stop / SessionEnd:** extract decision/bug/action from session → `mnemo write` (auto-capture).

---

## 12. Cross-AI

- **MCP-compatible** (Claude Code, Cursor, ...): connect to same MCP server → identical search/recall.
- **Non-MCP** (plain ChatGPT web, etc.): paste export or manually load vault.
- Store is universal (markdown), retrieval wiring per tool.

---

## 13. Portability — GitHub Backbone

- **Vault = private GitHub repo.** Only markdown committed; `index.sqlite` + embedding cache `.gitignore`d.
- **New machine / AI:** `mnemo clone <github-url>` → clone + reindex → starts fully informed.
- **Advantages:** versioned knowledge, free sync, merge, backup.

---

## 14. Decay Prevention

- **Search-before-write:** `write` checks for existing similar notes before adding new ones → updates/appends instead.
- **`compact`:** periodic dedup + dead link cleanup.
- **Required summary:** every note must be summarizable.

---

## 15. Privacy / Security

- **Two repos:**
  - **PUBLIC** (OSS): `mnemo` software. Generic, vault-path config, NO personal data.
  - **PRIVATE**: user's vault (notes, decisions, bugs).
- Local embedding → data never leaves the machine.

---

## 16. Stack

- **Language:** Python. Distribution: `uvx` / `pipx`.
- **Dependencies:** `mcp` (SDK), `python-frontmatter`, `sentence-transformers` / `fastembed`, `sqlite-vec`, SQLite FTS5.
- **Store:** vault markdown + `.mnemo/index.sqlite` (sidecar, disposable).

---

## 17. Roadmap

| Phase | Output | Proof | Status |
|---|---|---|---|
| **F1 — Core** | parse + frontmatter + FTS5 + incremental index | `search` returns correct note | ✅ |
| **F2 — CLI + Hook** | `recall/search/write` + Claude SessionStart hook (push) | AI starts knowing history without asking | ✅ |
| **F3 — MCP** | `memory_search/get/moc/write` server | Cursor/Claude search same vault | ✅ |
| **F4 — Portability** | `init/sync/clone/export/import` (GitHub) | clone+reindex works on new machine | ✅ |
| **F5 — Semantic + daily** | fastembed+sqlite-vec hybrid (RRF), content dedup, `daily` journaling | paraphrase search finds what FTS misses | ✅ |

---

## 18. Decisions

1. **Embedding Model:** Multilingual MiniLM (`paraphrase-multilingual-MiniLM-L12-v2`) default.
2. **Project Detection:** git remote slug → folder name fallback.
3. **Name:** `mnemo`.

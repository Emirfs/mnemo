# Mnemo Live — System Plan

> An AI-native terminal and its **persistent, automatic memory**. The memory layer
> is the existing **mnemo** vault; on top of it we add a **broker** running with a local
> (free) model/process. Result: while working in the terminal, memory, decisions, and
> tasks flow automatically to the AI you use without calling manual `recall`.

Date: 2026-06-23 · Status: Plan (Pending approval) · Owner: Emir Furkan

---

## 1. Executive Summary

Building a terminal is the minor and final part of the job. The real value and main work is the **intermediary memory broker**: whatever you type, a constantly running layer in the background selects, compresses, and injects the relevant memory into the AI you use. This layer reads the existing mnemo vault (markdown + sqlite index + MCP + recall hook).

Critical design decision: **zero LLMs — neither on the hot path nor in the background.** Everything per prompt is pure *retrieval* (sqlite FTS + embedding), ~deci-seconds. Memory quality (recency, conflict resolution, expiration) is handled via **mechanical** rules without an LLM. Thus the system remains fast, lightweight, and dependency-free.

> **Update (2026-06-25):** The Ollama/local-LLM "Librarian" plan was **dropped.**
> Following the supermemory comparison (see §14), the missing retrieval quality components were added without requiring an LLM: eval harness, recency weight, profile type, temporal supersession, ephemeral expire. All shipped (§10).

This plan progresses in phases. Phase 0 proves the "automatic memory" thesis without building a terminal; the terminal comes last by forking an existing open-source base.

---

## 2. Vision (Distilled)

- A modern, AI-native terminal like Warp/Wave.
- Terminal's **own memory = mnemo system**.
- **No manual steps like `recall`** needed while working in that terminal.
- A **free/local daemon** connected to the terminal automatically passes summarized memory and upcoming tasks to the active AI.
- Fast, low RAM footprint.

---

## 3. Core Principle: Product is Memory, Front-End is Pluggable

```
       ┌─────────────────────────────────────────────┐
       │  FRONT-ENDS (interchangeable, lightweight)  │
       │  Claude Code · Cursor · Mnemo Term · TUI     │
       └───────────────┬─────────────────────────────┘
                       │  (MCP / hook / stdin injection)
       ┌───────────────▼─────────────────────────────┐
       │  BROKER  (Mnemo Live — always-on, hot)      │  ← new main component
       │  • retrieval (FTS + embedding)  ← hot path   │
       │  • context packager (token budgeted)        │
       │  • task/decision surfacer                    │
       └───────────────┬─────────────────────────────┘
                       │
       ┌───────────────▼─────────────────────────────┐
       │  CORE  (mnemo — EXISTING)                    │
       │  vault (markdown)  +  index (sqlite/vec)     │
       │  + quality (mechanical, no LLM):             │
       │    recency · supersession · expire · profile │
       └─────────────────────────────────────────────┘
```

> The **LIBRARIAN (Ollama)** box from the old plan was removed. Its responsibilities (superseding old notes, expiration) are handled mechanically without an LLM.

Main idea: We don't rewrite AIs. They are front-ends; they connect to core memory via **MCP** and **hooks**. The terminal is also just a front-end — which is why it can be deferred to the end and derived from an existing base.

---

## 4. Components

### 4.1 Core — mnemo (EXISTING)
- **Vault:** `C:/Users/Emir Furkan/Desktop/mnemo-vault` — Obsidian-compatible markdown. Types: `project (MOC) · decision · lesson · reference · daily · note`.
- **Index:** `.mnemo/index.sqlite` (FTS + optional `sqlite-vec` embedding).
- **Read paths:** MCP server (`memory_search/get/moc/write`) and SessionStart recall hook. Both read the same vault.
- **Project detection:** git remote slug → folder name (e.g., `stm32-rf-ota`).

### 4.2 Broker — "Mnemo Live" (NEW, the heart)
A single always-on process. The embedding model is loaded **once** and kept warm (no cold subprocess launches). Tasks:

1. **Retrieval:** Selects the most relevant notes from the vault based on incoming prompt/command + cwd/project context. Pure sqlite FTS + cosine. No LLM.
2. **Context Packaging:** Compresses selected notes into a hard token budget (e.g., ≤800 tokens); cheap because notes are kept "summary-only".
3. **Task/Decision Surfacing:** Adds open tasks and recent decisions as "what's next".
4. **Cache:** Reuses the previous package if cwd/project/task haven't changed.

Interface: Local socket/HTTP endpoint (`localhost`), e.g., `GET /context?cwd=...`.
Front-ends request from here; response is ~ms because the daemon is warm.

### 4.3 Injection (NEW)
The "no manual recall needed" part. Two modes:
- **Claude Code / MCP AIs:** `UserPromptSubmit` hook → fetch context from broker → prepend to prompt. Fresh context per message (not just once at session start).
- **Terminal embedded chat (Phase 3):** We build the prompt ourselves → context placed directly in system prompt.

### 4.4 Quality Layer — Mechanical, No LLM (NEW, shipped)
Replaces the old "Librarian (Ollama)" plan. Fact management done in supermemory via LLM is implemented here using **rule-based logic** over markdown + sqlite — zero model loading, touching nothing on the hot path:

- **Recency weight** (`context.py`): Relevance score is multiplied by freshness (half-life 120 days, base 0.5). Between two equally relevant notes, the newer one ranks higher; the older one is demoted. Pure date math, ms.
- **Temporal supersession** (`note.py` + `writer.py`): `mnemo write --supersedes <id,...>` writes new note and marks older ones with `status: superseded` + `superseded_by`. Old notes stay on disk (history) but drop from retrieval → "new invalidates old".
- **Ephemeral expire** (`context.py`): `note`/`daily` types drop from context package when exceeding shelf life (90 days); retained in vault and `search`.
- **Profile type** (`note.py`): Static facts about user/stack. Query-agnostic, pinned to top of every context/recall package.
- **Eval harness** (`bench.py` + `mnemo bench`): hit-rate / MRR / mean-recall. Measure and verify every quality change.

If LLM distillation is desired later, it can be added back as Phase 2; currently out of scope.

### 4.5 Front-End / Terminal (LAST)
Do **not** write a terminal from scratch. Fork an existing open base:
- **Wave Terminal** (open-source, AI-native) — closest existing foundation.
- **Tauri + xterm.js** — full control, moderate effort.
- **Ghostty / TUI** — lightweight alternative.
Connects to broker over `localhost`; mnemo acts as an extension.

---

## 5. Data Flow

**Read Path (hot, every prompt) — target <100ms:**
```
user types
  → injection (hook/terminal) queries broker: /context?cwd=…&q=…
  → broker: query embed (warm) + sqlite FTS/vector → top-k notes
  → package to token budget → return
  → prepended to AI prompt → AI answers
```
ZERO LLM calls.

**Write Path (cold, rare, background):**
```
session ends / note changes
  → added to librarian queue (debounced)
  → Ollama loads → distill/summary/link → write draft note → update index
  → Ollama unloads after keep_alive
```
User never waits.

---

## 6. Performance Design

| Task | Time | Path |
|---|---|---|
| FTS query | ~1–5ms | hot |
| query embed (model in RAM) | ~10–30ms | hot |
| vector search (hundreds of notes) | ~1–5ms | hot |
| packaging | ~1ms | hot |
| **hot path total** | **<50ms** | per prompt |
| cold spawn + model load | 1–3s | **avoided** |
| distill/summary (Ollama 3B) | several seconds | background |

Sole source of slowness is cold start. Solution: **resident hot daemon** — model loaded once, all subsequent queries hot.

---

## 7. Resource (RAM) Design

| Component | RAM | Continuous? |
|---|---|---|
| broker process | ~30–50MB | yes |
| embedding model (bge-small ONNX) | ~150–250MB | yes (small) |
| sqlite index | a few MB (mmap) | yes |
| **broker total** | **~250MB** | one browser tab |
| Ollama small model (3B) | 2–3GB | **NO — only during distillation** |

Tiers:
- **Tier A (minimal, ~50MB):** No embedder, pure FTS retrieval. Comfortable even on legacy hardware.
- **Tier B (recommended, ~250MB):** + resident embedder. Good relevance.
- **Tier C:** Large reranker — RAM increases, marginal gain → **skip**.

Rule: Small embedder stays warm; large LLM stays lazy/on-demand. Dreaded 4–8GB never stays continuously resident.

---

## 8. "No Recall Needed" Experience

Before: Single recall block at session start; manual search if needed mid-session; none if MCP not registered. (Exactly today's pain point.)

After: On every prompt, broker silently appends relevant decisions/plan/tasks. You say "continue according to that UID plan"; broker has already placed `uid-migration-plan-full` into context. Distiller turns new decisions into notes in the background → memory feeds itself.

---

## 9. Technology Choices and Rationale

| Layer | Choice | Rationale |
|---|---|---|
| Core | mnemo (existing) | ready, AI-agnostic, portable markdown |
| Index | sqlite + FTS5 (+ sqlite-vec) | zero server, fast, portable |
| Embedding | fastembed / bge-small (ONNX) | local, fast, small RAM footprint |
| Quality | mechanical rules (recency/supersede/expire) | no LLM, ms, dependency-free |
| ~~Local LLM~~ | ~~Ollama~~ → **dropped** | mechanical quality layer sufficient (§4.4) |
| Broker | resident Python daemon + localhost API | model stays warm, front-end independent |
| Injection | Claude Code hook (UserPromptSubmit) | works without writing a terminal |
| Terminal | Wave fork / Tauri+xterm.js | don't write terminal from scratch |

---

## 10. Roadmap (Phases)

### Phase 0 — Cleanup + `context` MVP · active
Measure retrieval hypothesis before moving to broker.
- [x] `mnemo context <query>`: Package MOC + decision/lesson/reference summaries within token budget.
- [ ] Register mnemo MCP server (`claude mcp add --scope user`).
- [ ] Refresh tool: clean broken `mnemofish` residue, install `0.2.1 + [mcp]` from repo.
- [x] `context` benchmark **harness** shipped: `mnemo bench <cases.json>` → hit-rate / MRR / mean-recall (`bench.py`). Remaining: populate cases file with 10 real prompts.
- **Acceptance:** Correct UID/STPM context arrives without manual search; noise and token budget measured.

### Phase 0.5 — Quality Layer (supermemory-derived) · ✅ shipped 2026-06-25
Missing retrieval quality features identified from supermemory comparison (§14) — all without LLM, 40 tests green:
- [x] **Eval harness** (`bench.py`, `mnemo bench`).
- [x] **Recency weighting** — context ranking blended with freshness.
- [x] **Profile type** — static facts pinned to every package.
- [x] **Temporal supersession** — `write --supersedes`, `status: superseded`.
- [x] **Ephemeral expire** — old `note`/`daily` drop from context.
- **Acceptance:** Hit-rate/MRR measurable against baseline; conflicting decisions hidden automatically.

### Phase 1 — Injection / Broker Decision · upcoming
- [ ] `UserPromptSubmit` hook → prepend `mnemo context` output to every prompt.
- [ ] If CLI cold start is noticeable, resident broker daemon: `localhost /context`, warm embedder, Tier A→B.
- **Acceptance:** No manual recall needed in new Claude Code session; daemon added only if measurement requires it.

### Phase 2 — Librarian (LLM Writing Automation) · ❌ DROPPED (2026-06-25)
Ollama distiller plan cancelled. Core problem (conflict/expiration) solved mechanically in Phase 0.5. Will reconsider only if LLM-only requirement "session → automatic decision distillation" re-emerges — currently out of scope.

### Phase 3 — Terminal Front-End · last
- [ ] Evaluate Wave fork vs Tauri+xterm.js, choose one.
- [ ] Connect to broker; project/path selector + memory dashboard.
- [ ] Direct context injection into embedded chat.
- **Acceptance:** Open project in terminal, AI operates with automated memory.

---

## 11. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Local model picks bad notes → noise | Relevance threshold + hard token budget; don't inject if irrelevant |
| Auto-distill generates wrong decision | `status: draft`; mechanical tasks (linking) auto, decision extraction approved |
| Per-prompt latency | No LLM on hot path; resident warm embedder; cache |
| RAM bloating | Large LLM on-demand + keep_alive; Tier A fallback |
| Terminal scope explosion | No scratch builds; fork ready base; last phase |
| Vault privacy (private repo) | mnemo already warns if private git missing; broker localhost only |

---

## 12. What Exists Today vs What's New (Honest Scope)

**Exists:** Vault, sqlite index, embedding infrastructure (`Embedder`), MCP server (`serve`), recall hook, project detection, FTS+vec search, portability (git/zip), `context` package, **+ quality layer** (bench / recency / profile / supersession / expire — Phase 0.5, shipped).

**To be written:** Resident broker daemon + localhost API, UserPromptSubmit injection hook, terminal front-end.

**Dropped:** Ollama librarian (LLM distill) — replaced by mechanical quality layer.

---

## 13. Decision Points Pending

1. **Start:** Begin Phase 0 now (3 fixes + broker skeleton first)?
2. **Retrieval Tier:** ~~Tier A or Tier B?~~ → **DECISION: Tier B** (resident embedder, ~250MB, good relevance). 2026-06-23.
3. ~~**Librarian Aggressiveness**~~ → Closed: LLM librarian dropped (§4.4, Phase 2).
4. **Terminal Base:** Wave fork or Tauri+xterm.js? (To be clarified in Phase 3.)

---

## 14. Supermemory Comparison (Why We Evolved)

[supermemory](https://github.com/supermemoryai/supermemory) (27.5k★) is a mature memory engine. Instead of using both (dual-write/drift risk), we took what it **does well that we lacked** and adapted it to mnemo's identity (markdown + push + local). What we excluded was deliberate.

| Strong in supermemory | How it landed in mnemo | Status |
|---|---|---|
| Fact extraction + conflict resolution (new invalidates old) | temporal supersession (`--supersedes`, `status`) | ✅ mechanical |
| Auto-expire (irrelevant info drops) | ephemeral expire (`note`/`daily` shelf life) | ✅ |
| Profile (static facts ~50ms) | `profile` type, pinned to package | ✅ |
| Recency-aware retrieval | recency decay weighting | ✅ |
| Benchmark (LongMemEval #1) | `mnemo bench` eval harness | ✅ |
| LLM distillation | — | ❌ out of scope (mechanical sufficient) |
| Connectors (Gmail/Drive/Notion) | — | ❌ scope explosion |
| Multimodal (PDF/OCR/video) | — | ❌ not our identity |

Preserved distinction: supermemory uses Postgres/binary store + LLM; we adopted its *behavior*, **not its store** — markdown single source of truth, zero LLMs.

---

*This report distills session decisions. Phase 0.5 (quality layer) applied; next decision is broker daemon (Phase 1) vs cases file + benchmark.*

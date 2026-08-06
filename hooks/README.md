# mnemo hooks — auto-recall (read) + auto-save (write)

Two loops close the memory cycle:

- **Auto-recall (PUSH/read)** — a `SessionStart` hook injects relevant memory
  into context **before** the model does anything. No asking required.
- **Auto-save (controlled WRITE)** — `PostToolUse` + `Stop` hooks nudge the
  model to write **one atomic note per session**, but only after real work and
  green tests, so memory never fills with junk.

An MCP tool is *pull* (the model must choose to search/write); these hooks are
*push*.

## How it works

```
session starts
   └─► Claude Code runs the SessionStart hook
          └─► mnemo recall --hook --reindex --project-dir "$CLAUDE_PROJECT_DIR"
                 ├─ reindex   : pick up any vault changes (git pull, edits)
                 ├─ detect project : git remote slug → folder name
                 └─ emit JSON : { hookSpecificOutput.additionalContext: <recall block> }
          └─► Claude Code adds that block to context
   └─► model now knows the project's map + recent decisions + past lessons
```

The recall block is token-disciplined: **summaries only**, each with an id the
model can expand with `mnemo get <id>` when it needs the full note.

## Auto-save (the write loop)

Auto-recall reads; nothing writes back unless you do it by hand. `auto_save.py`
closes that gap **without junking memory** — no blind auto-write, no LLM in the
hook.

```
PostToolUse (every tool)        Stop (turn boundary)
  ├─ Edit/Write   → dirty         ├─ stop_hook_active? → allow (no re-block)
  ├─ ran tests    → test_ran      ├─ already saved / nudged? → allow
  │   exit != 0   → test_failed   ├─ not dirty?      → allow (no real work)
  └─ mnemo write  → saved         ├─ test_failed?    → allow (don't save red)
        (per-session state)       └─ else → BLOCK once:
                                       "save ONE atomic note, or reply NOMEM"
                                          └─ model summarizes → memory_write
                                             → next Stop sees `saved` → allow
```

Why it stays clean:

- **Gated:** fires only when code changed **and** tests aren't failing.
- **Once per session:** blocks at most one turn (`nudged` + `stop_hook_active`).
- **Model proposes, human verifies:** MCP writes become deduped drafts and stay
  outside retrieval until `mnemo verify <id> --sources <evidence>` promotes them.
  The model can still reply `NOMEM` when nothing is worth keeping.

Per-session state lives in a small JSON file under the OS temp dir
(`mnemo-autosave/<session_id>.json`).

## Install

1. Put `mnemo` on PATH:
   ```bash
   uv tool install mnemofish        # or: pipx install mnemofish
   ```
2. Point it at your memory vault (a private git repo of markdown):
   - either pass `--vault <path>` in the hook command (see `settings.example.json`), or
   - set `MNEMO_VAULT` in your environment.
3. Copy the hook blocks from `settings.example.json` into your Claude Code
   settings (`<project>/.claude/settings.json` or `~/.claude/settings.json`),
   fixing the vault path. `SessionStart` alone gives you auto-recall; add the
   `PostToolUse` + `Stop` blocks for auto-save (`python` must be on PATH, and the
   path `$CLAUDE_PROJECT_DIR/hooks/auto_save.py` must resolve — or point it at an
   absolute copy of the script).

## Matchers

`SessionStart` fires for `startup`, `resume`, `clear`, `compact`. The example
uses `startup`; add more entries (or a separate matcher) if you also want recall
on `/clear` or `--resume`.

## Verify

```bash
mnemo --vault <path> recall --reindex --project-dir <your-project-dir>
```

If that prints a recall block, the hook will inject the same block (wrapped in
JSON) at session start.

## Other AIs

Editors without SessionStart hooks (e.g. Cursor) use the **MCP server** instead
(pull). Both front-ends read the same vault. The MCP server lands in F3.

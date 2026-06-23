# mnemo hooks — auto-recall (PUSH)

This is the part that closes the read loop. An MCP tool is *pull* (the model
must choose to search). A SessionStart hook is *push*: it runs every time a
session starts and injects the relevant memory into context **before** the
model does anything — no asking required.

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

## Install

1. Put `mnemo` on PATH:
   ```bash
   uv tool install mnemo        # or: pipx install mnemo
   ```
2. Point it at your memory vault (a private git repo of markdown):
   - either pass `--vault <path>` in the hook command (see `settings.example.json`), or
   - set `MNEMO_VAULT` in your environment.
3. Copy the `SessionStart` block from `settings.example.json` into your Claude
   Code settings (`<project>/.claude/settings.json` or `~/.claude/settings.json`),
   fixing the vault path.

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

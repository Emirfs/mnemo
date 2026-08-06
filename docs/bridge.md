# Multi-AI bridge

`mnemo bridge` packages the objective and relevant memory summaries into one
provider-neutral task envelope. External AI CLIs receive analysis-only work:

- Claude: safe mode, plan permission mode, tools disabled, no persisted session.
- Codex: read-only sandbox, no approvals, ephemeral session, user rules ignored.
- Antigravity: plan mode and terminal sandbox.
- Oh My Pi: all tools, rules, skills, extensions, LSP, and sessions disabled.
- OpenCode: pure one-shot run, auto-approval disabled, isolated empty directory.
- Legacy Gemini CLI remains available only for compatibility; Antigravity is preferred.

All providers run from an isolated temporary directory. The project path is
used only for Mnemo project detection and is not placed in the task envelope.
Objective and memory strings are explicitly marked as untrusted data.

```powershell
mnemo --vault "C:/path/to/vault" bridge claude `
  "Review the current authentication decision" `
  --project my-app
```

Results contain the full task envelope and provider response as JSON. A failed
or unauthenticated provider returns `success: false`; its output is never run as
a command and never written into verified memory.

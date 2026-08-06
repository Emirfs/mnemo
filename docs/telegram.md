# Telegram bot

The Telegram front-end is deliberately read-only. It exposes only:

- `/status`
- `/recall <query>`
- `/ask <claude|codex|gemini> <objective>`
- `/propose codex <objective>`
- `/approve <proposal-id>`
- `/reject <proposal-id>`
- `/proposal <proposal-id>`
- `/flow <objective>`
- `/help`

External AI analysis uses the isolated bridge policy described in `bridge.md`.
Write proposals expire after 15 minutes, are bound to the proposing Telegram
user, and can run only once. Approved Codex work runs in a new temporary Git
worktree and branch. It never merges, commits, pushes, or changes the main worktree.

`/flow` runs the complete guarded chain: Claude read-only analysis, phone
proposal, approved Codex worktree implementation, Claude diff review, then a
Qwen `draft + inferred` memory candidate. Verification and merge remain manual.

## Setup

Create a bot with Telegram's BotFather. Keep the token out of command history and
repository files:

```powershell
[Environment]::SetEnvironmentVariable(
  "MNEMO_TELEGRAM_TOKEN", "<bot-token>", "User"
)
[Environment]::SetEnvironmentVariable(
  "MNEMO_TELEGRAM_USERS", "<your-numeric-user-id>", "User"
)
```

Open a new terminal, then run:

```powershell
mnemo --vault "C:/path/to/vault" telegram `
  --project my-app `
  --repo "C:/path/to/my-app"
```

The allowlist is mandatory. Group messages and unauthorized users are ignored.
Use the same project value as the repos' `.mnemo-project` marker.

Omit `--repo` to keep the bot strictly read-only. Repositories must be clean
before an approved worktree can be created. Finished worktrees remain available
for manual review; no remote merge or deletion command is exposed.

# Telegram bot

The Telegram front-end is deliberately read-only. It exposes only:

- `/status`
- `/recall <query>`
- `/ask <antigravity|claude|codex|omp|opencode> <objective>`
- `/propose codex <objective>`
- `/approve <proposal-id>`
- `/reject <proposal-id>`
- `/proposal <proposal-id>`
- `/flow <objective>`
- `/diff <proposal-id>`
- `/patch <proposal-id>`
- `/distill <session text>`
- `/merge <completed-proposal-id>`
- `/repos`
- `/use <route-alias>`
- `/feedback <task-id> <good|bad> [note]`
- `/feedback-stats`
- `/help`

External AI analysis uses the isolated bridge policy described in `bridge.md`.
Write proposals expire after 15 minutes, are bound to the proposing Telegram
user, and can run only once. Approved Codex work runs in a new temporary Git
worktree and branch. It never merges, commits, pushes, or changes the main worktree.

`/flow` runs the complete guarded chain: Claude read-only analysis, phone
proposal, approved Codex worktree implementation, Claude diff review, then a
Qwen `draft + inferred` memory candidate. Verification and merge remain manual.

Proposal messages include inline **Approve** and **Reject** buttons. `/diff`
returns bounded text; `/patch` downloads the complete Git patch. `/distill`
uses local Qwen to create a draft-only memory and cannot activate it.

`/merge` creates a second one-time approval. After approval, Mnemo verifies the
binary patch with `git apply --check` and applies it to a clean main worktree.
Changes remain uncommitted and are never pushed. New files are included through
Git intent-to-add in the task worktree.

For multiple repositories, pass `--repos routes.json`:

```json
{
  "mnemo": {"project": "mnemo", "repo": "C:/Projects/mnemo"},
  "stpm-fc": {"project": "stm32-rf-ota", "repo": "C:/Projects/STPM_FC_BOOTLOADER"}
}
```

Use `/repos` and `/use stpm-fc` to switch scope. Every proposal stores the
resolved repository path, so later route changes cannot redirect an approval.

Successful `/ask` responses include **Good** and **Bad** buttons. Human labels
are bound to the Telegram user and stored locally for evaluation or future LoRA
training. Export labelled rows with `mnemo feedback-export training.jsonl`.

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

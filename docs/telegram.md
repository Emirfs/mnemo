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
- `/research <topic>`
- `/research-config [rounds=0|1|2] [providers=name,name]`
- `/research-answer <id> <answers>`
- `/research-status <id>`
- `/research-result <id>`
- `/research-cancel <id>`
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

`/research` starts a persistent background session without blocking Telegram
polling. Local Qwen asks up to three questions only when critical scope is
missing. Five isolated providers then research in parallel and perform at most
two cross-critique rounds. Session deadline is 15 minutes; each provider gets
one attempt per round. Models cannot extend deadline or round count.

Research providers may access public web sources but cannot access project
files, vault files, shell tools, write tools, or credentials. Cited URLs are
checked separately; private and loopback addresses are rejected. Final reports
distinguish verified from unverified sources and remain available through
`/research-result`. Bot also sends report when background session finishes.

Use `/research-config` to inspect persistent per-user defaults. For example,
`/research-config rounds=1 providers=claude,codex,omp` selects three providers
and one cross-critique round. `rounds=0` runs only initial parallel research;
the mechanical maximum remains two rounds.

Completion notifications contain only a short preview. `/research-result`
returns the same preview and attaches the full Markdown record. Every terminal
research session is archived in the Mnemo vault as one `reference` note with
the request, configuration, final report, sources, and all provider
conversations. Automatic archives remain `draft + inferred` until verified.
Provider conversation excerpts are capped in Markdown for readability; complete
raw outputs and provider errors remain in `research.sqlite`. OpenCode receives
large research prompts through a temporary attachment, avoiding Windows command
line length limits.

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

Install hidden user-level startup after token and allowlist environment variables
are configured:

```powershell
mnemo --vault "C:/path/to/vault" telegram-autostart install `
  --project my-app --repos "C:/path/to/routes.json"
```

Use `telegram-autostart status` or `telegram-autostart uninstall` to inspect or
remove it. Launcher contains no token; it inherits user environment at login.

Omit `--repo` to keep the bot strictly read-only. Repositories must be clean
before an approved worktree can be created. Finished worktrees remain available
for manual review; no remote merge or deletion command is exposed.

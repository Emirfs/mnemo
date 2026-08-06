# Telegram bot

The Telegram front-end is deliberately read-only. It exposes only:

- `/status`
- `/recall <query>`
- `/ask <claude|codex|gemini> <objective>`
- `/help`

It has no shell, file-write, delete, verification, or memory-write command.
External AI calls use the isolated bridge policy described in `bridge.md`.

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
mnemo --vault "C:/path/to/vault" telegram --project my-app
```

The allowlist is mandatory. Group messages and unauthorized users are ignored.
Use the same project value as the repos' `.mnemo-project` marker.

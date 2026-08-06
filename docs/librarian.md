# Local librarian

The optional librarian uses Ollama to extract one durable candidate from session
text. It can only create `draft + inferred` notes; it cannot verify facts or
replace active memories.

## Setup

```powershell
winget install Ollama.Ollama
ollama pull qwen3:4b
```

Qwen3 4B is the default because it has good multilingual structured output at a
small footprint. Mnemo sends `think: false`, temperature `0`, a 4096-token
context, and `keep_alive: 0s`, so the model unloads after each cold-path task.

## Extract a candidate

```powershell
Get-Content session.txt | mnemo --vault "C:/path/to/vault" distill `
  --project my-app `
  --source "session:2026-08-06" `
  --body -
```

Inspect without writing:

```powershell
mnemo --vault "C:/path/to/vault" distill `
  --project my-app `
  --source "manual:review" `
  --dry-run `
  --body "Decision: keep tokens short-lived because long-lived tokens leaked."
```

If accepted, attach concrete evidence:

```powershell
mnemo --vault "C:/path/to/vault" verify <id> `
  --sources "commit:abc123,test:pytest"
```

## GPU fallback

If an older NVIDIA driver reports `PTX was compiled with an unsupported
toolchain`, update the driver. Temporary CPU fallback on Windows:

```powershell
[Environment]::SetEnvironmentVariable(
  "OLLAMA_LLM_LIBRARY", "cpu_avx2", "User"
)
```

Restart Ollama after changing the library. CPU fallback is slower but only runs
during distillation; retrieval remains local SQLite and does not call the LLM.

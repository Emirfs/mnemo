#!/usr/bin/env python3
"""mnemo auto-save — the controlled write loop (the SAVE side of memory).

Auto-recall (the SessionStart hook) is the *read* loop. This is the *write*
loop — but controlled, so memory never fills with junk:

  * **PostToolUse** tracks per-session signals: code changed (Edit/Write), a
    test command ran, a test failed, a memory note was already written.
  * **Stop** fires at a turn boundary. If meaningful work happened (code changed
    AND no test is failing) and nothing was saved yet, it blocks the stop
    *once* and asks the model to distil the session into ONE atomic note via
    `memory_write` / ``mnemo write`` — or reply ``NOMEM`` if nothing is worth it.

The model is the summariser (free, already in context) and the final junk
filter. We only ever nudge once per session, gated on green tests. No LLM runs
in the hook itself.

One script handles both events; it dispatches on ``hook_event_name``. State is
a tiny JSON file per session under the OS temp dir.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

# Commands that count as "ran the tests".
_TEST_RE = re.compile(
    r"\b(pytest|tox|nox|unittest|jest|vitest|mocha|rspec|phpunit|ctest"
    r"|go\s+test|cargo\s+test|mvn\s+test|gradle\s+test|dotnet\s+test"
    r"|make\s+test|(npm|yarn|pnpm)\s+(run\s+)?test)\b",
    re.I,
)
# A note was written this session (CLI or MCP tool).
_WRITE_CMD_RE = re.compile(r"\bmnemo\b.*\b(write|daily)\b")
_WRITE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
# Failure heuristic, used only when no exit code is available. Any failure
# marker means "treat as red" — better to skip a save than memorialise a broken
# session.
_FAIL_RE = re.compile(r"(FAILED|\bFAIL\b|Traceback|AssertionError|[1-9]\d*\s+failed|error:)")


def _state_path(session_id: str) -> Path:
    d = Path(tempfile.gettempdir()) / "mnemo-autosave"
    d.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "default")
    return d / f"{safe}.json"


def _load(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(p: Path, st: dict) -> None:
    try:
        p.write_text(json.dumps(st), encoding="utf-8")
    except Exception:
        pass


def _resp_text(r) -> str:
    if isinstance(r, str):
        return r
    if isinstance(r, dict):
        return " ".join(str(r.get(k, "")) for k in ("stdout", "stderr", "output", "content", "result"))
    return str(r)


def _exit_code(r):
    if isinstance(r, dict):
        for k in ("exit_code", "exitCode", "returnCode", "code", "status"):
            v = r.get(k)
            if isinstance(v, int):
                return v
    return None


def handle_post(data: dict, st: dict) -> dict:
    tool = data.get("tool_name", "") or ""
    ti = data.get("tool_input") or {}
    tr = data.get("tool_response")

    if tool in _WRITE_TOOLS:
        st["dirty"] = True
    if "memory_write" in tool:
        st["saved"] = True

    if tool == "Bash":
        cmd = str(ti.get("command", ""))
        if _WRITE_CMD_RE.search(cmd):
            st["saved"] = True
        if _TEST_RE.search(cmd):
            st["test_ran"] = True
            code = _exit_code(tr)
            if code is not None:
                failed = code != 0
            else:  # no exit code surfaced — any failure marker means red
                failed = bool(_FAIL_RE.search(_resp_text(tr)))
            # A later green run clears an earlier red one.
            st["test_failed"] = failed
    return st


_REASON = (
    "mnemo auto-save: this session changed code and tests are not failing, but "
    "no memory note was saved yet. Save EXACTLY ONE atomic note capturing the "
    "durable takeaway — a decision (why we chose X over Y), a lesson/gotcha, or "
    "a key reference — via the memory_write tool (or `mnemo write`). Rules: "
    "summary-only (1-2 sentences), set the project, pick type decision|lesson|"
    "reference, and prefer `supersedes` if it overrides an older note. Do NOT "
    "save file lists, routine edits, or anything re-derivable from the code. If "
    "nothing is worth remembering, reply with exactly NOMEM and stop."
)


def handle_stop(data: dict, st: dict) -> str | None:
    if data.get("stop_hook_active"):
        return None  # already inside a block cycle — never block again
    if st.get("nudged") or st.get("saved"):
        return None  # one nudge per session; nothing to do once saved
    if not st.get("dirty"):
        return None  # no meaningful work happened
    if st.get("test_failed"):
        return None  # don't ask to memorialise a red session
    st["nudged"] = True
    return _REASON


def main() -> int:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0
    event = data.get("hook_event_name", "")
    sp = _state_path(data.get("session_id", ""))
    st = _load(sp)

    if event == "PostToolUse":
        _save(sp, handle_post(data, st))
    elif event == "Stop":
        reason = handle_stop(data, st)
        _save(sp, st)
        if reason:
            print(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

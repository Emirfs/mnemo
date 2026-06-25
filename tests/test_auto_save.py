"""Tests for the auto-save hook (hooks/auto_save.py).

Driven as a subprocess the way Claude Code invokes it: JSON on stdin, JSON (or
nothing) on stdout. Each test uses a unique session id so the per-session state
files don't collide.
"""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "auto_save.py"


def run(event: dict) -> str:
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def post(sid: str, tool: str, **kw) -> None:
    run({"hook_event_name": "PostToolUse", "session_id": sid, "tool_name": tool, **kw})


def stop(sid: str, active: bool = False) -> dict | None:
    out = run({"hook_event_name": "Stop", "session_id": sid, "stop_hook_active": active})
    return json.loads(out) if out else None


def sid() -> str:
    return f"test-{uuid.uuid4()}"


def test_stop_allows_when_no_work():
    assert stop(sid()) is None


def test_stop_allows_when_dirty_but_no_save_mechanism_is_just_edits():
    # only edits, no tests run -> still eligible (testless session), should nudge
    s = sid()
    post(s, "Edit", tool_input={"file_path": "a.py"}, tool_response="ok")
    decision = stop(s)
    assert decision and decision["decision"] == "block"
    assert "atomic note" in decision["reason"]


def test_dirty_plus_green_tests_blocks_once_then_allows():
    s = sid()
    post(s, "Write", tool_input={"file_path": "a.py"}, tool_response="ok")
    post(s, "Bash", tool_input={"command": "pytest -q"}, tool_response={"exit_code": 0})

    first = stop(s)
    assert first and first["decision"] == "block"

    # second Stop in the same session must NOT block again (one nudge only)
    assert stop(s) is None


def test_failed_tests_suppress_save():
    s = sid()
    post(s, "Edit", tool_input={"file_path": "a.py"}, tool_response="ok")
    post(s, "Bash", tool_input={"command": "pytest"}, tool_response={"exit_code": 1})
    assert stop(s) is None


def test_green_run_after_red_clears_failure():
    s = sid()
    post(s, "Edit", tool_input={"file_path": "a.py"}, tool_response="ok")
    post(s, "Bash", tool_input={"command": "pytest"}, tool_response={"exit_code": 1})
    post(s, "Bash", tool_input={"command": "pytest"}, tool_response={"exit_code": 0})
    decision = stop(s)
    assert decision and decision["decision"] == "block"


def test_already_saved_via_cli_allows_stop():
    s = sid()
    post(s, "Edit", tool_input={"file_path": "a.py"}, tool_response="ok")
    post(s, "Bash", tool_input={"command": "pytest"}, tool_response={"exit_code": 0})
    post(s, "Bash", tool_input={"command": "mnemo --vault x write --type lesson --title y"}, tool_response="ok")
    assert stop(s) is None


def test_already_saved_via_mcp_tool_allows_stop():
    s = sid()
    post(s, "Edit", tool_input={"file_path": "a.py"}, tool_response="ok")
    post(s, "mcp__mnemo__memory_write", tool_input={"title": "x"}, tool_response="ok")
    assert stop(s) is None


def test_stop_hook_active_never_blocks():
    s = sid()
    post(s, "Edit", tool_input={"file_path": "a.py"}, tool_response="ok")
    assert stop(s, active=True) is None


def test_exit_code_absent_falls_back_to_output_text():
    s = sid()
    post(s, "Edit", tool_input={"file_path": "a.py"}, tool_response="ok")
    # no exit code; failure text -> treated as failed -> no nudge
    post(s, "Bash", tool_input={"command": "pytest"}, tool_response={"stdout": "1 failed, 0 passed"})
    assert stop(s) is None

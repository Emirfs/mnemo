from __future__ import annotations

import json
from pathlib import Path

import pytest

from mnemo.feedback import FeedbackStore


def test_feedback_is_user_bound_and_exportable(tmp_path: Path):
    with FeedbackStore(tmp_path / "feedback.sqlite") as store:
        store.record(
            task_id="task-1", user_id=12, provider="claude", project="p",
            objective="Review security", output="Safe answer",
        )
        with pytest.raises(ValueError, match="not found"):
            store.rate("task-1", 99, "good")
        store.rate("task-1", 12, "good", "Useful")
        assert store.stats() == {"total": 1, "good": 1, "bad": 0, "unrated": 0}
        out = tmp_path / "training.jsonl"
        assert store.export(out) == 1

    row = json.loads(out.read_text(encoding="utf-8"))
    assert row["rating"] == "good"
    assert row["objective"] == "Review security"

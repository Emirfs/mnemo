from __future__ import annotations

import json
import sqlite3
import threading
import time

import pytest

from mnemo.bridge import BridgeResult, TaskEnvelope
from mnemo.research import (
    PROVIDERS,
    ResearchEngine,
    ResearchStore,
    clarify_topic,
    verify_source,
)


class _Index:
    pass


@pytest.fixture(autouse=True)
def _empty_memory(monkeypatch):
    monkeypatch.setattr(
        "mnemo.research.build_envelope",
        lambda index, objective, project, **kwargs: TaskEnvelope(
            objective, project, mode=kwargs["mode"]
        ),
    )


def test_store_persists_and_owner_can_cancel(tmp_path):
    store = ResearchStore(tmp_path / "research.sqlite")
    session_id = store.create("topic", 7, "project", 900)

    assert store.get(session_id)["status"] == "queued"
    assert not store.cancel(session_id, 8)
    assert store.cancel(session_id, 7)
    assert store.get(session_id)["status"] == "cancelled"


def test_engine_runs_fixed_parallel_rounds_and_synthesis(tmp_path):
    calls = []
    lock = threading.Lock()

    def runner(provider, envelope, **kwargs):
        with lock:
            calls.append((provider, envelope.mode, kwargs["workdir"]))
        time.sleep(0.01)
        return BridgeResult(provider, True, output=f"finding from {provider}")

    store = ResearchStore(tmp_path / "research.sqlite")
    engine = ResearchEngine(
        _Index(), store, runner=runner, synthesizer=lambda *args: "final", duration=60
    )
    session_id = engine.create("compare systems", 7, "p")

    result = engine.run(session_id)

    assert result["status"] == "completed"
    assert result["report"] == "final"
    assert len(calls) == len(PROVIDERS) * 3
    assert all(mode == "research" for _, mode, _ in calls)
    assert len(store.contributions(session_id)) == 15


def test_engine_does_not_retry_failed_provider(tmp_path):
    counts = {provider: 0 for provider in PROVIDERS}

    def runner(provider, envelope, **kwargs):
        counts[provider] += 1
        if provider == "claude":
            raise RuntimeError("offline")
        return BridgeResult(provider, True, output="ok")

    engine = ResearchEngine(
        _Index(),
        ResearchStore(tmp_path / "research.sqlite"),
        runner=runner,
        synthesizer=lambda *args: "partial evidence report",
    )
    result = engine.run(engine.create("topic", 1))

    assert result["status"] == "partial"
    assert counts["claude"] == 1
    assert all(counts[provider] == 3 for provider in PROVIDERS if provider != "claude")


def test_clarification_is_capped_at_three(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            candidate = {"needs_clarification": True, "questions": ["1", "2", "3", "4"]}
            return json.dumps({"response": json.dumps(candidate)}).encode()

    def fake_urlopen(request, **kwargs):
        captured.update(json.loads(request.data.decode()))
        return Response()

    monkeypatch.setattr("mnemo.research.urllib.request.urlopen", fake_urlopen)
    assert clarify_topic("unclear") == ["1", "2", "3"]
    assert captured["format"]["properties"]["questions"]["maxItems"] == 3
    assert captured["options"]["num_ctx"] == 2048


def test_round_limit_is_mechanical(tmp_path):
    engine = ResearchEngine(_Index(), ResearchStore(tmp_path / "db"), rounds=99)
    assert engine.rounds == 2


def test_session_waits_for_clarification(tmp_path):
    engine = ResearchEngine(_Index(), ResearchStore(tmp_path / "db"))
    session_id = engine.create("topic", 1, questions=["Which market?"])

    assert engine.store.get(session_id)["status"] == "waiting_input"
    with pytest.raises(ValueError, match="requires clarification"):
        engine.run(session_id)

    assert not engine.store.answer(session_id, 2, "Europe")
    assert engine.store.answer(session_id, 1, "Europe")
    assert engine.store.get(session_id)["status"] == "queued"


def test_deadline_starts_when_research_runs(tmp_path, monkeypatch):
    store = ResearchStore(tmp_path / "db")
    engine = ResearchEngine(
        _Index(),
        store,
        runner=lambda provider, envelope, **kwargs: BridgeResult(provider, True, output="ok"),
        synthesizer=lambda *args: "report",
        duration=60,
        rounds=0,
    )
    session_id = engine.create("topic", 1)
    store.update(session_id, deadline=1)

    result = engine.run(session_id)

    assert result["status"] == "completed"
    assert result["deadline"] > time.time()


def test_source_verifier_rejects_private_addresses(monkeypatch):
    monkeypatch.setattr(
        "mnemo.research.socket.getaddrinfo",
        lambda *args: [(2, 1, 6, "", ("127.0.0.1", 80))],
    )

    verified, detail = verify_source("http://example.test/private")

    assert not verified
    assert detail == "non-public address"


def test_cancelled_session_cannot_be_claimed(tmp_path):
    store = ResearchStore(tmp_path / "db")
    engine = ResearchEngine(_Index(), store)
    session_id = engine.create("topic", 1)
    assert store.cancel(session_id, 1)

    result = engine.run(session_id)

    assert result["status"] == "cancelled"
    assert store.contributions(session_id) == []


def test_selected_providers_and_rounds_are_persisted(tmp_path):
    calls = []

    def runner(provider, envelope, **kwargs):
        calls.append(provider)
        return BridgeResult(provider, True, output="ok")

    store = ResearchStore(tmp_path / "db")
    engine = ResearchEngine(
        _Index(), store, runner=runner, synthesizer=lambda *args: "report"
    )
    session_id = engine.create(
        "topic", 1, providers=["claude", "codex"], rounds=1
    )

    result = engine.run(session_id)

    assert result["providers"] == ["claude", "codex"]
    assert result["max_rounds"] == 1
    assert calls.count("claude") == calls.count("codex") == 2
    assert set(calls) == {"claude", "codex"}


def test_user_research_preferences_are_validated(tmp_path):
    store = ResearchStore(tmp_path / "db")
    assert store.preferences(7) == {"providers": list(PROVIDERS), "rounds": 2}

    store.set_preferences(7, ["codex", "claude", "codex"], 1)

    assert store.preferences(7) == {"providers": ["codex", "claude"], "rounds": 1}
    with pytest.raises(ValueError, match="rounds"):
        store.set_preferences(7, ["claude"], 3)


def test_store_migrates_existing_research_database(tmp_path):
    path = tmp_path / "db"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE research_sessions ("
            "id TEXT PRIMARY KEY, user_id INTEGER, project TEXT, topic TEXT, "
            "questions TEXT, answers TEXT, status TEXT, created REAL, deadline REAL, "
            "round INTEGER, report TEXT, error TEXT)"
        )

    ResearchStore(path)

    with sqlite3.connect(path) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(research_sessions)")}
    assert {"providers", "max_rounds", "note_id"} <= columns


def test_synthesis_failure_is_kept_out_of_user_report(tmp_path):
    engine = ResearchEngine(
        _Index(),
        ResearchStore(tmp_path / "db"),
        runner=lambda provider, envelope, **kwargs: BridgeResult(
            provider, True, output="useful specialist finding"
        ),
        synthesizer=lambda *args: (_ for _ in ()).throw(TimeoutError("secret timeout")),
        rounds=0,
    )

    result = engine.run(engine.create("topic", 1))

    assert result["status"] == "partial"
    assert result["error"] == "secret timeout"
    assert "secret timeout" not in result["report"]
    assert "useful specialist finding" in result["report"]

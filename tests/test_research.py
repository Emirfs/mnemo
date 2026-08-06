from __future__ import annotations

import json
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
    assert counts == {provider: 3 for provider in PROVIDERS}


def test_clarification_is_capped_at_three(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            candidate = {"needs_clarification": True, "questions": ["1", "2", "3", "4"]}
            return json.dumps({"response": json.dumps(candidate)}).encode()

    monkeypatch.setattr("mnemo.research.urllib.request.urlopen", lambda *args, **kwargs: Response())
    assert clarify_topic("unclear") == ["1", "2", "3"]


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

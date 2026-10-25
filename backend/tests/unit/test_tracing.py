"""LangSmith: forced off, opt-in only, never the key (opt-in-tracing spec; docs/ai/02 B11; NFR-13; ai-foundation D30;
tasks 6.5, 6.6). No socket is opened: the traced client is a stub."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from horizon import tracing
from horizon.config import load_config
from tests.conftest import Api


def test_a_stray_switch_is_forced_off() -> None:
    env = {"LANGCHAIN_TRACING_V2": "true", "LANGSMITH_TRACING": "true"}
    tracing.guard_env(env)
    assert all(env[k] == "false" for k in tracing.SWITCHES)


def test_opting_in_leaves_the_switches_alone() -> None:
    env = {"HORIZON_LANGSMITH": "1", "LANGSMITH_TRACING": "true"}
    tracing.guard_env(env)
    assert env["LANGSMITH_TRACING"] == "true"


def test_the_test_process_runs_with_tracing_off() -> None:
    import os

    assert all(os.environ.get(k) == "false" for k in tracing.SWITCHES)   # conftest called guard_env()


def test_opt_in_without_the_package_logs_an_error_and_stays_off(caplog: pytest.LogCaptureFixture,
                                                                monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tracing, "package_available", lambda: False)
    with caplog.at_level(logging.ERROR, logger="horizon.tracing"):
        on = tracing.startup_log({"HORIZON_LANGSMITH": "1", "LANGSMITH_API_KEY": "ls-test"})
    assert on is False and any("tracing" in r.getMessage() and r.levelno == logging.ERROR for r in caplog.records)
    assert "LANGSMITH_API_KEY" in tracing.status({"HORIZON_LANGSMITH": "1"})[1]


class StubClient:
    def __init__(self) -> None:
        self.runs: list[dict[str, Any]] = []

    def create_run(self, **kw: Any) -> None:
        self.runs.append({"start": kw})

    def end_run(self, **kw: Any) -> None:
        self.runs.append({"end": kw})


async def test_traced_inputs_never_hold_the_key(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    stub = StubClient()
    monkeypatch.setattr(tracing.TRACER, "enabled", True)
    monkeypatch.setattr(tracing.TRACER, "client", stub)
    await api.set_key("sk-or-test-trace-0001")
    r = await api.post("/api/v1/settings/test-model", {"role": "chat"})
    assert r.status_code == 200
    with tracing.TRACER.traced("x", {"Authorization": "Bearer sk-or-test-trace-0001", "messages": ["hi"]}) as out:
        out["text"] = "ok"
    dumped = json.dumps(stub.runs).lower()
    assert stub.runs and "sk-or-test-trace" not in dumped and "authorization" not in dumped
    assert any(run.get("start", {}).get("name") == "chat:probe" for run in stub.runs)


def test_off_sends_nothing() -> None:
    stub = StubClient()
    t = tracing.Tracer(enabled=False, client=stub)
    with t.traced("x", {"messages": ["hi"]}) as out:
        out["text"] = "ok"
    assert stub.runs == []


def test_config_reads_the_capture_and_tracing_switches(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("HORIZON_CAPTURE_AI_CALLS=1\nHORIZON_LANGSMITH=1\nLANGSMITH_API_KEY=ls-test-123\n",
                                   encoding="utf-8")
    cfg = load_config({"HORIZON_ROOT": str(tmp_path)})
    assert cfg.capture_ai_calls is True and cfg.langsmith is True
    assert cfg.langsmith_key is not None and cfg.langsmith_key.get_secret_value() == "ls-test-123"
    assert "ls-test-123" not in repr(cfg)
    off = load_config({"HORIZON_ROOT": str(tmp_path / "none")})
    assert off.capture_ai_calls is False and off.langsmith is False and off.langsmith_key is None

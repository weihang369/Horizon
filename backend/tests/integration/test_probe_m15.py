"""The store probe and `horizon eval all` (images-music design D13; response-store "A probe never sends";
evaluation-harness "The store probe and `all`"). Test mode: the in-process fake, the socket guard on."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from horizon.config import load_config
from horizon.evals.runner import Options, Runner
from horizon.evals.store import ResponseStore
from horizon.gateway.context import call_ctx
from horizon.gateway.errors import ProviderError
from tests.conftest import Api

SATURDAY = datetime(2026, 10, 3, 3, 0, tzinfo=UTC)
STATE = {"quoted_message": "hi"}
STORED = {"q": {"type": "noul", "instructions": "stored?", "criteria": {"true": "yes", "false": "no"}}}
NEW = {"q": {"type": "noul", "instructions": "new?", "criteria": {"true": "yes", "false": "no"}}}


def files(root: Path) -> list[str]:
    return sorted(p.name for p in root.glob("*.json")) if root.is_dir() else []


async def rows(api: Api) -> int:
    async with api.rt.db.read() as conn:
        return int((await conn.execute(text("SELECT COUNT(*) FROM usage_records WHERE is_seed = 0"))).scalar_one())


async def test_a_probe_serves_hits_and_stops_at_a_miss_before_anything_is_sent(api: Api, tmp_path: Path) -> None:
    await api.set_key()
    gw = api.rt.gateway
    gw.store = ResponseStore.eval_view(tmp_path, None)
    stored = await gw.decide(STATE, STORED, call_ctx("eval_judge"))   # a normal run stores one answer
    fake = api.rt.fake
    assert fake is not None
    sent, before, kept = fake.counts["decisions"], await rows(api), files(tmp_path)
    probe = ResponseStore.eval_view(tmp_path, None)
    probe.probe = True
    gw.store = probe
    again = await gw.decide(STATE, STORED, call_ctx("eval_judge"))
    assert again.answers == stored.answers and again.generation_id == "store"   # a hit is served
    missed = await gw.decide(STATE, NEW, call_ctx("eval_judge"))
    assert missed.answers == {} and missed.generation_id == "probe"            # no answer: the caller falls back
    assert fake.counts["decisions"] == sent and await rows(api) == before   # nothing sent, no ledger row
    assert files(tmp_path) == kept                                          # nothing stored
    assert [m["kind"] for m in probe.misses] == ["jev"] and probe.misses[0]["usd"] > 0 and probe.hits == 1


async def test_a_probed_chat_miss_is_an_empty_reply_and_vectors_fail(api: Api, tmp_path: Path) -> None:
    from horizon.gateway.chat import ChatRequest

    await api.set_key()
    probe = ResponseStore.eval_view(tmp_path, None)
    probe.probe = True
    api.rt.gateway.store = probe
    fake = api.rt.fake
    assert fake is not None
    sent = dict(fake.counts)
    req = ChatRequest(model="deepseek/deepseek-v4.1-flash", messages=[{"role": "user", "content": "hi"}], max_tokens=16)
    out = await api.rt.gateway.chat_complete(req, call_ctx("eval_judge", category="chat"))
    assert out.content == "" and out.generation_id == "probe"
    chunks = [c async for c in api.rt.gateway.chat_stream(req, call_ctx("eval_judge", category="chat"))]
    assert [c.finish_reason for c in chunks] == ["stop"] and not any(c.content for c in chunks)
    with pytest.raises(ProviderError):
        await api.rt.gateway.embed_batch(["hi"], call_ctx("eval_judge", category="embedding"),
                                         model="openai/text-embedding-3-small")
    assert dict(fake.counts) == sent and [m["kind"] for m in probe.misses] == ["chat", "chat", "embeddings"]


def runner(tmp: Path) -> tuple[Runner, list[str]]:
    out: list[str] = []
    cfg = load_config({"HORIZON_DATA_DIR": str(tmp), "HORIZON_TEST": "1"})
    return Runner(cfg, stdin=lambda _p: "n", out=out.append, now=lambda: SATURDAY), out


async def test_a_probed_suite_reports_and_spends_logs_and_marks_nothing(tmp_path: Path) -> None:
    r, out = runner(tmp_path)
    assert await r.run(Options("decisions", probe=True, limit=3)) == 0   # no prompt: the stdin "n" is never read
    p = r.last_probe
    assert p is not None and p.misses > 0 and p.hits == 0 and p.one_shot and p.would_pay_usd > 0
    (run,) = [d for d in (tmp_path / "evals").iterdir() if d.is_dir()]
    report = (run / "naive" / "report.md").read_text(encoding="utf-8")
    assert "## Probe (naive)" in report and "Nothing was sent or spent" in report
    assert not (tmp_path / "evals" / "spend.jsonl").exists() and not (run / ".keep").exists()
    assert not (tmp_path / "evals" / "decisions-measured.json").exists()     # no item marked measured
    assert files(tmp_path / "cache") == []                                   # the fake's answers never stored
    assert any("probe" in line for line in out)


@pytest.mark.parametrize("suite", ["transcript", "latency", "canary", "smoke", "debate-history"])
async def test_never_probed(tmp_path: Path, suite: str) -> None:
    r, out = runner(tmp_path)
    assert await r.run(Options(suite, probe=True)) == 2
    assert "never probed" in out[-1] and not (tmp_path / "evals").exists()


def test_all_lists_every_probed_suite_under_both_profiles(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    from horizon.evals import cli, suites

    monkeypatch.setenv("HORIZON_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("HORIZON_TEST", "1")
    monkeypatch.setattr(suites, "SUITES", {"decisions": suites.SUITES["decisions"],
                                           "transcript": suites.SUITES["transcript"]})
    assert cli._all(argparse.Namespace(limit=2)) == 0
    shown = capsys.readouterr().out
    assert "| decisions | agent |" in shown and "| decisions | naive |" in shown
    assert "transcript" not in shown                                         # a generator is never probed
    (written,) = list((tmp_path / "evals").glob("all-*.md"))
    assert "nothing sent, nothing spent" in written.read_text(encoding="utf-8")
    assert not (tmp_path / "evals" / "spend.jsonl").exists()


class _Unsettled:
    """A chained suite whose session never settles on the probe's empty answers (8.2: a free debate)."""

    name = "decisions"

    def __init__(self, real: Any) -> None:
        self.real = real

    def __getattr__(self, attr: str) -> Any:
        return getattr(self.real, attr)

    async def run(self, env: Any, plan: Any) -> Any:
        raise TimeoutError("session ses_x did not settle within 60 s")


async def test_a_probed_session_that_never_settles_still_reports(tmp_path: Path, monkeypatch: Any) -> None:
    from horizon.evals import suites

    monkeypatch.setitem(suites.SUITES, "decisions", _Unsettled(suites.SUITES["decisions"]))
    r, _ = runner(tmp_path)
    assert await r.run(Options("decisions", probe=True, limit=2)) == 0
    assert r.last_probe is not None
    (run,) = [d for d in (tmp_path / "evals").iterdir() if d.is_dir()]
    assert "did not settle" in (run / "naive" / "report.md").read_text(encoding="utf-8")


def test_all_keeps_going_when_one_suite_crashes(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    from horizon.evals import cli, suites

    class Broken(_Unsettled):
        async def run(self, env: Any, plan: Any) -> Any:
            raise RuntimeError("boom")

    monkeypatch.setenv("HORIZON_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("HORIZON_TEST", "1")
    monkeypatch.setattr(suites, "SUITES", {"decisions": suites.SUITES["decisions"],
                                           "summary": Broken(suites.SUITES["summary"])})
    assert cli._all(argparse.Namespace(limit=2)) == 0
    shown = capsys.readouterr().out
    assert "| decisions | agent |" in shown and "| summary | agent | — | — | — | not probed: crashed (RuntimeError: boom) |" \
        in shown

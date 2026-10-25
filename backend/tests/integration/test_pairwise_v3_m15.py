"""`judge_pairwise` v3's set (images-music D12; evaluation-harness "The pairwise judge is validated on clean pairs";
task 5.3). Committed files and the in-process fake, no network."""

from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from horizon.ai.questions import bank, check_lock
from horizon.evals import judges, suites
from horizon.evals.runner import Options, RunEnv
from horizon.evals.suites import DATASETS, load_dataset
from tests.conftest import Api

SET = DATASETS / "judges" / "judge_pairwise.jsonl"
DEFECTS = {"off_topic": 8, "assistant": 8, "other_character": 7, "persona_fact": 7}


def test_one_planted_defect_per_pair_against_a_real_1on1_reply() -> None:
    rows = load_dataset(SET)
    assert len(rows) == 30 and Counter(r["defect"] for r in rows) == Counter(DEFECTS)
    assert Counter(r["label"] for r in rows) == Counter({"a": 15, "b": 15})
    assert len({r["source"] for r in rows}) == 30                       # each real reply used once
    assert all(r["source"].startswith(("long_one_on_one_en#", "long_one_on_one_ms#")) for r in rows)
    for r in rows:
        st = r["item"]["state"]
        real, wrong = (st["quoted_reply_a"], st["quoted_reply_b"])[:: 1 if r["label"] == "a" else -1]
        assert real != wrong and real.strip()
        if r["defect"] == "assistant":
            assert "AI" in wrong and real not in wrong
        if r["defect"] == "persona_fact":
            assert real.strip() in wrong and len(wrong) > len(real)        # the real reply plus one sentence


def test_the_bank_is_locked_at_v3() -> None:
    assert bank().get(judges.PAIRWISE).version == 3
    assert check_lock() == []


async def test_both_orders_are_asked_60_requests(api: Api, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from horizon.gateway.decisions import DecisionsResponse

    await api.set_key()
    monkeypatch.setattr(suites, "DATASETS", tmp_path / "datasets")
    monkeypatch.setattr(judges, "RECORD", tmp_path / "judges.json")
    (tmp_path / "datasets" / "judges").mkdir(parents=True)
    shutil.copy(SET, tmp_path / "datasets" / "judges" / SET.name)
    asked: list[dict[str, Any]] = []

    async def decide(state: Any, questions: Any, ctx: Any, **_kw: Any) -> DecisionsResponse:
        asked.append(dict(state))
        return DecisionsResponse("gen-p", {judges.PAIRWISE: {"type": "choice", "choice": "a", "confidence": 0.9}},
                                 None, "typesafe/jev-1.13")

    monkeypatch.setattr(api.rt.gateway, "decide", decide)
    d = suites.Decisions()
    opts = Options("decisions", set="judges")
    plan = d.plan(opts, api.rt.prices, paid=True)
    run_dir = tmp_path / "evals" / "run-p" / "naive"
    run_dir.mkdir(parents=True)
    await d.run(RunEnv(rt=api.rt, opts=opts, store=None, run_dir=run_dir, max_usd=1.0), plan)
    assert len(asked) == 60
    keys = {json.dumps(s, sort_keys=True) for s in asked}
    assert len(keys) == 60                                              # each order is its own request (and store key)
    rec = judges.load_record(tmp_path / "judges.json")
    assert rec[judges.PAIRWISE]["version"] == 3 and rec[judges.PAIRWISE]["n"] == 30

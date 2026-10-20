"""The Jev model comparison (jev-comparison design D3–D11; model-comparison and evaluation-harness specs). Test mode,
the in-process fake, no network."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

import pytest

from horizon.evals import suites
from horizon.evals.runner import EVALS_DIR, Options, Plan, Result, RunEnv, Runner, priced_for
from horizon.gateway.context import call_ctx
from tests.conftest import Api
from tests.integration.test_eval_runner import SATURDAY, base
from tests.integration.test_eval_suites import dataset

PINNED = "typesafe/jev-1.13"
CANDIDATE = "typesafe/jev-1.14"
SEED = Path(__file__).resolve().parents[3] / "seed"


def canary_item() -> dict[str, Any]:
    return dict(json.loads((EVALS_DIR / "canary.json").read_text(encoding="utf-8"))["items"][0])


class AsksJev:
    """One Jev request through the isolated runtime; records what reached the fake."""
    name = "asks_jev"
    seen: ClassVar[list[dict[str, Any]]] = []

    def plan(self, opts: Options, prices: Any, *, paid: bool) -> Plan:
        return Plan(items=[1], estimate_usd=0.0, expected_s=1.0, paid=paid)

    async def run(self, env: RunEnv, plan: Plan) -> Result:
        it = canary_item()
        r = await env.rt.gateway.decide(it["state"], it["questions"], call_ctx("eval_judge"))
        fake = env.rt.fake
        assert fake is not None
        AsksJev.seen = [json.loads(q.content) for q in fake.requests if q.url.path.endswith("/decisions")]
        res = Result(model=r.model)
        res.summary.append(f"candidate={env.candidate}")
        return res


# ── 1.1, 1.2: the override reaches every Jev request; the seed is untouched; an alias is refused ──
async def test_the_override_reaches_every_jev_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(suites.SUITES, "asks_jev", AsksJev())
    before = (SEED / "settings.json").read_bytes()
    out: list[str] = []
    r = Runner(base(tmp_path), stdin=lambda _p: "y", out=out.append, now=lambda: SATURDAY)
    assert await r.run(Options("asks_jev", yes=True, decision_model=CANDIDATE)) == 0, out
    assert AsksJev.seen and all(b["model"] == CANDIDATE for b in AsksJev.seen)
    assert (SEED / "settings.json").read_bytes() == before
    (run,) = [p for p in (tmp_path / "evals").iterdir() if p.is_dir()]
    report = (run / "naive" / "report.md").read_text(encoding="utf-8")
    assert f"decision model asked: `{CANDIDATE}`" in report and f"model: `{CANDIDATE}`" in report   # the fake echoes it
    assert "candidate=True" in report


async def test_without_the_override_the_pinned_model_is_asked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(suites.SUITES, "asks_jev", AsksJev())
    r = Runner(base(tmp_path), stdin=lambda _p: "y", out=lambda _s: None, now=lambda: SATURDAY)
    assert await r.run(Options("asks_jev", yes=True)) == 0
    assert AsksJev.seen and all(b["model"] == PINNED for b in AsksJev.seen)


async def test_an_alias_is_refused_before_anything(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(suites.SUITES, "asks_jev", AsksJev())
    AsksJev.seen = []
    out: list[str] = []
    r = Runner(base(tmp_path), stdin=lambda _p: "y", out=out.append, now=lambda: SATURDAY)
    assert await r.run(Options("asks_jev", yes=True, decision_model="~typesafe/jev-latest")) == 2
    assert AsksJev.seen == [] and not (tmp_path / "evals").exists()
    assert any("never an alias" in s for s in out)


# ── 1.3: the candidate's own price, when one is listed ──
def test_the_candidate_is_priced_at_its_own_price(tmp_path: Path) -> None:
    from horizon.domain.pricing import estimate_decision, load_price_table

    doc = json.loads((SEED / "pricing.json").read_text(encoding="utf-8"))
    (tmp_path / "pricing.json").write_text(json.dumps(doc), encoding="utf-8")
    pinned = load_price_table(tmp_path)
    same = priced_for(pinned, CANDIDATE, tmp_path)   # no listed price: the pinned one, under the candidate's id
    assert same.decision.model == CANDIDATE and same.decision.input_per_m == pinned.decision.input_per_m
    doc["data"]["decisionPrices"] = {CANDIDATE: {"inputPerM": 0.084}}
    (tmp_path / "pricing.json").write_text(json.dumps(doc), encoding="utf-8")
    own = priced_for(pinned, CANDIDATE, tmp_path)
    assert estimate_decision(own, 1000) == pytest.approx(2 * estimate_decision(pinned, 1000))
    assert priced_for(pinned, None, tmp_path) is pinned and priced_for(pinned, PINNED, tmp_path) is pinned


# ── 1.4: the "already measured" marks are per model ──
async def test_a_candidate_is_measured_afresh_and_the_pinned_marks_stay(api: Api, tmp_path: Path,
                                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    await api.set_key()
    monkeypatch.setattr(suites, "DATASETS", tmp_path / "datasets")
    dataset(tmp_path / "datasets")
    run_dir = tmp_path / "evals" / "run-1" / "naive"
    run_dir.mkdir(parents=True)
    env = RunEnv(rt=api.rt, opts=Options("decisions"), store=None, run_dir=run_dir, max_usd=1.0)
    d = suites.Decisions()
    fake = api.rt.fake
    assert fake is not None
    await d.run(env, d.plan(Options("decisions"), api.rt.prices, paid=True))
    assert fake.counts["decisions"] == 6 and not env.candidate
    marks = suites.measured_path(env)
    pinned_marks = marks.read_bytes()
    api.rt.gateway.decision_model = CANDIDATE
    api.rt.gateway.decisions.model = CANDIDATE
    assert env.candidate
    res = await d.run(env, d.plan(Options("decisions"), api.rt.prices, paid=True))
    assert len(res.rows) == 3 and fake.counts["decisions"] == 12          # every item asked on the candidate
    got = json.loads(marks.read_text(encoding="utf-8"))
    assert got["route"] == json.loads(pinned_marks)["route"] and f"{CANDIDATE}|route" in got
    again = await d.run(env, d.plan(Options("decisions"), api.rt.prices, paid=True))
    assert again.rows == [] and fake.counts["decisions"] == 12            # the candidate's own marks hold


# ── 1.5: the judges' record is never written by a candidate run ──
async def test_a_candidate_never_writes_the_judges_record(api: Api, tmp_path: Path,
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    from horizon.evals import judges
    from horizon.gateway.decisions import DecisionsResponse

    await api.set_key()
    monkeypatch.setattr(suites, "DATASETS", tmp_path / "datasets")
    record = tmp_path / "judges.json"
    record.write_text('{"keep": "me"}\n', encoding="utf-8")
    monkeypatch.setattr(judges, "RECORD", record)
    root = tmp_path / "datasets" / "judges"
    root.mkdir(parents=True)
    st = {"quoted_last": "hi", "quoted_reply": "Great question! You're so smart."}
    rows = [{"id": f"jf-{i}", "question_id": "judge_flattery", "split": "dev", "item": {"state": st},
             "label": lab, "planted": planted} for i, (lab, planted) in enumerate(
                 [("yes", False)] * 15 + [("no", False)] * 15 + [("yes", True)] * 30)]
    (root / "judge_flattery.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    asked: list[str] = []

    async def decide(state: Any, questions: Any, ctx: Any, **_kw: Any) -> DecisionsResponse:
        row = rows[len(asked)]
        asked.append(row["id"])
        return DecisionsResponse("gen-j", {"judge_flattery": {"type": "noul", "noul": 0.9 if row["label"] == "yes"
                                                              else 0.1}}, None, CANDIDATE)

    monkeypatch.setattr(api.rt.gateway, "decide", decide)
    api.rt.gateway.decision_model = CANDIDATE
    d = suites.Decisions()
    opts = Options("decisions", set="judges")
    run_dir = tmp_path / "evals" / "run-j" / "naive"
    run_dir.mkdir(parents=True)
    res = await d.run(RunEnv(rt=api.rt, opts=opts, store=None, run_dir=run_dir, max_usd=1.0),
                      d.plan(opts, api.rt.prices, paid=True))
    assert len(asked) == 60
    assert any("judge_flattery" in s and "PASS" in s for s in res.summary)
    assert any("information only" in s for s in res.summary)
    assert record.read_text(encoding="utf-8") == '{"keep": "me"}\n'

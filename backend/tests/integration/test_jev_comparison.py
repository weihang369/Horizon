"""The Jev model comparison (jev-comparison design D3–D11; model-comparison and evaluation-harness specs). Test mode,
the in-process fake, no network."""

from __future__ import annotations

import datetime as dt
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


def evals_dir(tmp: Path, monkeypatch: pytest.MonkeyPatch, *, candidate: bool) -> Path:
    """A copy of `evals/canary.json` (and, when asked, a candidate baseline) that the runner and the suites read."""
    from horizon.evals import runner

    d = tmp / "evals-dir"
    d.mkdir()
    main = json.loads((EVALS_DIR / "canary.json").read_text(encoding="utf-8"))
    (d / "canary.json").write_text(json.dumps(main), encoding="utf-8")
    if candidate:
        (d / "canary").mkdir()
        (d / "canary" / f"{CANDIDATE.replace('/', '__')}.json").write_text(json.dumps({**main, "model": CANDIDATE}),
                                                                           encoding="utf-8")
    monkeypatch.setattr(runner, "EVALS_DIR", d)
    monkeypatch.setattr(suites, "EVALS_DIR", d)
    return d


# ── 1.1, 1.2: the override reaches every Jev request; the seed is untouched; an alias is refused ──
async def test_the_override_reaches_every_jev_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(suites.SUITES, "asks_jev", AsksJev())
    evals_dir(tmp_path, monkeypatch, candidate=True)
    before = (SEED / "settings.json").read_bytes()
    out: list[str] = []
    r = Runner(base(tmp_path / "data"), stdin=lambda _p: "y", out=out.append, now=lambda: SATURDAY)
    assert await r.run(Options("asks_jev", yes=True, decision_model=CANDIDATE)) == 0, out
    assert AsksJev.seen and all(b["model"] == CANDIDATE for b in AsksJev.seen)
    assert (SEED / "settings.json").read_bytes() == before
    (run,) = [p for p in (tmp_path / "data" / "evals").iterdir() if p.is_dir()]
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
        asked.append(str(row["id"]))
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


# ── 2.1: a canary baseline per model ──
async def test_the_candidate_canary_writes_its_own_baseline(api: Api, tmp_path: Path,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    import copy

    from horizon.evals import canary as canary_mod
    from horizon.gateway.decisions import DecisionsResponse

    d = evals_dir(tmp_path, monkeypatch, candidate=False)
    main_before = (d / "canary.json").read_bytes()
    base_items = canary_mod.load_baseline(d / "canary.json").items
    canned = [copy.deepcopy(i["answers"]) for i in base_items]
    flip = next(i for i, a in enumerate(canned) if any("choice" in x for x in a.values()))
    a = next(v for v in canned[flip].values() if "choice" in v)
    a["choice"] = next(k for k in a["probabilities"] if k != a["choice"])   # the candidate answers one item otherwise
    calls = iter(range(10_000))

    async def decide(state: Any, questions: Any, ctx: Any, **_kw: Any) -> Any:
        return DecisionsResponse("gen-c", copy.deepcopy(canned[next(calls) % len(canned)]), None, CANDIDATE)

    monkeypatch.setattr(api.rt.gateway, "decide", decide)
    api.rt.gateway.decision_model = CANDIDATE
    c = suites.Canary()
    plan = c.plan(Options("canary"), api.rt.prices, paid=True)

    def env(sub: str, **kw: Any) -> RunEnv:
        run_dir = tmp_path / sub / "evals" / "run" / "naive"
        run_dir.mkdir(parents=True)
        return RunEnv(rt=api.rt, opts=Options("canary", **kw), store=None, run_dir=run_dir, max_usd=1.0)

    first = await c.run(env("1"), plan)
    own = d / "canary" / f"{CANDIDATE.replace('/', '__')}.json"
    assert first.status == "ok" and own.is_file()                         # a finding, not a failure
    assert any("first run" in s and "19/20" in s for s in first.summary)
    assert any(base_items[flip]["id"] in s for s in first.summary)
    assert (d / "canary.json").read_bytes() == main_before
    written = canary_mod.load_baseline(own)
    assert written.model == CANDIDATE and canary_mod.fingerprint_for(d, CANDIDATE) == written.fingerprint
    assert canary_mod.fingerprint_for(d, PINNED) == canary_mod.load_baseline(d / "canary.json").fingerprint
    a["choice"] = next(k for k in a["probabilities"] if k != a["choice"])  # a later drift on the candidate
    own_before = own.read_bytes()
    second = await c.run(env("2"), plan)
    assert second.status == "drift" and own.read_bytes() == own_before
    third = await c.run(env("3", accept=True), plan)                       # accepting writes the candidate's file only
    assert third.status == "ok" and own.read_bytes() != own_before
    assert (d / "canary.json").read_bytes() == main_before
    assert canary_mod.load_baseline(own).model == CANDIDATE


# ── 2.2: a candidate with no baseline waits for its canary; its stored answers are found again ──
async def test_a_candidate_without_a_baseline_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(suites.SUITES, "asks_jev", AsksJev())
    evals_dir(tmp_path, monkeypatch, candidate=False)
    AsksJev.seen = []
    out: list[str] = []
    r = Runner(base(tmp_path / "data"), stdin=lambda _p: "y", out=out.append, now=lambda: SATURDAY)
    assert await r.run(Options("asks_jev", yes=True, decision_model=CANDIDATE)) == 2
    assert AsksJev.seen == [] and any("canary --decision-model" in s for s in out)
    assert await r.run(Options("asks_jev", yes=True, decision_model=PINNED)) == 0   # the pinned model needs nothing


async def test_a_candidates_stored_answer_is_found_under_its_own_salt(api: Api, tmp_path: Path,
                                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    from horizon.evals import canary as canary_mod
    from horizon.evals.store import ResponseStore

    await api.set_key()
    d = evals_dir(tmp_path, monkeypatch, candidate=True)
    own = d / "canary" / f"{CANDIDATE.replace('/', '__')}.json"
    doc = json.loads(own.read_text(encoding="utf-8"))
    doc["items"][0]["answers"] = {"x": {"noul": 0.11}}                     # the candidate's own baseline, its own salt
    doc["fingerprint"] = canary_mod.fingerprint(doc["items"])
    own.write_text(json.dumps(doc), encoding="utf-8")
    fp_c, fp_p = canary_mod.fingerprint_for(d, CANDIDATE), canary_mod.fingerprint_for(d, PINNED)
    assert fp_c and fp_p and fp_c != fp_p
    fake = api.rt.fake
    assert fake is not None
    it = canary_item()
    api.rt.gateway.decision_model = CANDIDATE
    api.rt.gateway.store = ResponseStore.eval_view(tmp_path / "cache", fp_c)
    await api.rt.gateway.decide(it["state"], it["questions"], call_ctx("eval_judge"))
    n = fake.counts["decisions"]
    await api.rt.gateway.decide(it["state"], it["questions"], call_ctx("eval_judge"))
    assert fake.counts["decisions"] == n                                   # found again: nothing sent
    api.rt.gateway.store = ResponseStore.eval_view(tmp_path / "cache", fp_p)   # the pinned salt doesn't find it
    await api.rt.gateway.decide(it["state"], it["questions"], call_ctx("eval_judge"))
    assert fake.counts["decisions"] == n + 1


# ── 2.3: the pinned model's salt is the one every stored 1.13 answer was keyed with ──
def test_the_pinned_salt_is_unchanged() -> None:
    from horizon.evals import canary as canary_mod
    from horizon.evals.store import jev_key

    fp = canary_mod.fingerprint_for(EVALS_DIR, PINNED)
    assert fp == json.loads((EVALS_DIR / "canary.json").read_text(encoding="utf-8"))["fingerprint"]
    fix = Path(__file__).resolve().parents[1] / "fixtures" / "store"
    name = "03f58c0f98e05d2c116783f47f90a7d4a5b921712609641d2bb7fa6586f2c089.json"   # group A's, with the salt
    req = json.loads((fix / name).read_text(encoding="utf-8"))["request"]
    assert jev_key(PINNED, req["state"], req["questions"], fp) + ".json" == name
    assert canary_mod.baseline_path(EVALS_DIR, PINNED) == EVALS_DIR / "canary.json"
    assert canary_mod.baseline_path(EVALS_DIR, CANDIDATE).parent == EVALS_DIR / "canary"


# ── 3.1: the peak check holds only plans that call chat (D6) ──
MONDAY_1030 = dt.datetime(2026, 10, 5, 2, 30, tzinfo=dt.UTC)   # 10:30 KL: DeepSeek's peak


def paid_base(tmp: Path) -> Any:
    """A normal-mode config with an obviously fake key; every run below is answered `n` or refused, so nothing is sent."""
    from pydantic import SecretStr

    from tests.conftest import make_config

    return make_config(tmp, test_mode=False, openrouter_key=SecretStr("sk-or-test-peak-0001"))


@pytest.mark.parametrize(("opts", "refused"), [
    (Options("decisions", set="english"), False),
    (Options("canary"), False),
    (Options("deep-check"), False),
    (Options("safety", part="input,care"), False),
    (Options("latency", profile="agent"), True),
    (Options("safety", profile="agent", part="honesty"), True),
])
async def test_only_a_plan_with_chat_is_held_to_the_peak(tmp_path: Path, opts: Options, refused: bool) -> None:
    out: list[str] = []
    asked: list[str] = []

    def no(prompt: str) -> str:
        asked.append(prompt)
        return "n"

    r = Runner(paid_base(tmp_path), stdin=no, out=out.append, now=lambda: MONDAY_1030)
    code = await r.run(opts)
    peak = any("DeepSeek's peak" in s for s in out)
    assert peak is refused, out
    assert (code, bool(asked)) == ((2, False) if refused else (1, True))   # a Jev-only run reaches the y/N prompt
    assert not (tmp_path / "evals").exists() or not any((tmp_path / "evals").iterdir())


async def test_a_jev_only_plan_sends_only_decisions(api: Api, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The suites that declare `calls_chat=False` leave only `decision` rows in the ledger (D6's guard)."""
    from sqlalchemy import select

    from horizon.db import tables as t
    from horizon.evals import deep_check_suite, safety_suite

    await api.set_key()
    cases: list[tuple[Any, Options]] = [(suites.Canary(), Options("canary", limit=3)),
             (deep_check_suite.DeepCheck(), Options("deep-check", limit=3)),
             (safety_suite.Safety(), Options("safety", part=",".join(safety_suite.JEV_PARTS))),
             (suites.Decisions(), Options("decisions"))]
    for k, (suite, opts) in enumerate(cases):
        if opts.suite == "decisions":   # deep-check reads the real datasets; decisions a small made-up one
            monkeypatch.setattr(suites, "DATASETS", tmp_path / "datasets")
            dataset(tmp_path / "datasets")
        plan = suite.plan(opts, api.rt.prices, paid=False)
        assert plan.calls_chat is False, opts.suite
        run_dir = tmp_path / "evals" / f"run-{k}" / "naive"
        run_dir.mkdir(parents=True)
        await suite.run(RunEnv(rt=api.rt, opts=opts, store=None, run_dir=run_dir, max_usd=1.0), plan)
    async with api.rt.db.read() as conn:
        cats = {str(c) for c in (await conn.execute(select(t.usage_records.c.category)
                                                    .where(t.usage_records.c.is_seed.is_(False)))).scalars()}
    assert cats == {"decision"}


# ── 3.2: `.keep` from the start (D15) ──
async def test_a_paid_run_that_dies_keeps_its_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from horizon.evals import runner

    class Dies(AsksJev):
        name = "dies"

        async def run(self, env: RunEnv, plan: Plan) -> Result:
            raise RuntimeError("the provider went away mid-run")

    async def execute(self: Runner, suite: Any, plan: Plan, *_a: Any) -> Any:
        return await suite.run(None, plan)

    monkeypatch.setitem(suites.SUITES, "dies", Dies())
    monkeypatch.setattr(runner.Runner, "_execute", execute)   # the paid path up to the call, with nothing sent
    r = Runner(paid_base(tmp_path), stdin=lambda _p: "y", out=lambda _s: None, now=lambda: SATURDAY)
    with pytest.raises(RuntimeError):
        await r.run(Options("dies", yes=True))
    (run,) = [p for p in (tmp_path / "evals").iterdir() if p.is_dir()]
    assert (run / ".keep").is_file()
    for i in range(25):   # newer unmarked runs push past KEEP_RUNS; the dead paid run stays
        (tmp_path / "evals" / f"20261004T0300{i:02d}-smoke-x").mkdir()
    runner.prune_runs(tmp_path / "evals")
    assert run.is_dir()


# ── 6.1's guard: a sliced canary run never writes a baseline ──
async def test_a_limited_canary_never_writes_a_baseline(api: Api, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    await api.set_key()
    d = evals_dir(tmp_path, monkeypatch, candidate=False)
    api.rt.gateway.decision_model = CANDIDATE
    c = suites.Canary()
    for k, opts in enumerate((Options("canary", limit=1), Options("canary", start=19))):
        run_dir = tmp_path / str(k) / "evals" / "run" / "naive"
        run_dir.mkdir(parents=True)
        res = await c.run(RunEnv(rt=api.rt, opts=opts, store=None, run_dir=run_dir, max_usd=1.0),
                          c.plan(opts, api.rt.prices, paid=True))
        assert len(res.rows) == 1 and any("no baseline is written" in s for s in res.summary)
    assert not (d / "canary").exists()


# ── D13: a comparison run re-judges nothing, on the pinned model either ──
async def test_a_comparison_run_never_writes_the_judges_record(api: Api, tmp_path: Path,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    from horizon.evals import judges
    from horizon.gateway.decisions import DecisionsResponse

    await api.set_key()
    monkeypatch.setattr(suites, "DATASETS", tmp_path / "datasets")
    root = tmp_path / "datasets" / "judges"
    root.mkdir(parents=True)
    st = {"quoted_last": "hi", "quoted_reply": "Great question! You're so smart."}
    rows = [{"id": f"jf-{i}", "question_id": "judge_flattery", "split": "dev", "item": {"state": st}, "label": lab,
             "planted": planted} for i, (lab, planted) in enumerate([("yes", False)] * 30 + [("yes", True)] * 30)]
    (root / "judge_flattery.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    async def decide(state: Any, questions: Any, ctx: Any, **_kw: Any) -> DecisionsResponse:
        return DecisionsResponse("gen-j", {"judge_flattery": {"type": "noul", "noul": 0.9}}, None, PINNED)

    monkeypatch.setattr(api.rt.gateway, "decide", decide)
    before = judges.RECORD.read_bytes()
    d = suites.Decisions()
    opts = Options("decisions", set="judges", against="m.json")
    run_dir = tmp_path / "evals" / "run-j" / "naive"
    run_dir.mkdir(parents=True)
    res = await d.run(RunEnv(rt=api.rt, opts=opts, store=None, run_dir=run_dir, max_usd=1.0),
                      d.plan(opts, api.rt.prices, paid=True))
    assert any("judge_flattery" in s for s in res.summary) and judges.RECORD.read_bytes() == before

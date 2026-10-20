"""The Jev request manifest (images-music design D19; evaluation-harness "The Jev request manifest"). Built from the
datasets at $0; a comparison run refuses any Jev body it doesn't list. No network."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from horizon.evals.manifest import body_hash, build, decisions_bodies
from horizon.evals.runner import EVALS_DIR
from horizon.evals.store import ResponseStore, jev_key
from horizon.gateway.context import call_ctx
from horizon.gateway.errors import ProviderError
from tests.conftest import SEED_DIR, Api

JEV = json.loads((SEED_DIR / "pricing.json").read_text(encoding="utf-8"))["data"]["decision"]["model"]
FP = json.loads((EVALS_DIR / "canary.json").read_text(encoding="utf-8"))["fingerprint"]


def test_every_set_is_listed_by_hash_only(tmp_path: Path) -> None:
    doc = build(model=JEV, fingerprint=FP, store_root=tmp_path / "cache", private_store_root=tmp_path / "private",
                test_mode=True)
    sets = doc["sets"]
    assert {"canary", "deep-check", "judges", "emotion"} <= set(sets)
    assert sets["canary"]["n"] == 20 and sets["canary"]["stored"] == 0
    assert any(k.startswith("safety:") for k in sets)                     # the committed harmless items in test mode
    assert all(re.fullmatch(r"[0-9a-f]{64}", h) for s in sets.values() for h in s["bodies"])
    assert doc["model"] == JEV and doc["fingerprint"] == FP and doc["bank"]["emotion_reply"] >= 1
    text = json.dumps(doc)
    _name, state, _qs, _order = next(iter(decisions_bodies()))
    assert all(str(v) not in text for v in state.values() if isinstance(v, str) and len(v) > 12)   # no item text


def test_a_stored_answer_is_counted(tmp_path: Path) -> None:
    name, state, qs, order = next(iter(decisions_bodies()))
    store = ResponseStore.eval_view(tmp_path / "cache", FP)
    assert store.put("jev", jev_key(JEV, state, qs, FP, order), {"state": state, "questions": qs}, {"answers": {}}, None)
    doc = build(model=JEV, fingerprint=FP, store_root=tmp_path / "cache", private_store_root=tmp_path / "private",
                test_mode=True)
    assert doc["sets"][name]["stored"] == 1
    assert body_hash(state, qs) in doc["sets"][name]["bodies"]


async def test_a_comparison_refuses_an_unlisted_body_and_names_it(api: Api) -> None:
    await api.set_key()
    state = {"quoted_message": "hi"}
    listed = {"q": {"type": "noul", "instructions": "listed?", "criteria": {"true": "yes", "false": "no"}}}
    other = {"other_q": {"type": "noul", "instructions": "changed?", "criteria": {"true": "yes", "false": "no"}}}
    api.rt.gateway.allowed_bodies = frozenset({body_hash(state, listed)})
    fake = api.rt.fake
    assert fake is not None
    await api.rt.gateway.decide(state, listed, call_ctx("eval_judge"))
    sent = fake.counts["decisions"]
    # jev-comparison (D20): not sent, named, and answered with nothing, so the suite goes on with the next item
    r = await api.rt.gateway.decide(state, other, call_ctx("eval_judge"))
    assert r.answers == {} and r.generation_id == "not_in_manifest"
    assert api.rt.gateway.manifest_refused == [f"{body_hash(state, other)} other_q"]
    assert fake.counts["decisions"] == sent == 1


async def test_a_comparison_counts_a_rate_limit_and_goes_on(api: Api) -> None:
    """jev-comparison (D20): a 429 on a comparison run is counted, the item reads unanswered; live calls still raise."""
    await api.set_key()
    state = {"quoted_message": "hi"}
    q = {"q": {"type": "noul", "instructions": "listed?", "criteria": {"true": "yes", "false": "no"}}}
    fake = api.rt.fake
    assert fake is not None
    fake.refuse_question("q", 429)
    with pytest.raises(ProviderError):
        await api.rt.gateway.decide(state, q, call_ctx("eval_judge"))   # no manifest: the error stands
    api.rt.gateway.allowed_bodies = frozenset({body_hash(state, q)})
    fake.refuse_question("q", 429)
    r = await api.rt.gateway.decide(state, q, call_ctx("eval_judge"))
    assert r.answers == {} and api.rt.gateway.comparison_errors == [{"code": "rate_limited", "status": 429,
                                                                     "questions": ["q"]}]


async def test_every_body_the_decisions_suite_sends_is_listed(api: Api, tmp_path: Path,
                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    """jev-comparison (D20): the builder mirrors `Decisions.run`. M15's listed keyed nouls under the bare question id
    and the pairwise judge's second ask with its options reversed, so 491 of a comparison's bodies were refused."""
    from horizon.evals import suites
    from horizon.evals.runner import Options, RunEnv

    await api.set_key()
    real = EVALS_DIR / "datasets"
    root = tmp_path / "datasets"
    for rel in ("docs/docs.jsonl", "importance/importance.jsonl", "judges/judge_pairwise.jsonl",
                "who_speaks/who_first.jsonl", "emotion/emotion.jsonl"):
        lines = [ln for ln in (real / rel).read_text(encoding="utf-8").splitlines() if ln.strip()][:4]
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("\n".join(lines) + "\n", encoding="utf-8")
    monkeypatch.setattr(suites, "DATASETS", root)
    from horizon.evals import judges

    monkeypatch.setattr(judges, "RECORD", tmp_path / "judges.json")   # the pinned model's B4 run writes it
    api.rt.gateway.allowed_bodies = frozenset(body_hash(s, q) for _n, s, q, _o in decisions_bodies())
    d = suites.Decisions()
    for opts in (Options("decisions", against="m.json"), Options("decisions", set="judges", against="m.json")):
        run_dir = tmp_path / "evals" / f"run-{opts.set}" / "naive"
        run_dir.mkdir(parents=True)
        await d.run(RunEnv(rt=api.rt, opts=opts, store=None, run_dir=run_dir, max_usd=1.0),
                    d.plan(opts, api.rt.prices, paid=True))
    assert api.rt.gateway.manifest_refused == []
    fake = api.rt.fake
    assert fake is not None and fake.counts["decisions"] > 0

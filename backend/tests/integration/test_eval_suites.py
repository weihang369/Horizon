"""The decisions suite, stats/capture and the data checks (evaluation-harness spec; ai-foundation design D34, D36, D37;
tasks 7.6, 7.8, 7.9). Test mode, the in-process fake, no network."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from horizon.evals import datachecks, suites
from horizon.evals.runner import EVALS_DIR, Options, RunEnv
from horizon.evals.stats import capture_case, stats
from tests.conftest import Api
from tests.integration.test_capture import enable_capture, naive_group_turn

ITEM = {"state": {"mode": "group", "quoted_cast": [{"id": "chr_a", "name": "Ana", "role": "nurse", "lastSpoke": 0},
                                                  {"id": "chr_b", "name": "Ben", "role": "cook", "lastSpoke": 1}],
                  "quoted_recent": ["Kai: hi"], "quoted_message": "Ben, what's for dinner?"},
        "values": [{"key": "chr_a", "name": "Ana", "role": "nurse"}, {"key": "chr_b", "name": "Ben", "role": "cook"}]}


def dataset(root: Path, n: int = 3, smoke: bool = False) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    p = root / "route.jsonl"
    lines = []
    for i in range(n):
        iid = f"route-t-{i}"
        lines.append(json.dumps({"id": iid, "question_id": "route", "split": datachecks.split_for(iid), "item": ITEM,
                                 "label": "chr_b", **({"smoke_only": True} if smoke else {})}))
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def env_for(api: Api, tmp: Path) -> RunEnv:
    run_dir = tmp / "evals" / "run-1" / "naive"
    run_dir.mkdir(parents=True)
    return RunEnv(rt=api.rt, opts=Options("decisions"), store=None, run_dir=run_dir, max_usd=1.0)


# ── 7.6 ──
async def test_decisions_asks_both_orders_and_skips_unchanged_versions(api: Api, tmp_path: Path,
                                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    await api.set_key()
    monkeypatch.setattr(suites, "DATASETS", tmp_path / "datasets")
    dataset(tmp_path / "datasets")
    d = suites.Decisions()
    plan = d.plan(Options("decisions"), api.rt.prices, paid=True)
    env = env_for(api, tmp_path)
    fake = api.rt.fake
    assert fake is not None
    res = await d.run(env, plan)
    assert fake.counts["decisions"] == 6                       # 3 items × both option orders
    assert all("answer_reversed" in r for r in res.rows)
    assert any("order bias" in s for s in res.summary) and any("Wilson" in s for s in res.summary)
    again = await d.run(env, d.plan(Options("decisions"), api.rt.prices, paid=True))
    assert fake.counts["decisions"] == 6 and again.rows == []   # no bank change: nothing sent
    assert any("unchanged: route" in s for s in again.summary)


async def test_smoke_items_are_never_a_measurement(api: Api, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    await api.set_key()
    monkeypatch.setattr(suites, "DATASETS", tmp_path / "datasets")
    dataset(tmp_path / "datasets", smoke=True)
    assert suites.Decisions().plan(Options("decisions"), api.rt.prices, paid=True).items == []
    s = suites.Decisions(smoke=True)
    res = await s.run(env_for(api, tmp_path), s.plan(Options("smoke"), api.rt.prices, paid=False))
    assert res.summary == ["## Decisions (smoke only: 3 item(s), never a measurement)"]


def test_the_shipped_smoke_set_loads() -> None:
    rows = suites.load_dataset(EVALS_DIR / "datasets" / "_smoke" / "route.jsonl")
    assert len(rows) == 6 and all(r["smoke_only"] for r in rows)
    assert datachecks.split_problems(rows) == []


# ── 7.8 ──
async def test_stats_on_a_fresh_install_and_on_live_data(api: Api, tmp_path: Path) -> None:
    assert "no database yet" in stats(tmp_path / "missing.db")
    assert "no live data" in stats(api.rt.cfg.db_path)
    await naive_group_turn(api)
    await api.rt.db.checkpoint_truncate()
    before = api.rt.cfg.db_path.read_bytes()
    out = stats(api.rt.cfg.db_path)
    assert "p50" in out and "reply" in out and "route" in out and "Late decisions" in out
    assert api.rt.cfg.db_path.read_bytes() == before            # read-only: the file is untouched


async def test_capture_writes_a_case_or_says_capture_was_off(api: Api, tmp_path: Path) -> None:
    enable_capture(api.rt)
    _, reply = await naive_group_turn(api)
    await api.rt.capture.flush()
    await api.rt.db.checkpoint_truncate()
    p = capture_case(api.rt.cfg.db_path, reply["id"], tmp_path / "cases")
    assert p is not None
    doc: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    assert {r["kind"] for r in doc["rows"]} == {"call", "turn"} and any(r["purpose"] == "route" for r in doc["rows"])
    assert capture_case(api.rt.cfg.db_path, "msg_nope", tmp_path / "cases") is None


# ── 7.9 ──
def test_split_rule_and_split_changes(tmp_path: Path) -> None:
    assert datachecks.split_for("route-smoke-1") in ("dev", "test")
    assert datachecks.split_problems([{"id": "x", "split": "nope"}])
    repo = tmp_path / "repo"
    repo.mkdir()
    f = repo / "d.jsonl"
    f.write_text(json.dumps({"id": "a", "split": "dev"}) + "\n", encoding="utf-8")
    run = {"cwd": repo, "check": True, "capture_output": True}
    subprocess.run(["git", "init", "-q"], **run)  # type: ignore[call-overload]
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "add", "."], **run)  # type: ignore[call-overload]
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"], **run)  # type: ignore[call-overload]
    f.write_text(json.dumps({"id": "a", "split": "test"}) + "\n" + json.dumps({"id": "b", "split": "dev"}) + "\n",
                 encoding="utf-8")
    assert datachecks.split_changes(f, repo) == ["a: split changed dev → test"]


def test_overlap_catches_a_copied_bank_phrase() -> None:
    entry = suites.bank().get("route").raw
    phrase = " ".join(str(entry["instructions"]).split()[:8])
    assert datachecks.overlap_problems([{"id": "copied", "item": {"state": {"quoted_message": phrase}}}])
    assert datachecks.overlap_problems([{"id": "own", "item": {"state": {"quoted_message": "Ben, dinner tonight?"}}}]) == []
    assert datachecks.overlap_problems(list(suites.all_items())) == []


def test_review_sample_and_result(tmp_path: Path) -> None:
    ids = [f"i{n}" for n in range(100)]
    a = datachecks.review_sample(ids, 7)
    assert len(a) == 20 and a == datachecks.review_sample(ids, 7)      # max(15, ⌈100/5⌉), seeded
    assert len(datachecks.review_sample(ids[:10], 1)) == 10
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"sample": a, "disagree": ["i1"]}), encoding="utf-8")
    assert datachecks.review_result(p) == (True, 1)
    p.write_text(json.dumps({"sample": a, "disagree": ["i1", "i2"]}), encoding="utf-8")
    assert datachecks.review_result(p) == (False, 2)


def test_corpus_check(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    (root / "amara").mkdir(parents=True)
    (root / "LICENSE").write_text(datachecks.LICENSE_LINE + ".\n", encoding="utf-8")
    (root / "SOURCES.md").write_text("| amara/shift.md | https://www.cdc.gov/niosh/x | 2026-10-11 |\n", encoding="utf-8")
    (root / "amara" / "shift.md").write_text("# Shift work\nPlain federal text.\n", encoding="utf-8")
    assert datachecks.corpus_problems(root) == []
    (root / "amara" / "credit.md").write_text("Photo courtesy of Someone.\n", encoding="utf-8")
    (root / "amara" / "logo.png").write_bytes(b"\x89PNG")
    probs = datachecks.corpus_problems(root)
    assert any("courtesy of" in p for p in probs) and any("no SOURCES.md row" in p for p in probs)
    assert any("logo.png" in p for p in probs)



# ── 7.5: the canary on canned answers ──
async def test_canary_run_on_canned_answers(api: Api, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import copy

    from horizon.evals import canary as canary_mod
    from horizon.gateway.decisions import DecisionsResponse

    base = canary_mod.load_baseline(EVALS_DIR / "canary.json")
    canned = [copy.deepcopy(i["answers"]) for i in base.items]
    calls = iter(range(10_000))

    async def decide(state: Any, questions: Any, ctx: Any, **_kw: Any) -> DecisionsResponse:
        return DecisionsResponse("gen-c", canned[next(calls) % len(canned)], None, "typesafe/jev-1.13")

    monkeypatch.setattr(api.rt.gateway, "decide", decide)
    c = suites.Canary()
    plan = c.plan(Options("canary"), api.rt.prices, paid=True)
    res = await c.run(env_for(api, tmp_path), plan)
    assert res.status == "ok" and res.model == "typesafe/jev-1.13" and plan.estimate_usd < 0.001
    item = next(i for i, a in enumerate(canned) if any("choice" in x for x in a.values()))
    a = next(v for v in canned[item].values() if "choice" in v)
    a["choice"] = next(k for k in a["probabilities"] if k != a["choice"])
    res = await c.run(env_for(api, tmp_path / "2"), plan)
    assert res.status == "drift" and any(base.items[item]["id"] in s for s in res.summary)

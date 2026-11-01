"""`horizon eval compare-models`: the steps, the pairing and scoring, the behaviour figures, the probes and the re-cut
report (jev-comparison design D7–D11, D20; model-comparison spec). Test mode, the in-process fake, no network."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from horizon.evals import compare, suites
from horizon.evals.metrics import mcnemar_exact
from horizon.evals.runner import EVALS_DIR, Options, Plan, RunEnv, Runner
from tests.conftest import Api
from tests.integration.test_eval_runner import SATURDAY, base
from tests.integration.test_jev_comparison import CANDIDATE, PINNED, evals_dir

REAL = EVALS_DIR / "datasets"


def slice_datasets(root: Path) -> Path:
    """A few dev and test lines from real sets, so the real scoring groups run on the fake."""
    for rel, k in (("emotion/emotion.jsonl", 6), ("standalone/standalone.jsonl", 8), ("english/english.jsonl", 4),
                   ("judges/judge_flattery.jsonl", 4)):
        rows = [json.loads(ln) for ln in (REAL / rel).read_text(encoding="utf-8").splitlines() if ln.strip()]
        keep = [r for r in rows if r["split"] == "dev"][:k] + [r for r in rows if r["split"] == "test"][:k]
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("".join(json.dumps(r) + "\n" for r in keep), encoding="utf-8")
    return root


def categories(db: Path) -> set[str]:
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        return {str(c) for (c,) in con.execute("SELECT DISTINCT category FROM usage_records WHERE is_seed = 0")}
    finally:
        con.close()


# ── 4.1: the manifest is named by model ──
def test_the_manifest_is_named_by_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import argparse

    from horizon.evals import cli, manifest

    assert manifest.manifest_name(PINNED) == "jev-1.13-requests.json"
    assert manifest.manifest_name(CANDIDATE) == "jev-1.14-requests.json"
    d = evals_dir(tmp_path, monkeypatch, candidate=True)
    (d / "baselines").mkdir()
    monkeypatch.setattr(manifest, "build", lambda **kw: {"model": kw["model"], "fingerprint": kw["fingerprint"],
                                                         "sets": {}})
    seed = tmp_path / "seed"
    seed.mkdir()
    pricing = json.loads((EVALS_DIR.parent / "seed" / "pricing.json").read_text(encoding="utf-8"))
    for model in (PINNED, CANDIDATE):
        pricing["data"]["decision"]["model"] = model
        (seed / "pricing.json").write_text(json.dumps(pricing), encoding="utf-8")
        monkeypatch.setenv("HORIZON_SEED_DIR", str(seed))
        monkeypatch.setenv("HORIZON_DATA_DIR", str(tmp_path / "data"))
        assert cli._manifest(argparse.Namespace(out=None)) == 0
        doc = json.loads((d / "baselines" / manifest.manifest_name(model)).read_text(encoding="utf-8"))
        assert doc["model"] == model and doc["fingerprint"]   # each model's own canary salt
    assert sorted(p.name for p in (d / "baselines").iterdir()) == ["jev-1.13-requests.json", "jev-1.14-requests.json"]


# ── 4.2, 4.7: the whole sequence on the fake, and the re-cut ──
async def test_the_full_comparison_on_the_fake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from horizon.evals import canary as canary_mod
    from horizon.evals import compare_probes, runner
    from horizon.evals import manifest as man

    d = evals_dir(tmp_path, monkeypatch, candidate=False)
    monkeypatch.setattr(compare_probes, "EVALS_DIR", d)
    monkeypatch.setattr(runner, "PAID_ONLY", frozenset())             # the fake stands in for the paid provider
    monkeypatch.setattr(runner, "prune_runs", lambda *_a, **_k: [])   # the fake's runs are free, so never `.keep`
    monkeypatch.setattr(runner, "SAFETY_CACHE", tmp_path / "safety-cache")   # never this machine's private store
    from horizon.evals import judges

    record = tmp_path / "judges.json"   # the base side is the pinned model: its B4 run writes the record it is given
    monkeypatch.setattr(judges, "RECORD", record)
    monkeypatch.setattr(canary_mod, "compare", lambda _b, _n: [])     # the fake's answers aren't 1.13's
    monkeypatch.setattr(suites, "DATASETS", slice_datasets(tmp_path / "datasets"))
    doc = man.build(model=PINNED, fingerprint=canary_mod.fingerprint_for(d, PINNED), store_root=tmp_path / "cache",
                    private_store_root=tmp_path / "private", test_mode=True)
    dropped = doc["sets"]["standalone"]["bodies"].pop(0)              # a body that "changed" since the manifest
    mpath = tmp_path / "manifest.json"
    mpath.write_text(json.dumps(doc), encoding="utf-8")
    data = tmp_path / "data"
    out: list[str] = []

    def runner_for() -> Runner:
        return Runner(base(data), stdin=lambda _p: "y", out=out.append, now=lambda: SATURDAY)

    c = compare.Comparison(data, PINNED, CANDIDATE, str(mpath), runner_for=runner_for, out=out.append, yes=True,
                           now=lambda: SATURDAY + dt.timedelta(hours=2))
    for step in ("canary", "probe", "sets", "repeat", "timing-a"):
        assert await c.step(step) == 0, (step, out[-6:])
    assert await c.step("timing-b") == 2 and "≥ 3 h" in out[-1]       # too soon: refused, nothing sent
    c.now = lambda: SATURDAY + dt.timedelta(hours=4)
    assert await c.step("timing-b") == 0
    assert (d / "canary" / f"{CANDIDATE.replace('/', '__')}.json").is_file()   # the candidate's own baseline
    state = json.loads(compare.state_path(data, PINNED, CANDIDATE).read_text(encoding="utf-8"))
    assert {"canary:base", "canary:new", "sets:base:decisions", "sets:new:decisions", "sets:new:decisions:judges",
            "sets:new:deep-check", "sets:new:safety", "repeat", "timing-a", "timing-b"} <= set(state["runs"])
    for side in ("base", "new"):                                       # the changed body: named, sent on neither side
        meta = compare.run_meta(data, state["runs"][f"sets:{side}:decisions"])
        assert any(r.startswith(dropped) for r in meta["manifest_refused"])
        assert meta["decision_model"] == (PINNED if side == "base" else CANDIDATE)
    for run_id in state["runs"].values():                             # no chat request anywhere
        folder = compare.run_folder(data, run_id)
        assert folder is not None and categories(folder / "horizon.db") <= {"decision"}
    assert state["probe"] and all(v["hits"] == 0 for v in state["probe"].values())   # an empty store: all to pay
    # the report: re-cut from saved rows, the same each time, and nothing sent
    def run_folders() -> list[str]:
        return sorted(p.name for p in (data / "evals").iterdir() if p.is_dir() and p.name[:1].isdigit())

    runs_before = run_folders()
    first = compare.write_report(data, state)
    again = compare.write_report(data, state)
    named = compare.write_report(data, compare.report_only_state(data, PINNED, CANDIDATE, str(mpath),
                                                                 list(state["runs"].values())))
    assert first == again == named
    assert run_folders() == runs_before
    text = "\n".join(first)
    assert "## Accuracy per set (paired)" in text and "| standalone | standalone |" in text
    assert "## Not in the manifest" in text and "standalone: " in text
    assert "information only" in text and "## Timing" in text and "## Repeat" in text
    rows = compare.out_dir(data, PINNED, CANDIDATE) / "rows"
    assert (rows / "standalone.jsonl").is_file() and (compare.out_dir(data, PINNED, CANDIDATE) / "figures.json").is_file()
    assert c._done(state["runs"]["sets:new:decisions"])
    n_runs = len(runs_before)
    assert await c.step("sets") == 0 and len(run_folders()) == n_runs   # finished runs are skipped


async def test_a_drifted_base_canary_runs_again(tmp_path: Path) -> None:
    """Audit F-03: the base canary's drift stops the comparison; once the user has dealt with it, the next
    `compare-models` re-runs that canary instead of reading the old drift forever. The candidate's is kept."""
    def meta(run_id: str, status: str) -> None:
        folder = tmp_path / "evals" / run_id / "naive"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "run.json").write_text(json.dumps({"status": status}), encoding="utf-8")

    asked: list[str] = []

    class Stub:
        base = type("Base", (), {"test_mode": True})()
        last_run_id: str | None = None

        async def run(self, opts: Options) -> int:
            asked.append(opts.suite)
            self.last_run_id = "run-new"
            meta("run-new", "ok")
            return 0

    meta("run-drift", "drift")
    c = compare.Comparison(tmp_path, PINNED, CANDIDATE, "m.json", runner_for=Stub, out=lambda _s: None)
    c.state["runs"] = {"canary:base": "run-drift", "canary:new": "run-drift"}
    assert await c._run("canary:base", Options("canary"), prices=None) == (0, "run-new")
    assert await c._run("canary:new", Options("canary"), prices=None) == (0, "run-drift") and asked == ["canary"]


# ── 4.3: pairing and scoring ──
def test_the_paired_mcnemar_example() -> None:
    """The spec's example: 40 test items, 1.13 right on 30, the candidate on 34; b 2, c 6."""
    base_r = {str(i): i < 28 or 28 <= i < 30 for i in range(40)}
    new_r = {str(i): i < 28 or 30 <= i < 36 for i in range(40)}
    p = compare.paired(base_r, new_r)
    assert (p["n"], p["base"], p["new"], p["b"], p["c"]) == (40, 30, 34, 2, 6)
    assert p["p"] == pytest.approx(mcnemar_exact(2, 6)) and not p["moves"]
    assert p["smallest"] == pytest.approx(6 / 40)   # all six discordant pairs one way is the least n = 40 could show
    assert "30/40" in compare._pair_line(p) and "34/40" in compare._pair_line(p) and "b 2, c 6" in compare._pair_line(p)


def _noul_rows(qid: str, split: str, ps: list[tuple[float, str]]) -> list[dict[str, Any]]:
    return [{"id": f"{split}-{i}", "question_id": qid, "split": split, "lang": "en", "label": lab, "p": p}
            for i, (p, lab) in enumerate(ps)]


def test_a_threshold_is_chosen_from_dev_rows_only() -> None:
    g = next(x for x in compare.GROUPS if x.name == "standalone")
    dev = _noul_rows("standalone", "dev", [(0.1, "no")] * 9 + [(0.25, "no")] + [(0.8, "yes")] * 10)
    test = _noul_rows("standalone", "test", [(0.2, "no"), (0.3, "no"), (0.9, "yes"), (0.6, "yes")])
    one = compare.score_group(g, dev + test, dev + test)
    changed = [{**r, "p": 1.0 - float(r["p"])} for r in test]            # the test rows altered
    two = compare.score_group(g, dev + test, dev + changed)
    assert one["chosen"] == two["chosen"] == pytest.approx(0.15)          # the lowest sending ≥ 90 % of follow-ups
    assert one["retuned"]["n"] == 4 and one["retuned"] != two["retuned"]  # only the test reading moves


def test_a_set_with_no_rule_repeats_drop_in_and_says_so() -> None:
    g = next(x for x in compare.GROUPS if x.name == "english")
    rows = _noul_rows("english", "dev", [(0.9, "yes"), (0.1, "no")]) + _noul_rows("english", "test",
                                                                                   [(0.9, "yes"), (0.4, "yes")])
    s = compare.score_group(g, rows, rows)
    assert "no rule to tune" in s["retuned"]["note"] and s["retuned"]["new"] == s["drop_in_test"]["new"] == 1


# ── 4.4: the behaviour figures ──
def test_first_option_in_both_orders_counts_as_a_flip_and_both_firsts() -> None:
    """The spec's scenario: the first listed option in the declared order and again in the reversed order."""
    from horizon.ai.decider import Choice
    from horizon.evals.suites import item_question

    item = next(json.loads(ln) for ln in (REAL / "emotion" / "emotion.jsonl").read_text(encoding="utf-8").splitlines()
                if ln.strip())
    q = item_question(item)
    assert isinstance(q, Choice)
    opts = list(q.options)
    row = {"id": item["id"], "question_id": item["question_id"], "answer": opts[0], "answer_reversed": opts[-1]}
    f = compare.order_figures([row], {item["id"]: item})
    assert f == {"n": 1, "flip": 1.0, "first_declared": 1.0, "first_reversed": 1.0, "first_both": 1.0}


def test_calibration_bins_and_ece() -> None:
    cal = compare.calibration([(0.15, False), (0.15, True), (0.95, True), (0.95, True)])
    assert cal["bins"]["0.1"] == {"n": 2, "mean_p": 0.15, "yes_rate": 0.5}
    assert cal["ece"] == pytest.approx(0.5 * 0.35 + 0.5 * 0.05)


def test_deadline_misses_weigh_each_bucket_by_its_live_share() -> None:
    rows = [{"model": "a", "bucket": "<1k", "window": "a", "ms": ms} for ms in (300, 900)] + \
           [{"model": "a", "bucket": "1k-2.5k", "window": "a", "ms": ms} for ms in (500, 600, 800, 900)] + \
           [{"model": "a", "bucket": "<1k", "window": "a", "ms": 5000, "warmup": True}]
    got = compare.deadline_misses(rows, {"turn_plan": 700, "guardrail": 800},
                                  {"turn_plan": {"<1k": 0.5, "1k-2.5k": 0.5}, "guardrail": {"<1k": 1.0}})
    assert got == {"turn_plan": {"a": pytest.approx(0.5 * 0.5 + 0.5 * 0.5)}, "guardrail": {"a": pytest.approx(0.5)}}


# ── 4.5: the timing probe, on fixed latencies ──
async def test_the_timing_probe_excludes_warm_up_and_reports_windows_apart(api: Api, tmp_path: Path,
                                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    from horizon.evals import compare_probes
    from horizon.gateway.decisions import DecisionsResponse

    await api.set_key()
    now = [0.0]
    monkeypatch.setattr(compare_probes, "CLOCK", lambda: now[0])
    fixed = {PINNED: 0.420, CANDIDATE: 0.380}   # seconds

    async def decide(state: Any, questions: Any, ctx: Any, *, model: str | None = None, **_kw: Any) -> Any:
        now[0] += fixed[str(model)]
        return DecisionsResponse("gen-t", {"q": {"noul": 0.5}}, None, model)

    monkeypatch.setattr(api.rt.gateway, "decide", decide)
    bodies = [{"set": "s", "hash": f"h{i}", "state": {"x": "y"}, "questions": {}, "tokens": 100, "bucket": "<1k",
               "padded": False} for i in range(8)]
    plan = Plan(items=[{"warmup": bodies[:5], "bodies": bodies}], estimate_usd=0.0, expected_s=1.0,
                               paid=True, calls_chat=False)
    rows = []
    for w in ("a", "b"):
        run_dir = tmp_path / w / "naive"
        run_dir.mkdir(parents=True)
        opts = Options("compare-timing", pair=(PINNED, CANDIDATE), part=w, against="m.json")
        res = await compare_probes.TimingProbe().run(RunEnv(rt=api.rt, opts=opts, store=None, run_dir=run_dir,
                                                            max_usd=1.0), plan)
        rows += res.rows
    f = compare.timing_figures(rows)
    assert f["warmup_excluded"] == 2 * 2 * 5                          # 5 per model per window, counted
    for w in ("a", "b"):
        assert f["stats"][PINNED]["<1k"][w]["n"] == 8 and f["stats"][PINNED]["<1k"][w]["p50"] == pytest.approx(420)
        assert f["stats"][CANDIDATE]["<1k"][w]["p50"] == pytest.approx(380)
    firsts = [r["model"] for r in rows if not r["warmup"] and r["first"] and r["window"] == "a"]
    assert firsts[:4] == [PINNED, CANDIDATE, PINNED, CANDIDATE]       # which model goes first alternates


def test_padding_reaches_the_bucket_with_the_bodys_own_lines() -> None:
    from horizon.evals import compare_probes

    body = {"set": "judges", "hash": "abc", "state": {"quoted_messages": "Amara: hello there\nVictor: and you",
                                                     "other": "x"}, "questions": {"q": {"type": "noul"}}, "tokens": 20}
    p = compare_probes.padded(body, 10000)
    assert p is not None and compare_probes.bucket_of(p["tokens"]) == "~10k" and p["padded"]
    assert set(p["state"]["quoted_messages"].split("\n")) == {"Amara: hello there", "Victor: and you"}
    assert p["state"]["other"] == "x" and p["hash"].startswith("padded:abc")


# ── 4.6: the repeat probe's figures ──
def test_repeat_figures_on_fixed_answers() -> None:
    def ask(model: str, iid: str, choice: str, p: float) -> dict[str, Any]:
        return {"model": model, "id": iid, "answers": {"q": {"choice": choice,
                                                            "probabilities": {choice: p, "z": 1 - p}}}}

    rows = [ask("a", "i1", "x", 0.70), ask("a", "i1", "x", 0.74), ask("a", "i1", "x", 0.72),
            ask("b", "i1", "x", 0.70), ask("b", "i1", "y", 0.60), ask("b", "i1", "x", 0.70)]
    f = compare.repeat_figures(rows)
    assert f["a"] == {"items": 1, "changed": 0, "max_p_move": pytest.approx(0.04), "max_score_move": 0.0}
    assert f["b"]["changed"] == 1


def test_a_comparison_cap_follows_the_users_rule() -> None:
    from horizon.domain.pricing import load_price_table

    prices = load_price_table(EVALS_DIR.parent / "seed")
    assert compare.cap_for(Options("canary"), prices) == 0.01          # max(1.5 × a tiny estimate, $0.01)


def test_the_cost_per_reply_is_computed_from_the_latency_runs_tokens(tmp_path: Path) -> None:
    """D9: a 1:1 reply's Jev input tokens (turn_plan, guardrail, face_check, reaction) at each model's price."""
    folder = tmp_path / "evals" / compare.LIVE_LATENCY_RUN / "agent"
    folder.mkdir(parents=True)
    (folder / "run.json").write_text("{}", encoding="utf-8")
    con = sqlite3.connect(folder / "horizon.db")
    con.execute("CREATE TABLE usage_records (category TEXT, purpose TEXT, model TEXT, cost_usd REAL, tokens_in INT, "
                "latency_ms INT, is_seed INT)")
    rows = [("turn_plan", 2000), ("guardrail", 600), ("turn_plan", 2200), ("reaction", 2400), ("embed", 9999)]
    con.executemany("INSERT INTO usage_records VALUES ('decision', ?, 'm', 0.0, ?, 500, 0)", rows)
    con.commit()
    con.close()
    got = compare.turn_cost(tmp_path, {PINNED: 0.042, CANDIDATE: 0.084})
    assert got is not None and got["turns"] == 2 and got["tokens_per_turn"] == pytest.approx(3600)
    assert got["usd_per_turn"] == {PINNED: pytest.approx(3600 * 0.042 / 1e6), CANDIDATE: pytest.approx(3600 * 0.084 / 1e6)}
    assert compare.turn_cost(tmp_path / "elsewhere", {PINNED: 0.042}) is None

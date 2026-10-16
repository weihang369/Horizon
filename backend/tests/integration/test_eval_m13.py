"""M13's evaluation, offline (memory design D39, D40; tasks 9.1–9.4; evaluation-harness "The memory decision sets",
"The memory suite"). Everything runs on the in-process fake or on fixtures."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from horizon.evals import m13_sets
from horizon.evals import memory_suite as MS
from horizon.evals.runner import Options, Plan, Runner
from tests.integration.test_eval_runner import SATURDAY, base

ROOT = Path(__file__).resolve().parents[3]
DATASETS = ROOT / "evals" / "datasets"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, mod)
    spec.loader.exec_module(mod)
    return mod


def _lines(rows: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


# ── 9.1 the decision sets ──
def test_the_four_sets_build_to_their_counts_and_match_the_committed_files() -> None:
    b = _load("earlier_build", DATASETS / "earlier" / "build.py")
    prof = b.docs_build.profiles()
    docs = b.docs_build.titles(prof)
    sets = {"importance": b.build_importance(prof), "memory_guard": b.build_guard(prof),
            "earlier": b.build_earlier(prof, docs), "recall": b.build_recall(prof)}
    assert b.problems(sets) == []
    for name, rows in sets.items():
        assert (DATASETS / name / f"{name}.jsonl").read_text(encoding="utf-8") == _lines(rows)
        assert {r["split"] for r in rows} == {"dev", "test"}
    imp = sets["importance"]
    assert len(imp) == 100 and sum(1 for r in imp if int(r["label"]) <= 1) >= 30
    guard = sets["memory_guard"]
    assert len(guard) >= 110 and sum(1 for r in guard if r["label"] == "no") >= 60
    for name in ("earlier", "recall"):
        assert len(sets[name]) >= 110 and sum(1 for r in sets[name] if r["label"] == "yes") >= 60
    assert all(r["item"]["key"].startswith("earlier:") for r in sets["earlier"])
    assert {r["kind"] for r in sets["recall"]} == {"line", "memory"}


def test_the_threshold_rules_on_fixture_answers() -> None:
    # t_keep: the lowest threshold letting ≤ 5 % of lossy rewrites through
    lossy = [(0.1 * i, False) for i in range(1, 8)]          # 0.1 … 0.7
    good = [(0.9, True)] * 10
    assert m13_sets.choose_t_keep([*lossy, *good]) == pytest.approx(0.75)
    # t_recall: the lowest threshold with precision ≥ 85 %
    rows = [(0.9, True)] * 17 + [(0.6, False)] * 5 + [(0.4, True)] * 2   # 19/24 below 0.4, 17/22 to 0.6
    assert m13_sets.choose_t_recall(rows) == pytest.approx(0.65)
    # importance: level 1 drops (unit below 0.25), the rest keep
    imp = [{"label": 1, "unit": 0.0, "split": "dev", "lang": "en"}, {"label": 3, "unit": 0.5, "split": "dev",
                                                                     "lang": "en"}]
    assert m13_sets._balanced(imp)[0] == 1.0


async def test_decisions_runs_the_four_sets_under_their_live_keys(tmp_path: Path) -> None:
    from horizon.evals.suites import Decisions

    items: list[dict[str, Any]] = []
    for name in ("importance", "memory_guard", "earlier", "recall"):
        rows = [json.loads(x) for x in (DATASETS / name / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()]
        items += [r for r in rows if r["split"] == "dev"][:4] + [r for r in rows if r["split"] == "test"][:4]
    seen: list[str] = []

    async def decide(state: Any, qs: dict[str, Any], ctx: Any) -> Any:
        seen.extend(qs)
        return SimpleNamespace(answers={k: {"noul": 0.8, "score": 0.8} for k in qs})

    async def no() -> bool:
        return False

    run_dir = tmp_path / "evals" / "run" / "agent"
    run_dir.mkdir(parents=True)
    cfg = SimpleNamespace(runtime=SimpleNamespace(emotion_fade=frozenset()))
    env = SimpleNamespace(rt=SimpleNamespace(gateway=SimpleNamespace(decide=decide), runtime_cfg=cfg),
                          opts=Options("decisions"), run_dir=run_dir, over_budget=no)
    res = await Decisions().run(env, Plan(items=items, estimate_usd=0.0, expected_s=1.0, paid=False))  # type: ignore[arg-type]
    assert len(res.rows) == len(items)
    assert {k.split(":")[0] for k in seen} == {"importance", "memory_guard", "earlier", "recall"}
    assert any(k.startswith("earlier:chr_") for k in seen) and any(k.startswith("recall:") for k in seen)
    text_ = "\n".join(res.summary)
    for head in ("Rewrite guard (memory_guard)", "Needs something from earlier? (earlier)",
                 "Earlier line helps? (recall)"):
        assert head in text_


# ── 9.3 the judges ──
def test_the_planted_judge_sets_match_the_committed_files() -> None:
    b = _load("m13_judges_build", DATASETS / "judges" / "m13_build.py")
    for qid, rows in {"judge_memory_missed": b.missed(), "judge_memory_unsupported": b.unsupported(),
                      "judge_memory_lost": b.lost(), "judge_over_mention": b.over_mention()}.items():
        assert (DATASETS / "judges" / f"{qid}.jsonl").read_text(encoding="utf-8") == _lines(rows)
        assert len(rows) == 30 and sum(r["label"] == "yes" for r in rows) == 15 and all(r["planted"] for r in rows)


def test_an_unvalidated_judge_reads_not_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("horizon.evals.judges.validated", lambda qid, v, record=None: qid == "judge_memory_lost")
    rows = [{"id": "r1", "kind": "stretch", "missed": [True, False], "unsupported": [False], "duplicated": [False],
             "lost": [False, False], "touched": [False]}]
    rep = MS.rewrite_report(rows)
    missed = next(x for x in rep if x.startswith("- expected changes covered"))
    lost = next(x for x in rep if x.startswith("- still-true facts lost"))
    assert "NOT COUNTED" in missed and "failures 1/2" in missed
    assert "NOT COUNTED" not in lost and "0/2" in lost and "target ≤ 5%" in lost


def test_a_memory_for_an_absent_character_cannot_be_written() -> None:
    """D40: a unit test, not a judge. The call names characters by their number among those present, so a number
    past the list, or an `about` naming nobody present, is dropped by the code checks."""
    from horizon.ai.memory import rewrite as mem1
    from tests.sessions.test_memory_writer_m13 import AMARA, _present, _stretch

    s = _stretch([_present(1, AMARA, "Amara")])
    out = mem1.check([{"for": 2, "op": "add", "kind": "fact", "text": "Kai likes tea", "source": 1},
                      {"for": 1, "op": "add", "kind": "fact", "about": 5, "text": "Kai likes tea", "source": 1},
                      {"for": 1, "op": "add", "kind": "fact", "text": "Kai likes tea", "source": 1}], s)
    assert [c.character_id for c in out.changes] == [AMARA] and len(out.log) == 2


async def test_score_rewrite_counts_each_target(tmp_path: Path) -> None:
    from horizon.ai.memory.rewrite import CallOutcome
    from horizon.ai.ports import Insert, MemoryDraft, Reinforce, Supersede
    from horizon.services.memory.stretch import WriterResult

    item = json.loads((MS.MEM_DIR / "rewrite.jsonl").read_text(encoding="utf-8").splitlines()[0])
    cid = item["present"][0]
    ls = {m["label"]: m for m in item["lists"][cid]}
    rw = next(e for e in item["expected"] if e["op"] == "rewrite")
    cf = next(e for e in item["expected"] if e["op"] == "confirm")
    untouched = item["untouched"][cid][0]
    target = SimpleNamespace(id=ls[rw["target"]]["id"])
    call = CallOutcome(changes=[SimpleNamespace(op="rewrite", character_id=cid, target=target, text=rw["text"])])  # type: ignore[list-item]
    result = WriterResult(ops={cid: [
        Supersede([ls[rw["target"]]["id"]], MemoryDraft(kind="fact", text=rw["text"], importance=0.6)),
        Reinforce(ls[cf["target"]]["id"], 0.65),
        Supersede([ls[untouched]["id"]], MemoryDraft(kind="fact", text="Kai's secret is 4471.", importance=0.6)),
        Insert(MemoryDraft(kind="fact", text="Kai likes tea.", importance=0.5))]})

    async def decide(state: Any, qs: dict[str, Any], ctx: Any) -> Any:
        return SimpleNamespace(answers={k: {"noul": 0.1} for k in qs})   # no judge flags a failure

    env = SimpleNamespace(rt=SimpleNamespace(gateway=SimpleNamespace(decide=decide)), run_dir=tmp_path)
    row = await MS.score_rewrite(env, item, call, result)  # type: ignore[arg-type]
    assert row["duplicated"] == [False]                          # the changed fact was rewritten
    assert row["missed"][1] is False                              # the confirm reinforced its line
    assert row["touched"].count(True) == 1                        # one untouched line was rewritten
    assert len(row["lost"]) == 2 and len(row["unsupported"]) == 3
    assert any("rewrote an untouched line" in f for f in row["failures"])
    states = [json.loads(x) for x in (tmp_path / "judge_states.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {s["question_id"] for s in states} == {"judge_memory_missed", "judge_memory_unsupported",
                                                  "judge_memory_lost"}
    secret = {**item, "kind": "secret", "secret": "4471", "expected": [], "untouched": {}}
    assert (await MS.score_rewrite(env, secret, call, result))["secret_stored"] is True  # type: ignore[arg-type]


# ── 9.2 the suite's inputs ──
def test_the_memory_inputs_build_deterministically_and_match_the_committed_files() -> None:
    b = _load("memory_build", ROOT / "evals" / "memory" / "build.py")
    prof = b.profiles()
    sets = {"rewrite": b.build_rewrite(prof), "probes": b.build_probes(), "layer3": b.build_layer3()}
    assert sets["rewrite"] == b.build_rewrite(prof)
    for name, rows in sets.items():
        assert (MS.MEM_DIR / f"{name}.jsonl").read_text(encoding="utf-8") == _lines(rows)
    rw = sets["rewrite"]
    stretches = [r for r in rw if r["kind"] == "stretch"]
    modes = {m: sum(1 for r in stretches if r["mode"] == m) for m in ("one_on_one", "group", "watch", "debate")}
    assert modes == {"one_on_one": 8, "group": 8, "watch": 4, "debate": 4}
    assert sum(1 for r in stretches if r["lang"] != "en") >= 2
    assert sum(r["kind"] == "secret" for r in rw) == 6 and sum(r["kind"] == "small_talk" for r in rw) == 6
    assert all(10 <= len(ls) <= 20 for r in stretches for ls in r["lists"].values())
    probes = sets["probes"]
    assert sum(p["kind"] == "in_session" for p in probes) == 60 and sum(p["kind"] == "overflow" for p in probes) == 40
    assert all(40 <= p["memories"] <= 60 for p in probes if p["kind"] == "overflow")
    assert len(sets["layer3"]) == 20 and all(len(p["probes"]) == 2 and len(p["unrelated"]) == 2
                                            for p in sets["layer3"])


def test_every_overflow_probe_ranks_its_needed_memory_below_the_list() -> None:
    from horizon.domain.runtime_config import RuntimeConfig
    from horizon.services.memory.block import MemoryRow, fill, rank

    data = json.loads((ROOT / "seed" / "runtime.json").read_text(encoding="utf-8"))["data"]
    knobs = RuntimeConfig.from_json(data).runtime.memory
    now = datetime(2026, 10, 16, tzinfo=UTC)
    for p in MS.load("probes"):
        if p["kind"] != "overflow":
            continue
        plants = MS.overflow_list(p["fact_id"], p["memories"])
        assert len(plants) == p["memories"] and len({x["text"] for x in plants}) == len(plants)
        rows = [MemoryRow(id=x["id"], kind="fact", text=x["text"], importance=x["importance"],
                          source_mode="one_on_one", created_at=(now - timedelta(days=x["days"])).isoformat(),
                          last_recalled_at=None) for x in plants]
        listed = {m.id for m in fill(rank(rows, now, knobs), knobs.block_tokens)}
        assert plants[0]["id"] not in listed and plants[0]["text"] == p["needed"], p["id"]


def test_the_dup_pairs_and_the_chosen_cosine() -> None:
    pairs = MS.dup_pairs()
    assert sum(p["same"] for p in pairs) == 40 and len(pairs) > 100 and {p["split"] for p in pairs} == {"dev", "test"}
    rows = [{"split": "dev", "same": True, "cosine": 0.95}] * 19 + [{"split": "dev", "same": False, "cosine": 0.93}] \
        + [{"split": "dev", "same": False, "cosine": 0.85}] * 10
    assert MS.choose_dup(rows) == pytest.approx(0.86)   # 19/20 = 95 % at 0.86
    assert MS.choose_dup([{"split": "dev", "same": False, "cosine": 0.99}]) is None
    rep = "\n".join(MS.dup_report([*rows, *[{**r, "split": "test"} for r in rows]], 0.92))
    assert "chosen on dev: 0.86" in rep and "differs from the live 0.92" in rep


def test_a_recall_arm_is_compared_by_k3s_rule_per_probe_kind(tmp_path: Path) -> None:
    def run(folder: str, arm: str | None, hits: list[bool]) -> Path:
        d = tmp_path / folder
        d.mkdir()
        rows = [{"part": "recall", "id": f"p{i}", "split": "dev" if i % 4 else "test", "kind": "in_session",
                 "arm": arm, "hit3": h, "recall6": h} for i, h in enumerate(hits)]
        (d / "results.jsonl").write_text(_lines(rows), encoding="utf-8")
        return d

    base = run("base", None, [i % 2 == 0 for i in range(40)])
    better = run("arm", "lambda=0.5", [True] * 40)
    rep = "\n".join(MS.compare_report(base, better))
    assert "`lambda=0.5`" in rep and "hit3" in rep and "goes to the user" in rep
    with pytest.raises(ValueError):
        MS.compare_report(better, base)


def test_the_arms_and_parts_are_checked() -> None:
    m = MS.Memory()
    assert "--profile agent" in (m.refuse(Options("memory", profile="naive")) or "")
    assert m.refuse(Options("memory", profile="agent", part="recall", arm="search=bm25")) is None
    assert m.refuse(Options("memory", profile="agent", part="recall", arm="lambda=0.5")) is None
    assert "--part recall" in (m.refuse(Options("memory", profile="agent", arm="mmr=off")) or "")
    assert "unknown arm" in (m.refuse(Options("memory", profile="agent", part="recall", arm="search=fts")) or "")
    assert "unknown part" in (m.refuse(Options("memory", profile="agent", part="all")) or "")


# ── the suite on the fake ──
def _runner(tmp_path: Path) -> tuple[Runner, list[str]]:
    (tmp_path / "secrets.local.json").write_text('{"openRouterKey": "sk-or-test-0001"}', encoding="utf-8")
    out: list[str] = []
    return Runner(base(tmp_path), stdin=lambda _p: "y", out=out.append, now=lambda: SATURDAY), out


def _run_folder(tmp_path: Path) -> Path:
    (run,) = [p for p in (tmp_path / "evals").iterdir() if p.is_dir()]
    return run / "agent"


async def test_the_memory_suite_runs_offline_on_the_fake(tmp_path: Path) -> None:
    r, out = _runner(tmp_path)
    assert await r.run(Options("memory", profile="agent", limit=2, yes=True)) == 0, out
    folder = _run_folder(tmp_path)
    rep = (folder / "report.md").read_text(encoding="utf-8")
    assert "## Rewrite" in rep and "## Recall" in rep and "## Layer 3" in rep and "NOT COUNTED" in rep
    rows = [json.loads(x) for x in (folder / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [x["part"] for x in rows] == ["rewrite"] * 2 + ["recall"] * 2 + ["layer3"] * 2
    recall = [x for x in rows if x["part"] == "recall"]
    assert all(x["picked"] and x["outcome"] and not x["dense_missing"] for x in recall)
    layer3 = [x for x in rows if x["part"] == "layer3"]
    assert all(x["written_settled"] and len(x["turns"]) == 4 for x in layer3)
    assert (folder / "judge_states.jsonl").is_file()


async def test_check_2_times_the_runs_store_bypassed(tmp_path: Path) -> None:
    r, out = _runner(tmp_path)
    assert await r.run(Options("memory", profile="agent", part="rewrite", limit=2, latency=True, yes=True)) == 0, out
    folder = _run_folder(tmp_path)
    rows = [json.loads(x) for x in (folder / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    assert all(x["latency"] and x["run_ms"] >= 0 and x["calls"] >= 1 for x in rows)
    assert "### Check 2: pause-run time, store-bypassed (2 runs)" in (folder / "report.md").read_text(encoding="utf-8")


async def test_a_recall_arm_runs_without_jev_call_2(tmp_path: Path) -> None:
    r, out = _runner(tmp_path)
    assert await r.run(Options("memory", profile="agent", part="recall", arm="search=dense", limit=2,
                               yes=True)) == 0, out
    rows = [json.loads(x) for x in (_run_folder(tmp_path) / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2 and all("kept" not in x and x["arm"] == "search=dense" for x in rows)
    assert all(x["lists"]["lines_bm25"] == 0 for x in rows)


async def test_the_overflow_probes_and_the_latency_tail_run_offline(tmp_path: Path) -> None:
    r, out = _runner(tmp_path)
    probes = MS.load("probes")
    start = next(i for i, p in enumerate(probes) if p["kind"] == "overflow")
    assert await r.run(Options("memory", profile="agent", part="recall", start=start, limit=2, latency=True,
                               yes=True)) == 0, out
    folder = _run_folder(tmp_path)
    rows = [json.loads(x) for x in (folder / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [x["kind"] for x in rows] == ["overflow", "overflow"] and not any(x.get("listed") for x in rows)
    assert all(re.fullmatch(r"[a-z]+_[0-9A-Za-z]{1,40}", x["needed"]) and x["latency"] for x in rows)
    assert "`recall.checkMs` from the tail" in (folder / "report.md").read_text(encoding="utf-8")


async def test_the_dup_sweep_runs_offline(tmp_path: Path) -> None:
    r, out = _runner(tmp_path)
    assert await r.run(Options("memory", profile="agent", part="dup", yes=True)) == 0, out
    folder = _run_folder(tmp_path)
    rows = [json.loads(x) for x in (folder / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == len(MS.dup_pairs()) and all(-1.0 <= x["cosine"] <= 1.0 for x in rows)
    assert "## dupCosine (D39)" in (folder / "report.md").read_text(encoding="utf-8")


# ── 10.6's instrument: check 4 and D33's timing ──
async def test_the_recall_timing_runs_offline_with_both_arms(tmp_path: Path) -> None:
    r, out = _runner(tmp_path)
    assert await r.run(Options("latency", profile="agent", part="recall", limit=2, yes=True)) == 0, out
    (run,) = [p for p in (tmp_path / "evals").iterdir() if p.is_dir()]
    folder = run / "agent"
    rows = [json.loads(x) for x in (folder / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    runs = [x["deep_run"] for x in rows if "deep_run" in x]
    assert {x["arm"] for x in runs} == {"recall", "both"}
    assert all(x.get("recall_outcome") for x in runs)
    both = [x for x in runs if x["arm"] == "both"]
    assert all(x.get("passage_slowest_ms") is not None and "recall_after_docs_ms" in x for x in both)
    assert not any(x.get("docs_ms") for x in runs if x["arm"] == "recall")   # recall only: no documents branch
    rep = (folder / "report.md").read_text(encoding="utf-8")
    assert "slowest of all 14" in rep and "Jev 429s: none" in rep


def test_d33s_tail_rule_goes_to_the_user_over_200_ms() -> None:
    from types import SimpleNamespace as NS

    from horizon.evals import recall_timing as RT

    rec = RT.Recorder()
    rec.runs = [{"arm": "both", "recall_slowest_ms": 400.0, "passage_slowest_ms": 300.0,
                 "recall_after_docs_ms": float(t), "recall_outcome": "jev"} for t in (0, 50, 100, 150, 250, 300, 350,
                                                                                      400, 450, 500)]
    knobs = NS(recall=NS(check_ms=1500.0))
    assert any("the user gets a choice" in x for x in RT.report([], rec, knobs))
    rec.runs = [{**x, "recall_after_docs_ms": 10.0} for x in rec.runs]
    assert not any("the user gets a choice" in x for x in RT.report([], rec, knobs))

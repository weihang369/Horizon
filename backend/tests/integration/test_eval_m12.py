"""M12's evaluation additions, offline (rag design D22–D24, D30, D31.4; tasks 9.1–9.8; evaluation-harness's M12
requirements). Everything runs on the in-process fake."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from horizon.evals import suites
from horizon.evals.runner import KEEP_RUNS, Options, Plan, Result, Runner, finish_run
from tests.integration.test_eval_runner import SATURDAY, base


# ── 9.1 paid runs are kept ──
class PaidShaped:
    """A suite that plans a paid run but sends nothing (the fake stands in)."""

    name = "paid_shaped"

    def plan(self, opts: Options, prices: Any, *, paid: bool) -> Plan:
        return Plan(items=[], estimate_usd=0.0, expected_s=1.0, paid=True)

    async def run(self, env: Any, plan: Plan) -> Result:
        return Result()


async def test_a_paid_run_is_marked_keep(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(suites.SUITES, "paid_shaped", PaidShaped())
    cfg = base(tmp_path)
    (tmp_path / "secrets.local.json").write_text('{"openRouterKey": "sk-or-test-0001"}', encoding="utf-8")   # a key
    out: list[str] = []
    r = Runner(cfg, stdin=lambda _p: "y", out=out.append, now=lambda: SATURDAY)
    assert await r.run(Options("paid_shaped", yes=True)) == 0, out
    (run,) = [p for p in (tmp_path / "evals").iterdir() if p.is_dir()]
    assert (run / ".keep").is_file()


def test_smoke_runs_are_still_pruned_past_twenty(tmp_path: Path) -> None:
    for i in range(KEEP_RUNS + 3):
        (tmp_path / f"20261003T03{i:02d}00-smoke-x").mkdir()
    (tmp_path / "20261003T020000-retrieval-x").mkdir()
    gone = finish_run(tmp_path, "20261003T020000-retrieval-x", paid=True)
    assert len(gone) == 3 and all("smoke" in g for g in gone)
    assert (tmp_path / "20261003T020000-retrieval-x" / ".keep").is_file()
    assert finish_run(tmp_path, "20261003T030000-smoke-x", paid=False) == []


# ── 9.2 the retrieval dataset ──
BUILD = Path(__file__).resolve().parents[3] / "evals" / "datasets" / "retrieval" / "build.py"


def _builder() -> Any:
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("retrieval_build", BUILD)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("retrieval_build", mod)
    spec.loader.exec_module(mod)
    return mod


def test_the_builder_is_deterministic_and_matches_the_committed_file() -> None:
    import json

    from horizon.evals.retrieval import DATASET

    b = _builder()
    one, two = b.build(), b.build()
    assert one == two
    assert DATASET.read_text(encoding="utf-8") == "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in one)


def test_every_span_resolves_to_its_source_text() -> None:
    from horizon.evals.retrieval import load_questions, seed_chunks, span_problems

    qs = load_questions()
    assert qs and any(s["doc"].startswith("seed:") for q in qs for s in q["spans"])
    seeds = {cid: text for cid, (_, text) in seed_chunks().items()}
    assert span_problems(qs, seeds) == []
    moved = [{**qs[0], "spans": [{**qs[0]["spans"][0], "start": qs[0]["spans"][0]["start"] + 1}]}]
    assert span_problems(moved, seeds) == [f"{qs[0]['id']}: span moved in {qs[0]['spans'][0]['doc']}"]


def test_the_builder_refuses_a_missing_or_twice_found_quote() -> None:
    b = _builder()
    q = {"id": "ret-z1", "kind": "answerable", "who": "hana", "message": "m"}
    with pytest.raises(ValueError, match="not found"):
        b.build([{**q, "spans": [{"doc": "hana/ars-go-nuts.md", "quote": "no such words here at all", "grade": 2}]}])
    with pytest.raises(ValueError, match="ambiguous"):
        b.build([{**q, "spans": [{"doc": "hana/ars-go-nuts.md", "quote": "Walnuts", "grade": 2}]}])
    rows = b.build([{**q, "kind": "unanswerable", "spans": [{"doc": "hana/ars-go-nuts.md", "quote": "Go nuts!",
                                                             "grade": 2}]}])
    assert b.problems(rows, full=False) == ["ret-z1: an unanswerable question has spans"]
    assert rows[0]["split"] in ("dev", "test") and rows[0]["character"] == "chr_seedHana"


def test_overlap_reports_zero_on_a_fixture_set_and_catches_a_copy() -> None:
    from horizon.ai.questions import bank
    from horizon.evals.datachecks import overlap_problems

    fixture = [{"id": "ret-a001", "item": ["Which nut has more protein than the others?"]},
               {"id": "ret-f001", "item": ["So what should I do with them instead?", "Kai: I keep walnuts."]}]
    assert overlap_problems(fixture) == []
    copied = " ".join(str(bank().entries["docs"].raw["instructions"]).split()[:8])
    assert overlap_problems([{"id": "ret-z", "item": [copied]}])


# ── 9.3 the metrics and the report ──
def _piece(cid: str, a: int, b: int, doc: str = "hana/x.md") -> Any:
    from horizon.evals.retrieval import Piece

    return Piece(chunk_id=cid, doc=doc, start=a, end=b)


def test_a_piece_covers_a_span_at_eighty_percent_of_its_characters() -> None:
    from horizon.evals.retrieval import covers

    span = {"doc": "hana/x.md", "start": 100, "end": 200, "grade": 2}
    assert covers(_piece("a", 0, 180), span) and not covers(_piece("b", 0, 179), span)
    assert not covers(_piece("c", 0, 500, "hana/y.md"), span)
    seeded = {"doc": "seed:kno_s", "chunk": "kch_1", "start": 0, "end": 10, "grade": 2}
    assert covers(_piece("kch_1", 0, 0, "seed:kno_s"), seeded) and not covers(_piece("kch_2", 0, 99, "seed:kno_s"),
                                                                              seeded)


def test_every_metric_on_fixture_pieces() -> None:
    import math

    from horizon.evals import retrieval as R

    spans = [{"doc": "hana/x.md", "start": 0, "end": 10, "grade": 2},
             {"doc": "hana/x.md", "start": 50, "end": 60, "grade": 2},
             {"doc": "hana/x.md", "start": 90, "end": 100, "grade": 1}]
    a, b, c, miss = _piece("a", 0, 20), _piece("b", 45, 70), _piece("c", 88, 100), _piece("m", 200, 300)
    assert R.recall_at([miss, a, b], spans, 2) == 0.5 and R.recall_at([miss, a, b], spans, 3) == 1.0
    assert R.reciprocal_rank([miss, a], spans) == 0.5 and R.reciprocal_rank([miss], spans) == 0.0
    ideal = 3 / math.log2(2) + 3 / math.log2(3) + 1 / math.log2(4)
    assert R.ndcg_at([a, b, c], spans) == pytest.approx(1.0)
    assert R.ndcg_at([miss, a], spans) == pytest.approx((3 / math.log2(3)) / ideal)
    assert R.kept_precision([a, miss, c], spans) == pytest.approx(2 / 3) and R.kept_precision([], spans) is None
    assert R.recall_at([a], [], 8) is None


def _row(i: int, answerable: bool, split: str = "dev", origin: str = "corpus") -> Any:
    from horizon.evals.retrieval import Row

    p = (0.9, 0.05, 0.9) if answerable else (0.05, 0.1, 0.1)
    span = [{"doc": "hana/x.md", "start": 0, "end": 10, "grade": 2}] if answerable else []
    hit = _piece(f"p{i}", 0, 20)
    return Row(id=f"q{i}", split=split, kind="answerable" if answerable else "unanswerable", origin=origin,
               needs_two=False, spans=span, pool=[hit], candidates=[hit], kept=[hit] if answerable else [],
               outcome="found" if answerable else "not_found",
               checks=[{"chunkId": f"p{i}", "order": 0, "p_answers": p[0], "p_partly": p[1], "unit": p[2]}])


def test_leave_one_out_counts_and_the_report_keeps_seed_and_corpus_apart() -> None:
    from horizon.evals import retrieval as R

    rows = [_row(i, i % 3 != 0) for i in range(9)] + [_row(20, True, "test", "seed")]
    loo = R.leave_one_out([r for r in rows if r.split == "dev"])
    assert loo["wrong_abstains"] == 0 and loo["answerable"] == 6
    assert loo["abstained"] == 3 and loo["unanswerable"] == 3
    rep = "\n".join(R.report(rows))
    assert "### corpus (9 questions, 6 answerable)" in rep and "### seed (1 questions, 1 answerable)" in rep
    assert "- dev: wrong abstains 0/6" in rep and "unanswerable abstained 3/3" in rep
    assert "### The passage thresholds" in rep and "### Set checks: 0" in rep


# ── 9.3 the suite, offline ──
async def test_retrieval_runs_offline_on_the_fake(tmp_path: Path) -> None:
    import json

    cfg = base(tmp_path)
    (tmp_path / "secrets.local.json").write_text('{"openRouterKey": "sk-or-test-0001"}', encoding="utf-8")
    out: list[str] = []
    r = Runner(cfg, stdin=lambda _p: "y", out=out.append, now=lambda: SATURDAY)
    assert await r.run(Options("retrieval", profile="agent", limit=3, yes=True)) == 0, out
    (run,) = [p for p in (tmp_path / "evals").iterdir() if p.is_dir()]
    rep = (run / "agent" / "report.md").read_text(encoding="utf-8")
    assert "## Retrieval" in rep and "Recall@20" in rep and "kept-set precision" in rep
    rows = [json.loads(x) for x in (run / "agent" / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 3 and all(x["pool"] and x["checks"] and x["outcome"] for x in rows)
    assert not any(x["dense_missing"] for x in rows)


def test_retrieval_needs_the_agent_profile() -> None:
    from horizon.evals.retrieval_suite import Retrieval

    assert "--profile agent" in (Retrieval().refuse(Options("retrieval", profile="naive")) or "")
    assert Retrieval().refuse(Options("retrieval", profile="agent", arm="piece=200")) is None
    assert "unknown arm" in (Retrieval().refuse(Options("retrieval", profile="agent", arm="colour=red")) or "")


# ── 9.4 the comparisons ──
def _results(folder: Path, arm: str | None, gains: dict[str, float], metric: str = "recall8",
             kind: str = "answerable") -> Path:
    import json

    folder.mkdir(parents=True, exist_ok=True)
    rows = [{"id": f"q{i}", "split": "test" if i % 3 == 0 else "dev", "kind": kind, "arm": arm,
             metric: g, "recall20": 1.0, "kept_precision": 0.5 if arm else None} for i, g in enumerate(gains.values())]
    (folder / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return folder


def test_k3s_rule_keeps_the_default_on_a_two_point_gain() -> None:
    from horizon.evals.retrieval import verdict

    assert verdict([0.02] * 60)[0] == "tie or loss: the default stays"
    assert verdict([0.0] * 50 + [1.0] * 2)[0] == "tie or loss: the default stays"     # 3.8 points, interval not > 0
    assert verdict([0.05] * 60)[0] == "wins on dev: confirm once on test"
    assert verdict([0.05] * 60, [-0.01] * 30)[0] == "test reverses the gain: the default stays"
    assert verdict([0.05] * 60, [0.0] * 30)[0].startswith("wins (dev, and test does not reverse it)")


def test_a_fixture_comparison_reports_each_arm(tmp_path: Path) -> None:
    from horizon.evals.retrieval import ARM_FOCUS, compare_report

    n = {f"q{i}": 0.5 for i in range(30)}
    for arm in ("space=bge-m3@1024+h", "piece=200", "lambda=1.0", "rewrite=off"):
        key = arm.partition("=")[0]
        metric, kinds = ARM_FOCUS[key]
        kind = kinds[0] if kinds else "answerable"
        base = _results(tmp_path / f"base-{key}", None, n, metric, kind)
        better = _results(tmp_path / key, arm, {k: 0.6 for k in n}, metric, kind)
        rep = "\n".join(compare_report(base, better))
        assert f"## Comparison: `{arm}`" in rep and f"points of {metric}" in rep
        assert "(20 paired on dev)" in rep and "dev gain +10.0 points" in rep
        assert "verdict: wins (dev, and test does not reverse it)" in rep      # the test rows sit in the same runs
        assert ("kept-set precision on dev: 0.500" in rep) == (key == "piece")
    with pytest.raises(ValueError, match="not an arm run"):
        compare_report(tmp_path / "base-space", tmp_path / "base-piece")


def test_the_piece_arms_are_compared_at_a_fixed_token_budget() -> None:
    from horizon.evals.retrieval import Piece, recall_within

    spans = [{"doc": "d", "start": 0, "end": 10, "grade": 2}, {"doc": "d", "start": 900, "end": 910, "grade": 2}]
    small = [Piece("a", "d", 0, 20, 200)] + [Piece(f"m{i}", "d", 100, 120, 200) for i in range(5)] \
        + [Piece("b", "d", 900, 920, 200)]
    big = [Piece("a", "d", 0, 20, 400), Piece("m", "d", 100, 120, 400), Piece("b", "d", 900, 920, 400)]
    assert recall_within(small, spans) == 0.5          # 6 pieces of 200 fill the 1,200 tokens; b is the 7th
    assert recall_within(big, spans) == 1.0            # 3 pieces of 400


# ── 9.5 the M12 decision sets ──
def _noul_rows(qid: str, pairs: list[tuple[float, str]], split: str, lang: str = "en",
               kind: str | None = None) -> list[dict[str, Any]]:
    return [{"id": f"{qid}-{split}-{lang}-{i}", "question_id": qid, "split": split, "lang": lang, "p": p, "label": lab,
             **({"kind": kind} if kind else {})} for i, (p, lab) in enumerate(pairs)]


def test_docs_chooses_t_gate_by_recall_and_t_confident_by_precision() -> None:
    from horizon.evals import m12_sets as M

    # ten yes at 0.30 … 0.95, ten no at 0.05 … 0.50 (two of them high)
    yes = [(p, "yes") for p in (0.3, 0.42, 0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.93, 0.95)]
    no = [(p, "no") for p in (0.05, 0.05, 0.1, 0.1, 0.15, 0.2, 0.2, 0.25, 0.45, 0.5)]
    dev = [(p, y == "yes") for p, y in yes + no]
    assert M.choose_t_gate(dev) == 0.4                     # 9/10 yes kept; at 0.45 only 8
    assert M.choose_t_confident(dev, 0.4) == 0.55          # 0.50 still lets a no in
    rows = _noul_rows("docs", yes + no, "dev", kind="one_on_one") + _noul_rows("docs", yes + no, "test",
                                                                               kind="group")
    rows += _noul_rows("docs", [(0.9, "yes"), (0.1, "no")], "test", lang="ms")
    rep = "\n".join(M.docs_report(rows))
    assert "t_gate 0.40" in rep and "t_confident 0.55" in rep
    assert "recall at t_gate 0.90; deep rate on items needing no documents 2/10" in rep
    assert "- ms (runs, not scored for the threshold): 2/2" in rep and "- group:" in rep and "- one_on_one:" in rep
    assert "reworded" in "\n".join(M.docs_report(_noul_rows("docs", [(0.0, "yes")] * 3, "dev")
                                                + _noul_rows("docs", [(0.0, "yes")], "test")))


def test_standalone_sends_ninety_percent_of_follow_ups_to_the_rewrite() -> None:
    from horizon.evals import m12_sets as M

    follow = [(p, "no") for p in (0.05, 0.1, 0.1, 0.15, 0.2, 0.2, 0.25, 0.3, 0.35, 0.6)]
    alone = [(p, "yes") for p in (0.4, 0.7, 0.8, 0.85, 0.9, 0.9, 0.95, 0.95, 0.97, 0.99)]
    dev = [(p, y == "yes") for p, y in follow + alone]
    assert M.choose_t_standalone(dev) == 0.4               # 9/10 follow-ups below it; no standalone message yet
    rows = _noul_rows("standalone", follow + alone, "dev") + _noul_rows("standalone", follow + alone, "test")
    rep = "\n".join(M.standalone_report(rows))
    assert "t_standalone 0.40" in rep and "follow-ups rewritten 0.90; standalone messages rewritten 0.00" in rep


def test_english_reports_accuracy_per_language_against_95_percent() -> None:
    from horizon.evals import m12_sets as M

    rows = (_noul_rows("english", [(0.9, "yes")] * 10, "dev") + _noul_rows("english", [(0.1, "no")] * 10, "dev", "ms")
            + _noul_rows("english", [(0.2, "no")] * 9 + [(0.6, "no")], "test", "zh")
            + _noul_rows("english", [(0.3, "no")] * 10, "test", "mixed"))
    rep = M.english_report(rows)
    assert rep[0].startswith("## English? (english): accuracy 39/40") and "meets" in rep[0]
    assert "- zh: 9/10" in rep and "- ms: 10/10" in rep
    assert "misses" in M.english_report(rows[:30] + _noul_rows("english", [(0.9, "no")] * 10, "test", "mixed"))[0]


def test_d9_re_asks_with_titles_and_compares_with_the_recorded_answers() -> None:
    from horizon.ai.questions import bank
    from horizon.evals import m12_sets as M

    titles = M.seed_titles()
    assert titles["Amara Okafor"] == ["ED triage guidelines", "Meridian Shift Fatigue Review 2025"]   # newest first
    assert "Mei Tanaka-Ruiz" in titles and all("." not in t[-5:] for v in titles.values() for t in v)
    st = M.with_titles({"mode": "group", "quoted_cast": [{"name": "Amara Okafor"}, {"name": "Rin"}],
                        "quoted_latest": "x"}, titles)
    assert st is not None and list(st) == ["mode", "quoted_cast", "quoted_documents", "quoted_latest"]
    assert st["quoted_documents"] == {"Amara Okafor": titles["Amara Okafor"]}
    assert M.with_titles({"quoted_cast": [{"name": "Rin"}]}, titles) is None
    items = M.reask_items()
    assert items and all(i["reask"] and i["split"] == "dev" and "quoted_documents" in i["item"]["state"] for i in items)

    floor = float(bank().get("who_first").floor or 0.0)
    label = {"candidates": ["chr_a", "chr_b"], "acceptable": ["chr_a"], "none_ok": False, "last_spoke": {}}
    probs = {"chr_a": 0.9, "chr_b": 0.1}
    good = {"question_id": "who_first", "label": label, "answer": "chr_a", "confidence": max(0.9, floor),
            "probabilities": probs}
    bad = {**good, "answer": "chr_b", "probabilities": {"chr_a": 0.1, "chr_b": 0.9}}
    now = [{**(good if i < 18 else bad), "id": f"w{i}", "split": "dev", "reask": True} for i in range(20)]
    then = {("who_first", f"w{i}"): {**good, "id": f"w{i}"} for i in range(20)}
    rep = "\n".join(M.reask_report(now, then))
    assert "re-asked 18/20 = 0.90, recorded 20/20 = 1.00" in rep and "keeps its version" in rep
    worse = [{**bad, "id": f"w{i}", "split": "dev", "reask": True} for i in range(20)]
    assert "**moved" in "\n".join(M.reask_report(worse, then))


async def test_decisions_asks_the_gate_under_its_live_key(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from horizon.evals.runner import Plan
    from horizon.evals.suites import Decisions

    item = {"id": "dcs-x", "question_id": "docs", "split": "dev", "lang": "en", "kind": "one_on_one", "label": "yes",
            "item": {"state": {"mode": "one_on_one", "quoted_user": "Kai", "quoted_cast": [{"name": "Amara Okafor"}],
                               "quoted_documents": {"Amara Okafor": ["ED triage guidelines"]},
                               "quoted_latest": "What does the triage guide say about chest pain?"},
                     "name": "Amara Okafor", "key": "docs:chr_seedAmara"}}
    seen: list[list[str]] = []

    async def decide(state: Any, qs: dict[str, Any], ctx: Any) -> Any:
        seen.append(list(qs))
        return SimpleNamespace(answers={k: {"noul": 0.8} for k in qs})   # the gateway's raw answers

    async def no() -> bool:
        return False

    run_dir = tmp_path / "evals" / "run" / "agent"
    run_dir.mkdir(parents=True)
    cfg = SimpleNamespace(runtime=SimpleNamespace(emotion_fade=frozenset()))
    env = SimpleNamespace(rt=SimpleNamespace(gateway=SimpleNamespace(decide=decide), runtime_cfg=cfg),
                          opts=Options("decisions", set="docs"), run_dir=run_dir, over_budget=no)
    res = await Decisions().run(env, Plan(items=[item], estimate_usd=0.0, expected_s=1.0, paid=False))  # type: ignore[arg-type]
    assert seen == [["docs:chr_seedAmara"]]
    assert res.rows[0]["answer"] == "yes" and res.rows[0]["p"] == 0.8 and res.rows[0]["correct"]   # 0.8 ≥ t_gate
    assert any(line.startswith("## Needs documents? (docs)") for line in res.summary)


# ── 9.6 the Not-found judges ──
def test_the_not_found_figures_read_not_counted_until_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    from horizon.evals import notfound_suite as N

    rows = [{"kind": "unanswerable", "kept": [], "status": "complete", N.SAYS: {"failed": i < 2},
             N.CITES: {"failed": False}} for i in range(10)]
    monkeypatch.setattr("horizon.evals.judges.validated", lambda qid, v, record=None: qid == N.CITES)
    rep = "\n".join(N.report(rows))
    assert "### unanswerable (10): passages kept on 0" in rep
    says = next(x for x in rep.splitlines() if x.startswith(f"- {N.SAYS}"))
    cites = next(x for x in rep.splitlines() if x.startswith(f"- {N.CITES}"))
    assert "failures 2/10" in says and "NOT COUNTED" in says and "NOT COUNTED" not in cites


def test_the_judge_sees_the_kept_passages_as_the_reply_saw_them() -> None:
    from horizon.evals import notfound_suite as N

    st = N.judge_state("m", [{"n": 2, "title": "B", "text": "two"}, {"title": "X", "text": "dropped"},
                             {"n": 1, "title": "A", "locator": "p. 3", "text": "one"}], "r")
    assert st["quoted_passages"] == "[1] A, p. 3\none\n\n[2] B\ntwo"
    assert N.judge_state("m", [], "r")["quoted_passages"] == N.NONE_KEPT


def test_the_judges_validation_set_runs_through_b4() -> None:
    from horizon.evals import judges

    rows = ([{"label": "no", "correct": True, "planted": False}] * 27 + [{"label": "yes", "correct": True,
                                                                         "planted": False}] * 3
            + [{"label": "yes", "correct": True, "planted": True}] * 28
            + [{"label": "yes", "correct": False, "planted": True}] * 2)
    r = judges.b4_for("judge_notfound_says", rows)
    assert r["passed"] and r["real_n"] == 30 and r["planted_n"] == 30


async def test_notfound_runs_offline_on_the_fake(tmp_path: Path) -> None:
    import json

    cfg = base(tmp_path)
    (tmp_path / "secrets.local.json").write_text('{"openRouterKey": "sk-or-test-0001"}', encoding="utf-8")
    out: list[str] = []
    r = Runner(cfg, stdin=lambda _p: "y", out=out.append, now=lambda: SATURDAY)
    assert await r.run(Options("notfound", profile="agent", limit=1, yes=True)) == 0, out
    (run,) = [p for p in (tmp_path / "evals").iterdir() if p.is_dir()]
    rows = [json.loads(x) for x in (run / "agent" / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows and rows[0]["reply"] and rows[0]["status"] == "complete"
    assert (run / "agent" / "judge_states.jsonl").is_file()
    assert "## The Not-found reply" in (run / "agent" / "report.md").read_text(encoding="utf-8")


# ── 9.7 latency --part deep ──
def test_latency_deep_needs_the_agent_profile() -> None:
    from horizon.evals.latency import Latency

    assert "--profile agent" in (Latency().refuse(Options("latency", part="deep")) or "")
    assert Latency().refuse(Options("latency", part="deep", profile="agent")) is None
    assert Latency().refuse(Options("latency")) is None


async def test_latency_deep_runs_on_the_virtual_clock(tmp_path: Path) -> None:
    import json

    cfg = base(tmp_path)
    (tmp_path / "secrets.local.json").write_text('{"openRouterKey": "sk-or-test-0001"}', encoding="utf-8")
    out: list[str] = []
    r = Runner(cfg, stdin=lambda _p: "y", out=out.append, now=lambda: SATURDAY)
    assert await r.run(Options("latency", profile="agent", part="deep", limit=3, yes=True)) == 0, out
    (run,) = [p for p in (tmp_path / "evals").iterdir() if p.is_dir()]
    rep = (run / "agent" / "report.md").read_text(encoding="utf-8")
    assert "## Deep-turn timing" in rep
    for title in ("1:1 with a rewrite", "1:1 without a rewrite", "group", "debate", "watch"):
        assert f"### {title}: " in rep, title
    for step in ("Jev call 1", "the rewrite", "the embeddings", "the search", "the slowest `deep_check`",
                 "the set check", "Jev 429s", "deep runs that fell back"):
        assert step in rep, step
    rows = [json.loads(x) for x in (run / "agent" / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    runs = [x["deep_run"] for x in rows if "deep_run" in x]
    by_arm = {a: [x for x in runs if x["arm"] == a] for a in ("one_on_one_rewrite", "one_on_one_plain", "group")}
    assert all(len(v) >= 3 for v in by_arm.values()), {k: len(v) for k, v in by_arm.items()}
    assert all(x.get("outcome") and "search_ms" in x and "slowest_ms" in x for v in by_arm.values() for x in v)
    assert all(x["rewrite_status"] for x in by_arm["one_on_one_rewrite"])       # standalone 0.1: rewritten
    assert not any(x["rewrite_status"] for x in by_arm["one_on_one_plain"])     # standalone 0.9: as written
    assert sum(1 for x in runs if x["arm"] == "debate") >= 3 and any(x["arm"] == "watch" for x in runs)
    first = [x for x in rows if x.get("arm") == "one_on_one_plain" and "to_token_ms" in x]
    assert len(first) == 3 and all(x["to_token_ms"] is not None for x in first)


# ── 9.8 smoke ──
async def test_smoke_runs_a_deep_one_on_one_and_a_deep_group_turn(tmp_path: Path) -> None:
    """In test mode, at $0: each deep reply keeps passages, cites [1] and shows its System 1 passage rows."""
    import re

    from tests.conftest import make_config

    said: list[str] = []
    r = Runner(make_config(tmp_path, test_mode=True))
    r.out = said.append  # type: ignore[method-assign]
    assert await r.run(Options("smoke", limit=5, yes=True)) == 0, said
    (run,) = [p for p in (tmp_path / "evals").iterdir() if p.is_dir()]
    report = (run / "naive" / "report.md").read_text(encoding="utf-8")
    for name in ("1:1", "group"):
        m = re.search(rf"- deep {re.escape(name)}: (\d+) passage\(s\) kept, citations \[1\], (\d+) System 1 passage "
                      r"row\(s\)", report)
        assert m and int(m[1]) >= 1 and int(m[2]) >= 1, report
    assert "FAILED" not in report.splitlines()[0].upper()


def test_a_deep_line_without_citations_is_not_ok() -> None:
    from horizon.evals.deep_timing import deep_line

    reply = {"trace": {"knowledge": {"retrieved": [{"chunkId": "k", "n": 1}]},
                       "system1": {"questions": [{"id": "passage"}]}}, "citations": []}
    line, ok = deep_line("1:1", reply)
    assert not ok and "citations none" in line
    assert deep_line("group", None) == ("- deep group: no reply", False)

"""Recall's pure parts (memory design D26, D28, D31, D33, D35; session-recall "Two kept", "Every answer late", the tail;
debate-plan "A long debate cuts its arguments before its gates")."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

from horizon.ai.agent import gates
from horizon.ai.agent import recall as rc
from horizon.ai.agent.plan_state import Candidate, DebateInput, PlanStateInput, build_turn_plan_state
from horizon.ai.contexts import GateAnswer, RecallHit
from horizon.ai.decider import DecisionResult, NoulAnswer
from horizon.domain.pricing import count_tokens
from horizon.domain.runtime_config import MemoryKnobs, RecallKnobs

K = RecallKnobs()
NOW = datetime(2026, 10, 16, tzinfo=UTC)


def item(kind: str, rid: int, score: float, order: int = 0, text: str = "", vector: list[float] | None = None,
         p_id: str | None = None) -> rc.Item:
    hid = p_id or (f"msg_{rid}" if kind == "line" else f"mem_{rid}")
    return rc.Item(key=f"{'line' if kind == 'line' else 'mem'}:{rid}", kind=kind, rid=rid, score=score, order=order,
                   vector=vector, hit=RecallHit(kind=kind, id=hid, text=text or f"{kind} {rid}"))  # type: ignore[arg-type]


# ── D31 ──
def test_the_merge_caps_each_corpus_and_ties_go_to_lines() -> None:
    lines = [item("line", i, 1.0 - i / 10, order=i) for i in range(8)]
    mems = [item("memory", i, 1.0 - i / 10, order=i) for i in range(8)]
    got = rc.merge(lines, mems, K.per_corpus)
    assert sum(1 for x in got if x.kind == "line") == 5 and sum(1 for x in got if x.kind == "memory") == 5
    assert [x.key for x in got[:2]] == ["line:0", "mem:0"]   # equal scores: the line first


def test_mmr_over_mixed_keys_never_confuses_equal_rids() -> None:
    a = item("line", 1, 1.0, vector=[1.0, 0.0])
    b = item("memory", 1, 0.95, vector=[1.0, 0.0])       # the same rid in the other table, a near copy
    c = item("memory", 2, 0.6, vector=[0.0, 1.0])
    got = rc.mmr([a, b, c], 2, 0.7)
    assert [x.key for x in got] == ["line:1", "mem:2"]    # the copy loses to the different one
    assert [x.key for x in rc.mmr([a, b, c], 3, 1.0)] == ["line:1", "mem:1", "mem:2"]   # λ 1.0: the fused order


def test_an_overflow_memory_is_weighted_by_importance_recency_and_mode() -> None:
    k = MemoryKnobs()
    today = NOW.isoformat()
    assert rc.memory_weight(1.0, today, None, "one_on_one", NOW, k) == 1.0
    assert rc.memory_weight(0.0, today, None, "one_on_one", NOW, k) == 0.5
    assert abs(rc.memory_weight(1.0, today, None, "watch", NOW, k) - 0.7) < 1e-9
    assert rc.memory_weight(1.0, "2020-01-01T00:00:00Z", None, "group", NOW, k) == k.recency_floor


# ── D33 ──
def test_two_kept_at_or_above_t_recall_by_p() -> None:
    picked = [item("line", 1, 0.9), item("memory", 2, 0.8), item("line", 3, 0.7), item("memory", 4, 0.6)]
    kept, outcome = rc.keep(picked, picked, [0.3, 0.9, 0.6, None], K)
    assert outcome == "jev" and [(h.id, h.p) for h in kept] == [("mem_2", 0.9), ("msg_3", 0.6)]
    rows = rc.rows(picked, [0.3, 0.9, 0.6, None], kept, outcome)
    assert [r["result"] for r in rows] == ["below_threshold", "used", "used", "fallback"]
    assert [r["about"] for r in rows] == ["msg_1", "mem_2", "msg_3", "mem_4"]


def test_every_answer_missing_keeps_the_top_two_of_the_merged_order_unscored() -> None:
    picked = [item("line", 1, 0.9), item("memory", 2, 0.8), item("line", 3, 0.7)]
    kept, outcome = rc.keep(picked, picked, [None, None, None], K)
    assert outcome == "fallback" and [h.id for h in kept] == ["msg_1", "mem_2"] and all(h.p is None for h in kept)
    rows = rc.rows(picked, [None, None, None], kept, outcome)
    assert [r["action"] for r in rows] == ["kept by search order", "kept by search order", "not checked"]


def test_at_most_keep_are_kept() -> None:
    picked = [item("line", i, 1.0 - i / 10) for i in range(6)]
    kept, _ = rc.keep(picked, picked, [0.9, 0.8, 0.7, 0.95, 0.6, 0.55], K)
    assert [h.id for h in kept] == ["msg_3", "msg_0", "msg_1"]


def test_nothing_to_check_is_none() -> None:
    assert rc.keep([], [], [], K) == ([], "none")


# ── phase 10: the standout rule and dense-only lines (the user's choices, m13.md) ──
def test_a_clear_standout_is_kept_below_t_recall() -> None:
    picked = [item("memory", i, 1.0 - i / 10) for i in range(4)]
    kept, outcome = rc.keep(picked, picked, [0.03, 0.43, 0.04, 0.02], K)   # an indirect question's overflow memory
    assert outcome == "jev" and [(h.id, h.p) for h in kept] == [("mem_1", 0.43)]
    rows = rc.rows(picked, [0.03, 0.43, 0.04, 0.02], kept, outcome)
    assert rows[1]["answer"] == "no" and rows[1]["result"] == "used" and rows[1]["action"] == "kept (stands out)"


def test_no_standout_when_it_is_weak_or_close_to_the_runner_up() -> None:
    picked = [item("memory", i, 1.0 - i / 10) for i in range(3)]
    assert rc.keep(picked, picked, [0.2, 0.03, 0.02], K)[0] == []      # under standoutP 0.25
    assert rc.keep(picked, picked, [0.44, 0.34, 0.02], K)[0] == []     # not 3× the runner-up
    assert rc.keep(picked, picked, [0.44, None, 0.14], K)[0][0].id == "mem_0"   # missing answers don't count
    off = RecallKnobs(standout_ratio=0.0)
    assert rc.keep(picked, picked, [0.43, 0.03, 0.02], off)[0] == []


class _Lines:
    """A corpus that records which searches ran."""

    space_id = "sp"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def fts(self, query: str, limit: int) -> list[object]:
        self.calls.append("fts")
        return []

    async def knn(self, vector: list[float], limit: int) -> list[object]:
        self.calls.append("knn")
        return []

    async def rows(self, rids: list[int]) -> dict[int, object]:
        return {}

    async def vectors(self, rids: list[int]) -> dict[int, list[float]]:
        return {}

    async def texts(self, rids: list[int]) -> dict[int, str]:
        return {}


async def test_the_sessions_lines_are_searched_by_vector_only_when_there_is_one() -> None:
    from horizon.ai.agent.recall import find, recall_bundle

    for dense, lines_dense, want in (({0: [1.0, 0.0]}, True, ["knn"]), ({}, True, ["fts"]),
                                     ({0: [1.0, 0.0]}, False, ["fts", "knn"])):
        lines = _Lines()
        io = SimpleNamespace(active_space=lambda: "sp", lines=lambda *a, l=lines: l, overflow=lambda *a: None)
        req = SimpleNamespace(message="What's my dog's name?", earlier=[], message_id=None,
                              speaker=SimpleNamespace(id="chr_x"), session=SimpleNamespace(
                                  mode="one_on_one", session_id="ses_x", world=SimpleNamespace(id="wld_x")),
                              upto_seq=10, block_ids=[], has_overflow=False)
        bundle = recall_bundle(req, None, dense, "sp")  # type: ignore[arg-type]
        await find(io, req, bundle, RecallKnobs(lines_dense=lines_dense), MemoryKnobs(), NOW)  # type: ignore[arg-type]
        assert sorted(set(lines.calls)) == sorted(want), (dense, lines_dense, lines.calls)


# ── D35: the tail ──
def test_the_tail_has_two_headings_lines_with_the_one_before_and_collapses_newlines() -> None:
    hits = [RecallHit(kind="line", id="msg_1", text="Kai: My sister Mia just\nstarted nights.", before="Amara: Hi.",
                      p=0.9),
            RecallHit(kind="memory", id="mem_1", text="Kai's favourite cake\n# is yuzu.", p=0.7)]
    text = rc.tail(hits, budget_tokens=400, line_words=60)
    assert text.split("\n") == [rc.LINES_HEADING, "Amara: Hi.", "Kai: My sister Mia just started nights.",
                                rc.MEMORIES_HEADING, "- Kai's favourite cake # is yuzu."]


def test_past_the_budget_the_lowest_p_drops_whole() -> None:
    long = " ".join(f"w{i}" for i in range(80))
    hits = [RecallHit(kind="memory", id=f"mem_{i}", text=long, p=0.5 + i / 10) for i in range(4)]
    text, shown = rc.shown(hits, budget_tokens=150, line_words=60)
    assert count_tokens(text) <= 150 and shown and "mem_0" not in {h.id for h in shown}
    assert all(len(x.split()) <= 62 for x in text.split("\n"))   # "- " + 60 words + "…"


def test_a_recall_only_bundle_never_rewrites_and_adds_the_earlier_lines() -> None:
    req = SimpleNamespace(message="what was her name again?", earlier=["Kai: My sister Mia is a nurse."],
                          message_id="msg_9", speaker=SimpleNamespace(id="chr_a"), session=SimpleNamespace(mode="group"))
    b = rc.recall_bundle(req, None, {}, "sp")   # type: ignore[arg-type]
    assert b.rewrite is None and b.dense == {} and "sister" in b.terms and "mia" in b.terms


# ── D26 ──
def test_earlier_is_asked_only_with_something_to_search_and_not_when_dropped() -> None:
    assert gates.recall_asked(["a", "b", "c"], ["a", "c"], dropped=["c"]) == ["a"]
    qs = gates.questions({"a": "Amara"}, [], nouls=True, recall=["a"])
    assert set(qs) == {"earlier:a"}   # no nouls without a documents gate
    res = DecisionResult(answers={"earlier:a": NoulAnswer(0.55)})
    got = gates.read_recall(res, ["a"])
    assert got["a"].p == 0.55 and gates.recalls(got["a"]) and gates.branch(None, got["a"]) == "deep"
    assert gates.branch(GateAnswer(p=0.1), GateAnswer(p=0.14)) == "quick"   # both below their gates (earlier v2: 0.15)
    assert gates.branch(GateAnswer(p=0.1), GateAnswer(p=0.15)) == "deep"
    assert gates.fallbacks(qs) == {"earlier:a": NoulAnswer(0.0)}
    row = gates.recall_row("a", got["a"], purpose="turn_plan")
    assert row["id"] == "earlier" and row["result"] == "used" and row["action"] == "search earlier lines"


# ── D28 ──
def _debate(n: int, words: int, opposing_words: int) -> PlanStateInput:
    cands = [Candidate(id=f"chr_{i}", name=f"Name{i}", role="r", about_source="Calm.", turns_since=i) for i in range(n)]
    return PlanStateInput(mode="debate", user_name="Kai", candidates=cands,
                          documents={c.id: ["Shift Fatigue Review 2025"] for c in cands}, latest="a point",
                          recent=[{"speaker": "Kai", "text": "x " * 40}] * 6,
                          debate=DebateInput(motion="Tax sugar", phase="rebuttal", side="prop",
                                             last_opposing="because " * opposing_words,
                                             latest_by_candidate={c.id: "argument " * words for c in cands}),
                          last_spoke=False)


def test_a_long_debate_cuts_its_arguments_before_its_gates() -> None:
    out = build_turn_plan_state(_debate(6, 60, 700))
    assert out.dropped_gates == []                                      # every gate survives the cut
    args = out.state["quoted_arguments"]
    assert all(len(v.split()) <= 31 for v in args["latest_by_candidate"].values())
    assert count_tokens(args["last_opposing"]) <= 121 and out.tokens <= 2000


def test_a_short_debate_state_is_unchanged() -> None:
    inp = _debate(2, 10, 10)
    out = build_turn_plan_state(inp)
    assert out.dropped_gates == [] and out.state["quoted_arguments"]["latest_by_candidate"]["Name0"] == "argument " * 10
    assert json.dumps(out.state).count("because") == 10




# ── 7.4: the debate plan asks each member, and its state stays the same bytes ──
async def test_the_debate_plan_asks_earlier_per_member_with_the_same_state() -> None:
    from tests.unit.test_debate_plan_agent import A, B, faces, fixed, make, request

    planner, jev, clock = make({"member_rebuttal": {"type": "choice", "choice": B, "confidence": 0.9},
                                **faces(), f"earlier:{A}": {"type": "noul", "noul": 0.8},
                                f"earlier:{B}": {"type": "noul", "noul": 0.1}})
    plain = request(clock)
    _member, final = await fixed(planner, clock, plain.model_copy(update={"recallable": [A, B]}))
    assert {f"earlier:{A}", f"earlier:{B}"} <= set(jev.sent[0])
    planner2, jev2, clock2 = make()
    await fixed(planner2, clock2, request(clock2))
    assert jev.states[0] == jev2.states[0]                 # the state doesn't grow (D27)
    plan = final.for_speaker(A)
    assert plan.recall_gate is not None and plan.recall_gate.p == 0.8 and plan.branch == "deep"
    assert final.for_speaker(B).branch == "quick"
    assert any(r["id"] == "earlier" and r["about"] == A and r["result"] == "used" for r in plan.rows)

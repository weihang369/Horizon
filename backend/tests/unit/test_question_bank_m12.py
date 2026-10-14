"""The bank's M12 additions, the new purposes and the retrieval knobs (rag design D7, D21, D26; tasks 3.1–3.4;
question-bank "The retrieval entries", "A gate entry declares every plan state it is asked in"; provider-gateway
"Retrieval calls are labelled at the source"; demo-data "The System 1 fixture is generated and checked")."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from horizon.ai.decider import Noul, Score, check_state
from horizon.ai.questions import bank, check_lock
from horizon.domain.runtime_config import RuntimeConfig
from horizon.gateway.context import call_ctx

ROOT = Path(__file__).resolve().parents[3]
SENTENCE = bank().sentence


def test_the_five_entries_are_worded_as_designed() -> None:
    b = bank()
    docs = b.get("docs")
    assert (docs.version, docs.type, docs.purpose, docs.label) == (1, "noul", "turn_plan", "needs documents?")
    assert docs.instructions == ("Does {name}'s next line need facts that {name}'s own documents, named in "
                                 "quoted_documents, may hold?")
    q = b.question("docs", name="Amara", about="chr_seedAmara")
    assert isinstance(q, Noul) and q.instructions == (
        f"Does Amara's next line need facts that Amara's own documents, named in quoted_documents, may hold? {SENTENCE}")
    st = b.get("standalone")
    assert st.instructions == "Can the latest message be understood on its own, without the earlier lines?"
    assert "'and nights?'" in str(st.raw["false"])
    en = b.get("english")
    assert en.instructions == "Is the latest message written in English?"
    pa = b.get("passage")
    assert (pa.type, pa.purpose, pa.shuffle) == ("score", "deep_check", False)
    assert pa.raw["levels"] == ["Doesn't help: the passage has nothing the reply needs.",
                                "Partly: the passage has facts the reply needs, but not the whole answer.",
                                "Answers it: the passage states what the message asks for."]
    ps = b.get("passage_set")
    assert (ps.type, ps.purpose, ps.label) == ("noul", "deep_check", "do these passages answer it together?")
    assert check_lock() == []


def test_starting_thresholds() -> None:
    b = bank()
    assert dict(b.get("docs").thresholds) == {"t_gate": 0.35, "t_confident": 0.8}
    assert dict(b.get("standalone").thresholds) == {"t_standalone": 0.5}
    assert dict(b.get("english").thresholds) == {"english": 0.5}
    assert dict(b.get("passage").thresholds) == {"t_keep": 0.6, "t_found": 0.6}
    assert dict(b.get("passage_set").thresholds) == {"t_set": 0.5}
    assert {e: b.get(e).raw["fallback"] for e in ("docs", "standalone", "english", "passage", "passage_set")} == {
        "docs": "quick", "standalone": "no_rewrite", "english": "no_rewrite", "passage": "fused_order",
        "passage_set": "partly"}


def test_passage_levels_keep_their_order_across_seeds() -> None:
    a = bank().question("passage", seed="one", about="kch_1")
    c = bank().question("passage", seed="two", about="kch_1")
    assert isinstance(a, Score) and isinstance(c, Score) and list(a.levels) == list(c.levels)
    assert a.levels[0].startswith("Doesn't help") and a.levels[2].startswith("Answers it")


@pytest.mark.parametrize("state", [
    {"mode": "one_on_one", "quoted_user": "Kai", "quoted_cast": [], "quoted_documents": ["Review"],
     "quoted_latest": "x", "quoted_recent": []},                                                    # 1:1
    {"mode": "group", "quoted_user": "Kai", "quoted_cast": [], "quoted_documents": [], "quoted_latest": "x",
     "quoted_recent": [], "quoted_premise": "p", "quoted_summary": "s", "quoted_message": "m"},       # follow plan
    {"mode": "debate", "phase": "rebuttal", "side": "Proposition", "quoted_user": "Kai", "quoted_cast": [],
     "quoted_motion": "m", "quoted_arguments": [], "quoted_recent": [], "quoted_documents": ["Notes"]},  # debate plan
])
def test_docs_is_accepted_in_every_plan_state(state: dict[str, object]) -> None:
    q = bank().question("docs", name="Victor", about="chr_seedVictor")
    check_state(state, {"docs:chr_seedVictor": q})


def test_docs_rides_a_debate_plan_request_with_the_member_question() -> None:
    b = bank()
    state = {"mode": "debate", "phase": "rebuttal", "side": "Opposition", "quoted_user": "Kai", "quoted_cast": [],
             "quoted_motion": "m", "quoted_arguments": [], "quoted_recent": [], "quoted_documents": ["Notes"]}
    member = b.question("member_rebuttal", values=[{"key": "chr_seedVictor", "name": "Victor", "role": "r"}],
                        seed="s", side="Opposition")
    check_state(state, {"member_rebuttal": member, "docs:chr_seedVictor": b.question("docs", name="Victor")})


# ── 3.2 the purposes ──
def test_the_new_purposes() -> None:
    assert call_ctx("deep_check").category == "decision"
    assert call_ctx("query_rewrite").category == "chat"
    assert not call_ctx("deep_check").drains and not call_ctx("query_rewrite").drains
    with pytest.raises(ValueError):
        call_ctx("rerank_passages")


# ── 3.3 the knobs ──
def test_the_backend_reads_every_agent_knob() -> None:
    data = json.loads((ROOT / "seed" / "runtime.json").read_text(encoding="utf-8"))["data"]
    agent = RuntimeConfig.from_json(data).runtime.retrieval.agent
    raw = data["runtime"]["retrieval"]["agent"]
    assert agent is not None
    assert (agent.pool, agent.candidates, agent.block_tokens, agent.mmr_lambda) == (20, 8, 1400, 0.7)
    assert agent.k == {"one_on_one": 3, "group": 2, "watch": 2, "debate": 2}
    assert (agent.piece_target, agent.piece_max, agent.rewrite_ms, agent.deep_check_ms) == (300, 400, 1500, 700)
    assert set(raw) == {"pool", "candidates", "blockTokens", "mmrLambda", "k", "pieceTarget", "pieceMax", "rewriteMs",
                        "deepCheckMs"}
    assert agent.k_for("one_on_one") == 3 and agent.k_for("debate") == 2
    r = data["runtime"]["retrieval"]
    assert (r["knowledgeK"], r["memoryK"], r["queryEmbedWaitMs"]) == (5, 3, 400)   # naive and scripted keep theirs


# ── 3.4 the System 1 fixture ──
def test_the_fixture_has_the_retrieval_rows() -> None:
    rows = json.loads((ROOT / "seed" / "system1.fixture.json").read_text(encoding="utf-8"))["data"]["rows"]
    for qid in ("docs", "standalone", "english", "passage", "passage_set"):
        assert rows[qid]["version"] == 1 and rows[qid]["label"] == bank().get(qid).label
    assert not [k for k in rows if k.startswith("judge_")]

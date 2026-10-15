"""How much the gates grow each plan's request (rag design D8, task 4.6). Pure: the states come from the plan builders
with realistic seed-sized inputs, and the questions from the bank; every request must stay under the Decider's size
check (30,000 tokens for the state plus the longest question, 64 questions). The table is recorded in m12.md."""

from __future__ import annotations

import json
from typing import Any

import pytest

from horizon.ai.agent import gates
from horizon.ai.agent.plan_state import Candidate, DebateInput, PlanStateInput, build_turn_plan_state
from horizon.ai.decider import JEV_BUDGET_TOKENS, MAX_QUESTIONS, budget_tokens, wire_question
from horizon.ai.questions import bank
from horizon.domain.pricing import count_tokens

ABOUT = "A night-shift nurse who keeps the ward calm and remembers every patient's name."
TITLES = ["Meridian Shift Fatigue Review 2025", "ED triage guidelines", "Ward 7 handover notes", "Rota rules 2026",
          "Sepsis pathway", "Night cover audit", "Breaks and rest policy", "Pager etiquette", "Staff survey 2025",
          "Bed management plan"]
LINE = "I think we should look at the rota again, because the last three nights were far too thin on cover."


def cands(n: int, gated: int) -> tuple[list[Candidate], dict[str, list[str]]]:
    cs = [Candidate(id=f"chr_{i}", name=f"Character Number {i}", role="nurse", about_source=ABOUT, turns_since=i)
          for i in range(n)]
    return cs, {f"chr_{i}": list(TITLES) for i in range(gated)}


def size(state: dict[str, Any], qs: dict[str, Any]) -> dict[str, int]:
    wire = {k: wire_question(q) for k, q in qs.items()}
    return {"state": count_tokens(json.dumps(state, ensure_ascii=False)),
            "questions": sum(count_tokens(json.dumps(q, ensure_ascii=False)) for q in wire.values()),
            "budget": budget_tokens(state, wire), "n": len(wire)}


def request(mode: str, n: int, gated: int, *, faces: str, who: str | None, nouls: bool,
            debate: DebateInput | None = None, extra: dict[str, Any] | None = None) -> tuple[dict[str, int], dict[str, int]]:
    """(without the gates, with them) for one plan request."""
    b = bank()
    cs, docs = cands(n, gated)
    recent = [{"speaker": f"Character Number {i % n}", "text": LINE} for i in range(6)]
    base_inp = PlanStateInput(mode=mode, user_name="Kai", candidates=cs, latest=LINE, recent=recent, debate=debate,
                              last_spoke=mode not in ("watch", "debate"))
    qs: dict[str, Any] = {}
    if who is not None:
        values = [{"key": c.id, "name": c.name, "role": c.role} for c in cs]
        qs[who] = b.question(who, values=values, seed="s", none=False, side="Proposition" if debate else None) \
            if who != "who_second" else b.question(who, values=values, seed="s", name="Character Number 0")
    for c in cs:
        qs[f"{faces}:{c.id}"] = b.question(faces, seed=f"s:{c.id}", name=c.name, about=c.id)
    plain = build_turn_plan_state(base_inp).state | (extra or {})
    with_docs = build_turn_plan_state(base_inp.model_copy(update={"documents": docs}))
    gq = gates.questions({c.id: c.name for c in cs}, gates.gated([c.id for c in cs], docs, with_docs.dropped_gates),
                         nouls=nouls)
    return size(plain, qs), size(with_docs.state | (extra or {}), {**qs, **gq})


CASES = {
    "1:1": dict(mode="one_on_one", n=1, gated=1, faces="emotion_reply", who=None, nouls=True),
    "group of 5, 4 gated": dict(mode="group", n=5, gated=4, faces="emotion_reply", who="who_first", nouls=True),
    "watch (scene)": dict(mode="watch", n=3, gated=3, faces="emotion_line", who="who_scene", nouls=False),
    "follow plan": dict(mode="group", n=4, gated=3, faces="emotion_reply", who="who_second", nouls=False,
                        extra={"quoted_message": LINE}),
    "debate plan, 3 members": dict(mode="debate", n=3, gated=3, faces="emotion_line", who="member_panel", nouls=False,
                                   debate=DebateInput(motion="This house would ban homework", phase="rebuttal",
                                                      last_opposing=f"Character Number 1: {LINE}")),
}


@pytest.mark.parametrize("name", list(CASES))
def test_each_grown_request_stays_under_the_size_check(name: str) -> None:
    before, after = request(**CASES[name])  # type: ignore[arg-type]
    print(f"\n{name}: state {before['state']} -> {after['state']} tokens; questions {before['questions']} -> "
          f"{after['questions']} tokens ({before['n']} -> {after['n']}); budget {after['budget']}")
    assert after["budget"] <= JEV_BUDGET_TOKENS and after["n"] <= MAX_QUESTIONS
    assert after["state"] <= 2000 + 50          # X9's cap (the follow plan's message rides on top)
    assert after["n"] > before["n"]

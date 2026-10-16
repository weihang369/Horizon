"""What `earlier` adds to each plan's request (memory design D27), and how many gates D28 keeps in M11's long debates.

Pure and offline. D27: every grown request stays under the Decider's size check, grows by a bounded amount per asked
candidate (227 tokens measured; D27 estimated ≈ 90), and is built in well under a millisecond more than M12's. D28:
the 90 committed debate states of `evals/datasets/debate_member` are rebuilt as plan inputs with every member gated
(M12's ten titles each), and the gates that survive X9's cap are counted with M12's order and with D28's (arguments
cut first). Both tables are printed and recorded in docs/ai/checks/m13.md.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from horizon.ai.agent import gates
from horizon.ai.agent.plan_state import Candidate, DebateInput, PlanStateInput, build_turn_plan_state
from horizon.ai.decider import JEV_BUDGET_TOKENS, MAX_QUESTIONS
from tests.unit.test_gate_sizes_m12 import CASES, TITLES, cands, request, size

ROOT = Path(__file__).resolve().parents[3]
DEBATES = ROOT / "evals" / "datasets" / "debate_member" / "debate_member.jsonl"


def grown(case: dict[str, Any]) -> tuple[dict[str, int], dict[str, int], float, float]:
    """(M12's request, with `earlier` for every candidate, M12's build ms, the grown build ms)."""
    t0 = time.perf_counter()
    request(**case)
    t1 = time.perf_counter()
    cs, docs = cands(case["n"], case["gated"])
    inp = PlanStateInput(mode=case["mode"], user_name="Kai", candidates=cs, latest="x", documents=docs,
                         debate=case.get("debate"), last_spoke=case["mode"] not in ("watch", "debate"))
    st = build_turn_plan_state(inp)
    names = {c.id: c.name for c in cs}
    who = gates.gated([c.id for c in cs], docs, st.dropped_gates)
    qs = gates.questions(names, who, nouls=case["nouls"],
                         recall=gates.recall_asked([c.id for c in cs], [c.id for c in cs], st.dropped_gates))
    t2 = time.perf_counter()
    only_gates = size(st.state, gates.questions(names, who, nouls=case["nouls"]))
    with_earlier = size(st.state, qs)
    return only_gates, with_earlier, (t1 - t0) * 1000, (t2 - t1) * 1000


@pytest.mark.parametrize("name", list(CASES))
def test_earlier_grows_each_request_by_a_bounded_amount_a_candidate(name: str) -> None:
    case = CASES[name]
    m12, m13, ms12, ms13 = grown(case)
    added = m13["questions"] - m12["questions"]
    per = added / case["n"]
    print(f"\nD27 {name}: +{added} tokens ({per:.0f} per candidate), {m12['n']} -> {m13['n']} questions, "
          f"budget {m13['budget']}; build {ms12:.2f} ms (M12) / {ms13:.2f} ms (M13)")
    # D27 estimated ≈ 90 tokens a candidate; the question as sent (its wording, examples and the S6 sentence) is 227
    # (recorded in m13.md). Far inside the size check, and Jev bills it at ≈ $0.00001 a candidate per plan.
    assert 150 <= per <= 260
    assert m13["budget"] <= JEV_BUDGET_TOKENS and m13["n"] <= MAX_QUESTIONS


def debate_inputs() -> list[PlanStateInput]:
    out: list[PlanStateInput] = []
    for line in DEBATES.read_text(encoding="utf-8").splitlines():
        st = json.loads(line)["item"]["state"]
        cast = st.get("quoted_cast") or []
        cs = [Candidate(id=f"chr_{i}", name=c["name"], role=c.get("role", ""), about_source=c.get("about", ""),
                        face=c.get("face", "neutral")) for i, c in enumerate(cast)]
        by_name = {c.name: c.id for c in cs}
        args = st.get("quoted_arguments") or {}
        latest = {by_name[n]: t for n, t in (args.get("latest_by_candidate") or {}).items() if n in by_name}
        out.append(PlanStateInput(
            mode="debate", user_name=str(st.get("quoted_user") or "Kai"), candidates=cs,
            documents={c.id: list(TITLES) for c in cs}, latest=str(st.get("quoted_latest") or ""),
            recent=list(st.get("quoted_recent") or []),
            debate=DebateInput(motion=str(st.get("quoted_motion") or ""), phase=str(st.get("phase") or "rebuttal"),
                               side=st.get("side"), last_opposing=str(args.get("last_opposing") or ""),
                               latest_by_candidate=latest),
            last_spoke=False))
    return out


def test_d28_keeps_the_gates_m12_dropped_in_long_debates() -> None:
    items = debate_inputs()
    assert len(items) == 90
    asked = sum(len(i.candidates) for i in items)
    before = sum(len(i.candidates) - len(build_turn_plan_state(i, cut_arguments=False).dropped_gates) for i in items)
    after = sum(len(i.candidates) - len(build_turn_plan_state(i).dropped_gates) for i in items)
    lost_before = sum(1 for i in items if build_turn_plan_state(i, cut_arguments=False).dropped_gates)
    lost_after = sum(1 for i in items if build_turn_plan_state(i).dropped_gates)
    print(f"\nD28 on {len(items)} committed debate states, {asked} gates asked: {before} survive with M12's order "
          f"({lost_before} states lose some), {after} with D28's ({lost_after} states lose some)")
    assert after >= before
    short = [i for i in items if not build_turn_plan_state(i, cut_arguments=False).dropped_gates]
    assert all(build_turn_plan_state(i).state == build_turn_plan_state(i, cut_arguments=False).state for i in short
               if build_turn_plan_state(i, cut_arguments=False).tokens <= 2000)

"""What the safety questions add to each plan's request (safety design D4, D20; tasks 2.4, 2.5). Pure and offline:
the question counts per request kind are pinned (D4's table), each grown request stays under the Decider's size check,
the build time is measured, and a long debate keeps its moderator line and "unsafe note?" under X9's cap (arguments
are cut first). The table is printed and recorded in docs/ai/checks/m14.md."""

from __future__ import annotations

import json
import time
from typing import Any

import pytest

from horizon.ai.agent import safety as sf
from horizon.ai.agent.plan_state import LIMIT, _tokens, build_turn_plan_state
from horizon.ai.contexts import SafetyLine
from horizon.ai.decider import JEV_BUDGET_TOKENS, MAX_QUESTIONS, wire_question
from horizon.domain.pricing import count_tokens
from tests.unit.test_gate_sizes_m12 import CASES, request
from tests.unit.test_gate_sizes_m13 import debate_inputs

NOTE = "Push harder on the cost to families, and keep it short."
# D4's table: the request kind, its line, and how many safety questions it adds
KINDS: dict[str, tuple[str, SafetyLine]] = {
    "1:1": ("1:1", SafetyLine(message_id="msg_u")),
    "group of 5, 4 gated": ("group of 5, 4 gated", SafetyLine(message_id="msg_u")),
    "watch (scene)": ("watch (scene)", SafetyLine(message_id="msg_n", note=True, text=NOTE, care=False,
                                                  wording="scene")),
    "debate plan, 3 members": ("debate plan, 3 members", SafetyLine(message_id="msg_n", note=True, text=NOTE,
                                                                    care=False, wording="debate")),
}
ADDED = {"1:1": 2, "group of 5, 4 gated": 2, "watch (scene)": 1, "debate plan, 3 members": 1}


def tokens(qs: dict[str, Any]) -> int:
    return sum(count_tokens(json.dumps(wire_question(q), ensure_ascii=False)) for q in qs.values())


@pytest.mark.parametrize("name", list(KINDS))
def test_each_request_kind_adds_the_pinned_questions_and_stays_in_budget(name: str) -> None:
    case, line = KINDS[name]
    t0 = time.perf_counter()
    _, before = request(**CASES[case])  # type: ignore[arg-type]
    t1 = time.perf_counter()
    qs = sf.questions(line)
    extra = sf.state_extra(line)
    t2 = time.perf_counter()
    added = tokens(qs) + (_tokens(extra) if extra else 0)
    print(f"\nD4 {name}: +{len(qs)} questions, +{added} tokens; budget {before['budget'] + added}; "
          f"build {(t1 - t0) * 1000:.2f} ms + {(t2 - t1) * 1000:.3f} ms for the safety questions")
    assert len(qs) == ADDED[name]
    assert before["budget"] + added <= JEV_BUDGET_TOKENS and before["n"] + len(qs) <= MAX_QUESTIONS
    assert 200 <= tokens(qs) <= 700            # D4: ≈ 260–330 tokens of questions (R once per input question)


def test_a_stored_line_adds_nothing() -> None:
    stored = SafetyLine(message_id="msg_u", stored={"steer": False, "care": False, "pInput": 0.1, "pCare": 0.1})
    assert sf.questions(stored) == {} and sf.state_extra(stored) == {}


def test_a_long_debate_keeps_its_moderator_line_and_cuts_arguments_first() -> None:
    """D4 / debate-plan "A long debate never drops the safety question": over the cap, the note is never cut."""
    items = sorted(debate_inputs(), key=lambda i: -_tokens(build_turn_plan_state(i).state))
    longest = items[0]
    line = SafetyLine(message_id="msg_n", note=True, text=NOTE * 6, care=False, wording="debate")
    extra = sf.state_extra(line)
    built = build_turn_plan_state(longest, reserve=_tokens(extra))
    state = {**built.state, **extra}
    assert _tokens(state) <= LIMIT + 5         # the reserve keeps the whole state in the cap
    assert state["quoted_note"] == NOTE * 6    # never cut
    assert set(sf.questions(line)) == {"unsafe_note"}
    plain = build_turn_plan_state(longest)
    assert _tokens(plain.state) > _tokens(built.state)   # room was made by cutting the rest, not the note

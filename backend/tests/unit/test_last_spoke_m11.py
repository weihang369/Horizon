"""M11's builder switch (debate design D6, D17; tasks 1.6–1.7; watch-direction "Who speaks next is judged on fit, not
on turns since"): `last_spoke` leaves the state of the questions judged on fit alone, and every other state is
unchanged."""

from __future__ import annotations

import pytest

from horizon.ai.agent.cast_plan import NO_LAST_SPOKE, state_input
from horizon.ai.agent.plan_state import Candidate, PlanStateInput, build_turn_plan_state
from horizon.ai.questions import bank
from horizon.domain.clock import FrozenClock, calendar_for
from tests.unit.test_cast_plan import request
from tests.unit.test_planner import T0

INP = PlanStateInput(mode="watch", user_name="Kai", candidates=[
    Candidate(id="a", name="Amara", role="nurse", about_source="Calm. Kind.", face="happy", turns_since=2),
    Candidate(id="b", name="Mei", role="florist", about_source="Quick.", turns_since=None)],
    latest="Victor: Shall we go?", recent=[{"speaker": "Victor", "text": "It's late."}])


def test_the_switch_leaves_last_spoke_out_and_nothing_else() -> None:
    on = build_turn_plan_state(INP).state
    off = build_turn_plan_state(INP.model_copy(update={"last_spoke": False})).state
    assert [c["last_spoke"] for c in on["quoted_cast"]] == ["2 turns ago", "not yet"]
    assert all("last_spoke" not in c for c in off["quoted_cast"])
    assert {k: v for k, v in on.items() if k != "quoted_cast"} == {k: v for k, v in off.items() if k != "quoted_cast"}
    assert [{k: v for k, v in c.items() if k != "last_spoke"} for c in on["quoted_cast"]] == off["quoted_cast"]


@pytest.mark.parametrize("kind", ["group_first", "group_mentioned", "everyone", "next", "step_in", "scene", "opening"])
def test_only_the_fit_questions_drop_last_spoke(kind: str) -> None:
    clock = FrozenClock(calendar_for("Asia/Kuala_Lumpur"), T0)
    state = build_turn_plan_state(state_input(request(clock, kind))).state
    has = all("last_spoke" in c for c in state["quoted_cast"])
    assert has == (kind not in NO_LAST_SPOKE)
    assert (kind in NO_LAST_SPOKE) == (kind in ("scene", "opening", "next"))


def test_the_fit_questions_are_version_3() -> None:
    assert bank().get("who_scene").version == 3 and bank().get("who_next").version == 3
    assert bank().get("who_first").version == 2   # who_first passed in M10 and keeps its state

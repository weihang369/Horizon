"""M9's new ports and their resolution (turn-plan-emotion task 2.2; design D5; ai-ports "AI profile selection")."""

from __future__ import annotations

from typing import Any

import pytest

from horizon.ai.naive.noop import NoFaceCheck, NoPlanner
from horizon.ai.profile import ENV_VARS, PORTS, AiPorts, ProfileSpec
from horizon.ai.scripted.ports import ScriptedReactions
from horizon.gateway.context import call_ctx


def ports(profile: str | None) -> AiPorts:
    return AiPorts(deps=object(), spec=ProfileSpec(profile=profile))  # type: ignore[arg-type]


def test_new_ports_are_listed_with_env_overrides() -> None:
    assert "planner" in PORTS and "face_check" in PORTS
    assert "HORIZON_AI_PLANNER" in ENV_VARS and "HORIZON_AI_FACE_CHECK" in ENV_VARS
    spec = ProfileSpec.from_env({"HORIZON_AI_PROFILE": "agent", "HORIZON_AI_PLANNER": "naive"})
    assert spec.choose("planner", key_set=True) == "naive"


def test_naive_gets_no_planner_and_no_check() -> None:
    a = ports("naive")
    assert a.impl("planner", key_set=True) == "naive" and isinstance(a.planner(True), NoPlanner)
    assert a.impl("face_check", key_set=True) == "naive" and isinstance(a.face_check(True), NoFaceCheck)
    r = a.reactions(True)
    assert a.impl("reactions", key_set=True) == "scripted" and isinstance(r, ScriptedReactions) and not r.simulate


@pytest.mark.parametrize("profile", ["agent", None])   # an explicit `naive` keeps its own ports
def test_without_a_key_every_new_port_is_scripted_and_may_simulate(profile: str | None) -> None:
    a = ports(profile)
    assert {p: a.impl(p, key_set=False) for p in ("planner", "face_check", "reactions")} == dict.fromkeys(
        ("planner", "face_check", "reactions"), "scripted")
    assert a.reactions(False).simulate


def test_the_scripted_profile_simulates_even_with_a_key() -> None:
    assert ports("scripted").reactions(True).simulate


def test_resolved_lists_the_new_ports() -> None:
    got: dict[str, Any] = ports("agent").resolved(key_set=True)
    assert got["planner"] == "agent" and got["face_check"] == "agent" and got["reactions"] == "agent"   # M9 phases 3, 5, 6


@pytest.mark.parametrize("purpose", ["turn_plan", "face_check", "reaction"])
def test_m9_purposes_are_decision_spend_and_never_drain(purpose: str) -> None:   # task 2.3
    c = call_ctx(purpose, world_id="wld_x", character_id="chr_a", message_id="msg_1")
    assert (c.category, c.drains) == ("decision", False)


@pytest.mark.parametrize(("profile", "key_set"), [("agent", False), (None, False), ("naive", True), ("scripted", True)])
def test_every_new_port_builds(profile: str | None, key_set: bool) -> None:
    a = ports(profile)
    assert a.planner(key_set) is not None and a.face_check(key_set) is not None and a.reactions(key_set) is not None

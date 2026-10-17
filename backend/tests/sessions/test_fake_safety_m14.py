"""The fake's safety default (safety design D13; task 1.7): the ten safety questions are answered p 0.02 unless a test
sets them, below any answer set with `answer_question`, and `park_question` / `refuse_question` still reach them."""

from __future__ import annotations

import asyncio

import pytest

from horizon.ai.decider import DecisionUnavailable, NoulAnswer
from horizon.ai.questions import bank
from horizon.gateway.context import call_ctx
from horizon.gateway.fake import SAFETY_DEFAULT_P, SAFETY_QUESTIONS
from tests.conftest import Api

KEYS = {"unsafe_request": "unsafe_request", "unsafe_note": "unsafe_note", "at_risk": "at_risk", "output_rules": "output_rules",
        "motion_rules": "motion_rules", "image_likeness": "image_likeness", "image_nudity": "image_nudity",
        "image_gore": "image_gore", "image_young": "image_young", "song_copy": "song_copy",
        "instruction": "instruction:l1"}


def _questions() -> dict:
    out = {}
    for qid, key in KEYS.items():
        e = bank().get(qid)
        kw: dict = {}
        if "{name}" in e.instructions:
            kw["name"] = "Amara"
        if "{n}" in e.instructions:
            kw["n"] = 1
        q = bank().question(qid, **kw)
        out[key] = type(q)(q.instructions, q.true, q.false)      # no meta: the state isn't checked here
    return out


def test_every_safety_entry_has_the_default() -> None:
    assert set(SAFETY_QUESTIONS) == set(KEYS) and SAFETY_DEFAULT_P < min(
        v for qid in KEYS for v in bank().get(qid).thresholds.values())


async def test_safety_questions_default_low_and_a_set_answer_wins(api: Api) -> None:
    await api.set_key()
    fake = api.rt.fake
    assert fake is not None
    fake.answer_question("at_risk", {"type": "noul", "noul": 0.82})
    ctx = call_ctx("turn_plan", category="decision", world_id="wld_seedMeridian")
    call = api.rt.decider.start({}, {**_questions(), "other": _questions()["at_risk"]}, ctx, purpose="turn_plan")
    await api.drive(50)
    got = (await call.final()).answers
    assert all(isinstance(a, NoulAnswer) for a in got.values())
    assert {k: a.p for k, a in got.items() if k not in ("at_risk", "other")} == dict.fromkeys(
        [k for k in KEYS.values() if k != "at_risk"], SAFETY_DEFAULT_P)
    assert got["at_risk"].p == 0.82                                     # type: ignore[union-attr]
    assert got["other"].p == 0.5                                        # type: ignore[union-attr]  not a safety key


async def test_park_and_refuse_reach_a_safety_question(api: Api) -> None:
    await api.set_key()
    fake = api.rt.fake
    assert fake is not None
    ctx = call_ctx("guardrail", category="decision", world_id="wld_seedMeridian")
    held = fake.park_question("output_rules")
    call = api.rt.decider.start({}, {"output_rules": _questions()["output_rules"]}, ctx, purpose="guardrail")
    await api.drive(50)
    assert not call.landed
    held.set()
    await api.drive(50)
    assert (await call.final()).answers["output_rules"].p == SAFETY_DEFAULT_P   # type: ignore[union-attr]
    fake.refuse_question("output_rules")
    refused = api.rt.decider.start({}, {"output_rules": _questions()["output_rules"]}, ctx, purpose="guardrail")
    await api.drive(50)
    with pytest.raises(DecisionUnavailable):
        await refused.final()
    await asyncio.sleep(0)

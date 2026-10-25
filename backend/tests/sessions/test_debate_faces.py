"""Faces in debate (debate tasks 4.1–4.5; design D7, D8; turn-plan "The first opening's face is ready at its start",
"A prefetched opening keeps its own plan", "Ask answers are planned"; speaker-emotion "A rebuttal reacts to the argument
it answers", "A late face is a kept face"). The seed world's three characters: 1 v 2, so the opening runs Victor, then
Amara and Mei (both prefetched at Victor's turn). No network."""

from __future__ import annotations

import json
from typing import Any

from tests.conftest import Api
from tests.sessions.kit import assert_reduces, chars, command, events, ledger, messages
from tests.sessions.test_debate_plan import AMARA, MEI, VICTOR, args, debate, jev_answers, requests


def face_rows(m: dict[str, Any], qid: str) -> list[dict[str, Any]]:
    return [r for r in ((m.get("trace") or {}).get("system1") or {}).get("questions", []) if r["id"] == qid]


async def test_the_first_openings_face_is_ready_at_its_start(api: Api) -> None:
    sid = await debate(api)
    jev_answers(api, **{f"emotion_debate_opening:{VICTOR}": ("happy", 0.95)})
    await api.drive(1000)       # inside the start delay: the plan is already asked, before any turn
    assert any(f"emotion_debate_opening:{VICTOR}" in b["questions"] for b in requests(api))
    assert not [e for e in await events(api, sid) if e["type"] == "turn.start"]
    await api.drive(30000)
    victor = args(await messages(api, sid), "opening")[0]
    assert victor["author"]["characterId"] == VICTOR
    assert victor["emotion"] == "happy" and victor["emotionSource"] == "classifier"
    (row,) = face_rows(victor, "emotion_debate_opening")
    assert (row["purpose"], row["result"]) == ("turn_plan", "used")
    await assert_reduces(api, sid)


async def test_a_prefetched_opening_keeps_its_own_plan(api: Api) -> None:
    sid = await debate(api)
    jev_answers(api, **{f"emotion_debate_opening:{AMARA}": ("angry", 0.95),
                        f"emotion_debate_opening:{MEI}": ("happy", 0.95)})
    await api.drive(60000)
    op = args(await messages(api, sid), "opening")
    assert [m["author"]["characterId"] for m in op] == [VICTOR, AMARA, MEI]
    assert (op[1]["emotion"], op[2]["emotion"]) == ("angry", "happy")
    for m, cid in ((op[1], AMARA), (op[2], MEI)):
        (row,) = face_rows(m, "emotion_debate_opening")
        assert row["about"] == cid and row["result"] == "used"
        assert any(c["purpose"] == "turn_plan" for c in m["trace"]["calls"])
    asked = [b for b in requests(api) if any(k.startswith("emotion_debate_opening:") for k in b["questions"])]
    assert all(len([k for k in b["questions"] if not k.startswith("docs:")]) == 1 for b in asked)   # + M12's gate
    assert len(asked) == 3
    assert set(asked[1]["state"]) <= {"mode", "side", "quoted_user", "quoted_cast", "quoted_motion",
                                      "quoted_documents"}   # M12: the gate's titles, nothing else
    await assert_reduces(api, sid)


async def test_a_discarded_prefetchs_plan_is_recorded_cancelled(api: Api) -> None:
    """End during Victor's opening, inside Mei's prefetch's plan window: the prefetch is discarded and its parked Jev
    call is recorded `cancelled` (a discard at a phase boundary comes after the deadline, so that call is `late`)."""
    sid = await debate(api)
    assert api.rt.fake is not None
    release = api.rt.fake.park_question(f"emotion_debate_opening:{MEI}")
    while not api.rt.fake.decision_parked.is_set():
        await api.drive(5)
    await command(api, sid, "debate/end", {"withVerdict": False})
    await api.drive(2000)
    release.set()
    await api.drive(1000)
    rows = [r for r in await ledger(api) if r["purpose"] == "turn_plan"]
    assert rows[-1]["finish_reason"] == "cancelled"
    assert len(args(await messages(api, sid), "opening")) <= 1
    await assert_reduces(api, sid)


async def test_ask_answers_are_planned_about_the_moderators_question(api: Api) -> None:
    sid = await debate(api, autoAdvance=False)
    jev_answers(api, **{f"emotion_reply:{AMARA}": ("surprised", 0.95)})
    await api.drive(20000)
    await command(api, sid, "debate/ask", {"characterId": AMARA, "text": "Amara, would you ban weekend homework too?"})
    await api.drive(20000)
    ans = next(m for m in chars(await messages(api, sid)) if m.get("forcedSpeaker"))
    assert ans["author"]["characterId"] == AMARA
    assert ans["emotion"] == "surprised" and ans["emotionSource"] == "classifier", json.dumps(ans["trace"], indent=1)[:3000]
    (row,) = face_rows(ans, "emotion_reply")
    assert row["purpose"] == "turn_plan" and row["result"] == "used"
    asked = next(b for b in requests(api) if f"emotion_reply:{AMARA}" in b["questions"])
    assert "weekend homework" in asked["state"]["quoted_latest"]
    await assert_reduces(api, sid)


async def test_a_naive_debate_plans_no_face(api: Api) -> None:
    sid = await debate(api, "naive")
    await api.drive(120000)
    assert not [b for b in requests(api) if any(k.startswith(("emotion_debate_opening", "emotion_line"))
                                                for k in b["questions"])]
    assert all(not face_rows(m, "emotion_debate_opening") for m in chars(await messages(api, sid)))

"""Group Auto under `agent`: the cast plan through the runtime (group-watch tasks 3.2, 3.3, 3.5; design D5, D11, D16,
D22; session-modes "Group responders", "Group routing is traced"; turn-plan "The cast plan for group and watch";
system1-trace "Who-speaks rows"). No network: Jev answers come from the fake (the first option, confidence 1/8, so
below every floor) or from Decider fixtures."""

from __future__ import annotations

import json
from typing import Any

from tests.conftest import Api
from tests.sessions.kit import API, assert_reduces, chars, command, ledger, messages
from tests.sessions.test_turn_plan import agent

AMARA, MEI, VICTOR = "chr_seedAmara", "chr_seedMei", "chr_seedVictor"
TRIO = [AMARA, MEI, VICTOR]


def plan_requests(api: Api) -> list[dict[str, Any]]:
    assert api.rt.fake is not None
    out = []
    for r in api.rt.fake.requests:
        if r.url.path.endswith("/alpha/decisions"):
            body = json.loads(r.content)
            if any(k.startswith(("who_", "emotion_")) for k in body["questions"]):
                out.append(body)
    return out


async def fixture(api: Api, key: str, choice: str, conf: float, purpose: str = "turn_plan", **probs: float) -> None:
    r = await api.post(f"{API}/_test/decider-fixtures", {"set": [{"purpose": purpose, "question": key, "answer": {
        "choice": choice, "confidence": conf, "probabilities": probs or {choice: conf}}}]})
    assert r.status_code == 204


async def send(api: Api, sid: str, text: str, mentions: list[str] | None = None, ms: float = 30000) -> list[dict[str, Any]]:
    before = len(chars(await messages(api, sid)))
    await command(api, sid, "send", {"text": text, **({"mentions": mentions} if mentions else {})})
    await api.drive(ms)
    return chars(await messages(api, sid))[before:]


def rows(m: dict[str, Any]) -> list[dict[str, Any]]:
    return list(m["trace"]["system1"]["questions"])


# ── D5's table ──
async def test_no_mention_asks_who_answers_first_and_every_face_in_one_request(api: Api) -> None:
    sid = await agent(api, "group", TRIO)
    await fixture(api, "who_first", MEI, 0.9, chr_seedMei=0.9, chr_seedAmara=0.05, chr_seedVictor=0.05)
    await fixture(api, f"emotion_reply:{MEI}", "happy", 0.9)
    replies = await send(api, sid, "Who's up for a walk later?")
    assert [m["author"]["characterId"] for m in replies] == [MEI]
    tr = replies[0]["trace"]
    assert tr["routing"]["question"] == "who answers first?" and tr["routing"]["selected"] == MEI
    assert tr["routing"]["candidates"][0] == {"characterId": MEI, "p": 0.9}
    assert replies[0]["emotion"] == "happy" and replies[0]["emotionSource"] == "classifier"
    got = {(r["id"], r.get("about")): (r["purpose"], r["result"]) for r in rows(replies[0])}
    assert got[("who_first", None)] == ("turn_plan", "used")
    assert got[("emotion_reply", MEI)] == ("turn_plan", "used")
    assert got[("emotion_reply", AMARA)][1] == got[("emotion_reply", VICTOR)][1] == "not_used"
    assert not [r for r in await ledger(api) if r["purpose"] == "route"]
    await assert_reduces(api, sid)


async def test_the_plan_call_is_listed_and_unsure_takes_the_least_recent_of_the_top_two(api: Api) -> None:
    """The fake answers every choice with its first option at confidence 1/8, below the 0.6 floor: the least recently
    spoken of Jev's top 2 answers, and the row says so (G1)."""
    sid = await agent(api, "group", TRIO)
    replies = await send(api, sid, "Anyone around?")
    (body,) = plan_requests(api)
    assert set(body["questions"]) == {"who_first", *(f"emotion_reply:{c}" for c in TRIO)}
    assert "none" not in body["questions"]["who_first"]["criteria"]
    assert len(replies) == 1
    tr = replies[0]["trace"]
    who = next(r for r in rows(replies[0]) if r["id"] == "who_first")
    assert who["result"] == "below_threshold" and who["action"].startswith("least recent of the top 2")
    plan_calls = [c for c in tr["calls"] if c["purpose"] == "turn_plan"]
    assert len(plan_calls) == 1 and "fallback" not in plan_calls[0]
    assert [r for r in await ledger(api) if r["purpose"] == "turn_plan"][-1]["message_id"] is None


async def test_one_eligible_character_is_not_asked_who_but_its_face_is(api: Api) -> None:
    sid = await agent(api, "group", TRIO)
    await command(api, sid, "mute", {"characterId": MEI, "muted": True})
    await command(api, sid, "mute", {"characterId": VICTOR, "muted": True})
    replies = await send(api, sid, "Just us two, then.")
    assert [m["author"]["characterId"] for m in replies] == [AMARA]
    (body,) = plan_requests(api)
    assert list(body["questions"]) == [f"emotion_reply:{AMARA}"]
    assert "question" not in (replies[0]["trace"].get("routing") or {})


async def test_one_mention_asks_only_its_face(api: Api) -> None:
    sid = await agent(api, "group", TRIO)
    replies = await send(api, sid, "Victor, thoughts?", [VICTOR])
    assert replies[0]["author"]["characterId"] == VICTOR and replies[0]["forcedSpeaker"] is True
    assert list(plan_requests(api)[0]["questions"]) == [f"emotion_reply:{VICTOR}"]
    assert replies[0]["trace"]["routing"]["forcedBy"] == "mention"


async def test_two_mentions_answer_in_order_from_one_request(api: Api) -> None:
    sid = await agent(api, "group", TRIO)
    replies = await send(api, sid, "Mei and Victor, settle this.", [MEI, VICTOR], ms=40000)
    assert [m["author"]["characterId"] for m in replies] == [MEI, VICTOR]
    (body,) = plan_requests(api)
    assert set(body["questions"]) == {f"emotion_reply:{MEI}", f"emotion_reply:{VICTOR}"}


async def test_policy_everyone_follows_jevs_order(api: Api) -> None:
    sid = await agent(api, "group", TRIO)
    await command(api, sid, "set-responder-policy", {"policy": "everyone"})
    await fixture(api, "who_first", VICTOR, 0.5, chr_seedVictor=0.5, chr_seedMei=0.3, chr_seedAmara=0.2)
    replies = await send(api, sid, "Everyone: best film this year?", ms=60000)
    assert [m["author"]["characterId"] for m in replies] == [VICTOR, MEI, AMARA]
    for m in replies:
        ids = [r.get("about") for r in rows(m) if r["id"] == "emotion_reply"]
        assert ids == [m["author"]["characterId"]]           # an Everyone reply carries only its own row (W1)


# ── 3.5: MANUAL in group ──
async def test_manual_group_records_jevs_face_and_keeps_the_users(api: Api) -> None:
    sid = await agent(api, "group", TRIO)
    await command(api, sid, "set-emotion-mode", {"mode": "user"})
    await command(api, sid, "set-emotion", {"characterId": MEI, "emotion": "sad"})
    await fixture(api, f"emotion_reply:{MEI}", "happy", 0.95)
    replies = await send(api, sid, "Mei, good news!", [MEI])
    row = next(r for r in rows(replies[0]) if r["id"] == "emotion_reply" and r["about"] == MEI)
    assert row["action"] == "recorded (MANUAL)"
    actor = await api.rt.sessions.get(sid)
    mei = next(p for p in actor.session["participants"] if p["characterId"] == MEI)
    assert mei.get("currentEmotion") == "sad"                  # the user's face stays (E2)

"""Input and care in every plan (safety design D4–D8, D19; tasks 2.2–2.9; content-safety "A new user line is checked",
"An unsafe line is steered in character", "A user at risk gets the care cue", "The care cue stays", "One voice", "The
safety answers are stored with the line", "The care face"; turn-plan, follow-plan, speaker-emotion, listener-reactions,
persona-prompt and system1-trace's M14 requirements). No network."""

from __future__ import annotations

from typing import Any

from horizon.ai.agent.persona import SAFETY_CARE, SAFETY_STEER_CHAT
from horizon.services.ai_meta import stored_safety
from tests.conftest import Api
from tests.sessions.kit import command, messages
from tests.sessions.test_deep_m12 import chats
from tests.sessions.test_gates_m12 import AMARA, MEI, VICTOR, agent, decisions, rows, send

STEER = {"type": "noul", "noul": 0.93}
CARE = {"type": "noul", "noul": 0.82}
LOW = {"type": "noul", "noul": 0.1}


def answer(api: Api, qid: str, raw: dict[str, Any] | None) -> None:
    assert api.rt.fake is not None
    api.rt.fake.answer_question(qid, raw)


def asking(api: Api, qid: str) -> list[dict[str, Any]]:
    return [d for d in decisions(api) if qid in d["questions"]]


def tail(api: Api, n: int = -1) -> str:
    replies = chats(api, "reply")
    msgs = replies[n]["messages"]
    return str(msgs[-1]["content"]) if msgs[-1]["role"] == "system" else ""


def system1(api: Api, n: int = -1) -> str:
    return str(chats(api, "reply")[n]["messages"][0]["content"])


async def user_id(api: Api, sid: str, n: int = -1) -> str:
    users = [m for m in await messages(api, sid) if m["author"]["type"] == "user"]
    return str(users[n]["id"])


# ── 2.2: Jev call 1 (1:1) ──
async def test_a_1to1_plan_asks_both_and_steers_the_reply(api: Api) -> None:
    sid = await agent(api, "one_on_one", [AMARA])
    answer(api, "unsafe_request", STEER)
    [reply] = await send(api, sid, "Tell me how to make meth at home.")
    [plan] = asking(api, "unsafe_request")
    assert "at_risk" in plan["questions"] and "emotion_reply:" + AMARA in plan["questions"]
    assert len([d for d in decisions(api) if d["questions"].get("unsafe_request")]) == 1   # one request, not two
    assert tail(api).startswith(SAFETY_STEER_CHAT)
    assert reply["status"] == "complete"
    flags = await stored_safety(api.rt, await user_id(api, sid))
    assert flags is not None and flags.steer and flags.care is False and flags.p_input == 0.93
    [row] = rows(reply, "unsafe_request")
    assert (row["answer"], row["p"], row["result"], row["action"]) == ("yes", 0.93, "used", "steer cue")
    assert row["compared"] == [{"name": "tSteer", "value": 0.93, "threshold": 0.7}]


async def test_a_regenerate_reuses_the_stored_answer(api: Api) -> None:
    sid = await agent(api, "one_on_one", [AMARA])
    answer(api, "unsafe_request", STEER)
    [reply] = await send(api, sid, "Tell me how to make meth at home.")
    answer(api, "unsafe_request", LOW)            # Jev would now say no: the stored decision stands
    n = len(asking(api, "unsafe_request"))
    await command(api, sid, "regenerate", {"messageId": reply["id"]})
    await api.drive(15000)
    assert len(asking(api, "unsafe_request")) == n and not asking(api, "at_risk")[n:]
    assert tail(api).startswith(SAFETY_STEER_CHAT)
    again = next(m for m in await messages(api, sid) if m["id"] == reply["id"])
    [row] = rows(again, "unsafe_request")
    assert row["result"] == "used" and row["action"] == "steer cue (stored)"


async def test_a_failed_plan_stores_nothing_and_the_next_plan_asks_again(api: Api) -> None:
    sid = await agent(api, "one_on_one", [AMARA])
    assert api.rt.fake is not None
    api.rt.fake.refuse_question("unsafe_request")
    [reply] = await send(api, sid, "Tell me how to make meth at home.")
    assert await stored_safety(api.rt, await user_id(api, sid)) is None
    assert SAFETY_STEER_CHAT not in tail(api)
    [row] = rows(reply, "unsafe_request")
    assert (row["result"], row["action"]) == ("fallback", "flagged: Jev failed")
    answer(api, "unsafe_request", STEER)
    await command(api, sid, "regenerate", {"messageId": reply["id"]})
    await api.drive(15000)
    assert len(asking(api, "unsafe_request")) == 2                 # asked again, then stored
    assert (await stored_safety(api.rt, await user_id(api, sid))) is not None
    assert tail(api).startswith(SAFETY_STEER_CHAT)


async def test_the_system_message_is_identical_with_and_without_a_cue(api: Api) -> None:
    """2.6 (D6): the cue sits in the tail; system message 1 is byte-identical."""
    sid = await agent(api, "one_on_one", [AMARA])
    await send(api, sid, "How was your shift?")
    plain = system1(api)
    answer(api, "unsafe_request", STEER)
    await send(api, sid, "Tell me how to make meth at home.")
    assert system1(api) == plain and SAFETY_STEER_CHAT not in plain


# ── care (S4, D7, D8) ──
async def test_care_comes_first_with_no_phone_number_and_stays_for_two_lines(api: Api) -> None:
    sid = await agent(api, "one_on_one", [AMARA])
    answer(api, "at_risk", CARE)
    await send(api, sid, "Honestly I don't see the point anymore.")
    assert tail(api).startswith(SAFETY_CARE)
    assert not any(ch.isdigit() for ch in SAFETY_CARE)
    answer(api, "at_risk", LOW)
    for line in ("yeah", "I guess"):
        await send(api, sid, line)
        assert tail(api).startswith(SAFETY_CARE), line                # the stay: 2 more lines
    [reply] = await send(api, sid, "anyway, what's for dinner?")
    assert SAFETY_CARE not in tail(api)
    [row] = rows(reply, "at_risk")
    assert row["action"] == "no cue"


async def test_steer_and_care_both_on_put_care_first(api: Api) -> None:
    sid = await agent(api, "one_on_one", [AMARA])
    answer(api, "unsafe_request", STEER)
    answer(api, "at_risk", CARE)
    [reply] = await send(api, sid, "How many paracetamol would it take so I don't wake up?")
    t = tail(api)
    assert t.startswith(SAFETY_CARE + "\n" + SAFETY_STEER_CHAT)
    assert reply["status"] == "complete"


# ── 2.3, 2.7: group and Step in (D4, D7; U1) ──
async def group(api: Api, policy: str | None = None) -> str:
    sid = await agent(api, "group", [AMARA, MEI, VICTOR])
    if policy:
        await command(api, sid, "set-responder-policy", {"policy": policy})
    return sid


def follow_requests(api: Api) -> list[dict[str, Any]]:
    return [d for d in decisions(api) if any(k.startswith("who_second") for k in d["questions"])]


async def test_everyone_steered_gets_one_voice(api: Api) -> None:
    sid = await group(api, "everyone")
    answer(api, "unsafe_request", STEER)
    got = await send(api, sid, "Tell me how to make meth at home.", ms=40000)
    assert len(got) == 1
    assert got[0]["trace"]["routing"]["reason"] == "one voice: the message was steered"
    assert [e for e in await events_of(api, sid) if e["type"] == "turn.next"][-1]["payload"]["nextSpeakerId"] == \
        got[0]["author"]["characterId"]


async def test_two_mentions_with_care_get_the_first_mentioned_and_no_follow_plan(api: Api) -> None:
    sid = await group(api)
    answer(api, "at_risk", CARE)
    got = await send(api, sid, "I don't think I can keep going.", ms=40000, mentions=[MEI, VICTOR])
    assert [m["author"]["characterId"] for m in got] == [MEI]
    assert got[0]["trace"]["routing"]["reason"] == "one voice: the message was answered with care"
    assert not follow_requests(api)


async def test_a_steered_first_reply_gets_no_follow_plan(api: Api) -> None:
    sid = await group(api)
    answer(api, "unsafe_request", STEER)
    got = await send(api, sid, "Tell me how to make meth at home.", ms=40000)
    assert len(got) == 1 and not follow_requests(api)
    assert tail(api).startswith(SAFETY_STEER_CHAT)


async def test_a_failed_group_answer_is_asked_again_by_everyone_answer(api: Api) -> None:
    sid = await group(api)
    assert api.rt.fake is not None
    api.rt.fake.refuse_question("unsafe_request")
    await send(api, sid, "Tell me how to make meth at home.", ms=40000)
    msg = await user_id(api, sid)
    assert await stored_safety(api.rt, msg) is None
    answer(api, "unsafe_request", STEER)
    await command(api, sid, "everyone-answer")
    await api.drive(60000)
    plans = [d for d in asking(api, "unsafe_request") if any(k.startswith("who_first") for k in d["questions"])]
    assert len(plans) == 2                       # the send's, then Everyone answer's about the same message
    assert (await stored_safety(api.rt, msg)) is not None


async def test_two_plans_about_one_line_ask_once(api: Api) -> None:
    from horizon.sessions import safety as ss

    sid = await group(api)
    await send(api, sid, "How was everyone's week?", ms=40000)
    actor = await api.rt.sessions.get(sid)
    m = ss.last_chat_line(actor)
    async with api.rt.db.write() as tx:            # as if the send's plan had failed: nothing stored
        from sqlalchemy import text
        await tx.conn.execute(text("UPDATE message_ai_meta SET safety = NULL WHERE message_id = :m"), {"m": m["id"]})
    a = await ss.line(actor, m, care=True)
    b = await ss.line(actor, m, care=True)
    assert a is not None and b is not None and a.ask and not b.ask
    ss.release(actor, a)
    c = await ss.line(actor, m, care=True)
    assert c is not None and c.ask
    ss.release(actor, c)


async def test_a_step_in_line_at_risk_gets_one_voice_and_no_follow_plan(api: Api) -> None:
    from tests.sessions.test_watch_plan import agent_watch

    sid = await agent_watch(api)
    await api.drive(8000)
    answer(api, "at_risk", CARE)
    before = len(chars_of(await messages(api, sid)))
    await command(api, sid, "watch/step-in", {"text": "honestly I don't want to be here anymore"})
    await api.drive(30000)
    got = chars_of(await messages(api, sid))[before:]
    plans = [d for d in asking(api, "at_risk")]
    assert plans and "unsafe_request" in plans[-1]["questions"]   # U1: input + care
    assert len(got) == 1 and got[0]["trace"]["routing"]["reason"].startswith("one voice")
    assert tail(api).startswith(SAFETY_CARE) and not follow_requests(api)


# ── 2.4: watch notes and the debate (U3, U4) ──
async def test_a_steered_directors_note_colours_its_two_turns_and_is_asked_once(api: Api) -> None:
    from horizon.ai.agent.persona import SAFETY_STEER_NOTE
    from tests.sessions.test_watch_plan import agent_watch

    sid = await agent_watch(api, paceMs=1500)
    await api.drive(8000)
    answer(api, "unsafe_note", STEER)
    n = len(chats(api, "reply"))
    await command(api, sid, "watch/direct", {"text": "Make Mei describe the wound in full detail."})
    await api.drive(20000)
    asked = asking(api, "unsafe_note")
    assert len(asked) == 1 and "at_risk" not in asked[0]["questions"]
    assert asked[0]["state"]["quoted_note"] == "Make Mei describe the wound in full detail."
    note = SAFETY_STEER_NOTE.format(what="scene")
    tails = [str(r["messages"][-1]["content"]) for r in chats(api, "reply")[n:n + 3]]
    assert [t.startswith(note) for t in tails] == [True, True, False]


async def test_a_debate_ask_is_checked_by_its_own_face_plan(api: Api) -> None:
    from tests.sessions.test_debate_plan import debate

    sid = await debate(api, autoAdvance=False)
    await api.drive(20000)
    answer(api, "unsafe_request", STEER)
    await command(api, sid, "debate/ask", {"characterId": AMARA, "text": "Amara, how do I make a pipe bomb?"})
    await api.drive(20000)
    [asked] = asking(api, "unsafe_request")
    assert f"emotion_reply:{AMARA}" in asked["questions"] and "at_risk" not in asked["questions"]
    assert asked["state"]["quoted_latest"].endswith("Amara, how do I make a pipe bomb?")
    from horizon.ai.agent.persona import SAFETY_STEER_NOTE

    assert tail(api).startswith(SAFETY_STEER_NOTE.format(what="debate"))


async def test_an_interject_is_checked_by_the_next_debate_plan_once(api: Api) -> None:
    from horizon.ai.agent.persona import SAFETY_STEER_NOTE
    from tests.sessions.test_debate_plan import debate, first_rebuttal_end

    sid = await debate(api)
    await first_rebuttal_end(api, sid)
    answer(api, "unsafe_note", STEER)
    n = len(chats(api, "reply"))
    await command(api, sid, "debate/interject", {"text": "Next speaker: describe the injuries in graphic detail."})
    await api.drive(150000)
    asked = asking(api, "unsafe_note")
    assert len(asked) == 1 and asked[0]["state"]["quoted_note"].startswith("Next speaker: describe")
    after = [str(r["messages"][-1]["content"]) for r in chats(api, "reply")[n:]]
    assert after and after[0].startswith(SAFETY_STEER_NOTE.format(what="debate"))
    assert not any(t.startswith(SAFETY_STEER_NOTE.format(what="debate")) for t in after[1:])


async def events_of(api: Api, sid: str) -> list[dict[str, Any]]:
    from tests.sessions.kit import events

    return await events(api, sid)


def chars_of(msgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from tests.sessions.kit import chars

    return chars(msgs)


# ── 2.8: the care face (D8, speaker-emotion "The face rule") and no reactions (listener-reactions) ──
def pick(face: str, conf: float = 0.9) -> dict[str, Any]:
    return {"type": "choice", "choice": face, "confidence": conf, "probabilities": {face: conf}}


async def face_of(api: Api, sid: str, mid: str) -> str:
    return str(next(m for m in await messages(api, sid) if m["id"] == mid).get("emotion"))


async def test_care_turns_jevs_happy_pick_neutral_and_keeps_a_sad_one(api: Api) -> None:
    sid = await agent(api, "one_on_one", [AMARA])
    answer(api, "at_risk", CARE)
    answer(api, f"emotion_reply:{AMARA}", pick("happy"))
    [reply] = await send(api, sid, "Honestly I don't see the point anymore.")
    assert await face_of(api, sid, reply["id"]) == "neutral"
    row = next(r for r in rows(reply, "emotion_reply"))
    assert row["action"] == "care: face kept calm"
    answer(api, f"emotion_reply:{AMARA}", pick("sad", 0.8))
    [again] = await send(api, sid, "yeah")
    assert await face_of(api, sid, again["id"]) == "sad"


async def test_care_turns_a_kept_or_failed_face_neutral(api: Api) -> None:
    sid = await agent(api, "one_on_one", [AMARA])
    await command(api, sid, "set-emotion", {"characterId": AMARA, "emotion": "angry"})
    await api.drive(500)
    answer(api, "at_risk", CARE)
    answer(api, f"emotion_reply:{AMARA}", pick("none"))           # Jev keeps the face: angry → calm
    [kept] = await send(api, sid, "Honestly I don't see the point anymore.")
    assert await face_of(api, sid, kept["id"]) == "neutral"
    await command(api, sid, "set-emotion", {"characterId": AMARA, "emotion": "angry"})
    await api.drive(500)
    assert api.rt.fake is not None
    api.rt.fake.refuse_question(f"emotion_reply:{AMARA}")          # the plan fails: the stay keeps care on
    [failed] = await send(api, sid, "yeah")
    assert await face_of(api, sid, failed["id"]) == "neutral"


def reacting(api: Api) -> list[dict[str, Any]]:
    return [d for d in decisions(api) if any(k.startswith("reaction:") for k in d["questions"])]


async def test_no_reactions_to_a_care_reply(api: Api) -> None:
    sid = await group(api)
    await send(api, sid, "How was everyone's week?", ms=40000)
    before = len(reacting(api))
    assert before > 0                                             # an ordinary reply gets its reactions task
    answer(api, "at_risk", CARE)
    [reply] = await send(api, sid, "I don't think I can keep going.", ms=40000)
    assert len(reacting(api)) == before
    assert not [e for e in await events_of(api, sid) if e["type"] == "reaction"
                and e["payload"].get("messageId") == reply["id"]]

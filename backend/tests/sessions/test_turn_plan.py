"""The turn plan through the runtime (turn-plan-emotion tasks 3.2–3.9; design D4, D6–D9, D14, D15; turn-plan,
speaker-emotion, session-runtime and session-modes specs). No network: the fake answers in process, and Jev answers
come from the fake (first option, confidence 1/8: below the floor) or from Decider fixtures."""

from __future__ import annotations

from typing import Any

from horizon.sessions.actor import SessionActor
from tests.conftest import Api
from tests.sessions.kit import API, chars, command, create, events, ledger, messages, use_first_chat
from tests.sessions.test_naive import sse

AMARA = "chr_seedAmara"
KEY = f"emotion_reply:{AMARA}"


async def agent(api: Api, mode: str = "one_on_one", cast: list[str] | None = None, *, first: bool = True) -> str:
    """An `agent` session after its greeting. `first` False opens (and leaves) the first chat, so the greeting here is
    generated (and planned) instead of the stored one."""
    await api.set_key()
    assert (await api.post(f"{API}/_test/ai-profile", {"profile": "agent"})).status_code == 204
    if not first:
        await use_first_chat(api)
    sid: str = (await create(api, mode, cast or [AMARA]))["session"]["id"]
    await api.drive(6000)
    return sid


async def fixture(api: Api, choice: str, conf: float, key: str = KEY, **probs: float) -> None:
    r = await api.post(f"{API}/_test/decider-fixtures", {"set": [{"purpose": "turn_plan", "question": key, "answer": {
        "choice": choice, "confidence": conf, "probabilities": probs or {choice: conf}}}]})
    assert r.status_code == 204


def purposes(rows: list[dict[str, Any]]) -> list[str]:
    return [str(r["purpose"]) for r in rows]


async def send(api: Api, sid: str, text: str, ms: float = 12000) -> dict[str, Any]:
    await command(api, sid, "send", {"text": text})
    await api.drive(ms)
    return chars(await messages(api, sid))[-1]


# ── 3.2: where the planner runs ──
async def test_a_one_on_one_send_is_planned(api: Api) -> None:
    sid = await agent(api)
    before = len(await ledger(api))
    reply = await send(api, sid, "My dog died this morning.")
    new = (await ledger(api))[before:]
    # the plan's row lands before the chat row (a short message's rewrite may start beside the plan, rag 11.9, and so
    # does the early query embedding, rag 11.5, now that the seed ships Amara's vectors, D-110)
    assert [p for p in purposes(new) if p not in ("query_rewrite", "query_embed")][:2] == ["turn_plan", "reply"]
    plan_row = next(r for r in new if r["purpose"] == "turn_plan")
    assert plan_row["category"] == "decision" and plan_row["message_id"] == reply["id"]
    sys1 = reply["trace"]["system1"]
    assert sys1["seed"].endswith(":1") or ":" in sys1["seed"]
    row = sys1["questions"][0]
    assert (row["purpose"], row["id"], row["about"], row["result"]) == ("turn_plan", "emotion_reply", AMARA,
                                                                        "below_threshold")
    assert reply["trace"]["graph"]["path"] == ["state", "ask", "decide", "route"]
    assert any(c["purpose"] == "turn_plan" for c in reply["trace"]["calls"])


async def test_the_first_chat_greeting_asks_nothing(api: Api) -> None:
    await agent(api)
    assert "turn_plan" not in purposes(await ledger(api))


async def test_a_generated_greeting_asks_the_greeting_question(api: Api) -> None:
    await fixture(api, "happy", 0.9, key=f"emotion_greeting:{AMARA}")
    sid = await agent(api, first=False)
    greeting = chars(await messages(api, sid))[-1]
    assert greeting["emotion"] == "happy" and greeting["emotionSource"] == "classifier"
    assert greeting["trace"]["system1"]["questions"][0]["id"] == "emotion_greeting"


async def test_group_stays_unplanned(api: Api) -> None:
    """M9's behaviour, now M10's rollback: with the planner overridden to `naive`, an `agent` group is routed by the
    naive router and nothing is planned (turn-plan "Group stays unplanned in M9")."""
    sid = await agent(api, "group", [AMARA, "chr_seedMei"])
    r = await api.post(f"{API}/_test/ai-profile", {"profile": "agent", "overrides": {"planner": "naive"}})
    assert r.status_code == 204
    before = len(await ledger(api))
    await command(api, sid, "send", {"text": "@Amara what do you think?"})
    await api.drive(20000)
    new = purposes((await ledger(api))[before:])
    assert "turn_plan" not in new and "route" in new


async def test_group_is_planned_from_m10(api: Api) -> None:
    sid = await agent(api, "group", [AMARA, "chr_seedMei"])
    before = len(await ledger(api))
    await command(api, sid, "send", {"text": "What do you both think?"})
    await api.drive(20000)
    new = purposes((await ledger(api))[before:])
    assert new[0] == "turn_plan" and "route" not in new


async def test_naive_asks_nothing_new(api: Api) -> None:
    await api.set_key()
    assert (await api.post(f"{API}/_test/ai-profile", {"profile": "naive"})).status_code == 204
    sid: str = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    reply = await send(api, sid, "Hello there.")
    assert "turn_plan" not in purposes(await ledger(api)) and "system1" not in reply["trace"]


async def test_the_plan_overlaps_the_thinking_delay(api: Api) -> None:
    sid = await agent(api)
    await send(api, sid, "Hello again.")
    evs = await events(api, sid)
    thinking = [e for e in evs if e["type"] == "turn.thinking"][-1]
    plan_at = [r for r in await ledger(api) if r["purpose"] == "turn_plan"][-1]["at"]
    assert plan_at <= thinking["at"]                             # Jev answered before turn.thinking went out


async def test_a_late_answer_falls_back_and_is_still_recorded(api: Api) -> None:
    from tests.sessions.test_deep_m12 import measured_deadlines

    measured_deadlines(api)          # D-113: with `docsWaitAll` on, a plan asking about documents is waited for
    sid = await agent(api)
    assert api.rt.fake is not None
    n = api.rt.fake.counts["decisions"] + 1
    release = api.rt.fake.park_decision(n)
    reply = await send(api, sid, "Are you there?", ms=3000)
    row = reply["trace"]["system1"]["questions"][0]
    # the reply's own face is the fallback's (a face check's clash may switch it afterwards, D-112)
    assert row["result"] == "fallback" and "p" not in row and reply["trace"]["emotion"]["source"] == "default"
    release.set()
    await api.drive(1000)
    late = [r for r in await ledger(api) if r["purpose"] == "turn_plan"][-1]
    assert late["finish_reason"] == "late"


# ── 3.3: agent 1:1 retrieves nothing (D9) ──
async def test_agent_one_on_one_is_quick(api: Api) -> None:
    sid = await agent(api)
    before = len(await ledger(api))
    reply = await send(api, sid, "What does the sleep guide say about night shifts?")
    new = purposes((await ledger(api))[before:])
    # only the early embedding started beside the plan (rag 11.5; the seed ships her vectors, D-110): no search
    assert new.count("query_embed") <= 1 and "deep_check" not in new and "knowledge" not in reply["trace"]


# ── 3.5: turn.start and the first face in one write (D14) ──
async def test_turn_start_and_the_face_are_one_write(api: Api, monkeypatch: Any) -> None:
    batches: list[list[str]] = []
    real = SessionActor.emit

    async def spy(self: SessionActor, *evs: Any, **kw: Any) -> Any:
        batches.append([str(e["type"]) for e in evs])
        return await real(self, *evs, **kw)

    monkeypatch.setattr(SessionActor, "emit", spy)
    sid = await agent(api)
    await send(api, sid, "Morning.")
    assert ["turn.start", "emotion"] in batches
    assert ["turn.start"] not in batches[-12:]                   # the planned reply never starts alone
    evs = await events(api, sid)
    starts = [i for i, e in enumerate(evs) if e["type"] == "turn.start"]
    assert evs[starts[-1] + 1]["type"] == "emotion"


# ── 3.6: the engine's face comes from the plan (D14) ──
async def test_face_from_the_plan_and_a_tag_never_wins(api: Api) -> None:
    await fixture(api, "sad", 0.8, sad=0.8, thinking=0.1, none=0.1)
    sid = await agent(api)
    assert api.rt.fake is not None
    api.rt.fake.queued.append(sse(["<e:happy>Oh.", " I'm sorry."]))
    reply = await send(api, sid, "My dog died this morning.")
    assert (reply["emotion"], reply["emotionSource"], reply["content"]) == ("sad", "classifier", "Oh. I'm sorry.")
    emo = reply["trace"]["emotion"]
    assert emo["chosen"] == "sad" and [c["label"] for c in emo["candidates"]] == ["sad", "thinking"]


# ── 3.9: MANUAL still asks; the base is the last AI-chosen face (E2) ──
async def test_manual_records_the_pick_on_the_last_ai_face(api: Api) -> None:
    sid = await agent(api)                                       # the verbatim greeting's face is `happy`
    await command(api, sid, "set-emotion-mode", {"mode": "user"})
    await command(api, sid, "set-emotion", {"characterId": AMARA, "emotion": "angry"})
    await api.drive(500)
    await fixture(api, "none", 0.9)
    reply = await send(api, sid, "Just checking in.")
    assert reply["emotion"] == "happy" and reply["emotionSource"] == "default"   # kept from the last AI face, not angry
    assert reply["trace"]["system1"]["questions"][0]["action"] == "recorded (MANUAL)"


# ── 3.4: Stop, leave, a cap pause and end during the plan, through the runtime (D8) ──
async def _park_and_send(api: Api) -> tuple[str, Any, int]:
    sid = await agent(api)
    assert api.rt.fake is not None
    n = api.rt.fake.counts["decisions"] + 1
    release = api.rt.fake.park_decision(n)
    starts = sum(1 for e in await events(api, sid) if e["type"] == "turn.start")
    await command(api, sid, "send", {"text": "Are you awake?"})
    await api.drive(300)                       # turn.next and turn.thinking are out; Jev is parked
    return sid, release, starts


async def _stopped_cleanly(api: Api, sid: str, release: Any, starts: int) -> None:
    await api.drive(500)                       # NFR-20: gone within 500 ms
    actor = await api.rt.sessions.get(sid)
    assert actor.current is None or actor.current.closed
    assert sum(1 for e in await events(api, sid) if e["type"] == "turn.start") == starts   # no message was made
    release.set()
    await api.drive(2000)
    assert [r for r in await ledger(api) if r["purpose"] == "turn_plan"][-1]["finish_reason"] == "cancelled"
    assert not [r for r in await ledger(api) if r["purpose"] == "reply"]   # no reply was billed
    assert sum(1 for e in await events(api, sid) if e["type"] == "turn.start") == starts


async def test_stop_during_the_plan(api: Api) -> None:
    sid, release, starts = await _park_and_send(api)
    await command(api, sid, "stop")
    await _stopped_cleanly(api, sid, release, starts)


async def test_leave_during_the_plan(api: Api) -> None:
    sid, release, starts = await _park_and_send(api)
    assert (await api.post(f"{API}/sessions/{sid}/leave", {})).status_code == 204
    await _stopped_cleanly(api, sid, release, starts)


async def test_end_during_the_plan(api: Api) -> None:
    sid, release, starts = await _park_and_send(api)
    assert (await api.post(f"{API}/sessions/{sid}/end", {})).status_code == 204
    await _stopped_cleanly(api, sid, release, starts)


async def test_a_cap_pause_during_the_plan(api: Api) -> None:
    sid, release, starts = await _park_and_send(api)
    api.rt.sessions.pause_all_for_cap()
    await _stopped_cleanly(api, sid, release, starts)


# ── 3.6: a refused reply leaves no face change ──
async def test_a_refused_reply_leaves_no_face_change(api: Api) -> None:
    """The plan picks `happy` for a generated greeting, but the reply's preflight meets the daily cap: no turn.start,
    no face (speaker-emotion "Refused reply")."""
    await fixture(api, "happy", 0.9, key=f"emotion_greeting:{AMARA}")
    await api.set_key()
    assert (await api.post(f"{API}/_test/ai-profile", {"profile": "agent"})).status_code == 204
    await use_first_chat(api)
    assert (await api.client.patch(f"{API}/settings", json={"budget": {"dailyCapUsd": 0.00005}})).status_code == 200
    sid: str = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(8000)
    types = [e["type"] for e in await events(api, sid)]
    assert "turn.start" not in types and "emotion" not in types and chars(await messages(api, sid)) == []


# ── 3.7: the captured turn row holds the plan ──
async def test_the_captured_turn_holds_the_plan(api: Api) -> None:
    from tests.integration.test_capture import enable_capture, rows

    sid = await agent(api)
    enable_capture(api.rt)
    reply = await send(api, sid, "Hello.")
    turn = next(r for r in await rows(api) if r["kind"] == "turn" and r["message_id"] == reply["id"])
    plan = turn["response"]["plan"]
    assert plan is not None and plan["seed"] and plan["rows"][0]["id"] == "emotion_reply"


# ── 3.8: replay from JSON (A9) ──
def test_a_planned_context_replays_to_the_same_request() -> None:
    from horizon.ai.contexts import PlannedFace, TurnContext, TurnPlan
    from tests.sessions.test_agent_turn import ctx, engine, mv

    face = PlannedFace(face="sad", source="classifier", base="thinking", outcome="jev", pick="sad", p=0.8,
                       confidence=0.8, candidates=[{"label": "sad", "p": 0.8}])
    planned = ctx([mv(1, "user", "My dog died.", name="user")], mode="one_on_one", others=False).model_copy(
        update={"plan": TurnPlan(seed="s:1", branch="quick", emotion=face)})
    again = TurnContext.model_validate_json(planned.model_dump_json())
    a, _ = engine().request(planned)
    b, _ = engine().request(again)
    assert a == b and again.plan == planned.plan

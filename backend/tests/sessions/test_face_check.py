"""The face check through the runtime (turn-plan-emotion tasks 6.3, 6.4; design D24, D35; face-check, system1-trace and
decider specs). No network: the plan's face comes from a Decider fixture; the check itself is a real fake request,
parked so a test can choose its answer (a queued response) or its timing."""

from __future__ import annotations

import json
from typing import Any

import httpx

from tests.conftest import Api
from tests.sessions.kit import chars, command, create, events, ledger, messages
from tests.sessions.test_turn_plan import AMARA, agent, fixture

MEI, VICTOR = "chr_seedMei", "chr_seedVictor"


def checks(api: Api) -> list[dict[str, Any]]:
    assert api.rt.fake is not None
    out = []
    for r in api.rt.fake.requests:
        if r.url.path.endswith("/alpha/decisions"):
            body = json.loads(r.content)
            if "face_check" in (body.get("questions") or {}):
                out.append(body)
    return out


def answer(choice: str, p: float, face: str | None = None, p_face: float | None = None) -> httpx.Response:
    probs = {choice: p}
    if face is not None and p_face is not None:
        probs[face] = p_face
    return httpx.Response(200, json={"id": "dec-face", "model": "typesafe/jev-1.13", "answers": {"face_check": {
        "type": "choice", "choice": choice, "confidence": p, "probabilities": probs}},
        "usage": {"input_tokens": 400, "output_tokens": 0, "cost": 0.00002}})


def face_row(m: dict[str, Any]) -> dict[str, Any] | None:
    rows = ((m.get("trace") or {}).get("system1") or {}).get("questions") or []
    return next((r for r in rows if r["purpose"] == "face_check"), None)


async def checked_reply(api: Api, face: str, response: httpx.Response | None, *, text: str = "My dog died.",
                        after_ms: float = 380) -> tuple[str, dict[str, Any]]:
    """An agent 1:1 reply with `face`; its face check is held, answered with `response` `after_ms` after turn.end."""
    sid = await agent(api)
    await fixture(api, face, 0.9)
    assert api.rt.fake is not None
    release = api.rt.fake.park_question("face_check")   # M12: the plan sends its gate questions; hold the check
    await command(api, sid, "send", {"text": text})
    await until_parked(api)
    if response is not None:
        api.rt.fake.queued.append(response)
    release.set()
    await api.drive(after_ms)
    return sid, chars(await messages(api, sid))[-1]


async def until_parked(api: Api, limit_ms: float = 12000) -> None:
    """Drive in small steps until the held check request arrives (right after turn.end), well inside its 1.5 s."""
    assert api.rt.fake is not None
    t = 0.0
    while not api.rt.fake.decision_parked.is_set() and t < limit_ms:
        await api.drive(50)
        t += 50
    assert api.rt.fake.decision_parked.is_set()


# ── when it runs ──
async def test_a_non_neutral_auto_reply_is_checked_once_with_only_the_reply(api: Api) -> None:
    sid, reply = await checked_reply(api, "sad", answer("sad", 0.66))
    assert reply["emotion"] == "sad"
    sent = checks(api)
    assert len(sent) == 1 and set(sent[0]["state"]) == {"quoted_reply"}
    evs = await events(api, sid)
    end = next(e for e in evs if e["type"] == "turn.end")
    first_req = next(r for r in await ledger(api) if r["purpose"] == "face_check")
    assert first_req["at"] >= end["at"]                                        # asked after turn.end


async def test_a_neutral_reply_is_not_checked(api: Api) -> None:
    sid = await agent(api)
    await fixture(api, "neutral", 0.9)
    await command(api, sid, "send", {"text": "Hello there."})
    await api.drive(12000)
    assert chars(await messages(api, sid))[-1]["emotion"] == "neutral" and checks(api) == []


async def test_a_manual_reply_is_not_checked(api: Api) -> None:
    sid = await agent(api)
    await fixture(api, "sad", 0.9)
    await command(api, sid, "set-emotion-mode", {"mode": "user"})
    await command(api, sid, "send", {"text": "My dog died."})
    await api.drive(12000)
    assert checks(api) == []


# ── the row ──
async def test_agreement_adds_a_second_insight_with_the_row_and_the_call(api: Api) -> None:
    sid, reply = await checked_reply(api, "sad", answer("sad", 0.66))
    row = face_row(reply)
    assert row is not None and (row["answer"], row["p"], row["result"]) == ("yes", 0.66, "shown_only")
    assert any(c["purpose"] == "face_check" and "latencyMs" in c for c in reply["trace"]["calls"])
    insights = [e for e in await events(api, sid) if e["type"] == "insight" and e["payload"]["messageId"] == reply["id"]]
    assert len(insights) == 2
    before, after = insights[0]["payload"]["trace"], insights[1]["payload"]["trace"]
    assert after["system1"]["questions"][:-1] == before["system1"]["questions"]   # the earlier rows unchanged
    face_rows = [r for r in await ledger(api) if r["purpose"] in ("turn_plan", "face_check")]
    # the face was a fixture; M12's gates (Amara has documents) still ride the plan's one request
    assert {r["purpose"] for r in face_rows} == {"turn_plan", "face_check"}


async def test_clash(api: Api) -> None:
    _, reply = await checked_reply(api, "happy", answer("angry", 0.8, "happy", 0.05))
    row = face_row(reply)
    assert row is not None and (row["answer"], row["p"]) == ("clash", 0.05)


async def test_a_failed_check_changes_nothing(api: Api) -> None:
    sid, reply = await checked_reply(api, "sad", httpx.Response(500, json={"error": {"code": 500, "message": "boom"}}))
    assert face_row(reply) is None and reply["emotion"] == "sad"
    types = [e["type"] for e in await events(api, sid)]
    assert "error" not in types and "session.paused" not in types
    assert len([e for e in await events(api, sid) if e["type"] == "insight"
                and e["payload"]["messageId"] == reply["id"]]) == 1


async def test_a_late_check_adds_no_row(api: Api) -> None:
    sid = await agent(api)
    await fixture(api, "sad", 0.9)
    assert api.rt.fake is not None
    release = api.rt.fake.park_question("face_check")
    await command(api, sid, "send", {"text": "My dog died."})
    await api.drive(12000)                                                     # well past the 1.5 s deadline
    api.rt.fake.queued.append(answer("sad", 0.9))
    release.set()
    await api.drive(1000)
    assert face_row(chars(await messages(api, sid))[-1]) is None


# ── cancelling ──
async def test_regenerated_before_the_row_drops_it(api: Api) -> None:
    sid = await agent(api)
    await fixture(api, "sad", 0.9)
    assert api.rt.fake is not None
    release = api.rt.fake.park_question("face_check")
    await command(api, sid, "send", {"text": "My dog died."})
    await until_parked(api)
    reply = chars(await messages(api, sid))[-1]
    seen = len(await events(api, sid))
    await command(api, sid, "regenerate", {"messageId": reply["id"]})       # variant 2 starts; its own check follows
    for _ in range(20):                                                       # until variant 2's turn.start
        await api.drive(50)
        if any(e["type"] == "turn.start" for e in (await events(api, sid))[seen:]):
            break
    assert any(e["type"] == "turn.start" and e["payload"].get("variantId") for e in (await events(api, sid))[seen:])
    api.rt.fake.queued.append(answer("sad", 0.93))
    release.set()
    await api.drive(3000)
    insights = [e for e in await events(api, sid) if e["type"] == "insight" and e["payload"]["messageId"] == reply["id"]]
    rows = [r for e in insights for r in (e["payload"]["trace"].get("system1") or {}).get("questions", [])
            if r["purpose"] == "face_check"]
    assert not any(r.get("p") == 0.93 for r in rows)                          # variant 1's answer was dropped


async def test_stop_cancels_a_pending_check(api: Api) -> None:
    sid = await agent(api)
    await fixture(api, "sad", 0.9)
    assert api.rt.fake is not None
    release = api.rt.fake.park_question("face_check")
    await command(api, sid, "send", {"text": "My dog died."})
    await until_parked(api)
    await command(api, sid, "stop")
    api.rt.fake.queued.append(answer("sad", 0.9))
    release.set()
    await api.drive(2000)
    assert face_row(chars(await messages(api, sid))[-1]) is None


async def test_the_next_turn_does_not_cancel_a_group_check(api: Api) -> None:
    """A held non-neutral face (M8 D4) in an `agent` group: the check of the first reply survives the next speaker."""
    sid = await agent(api, "group", [AMARA, MEI, VICTOR])
    await command(api, sid, "set-emotion", {"characterId": AMARA, "emotion": "thinking"})
    # M10: two speakers from one send under `agent` means policy `everyone` (one plan, then every reply in order)
    await command(api, sid, "set-responder-policy", {"policy": "everyone"})
    assert api.rt.fake is not None
    n = api.rt.fake.counts["decisions"]
    held = [api.rt.fake.park_decision(n + 2), api.rt.fake.park_decision(n + 3)]   # after the plan: the reaction, the check
    await command(api, sid, "send", {"text": "What do you think?", "mentions": [AMARA]})
    await api.drive(800)                                                        # the next turn starts at ~+520 ms
    evs = await events(api, sid)
    assert len([e for e in evs if e["type"] == "turn.start"]) >= 2
    first = next(e for e in evs if e["type"] == "turn.end")["payload"]["messageId"]
    for h in held:
        h.set()
    await api.drive(1000)
    msg = next(m for m in await messages(api, sid) if m["id"] == first)
    assert face_row(msg) is not None                                           # the fake's answer, whatever it reads


# ── decider spec: the 1:1 rows ──
async def test_turn_plan_and_face_check_rows_and_only_the_reply_drains(api: Api) -> None:
    sid = await agent(api)
    assert api.rt.fake is not None
    key = f"emotion_reply:{AMARA}"
    api.rt.fake.queued.append(httpx.Response(200, json={"id": "dec-plan", "model": "typesafe/jev-1.13", "answers": {
        key: {"type": "choice", "choice": "sad", "confidence": 0.9, "probabilities": {"sad": 0.9}}},
        "usage": {"input_tokens": 900, "output_tokens": 0, "cost": 0.00005}}))      # Jev call 1, the first request
    before = len(await ledger(api))
    seen = len(await events(api, sid))
    await command(api, sid, "send", {"text": "My dog died."})
    await api.drive(12000)
    new = (await ledger(api))[before:]
    assert sorted(r["purpose"] for r in new if r["category"] == "decision") == ["face_check", "turn_plan"]
    reply = chars(await messages(api, sid))[-1]
    drains = [e["payload"] for e in (await events(api, sid))[seen:] if e["type"] == "energy"]
    assert [d["spent"] for d in drains] == [reply["usage"]["energySpent"]]       # only the reply drains


# ── 6.4: scripted ──
async def test_scripted_check_writes_a_simulated_row_and_a_second_insight(api: Api) -> None:
    await api.set_key()
    sid: str = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    for text in ("Hello!", "How was your day?", "Tell me something nice.", "Any plans?"):
        await command(api, sid, "send", {"text": text})
        await api.drive(12000)
    rows = [r for r in await ledger(api) if r["purpose"] == "face_check"]
    replies = [m for m in chars(await messages(api, sid)) if m.get("emotion") not in (None, "neutral")
               and m["kind"] == "chat"]
    assert len(rows) >= 1 and all(r["category"] == "decision" for r in rows)
    for m in replies:
        row = face_row(m)
        if row is not None:
            assert (row["answer"], row["result"]) == ("yes", "shown_only")
    assert any(face_row(m) is not None for m in replies)

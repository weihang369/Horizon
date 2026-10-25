"""Next speaker, Everyone and Step in under `agent` (group-watch tasks 5.4–5.6; design D11; doc 07 G4;
session-modes "Everyone in Jev's order", "Next speaker under agent", "Step in under agent"). No network: Jev answers
come from the fake, with chosen answers patched in for the questions a test cares about."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from horizon.sessions.turn import TurnRunner
from tests.conftest import Api
from tests.sessions.kit import API, chars, command, create, ledger, messages
from tests.sessions.test_group_plan import fixture, send
from tests.sessions.test_turn_plan import agent

AMARA, MEI, VICTOR = "chr_seedAmara", "chr_seedMei", "chr_seedVictor"
TRIO = [AMARA, MEI, VICTOR]


def jev_answers(api: Api, answers: dict[str, dict[str, Any]]) -> None:
    """Patch the fake's decisions: a question named in `answers` gets that answer; the rest keep the fake's default."""
    fake = api.rt.fake
    assert fake is not None
    plain = fake._decide

    def decide(body: dict[str, Any]) -> httpx.Response:
        resp = plain(body)
        data = json.loads(resp.content)
        for key in body.get("questions") or {}:
            if key in answers:
                data["answers"][key] = {"type": "choice", **answers[key]}
        return httpx.Response(200, json=data)

    fake._decide = decide  # type: ignore[method-assign]


def choice(c: str, conf: float, **probs: float) -> dict[str, Any]:
    return {"choice": c, "confidence": conf, "probabilities": probs or {c: conf}}


def decision_bodies(api: Api, key: str) -> list[dict[str, Any]]:
    assert api.rt.fake is not None
    return [b for b in (json.loads(r.content) for r in api.rt.fake.requests if r.url.path.endswith("/alpha/decisions"))
            if key in b["questions"]]


def cues(monkeypatch: Any) -> list[tuple[str, Any]]:
    """Record each streamed turn's (speaker, plan cue)."""
    seen: list[tuple[str, Any]] = []
    stream = TurnRunner._stream

    async def spy(self: TurnRunner, actor: Any, spec: Any, info: Any, ctx: Any, *a: Any, **k: Any) -> Any:
        seen.append((spec.speaker, ctx.plan.cue if ctx.plan is not None else None))
        return await stream(self, actor, spec, info, ctx, *a, **k)

    monkeypatch.setattr(TurnRunner, "_stream", spy)
    return seen


# ── 5.4: Next speaker ──
async def test_next_speaker_under_agent_asks_who_next_without_the_last_speaker(api: Api, monkeypatch: Any) -> None:
    sid = await agent(api, "group", TRIO)
    await fixture(api, "who_first", AMARA, 0.9, chr_seedAmara=0.9, chr_seedMei=0.05, chr_seedVictor=0.05)
    await fixture(api, "who_second", "none", 0.9, purpose="follow_plan")
    await send(api, sid, "Who's cooking tonight?")
    seen = cues(monkeypatch)
    jev_answers(api, {"who_next": choice(VICTOR, 0.8, chr_seedVictor=0.8, chr_seedMei=0.2)})
    before = len(chars(await messages(api, sid)))
    await command(api, sid, "next-speaker", {})
    await api.drive(30000)
    (body,) = decision_bodies(api, "who_next")
    assert set(body["questions"]["who_next"]["criteria"]) == {MEI, VICTOR}           # not the last speaker
    assert set(body["questions"]) == {"who_next", f"emotion_line:{MEI}", f"emotion_line:{VICTOR}",
                                      f"docs:{MEI}", f"docs:{VICTOR}"}   # M12: Next speaker asks the gate only
    (reply,) = chars(await messages(api, sid))[before:]
    assert reply["author"]["characterId"] == VICTOR
    who = next(r for r in reply["trace"]["system1"]["questions"] if r["id"] == "who_next")
    assert (who["answer"], who["result"], who["action"]) == (VICTOR, "used", "speaks next")
    assert seen == [(VICTOR, "next")]


async def test_next_speaker_with_a_chosen_character_asks_only_its_face(api: Api, monkeypatch: Any) -> None:
    sid = await agent(api, "group", TRIO)
    seen = cues(monkeypatch)
    await command(api, sid, "next-speaker", {"characterId": MEI})
    await api.drive(30000)
    (body,) = decision_bodies(api, f"emotion_line:{MEI}")
    assert list(body["questions"]) == [f"emotion_line:{MEI}", f"docs:{MEI}"]
    reply = chars(await messages(api, sid))[-1]
    assert reply["author"]["characterId"] == MEI and reply["trace"]["routing"]["forcedBy"] == "nudge"
    assert seen == [(MEI, "next")]


@pytest.mark.parametrize("profile", ["scripted", "naive"])
async def test_next_speaker_stays_random_without_a_cast_planner(api: Api, profile: str) -> None:
    await api.set_key()
    sid: str = (await create(api, "group", TRIO))["session"]["id"]
    await api.drive(6000)
    assert (await api.post(f"{API}/_test/ai-profile", {"profile": profile})).status_code == 204
    before = len(chars(await messages(api, sid)))
    await command(api, sid, "next-speaker", {})
    await api.drive(30000)
    assert len(chars(await messages(api, sid))) == before + 1
    assert decision_bodies(api, "who_next") == []


# ── 5.5: Everyone ──
async def test_everyone_in_jevs_order_from_one_request_with_its_faces(api: Api) -> None:
    sid = await agent(api, "group", TRIO)
    await fixture(api, "who_second", "none", 0.9, purpose="follow_plan")
    await send(api, sid, "Best film this year?")
    jev_answers(api, {"who_first": choice(VICTOR, 0.5, chr_seedVictor=0.5, chr_seedMei=0.3, chr_seedAmara=0.2),
                      f"emotion_reply:{AMARA}": choice("happy", 0.95)})
    n = len(decision_bodies(api, "who_first"))
    before = len(chars(await messages(api, sid)))
    await command(api, sid, "everyone-answer")
    await api.drive(60000)
    replies = chars(await messages(api, sid))[before:]
    assert [m["author"]["characterId"] for m in replies] == [VICTOR, MEI, AMARA]
    assert len(decision_bodies(api, "who_first")) == n + 1                # one request for the whole run
    amara = replies[2]                                                     # the third: prefetched
    assert amara["trace"]["emotion"]["chosen"] == "happy" and amara["trace"]["emotion"]["source"] == "classifier"   # D-112
    for m in replies:
        assert [r.get("about") for r in m["trace"]["system1"]["questions"] if r["id"] == "emotion_reply"] == [
            m["author"]["characterId"]]


async def test_everyone_when_jev_fails_goes_in_cast_order_with_fallback_faces(api: Api) -> None:
    sid = await agent(api, "group", TRIO)
    await fixture(api, "who_second", "none", 0.9, purpose="follow_plan")
    await send(api, sid, "Best film this year?")
    assert api.rt.fake is not None
    api.rt.fake.queued.append(httpx.Response(503, json={"error": {"message": "unavailable"}}))
    before = len(chars(await messages(api, sid)))
    await command(api, sid, "everyone-answer")
    await api.drive(60000)
    replies = chars(await messages(api, sid))[before:]
    assert [m["author"]["characterId"] for m in replies] == TRIO
    for m in replies:
        row = next(r for r in m["trace"]["system1"]["questions"] if r["id"] == "emotion_reply")
        assert row["result"] == "fallback"
    plan_calls = [c for c in replies[0]["trace"]["calls"] if c["purpose"] == "turn_plan"]
    assert plan_calls and plan_calls[0].get("fallback") is True


# ── 5.6: Step in ──
async def _agent_watch(api: Api) -> str:
    await api.set_key()
    assert (await api.post(f"{API}/_test/ai-profile", {"profile": "agent"})).status_code == 204
    sid: str = (await create(api, "watch", TRIO, config={"premise": "A storm traps everyone at the inn.",
                                                          "maxTurns": 20, "paceMs": 1500}))["session"]["id"]
    await api.drive(500)
    await command(api, sid, "watch/pause")
    await api.drive(30000)
    return sid


@pytest.mark.parametrize("second", [None, MEI])
async def test_step_in_under_agent_answers_first_then_maybe_a_second(api: Api, second: str | None) -> None:
    sid = await _agent_watch(api)
    await fixture(api, "who_first", VICTOR, 0.9, chr_seedVictor=0.9, chr_seedMei=0.05, chr_seedAmara=0.05)
    await fixture(api, "who_second", second or "none", 0.9, purpose="follow_plan")
    before = len(chars(await messages(api, sid)))
    await command(api, sid, "watch/step-in", {"text": "Who left the door open?"})
    await api.drive(40000)
    replies = chars(await messages(api, sid))[before:]
    assert [m["author"]["characterId"] for m in replies] == [VICTOR, *([second] if second else [])]
    assert replies[0]["trace"]["routing"]["question"] == "who answers first?"
    assert not [r for r in await ledger(api) if r["purpose"] == "route"]


async def test_step_in_without_a_cast_planner_keeps_two_random_replies(api: Api) -> None:
    await api.set_key()
    sid: str = (await create(api, "watch", TRIO, config={"premise": "A storm traps everyone at the inn.",
                                                          "maxTurns": 20, "paceMs": 1500}))["session"]["id"]
    await api.drive(500)
    await command(api, sid, "watch/pause")
    await api.drive(30000)
    before = len(chars(await messages(api, sid)))
    await command(api, sid, "watch/step-in", {"text": "Who left the door open?"})
    await api.drive(40000)
    assert len(chars(await messages(api, sid))) == before + 2
    assert decision_bodies(api, "who_first") == []

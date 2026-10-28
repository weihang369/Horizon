"""The output check (safety design D9–D12, D19; tasks 3.1–3.3, 3.6, 3.9; content-safety "The output check reads every
reply", "blocks, flags or passes", "A blocked reply keeps its trace", "No second reply after a block"; session-runtime
"Turn event sequence", "An interrupted reply is checked after the fact"; ai-ports "AI profile selection"). No network."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from horizon.ai.agent import guardrail as gr
from horizon.ai.contexts import (
    CharacterView,
    DebateMeta,
    LineHint,
    MessageView,
    ParticipantView,
    SafetyCue,
    SessionContext,
    TurnContext,
    TurnPlan,
    WorldView,
)
from horizon.domain import vclock
from horizon.domain.pricing import count_tokens
from tests.conftest import Api
from tests.helpers.storm import after_storm
from tests.sessions.kit import API, assert_reduces, chars, command, create, events, ledger, messages
from tests.sessions.test_gates_m12 import AMARA, MEI, VICTOR, agent, decisions, send

BLOCK = {"type": "noul", "noul": 0.95}
FLAG = {"type": "noul", "noul": 0.6}


def answer(api: Api, qid: str, raw: dict[str, Any] | None) -> None:
    assert api.rt.fake is not None
    api.rt.fake.answer_question(qid, raw)


def checks_of(m: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["name"]: c for c in ((m.get("trace") or {}).get("guardrail") or {}).get("checks") or []}


def guard_rows(m: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in ((m.get("trace") or {}).get("system1") or {}).get("questions") or [] if r["id"] == "output_rules"]


def guard_requests(api: Api) -> list[dict[str, Any]]:
    return [d for d in decisions(api) if "output_rules" in d["questions"]]


# ── 3.1: the state, the cut, the outcomes ──
def ctx(reply_kind: str = "chat", recent: list[MessageView] | None = None, care: bool = False,
        debate: DebateMeta | None = None, prompt: str = "") -> TurnContext:
    s = SessionContext(session_id="ses_x", world=WorldView(id="wld_x", name="W"), mode="debate" if debate else "one_on_one",
                       title="t", participants=[ParticipantView(character_id="chr_a", name="Amara Okafor", role="speaker",
                                                                character_role="Emergency physician",
                                                                energy={"current": 100})],
                       recent=recent or [MessageView(id="m1", seq=1, author_type="user", name="Kai", kind="chat",
                                                     content="What's a dangerous dose of paracetamol?")])
    plan = TurnPlan(seed="s:1", safety=SafetyCue(message_id="m1", care=care, p_care=0.8 if care else 0.02)) \
        if care else None
    return TurnContext(session=s, speaker=CharacterView(id="chr_a", name="Amara Okafor", profile={}), message_id="msg_r",
                       line=LineHint(kind=reply_kind), max_tokens=200, plan=plan, debate=debate, prompt=prompt)


def test_the_state_reads_the_reply_and_the_line_it_answers() -> None:
    state, qs = gr.build(ctx(care=True), "Over 4 g a day is dangerous; call a poison line for a real case.")
    assert set(qs) == {"output_rules"}
    assert state == {"name": "Amara Okafor", "role": "Emergency physician", "care": True,
                     "quoted_message": "What's a dangerous dose of paracetamol?",
                     "quoted_reply": "Over 4 g a day is dangerous; call a poison line for a real case."}


def test_a_long_answered_line_is_cut_from_its_start_and_the_reply_never() -> None:
    reply = "word " * 288                                   # ≈ 480 tokens: a long debate argument
    motion = "x" * 9000                                     # ≈ 3,000 tokens
    c = ctx("debate", recent=[MessageView(id="m1", seq=1, author_type="character", character_id="chr_b", name="Hana",
                                          kind="chat", content="y" * 9000)],
            debate=DebateMeta(phase="rebuttal", round=2, iteration=1, motion=motion))
    state, qs = gr.build(c, reply)
    assert state["quoted_reply"] == reply
    assert gr.size(state, qs) <= gr.CAP
    assert state["quoted_message"].startswith("…") and state["quoted_message"].endswith("y")


def test_the_outcomes_and_thresholds() -> None:
    assert gr.thresholds() == {"tFlag": 0.5, "tBlock": 0.9}
    assert [gr.verdict_for(p) for p in (0.1, 0.5, 0.89, 0.9, 0.99)] == ["pass", "flag", "flag", "block", "block"]
    assert count_tokens("x") >= 1


# ── 3.2: a blocked reply keeps its trace; the event order ──
async def test_a_blocked_care_reply_shows_all_three_checks_and_its_p(api: Api) -> None:
    sid = await agent(api, "one_on_one", [AMARA])
    answer(api, "at_risk", {"type": "noul", "noul": 0.82})
    answer(api, "output_rules", BLOCK)
    await command(api, sid, "send", {"text": "How many paracetamol would it take so I don't wake up?"})
    await api.drive(15000)
    [reply] = chars(await messages(api, sid))[-1:]
    assert reply["status"] == "error" and reply["content"] == "" and reply["error"]["code"] == "content_refused"
    c = checks_of(reply)
    assert set(c) == {"input", "care", "output"}
    assert c["output"] == {"name": "output", "verdict": "block", "p": 0.95} and c["care"]["verdict"] == "flag"
    [row] = guard_rows(reply)
    assert (row["action"], row["result"], row["p"]) == ("block", "used", 0.95)
    [req] = guard_requests(api)
    assert req["state"]["care"] is True and req["state"]["quoted_reply"]          # the reply as stored
    evs = [e for e in await events(api, sid) if e["payload"].get("messageId") == reply["id"]]
    kinds = [e["type"] for e in evs]
    i = kinds.index("error")
    assert kinds[i + 1] == "turn.end" and evs[i + 1]["payload"]["status"] == "error" and "insight" in kinds[i + 2:]
    await assert_reduces(api, sid)


async def test_a_flag_keeps_the_reply_and_jev_down_never_blocks(api: Api) -> None:
    sid = await agent(api, "one_on_one", [AMARA])
    answer(api, "output_rules", FLAG)
    [flagged] = await send(api, sid, "Tell me about a hard night shift.")
    assert flagged["status"] == "complete" and checks_of(flagged)["output"] == {"name": "output", "verdict": "flag",
                                                                               "p": 0.6}
    assert api.rt.fake is not None
    api.rt.fake.refuse_question("output_rules")
    [down] = await send(api, sid, "And the next one?")
    assert down["status"] == "complete" and checks_of(down)["output"] == {"name": "output", "verdict": "flag"}
    [row] = guard_rows(down)
    assert row["result"] == "fallback" and row["action"] == "flagged: Jev failed"
    rows = [r for r in await ledger(api) if r["purpose"] == "guardrail"]
    assert len(rows) == 1 and rows[0]["message_id"] == flagged["id"]   # linked to its reply; a 429 bills nothing


async def test_a_pass_is_merged_with_the_input_check(api: Api) -> None:
    sid = await agent(api, "one_on_one", [AMARA])
    [reply] = await send(api, sid, "How was your shift?")
    c = checks_of(reply)
    assert c["input"] == {"name": "input", "verdict": "pass", "p": 0.02}
    assert c["output"] == {"name": "output", "verdict": "pass", "p": 0.02}
    assert c["care"]["verdict"] == "pass"


# ── 3.9: the other profiles (D12) ──
async def test_naive_asks_nothing_and_shows_no_checks(api: Api) -> None:
    await api.set_key()
    assert (await api.post(f"{API}/_test/ai-profile", {"profile": "naive"})).status_code == 204
    sid = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    [reply] = await send(api, sid, "How was your shift?")
    assert checks_of(reply) == {}
    assert not [r for r in await ledger(api) if r["purpose"] == "guardrail"]
    assert api.rt.ai.resolved(key_set=True)["guardrail"] == "naive"


async def test_scripted_shows_one_passing_output_check(api: Api) -> None:
    await api.set_key()
    assert (await api.post(f"{API}/_test/ai-profile", {"profile": "scripted"})).status_code == 204
    sid = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    await command(api, sid, "send", {"text": "Hello"})
    await api.drive(15000)
    reply = chars(await messages(api, sid))[-1]
    c = checks_of(reply)
    assert list(c) == ["output"] and c["output"]["verdict"] == "pass" and 0 < c["output"]["p"] < 0.1


async def test_agent_resolves_the_agent_guardrail(api: Api) -> None:
    await agent(api, "one_on_one", [AMARA])
    assert api.rt.ai.resolved(key_set=True)["guardrail"] == "agent"


# ── 3.3: doc 11 check 3 offline: the follow plan's pick lands before the block ──
async def test_no_second_reply_after_a_block_even_when_the_pick_lands_first(api: Api) -> None:
    sid = await agent(api, "group", [AMARA, MEI, VICTOR])
    fake = api.rt.fake
    assert fake is not None
    fake.answer_question("who_second", {"type": "choice", "choice": MEI, "confidence": 0.95,
                                        "probabilities": {MEI: 0.95}})
    held = fake.park_question("output_rules")
    answer(api, "output_rules", BLOCK)
    await command(api, sid, "send", {"text": "@Amara what happened on the ward?", "mentions": [AMARA]})
    for _ in range(200):
        await api.drive(10)
        if any("who_second" in d["questions"] for d in decisions(api)) and fake.decision_parked.is_set():
            break
    await api.drive(300)                       # the follow plan's pick is back; the check is still held
    held.set()
    await api.drive(20000)
    replies = chars(await messages(api, sid))
    assert [m["author"]["characterId"] for m in replies[-1:]] == [AMARA] and replies[-1]["status"] == "error"
    assert not any(e["type"] == "turn.next" and e["payload"]["nextSpeakerId"] == MEI for e in await events(api, sid))


# ── 3.6: the after-the-fact check ──
async def _stopped_during_the_check(api: Api, verdict: dict[str, Any]) -> tuple[str, asyncio.Event]:
    sid = await agent(api, "one_on_one", [AMARA])
    fake = api.rt.fake
    assert fake is not None
    held = fake.park_question("output_rules")
    answer(api, "output_rules", verdict)
    await command(api, sid, "send", {"text": "Tell me about the night shift."})
    for _ in range(400):
        await api.drive(10)
        if guard_requests(api):
            break
    assert guard_requests(api)
    await command(api, sid, "stop")
    return sid, held


async def test_stop_during_the_check_blocks_after_the_fact_with_one_ledger_row(api: Api) -> None:
    sid, held = await _stopped_during_the_check(api, BLOCK)
    reply = chars(await messages(api, sid))[-1]
    assert reply["status"] == "interrupted" and reply["content"]                 # Stop closed it; the check is out
    held.set()
    await api.drive(3000)
    reply = chars(await messages(api, sid))[-1]
    assert reply["status"] == "error" and reply["content"] == ""                 # U2: a blocked row, Regenerate only
    assert checks_of(reply)["output"]["verdict"] == "block" and guard_rows(reply)[0]["action"] == "block"
    assert len([r for r in await ledger(api) if r["purpose"] == "guardrail"]) == 1   # nothing paid twice
    evs = await events(api, sid)
    end = next(e for e in evs if e["type"] == "turn.end" and e["payload"]["messageId"] == reply["id"])
    err = next(e for e in evs if e["type"] == "error" and e["payload"].get("messageId") == reply["id"])
    assert end["payload"]["status"] == "interrupted" and err["seq"] > end["seq"]
    tokens = [e for e in evs if e["type"] == "token" and e["payload"]["messageId"] == reply["id"]]
    assert all(e["payload"]["delta"] == "" for e in tokens)                     # scrubbed in the stored events too
    await after_storm(api, sid)


async def test_a_stop_after_the_check_answered_keeps_its_block_and_pays_once(api: Api) -> None:
    """Pass 2 J2-06: Stop lands after the check answered but before the turn closed (here: the usage read). The
    interrupted close reuses that answer: no second request, and the block still scrubs the reply."""
    sid = await agent(api, "one_on_one", [AMARA])
    answer(api, "output_rules", BLOCK)
    real, gate, reached = api.rt.ledger.reply_usage, asyncio.Event(), asyncio.Event()

    async def held_once(message_id: str, since: str | None = None) -> Any:
        if guard_requests(api) and not reached.is_set():
            reached.set()
            holder = vclock.current_holder()   # parked like the fake's holds, so virtual time can still settle
            if holder is not None:
                holder.drop()
            try:
                await gate.wait()
            finally:
                if holder is not None:
                    holder.hold()
        return await real(message_id, since=since)

    api.rt.ledger.reply_usage = held_once  # type: ignore[method-assign]
    await command(api, sid, "send", {"text": "Tell me about the night shift."})
    for _ in range(400):
        await api.drive(10)
        if reached.is_set():
            break
    assert reached.is_set()
    await command(api, sid, "stop")
    gate.set()
    await api.drive(3000)
    reply = chars(await messages(api, sid))[-1]
    assert reply["status"] == "error" and reply["content"] == ""
    assert checks_of(reply)["output"]["verdict"] == "block"
    assert len(guard_requests(api)) == 1
    assert len([r for r in await ledger(api) if r["purpose"] == "guardrail"]) == 1
    await after_storm(api, sid)


async def test_an_after_the_fact_pass_appends_its_row(api: Api) -> None:
    sid, held = await _stopped_during_the_check(api, {"type": "noul", "noul": 0.1})
    held.set()
    await api.drive(3000)
    reply = chars(await messages(api, sid))[-1]
    assert reply["status"] == "interrupted" and reply["content"]
    assert checks_of(reply)["output"] == {"name": "output", "verdict": "pass", "p": 0.1}
    assert guard_rows(reply)[0]["action"] == "pass"
    await assert_reduces(api, sid)


async def test_a_delete_cancels_the_after_the_fact_check(api: Api) -> None:
    sid, held = await _stopped_during_the_check(api, BLOCK)
    reply = chars(await messages(api, sid))[-1]
    assert (await api.client.delete(f"{API}/sessions/{sid}")).status_code == 204
    held.set()
    await api.drive(3000)
    async with api.rt.db.read() as conn:
        from sqlalchemy import text

        n = (await conn.execute(text("SELECT count(*) FROM messages WHERE id = :m"), {"m": reply["id"]})).scalar_one()
    assert n == 0


def test_unused() -> None:
    assert json


# ── 3.4: prefetches are checked before release ──
def block_named(api: Api, name: str, times: int = 99) -> list[str]:
    """Patch the fake: the output check blocks replies by `name` (the first `times` of them); returns who was checked."""
    import httpx

    fake = api.rt.fake
    assert fake is not None
    plain = fake._decide
    seen: list[str] = []

    def decide(body: dict[str, Any]) -> httpx.Response:
        data = json.loads(plain(body).content)
        if "output_rules" in (body.get("questions") or {}):
            who = str(body["state"]["name"])
            seen.append(who)
            if who.startswith(name) and seen.count(who) <= times:
                data["answers"]["output_rules"] = BLOCK
        return httpx.Response(200, json=data)

    fake._decide = decide  # type: ignore[method-assign]
    return seen


async def linked_guard_rows(api: Api) -> dict[str | None, int]:
    out: dict[str | None, int] = {}
    for r in await ledger(api):
        if r["purpose"] == "guardrail":
            out[r["message_id"]] = out.get(r["message_id"], 0) + 1
    return out


async def test_a_blocked_everyone_prefetch_is_never_shown_and_the_next_speaker_follows(api: Api) -> None:
    sid = await agent(api, "group", [AMARA, MEI, VICTOR])
    await command(api, sid, "set-responder-policy", {"policy": "everyone"})
    block_named(api, "Mei")
    got = await send(api, sid, "What did everyone do this weekend?", ms=60000)
    assert [m["author"]["characterId"] for m in got] == [AMARA, VICTOR]
    evs = await events(api, sid)
    assert not any(e["type"] == "turn.start" and e["payload"]["author"].get("characterId") == MEI for e in evs)
    rows = await linked_guard_rows(api)
    assert all(rows.get(m["id"]) == 1 for m in got)          # one check per shown reply: never checked twice
    assert rows.get(None, 0) == 1                            # the blocked prefetch's check, never linked
    await assert_reduces(api, sid)


async def test_a_blocked_opening_prefetch_is_redone_live(api: Api) -> None:
    from tests.sessions.test_debate_plan import debate

    sid = await debate(api, autoAdvance=True)
    seen = block_named(api, "Mei", times=1)
    await api.drive(150000)
    openings = [m for m in chars(await messages(api, sid)) if (m.get("debate") or {}).get("phase") == "opening"]
    mei = [m for m in openings if m["author"]["characterId"] == MEI]
    assert len(mei) == 1 and mei[0]["status"] == "complete" and mei[0]["content"]
    assert seen.count("Mei Lin") >= 2 or len([s for s in seen if s.startswith("Mei")]) >= 2
    rows = await linked_guard_rows(api)
    assert all(rows.get(m["id"]) == 1 for m in openings)


# ── 3.5: a host line and verdict prose are checked inside their tasks ──
async def test_a_blocked_host_line_shows_the_fixed_line(api: Api) -> None:
    from tests.sessions.test_debate_host import WRITTEN, can, debate, host_lines

    sid = await debate(api, profile="agent")
    can(api, WRITTEN)
    block_named(api, "The host", times=1)                 # the welcome only
    await api.drive(8000)
    lines = host_lines(await messages(api, sid))
    assert lines[0] == 'Welcome. Tonight\'s motion: "This house would ban homework". Opening statements, please.'
    req = next(d for d in guard_requests(api) if d["state"]["name"] == "The host")
    assert req["state"]["quoted_reply"] == WRITTEN[0] and req["state"]["role"] == "debate host"


async def test_blocked_verdict_prose_takes_the_failed_prose_fallback(api: Api) -> None:
    from horizon.ai.naive.verdict import NOTE_PROSE
    from tests.sessions.test_debate_verdict import can, debate, jev_scores, prose, verdict_of

    sid = await debate(api)
    jev_scores(api, prop=4, opp=1)
    can(api, prose())
    seen = block_named(api, "The arbiter")
    await api.drive(120000)
    v = await verdict_of(api, sid)
    assert "The arbiter" in seen
    assert v["strongerCase"] == "prop" and v["scores"]                 # the scores and the winner stay
    assert v.get("rationale") is None and v["summary"] != [{"subjectId": "prop", "points": ["Prop point 0"]}]
    assert NOTE_PROSE in [m["content"] for m in await messages(api, sid)]


# ── 3.7: the waits after a turn count from the stream's end (D10) ──
class SlowCheck:
    """An `agent`-shaped guardrail whose check takes `s` seconds of clock time and passes."""

    def __init__(self, api: Api, s: float) -> None:
        self.api, self.s = api, s

    def start(self, ctx: Any, text: str) -> Any:
        from datetime import timedelta

        from horizon.ai.ports import GuardrailResult

        clock = self.api.rt.clock
        s = self.s

        class Call:
            def __init__(self) -> None:
                self.started_at = clock.now()

            def deadline(self) -> Any:
                return self.started_at + timedelta(seconds=0.7)

            async def by(self, at: Any) -> GuardrailResult:   # Jev answers `s` after the check was sent
                await clock.sleep(max(0.0, (self.started_at + timedelta(seconds=s) - clock.now()).total_seconds()))
                return GuardrailResult("pass", [{"name": "output", "verdict": "pass", "p": 0.1}])

            async def final(self) -> GuardrailResult:
                return await self.by(None)

        return Call()

    async def check(self, ctx: Any, text: str) -> Any:
        return await self.start(ctx, text).by(None)


def ms(at: str) -> float:
    from horizon.domain.timeutil import ms_from_iso

    return float(ms_from_iso(at))


async def gap_after_first_reply(api: Api, sid: str, after: str = "turn.next") -> tuple[float, float]:
    """(stream end → the next `after` event, stream end → `turn.end`) for the session's first character reply."""
    evs = await events(api, sid)
    first = next(e for e in evs if e["type"] == "turn.start")
    mid = first["payload"]["messageId"]
    last_token = max(ms(e["at"]) for e in evs if e["type"] == "token" and e["payload"]["messageId"] == mid)
    end = next(e for e in evs if e["type"] == "turn.end" and e["payload"]["messageId"] == mid)
    nxt = next(e for e in evs if e["type"] == after and e["seq"] > end["seq"])
    return ms(nxt["at"]) - last_token, ms(end["at"]) - last_token


async def watch_cadence(api: Api, check_s: float) -> tuple[float, float]:
    from tests.sessions.test_watch_plan import agent_watch

    sid = await agent_watch(api, paceMs=3000)
    if check_s:   # after the profile is set (setting it rebuilds the ports)
        api.rt.ai.override("guardrail", SlowCheck(api, check_s))
    await api.drive(20000)
    return await gap_after_first_reply(api, sid)


async def test_a_short_check_is_hidden_in_the_watch_pace(make_api: Any) -> None:
    plain = await watch_cadence(await make_api(), 0.0)
    slow = await watch_cadence(await make_api(), 0.5)
    assert slow[1] - plain[1] >= 490                     # the check really took 0.5 s before turn.end
    assert abs(slow[0] - plain[0]) <= 40                 # but the next turn starts as if it took none


async def debate_cadence(api: Api, check_s: float) -> tuple[float, float]:
    from tests.sessions.test_debate_plan import debate

    sid = await debate(api, autoAdvance=True, pauseMs=1500)
    if check_s:
        api.rt.ai.override("guardrail", SlowCheck(api, check_s))
    await api.drive(30000)
    return await gap_after_first_reply(api, sid, after="turn.start")   # the next argument starts on time


async def test_a_short_check_is_hidden_in_the_debate_pause(make_api: Any) -> None:
    plain = await debate_cadence(await make_api(), 0.0)
    slow = await debate_cadence(await make_api(), 0.5)
    assert slow[1] - plain[1] >= 490
    assert abs(slow[0] - plain[0]) <= 40

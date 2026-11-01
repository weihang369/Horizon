"""The debate plan through the runtime (debate tasks 3.2–3.8; design D5, D6, D8, D27; debate-plan spec; system1-trace's
debate scenarios). The seed world has three characters, so a side with two members is 1 v 2 (in-phase member questions:
Victor's rebuttal, then the Opposition's slot with Amara and Mei eligible) or 2 v 1 (the boundary plan: the rebuttal's
first slot is the Proposition's, Amara and Mei). No network."""

from __future__ import annotations

import json
from typing import Any

import httpx

from horizon.domain.timeutil import ms_from_iso
from tests.conftest import Api
from tests.sessions.kit import API, assert_reduces, chars, command, create, events, ledger, messages

AMARA, MEI, VICTOR = "chr_seedAmara", "chr_seedMei", "chr_seedVictor"
TRIO = [AMARA, MEI, VICTOR]
ONE_V_TWO = {"prop": [VICTOR], "opp": [AMARA, MEI]}
TWO_V_ONE = {"prop": [AMARA, MEI], "opp": [VICTOR]}


async def debate(api: Api, profile: str = "agent", sides: dict[str, list[str]] | None = None, **cfg: Any) -> str:
    await api.set_key()
    assert (await api.post(f"{API}/_test/ai-profile", {"profile": profile})).status_code == 204
    config = {"motion": "This house would ban homework", "format": "two_sided", "sides": sides or ONE_V_TWO,
              "roundsPreset": "quick", "phases": ["opening", "rebuttal"], "turnLength": "short", "moderator": "user",
              "verdictBy": "user", "rubric": [], "autoAdvance": True, "pauseMs": 1500, **cfg}
    sid: str = (await create(api, "debate", TRIO, config=config))["session"]["id"]
    return sid


def requests(api: Api) -> list[dict[str, Any]]:
    assert api.rt.fake is not None
    return [json.loads(r.content) for r in api.rt.fake.requests if r.url.path.endswith("/alpha/decisions")]


def plan_requests(api: Api) -> list[dict[str, Any]]:
    return [b for b in requests(api) if any(k.startswith(("member_", "emotion_line:")) for k in b["questions"])
            and not any(k.startswith("emotion_reply") for k in b["questions"])]


def jev_answers(api: Api, **answers: tuple[str, float]) -> None:
    """The fake answers every choice at 1/n (below every floor); give these question keys a sure (or set) answer."""
    fake = api.rt.fake
    assert fake is not None
    plain = fake._decide

    def decide(body: dict[str, Any]) -> httpx.Response:
        resp = plain(body)
        data = json.loads(resp.content)
        for key in body.get("questions") or {}:
            if key in answers:
                choice, conf = answers[key]
                data["answers"][key] = {"type": "choice", "choice": choice, "confidence": conf,
                                        "probabilities": {choice: conf}}
        return httpx.Response(200, json=data)

    fake._decide = decide  # type: ignore[method-assign]


def args(msgs: list[dict[str, Any]], phase: str) -> list[dict[str, Any]]:
    return [m for m in chars(msgs) if (m.get("debate") or {}).get("phase") == phase and not m.get("forcedSpeaker")]


async def until(api: Api, sid: str, test: Any, step: float = 5, limit: float = 120000) -> None:
    spent = 0.0
    while spent < limit:
        if await test():
            return
        await api.drive(step)
        spent += step
    raise AssertionError("timed out")


async def first_rebuttal_end(api: Api, sid: str) -> dict[str, Any]:
    """Drive until the rebuttal's first argument has ended: its `turn.end`."""
    async def done() -> bool:
        reb = args(await messages(api, sid), "rebuttal")
        evs = await events(api, sid)
        return bool(reb) and any(e["type"] == "turn.end" and e["payload"]["messageId"] == reb[0]["id"] for e in evs)
    await until(api, sid, done, step=50)
    first = args(await messages(api, sid), "rebuttal")[0]
    return next(e for e in await events(api, sid) if e["type"] == "turn.end" and e["payload"]["messageId"] == first["id"])


def next_after(evs: list[dict[str, Any]], seq: int) -> dict[str, Any]:
    return next(e for e in evs if e["type"] == "turn.next" and e["seq"] > seq)


# ── 3.2: naive and scripted make no debate plan ──
async def test_naive_and_scripted_debates_make_no_debate_plan(api: Api) -> None:
    for profile in ("naive", "scripted"):
        sid = await debate(api, profile)
        await api.drive(120000)
        assert len(args(await messages(api, sid), "rebuttal")) == 3
    assert not [b for b in requests(api) if any(k.startswith("member_") for k in b["questions"])]
    assert not [r for r in await ledger(api) if r["purpose"] == "debate_plan"]


# ── 3.3 / D8: who is asked about ──
async def test_two_eligible_members_are_asked_about_in_one_request_with_the_rebuttal_state(api: Api) -> None:
    sid = await debate(api)
    await api.drive(120000)
    reb = args(await messages(api, sid), "rebuttal")
    assert reb[0]["author"]["characterId"] == VICTOR
    asked = [b for b in plan_requests(api) if "member_rebuttal" in b["questions"]]
    assert len(asked) == 1
    body = asked[0]
    assert set(body["questions"]) == {"member_rebuttal", f"emotion_line:{AMARA}", f"emotion_line:{MEI}",
                                      f"docs:{AMARA}", f"docs:{MEI}"}   # M12 (rag D8): the gate, no rewrite nouls
    assert set(body["state"]["quoted_documents"]) == {"Amara Okafor", "Mei Tanaka-Ruiz"}
    assert set(body["questions"]["member_rebuttal"]["criteria"]) == {AMARA, MEI}
    st = body["state"]
    text = json.dumps(st)
    assert "last_spoke" not in text
    arguments = st["quoted_arguments"]
    assert arguments["last_opposing"].startswith("Victor")
    assert all(len(v.removesuffix(" …").split()) <= 60 for v in arguments["latest_by_candidate"].values())
    assert {r["purpose"] for r in await ledger(api) if r["purpose"] == "debate_plan"} == {"debate_plan"}
    await assert_reduces(api, sid)


async def test_one_eligible_member_is_not_asked_about(api: Api) -> None:
    sid = await debate(api)
    await api.drive(120000)
    single = [b for b in plan_requests(api) if not any(k.startswith("member_") for k in b["questions"])]
    assert single, "the boundary plan for Victor's rebuttal and the last Opposition slot ask the face only"
    assert all(len([k for k in b["questions"] if not k.startswith("docs:")]) == 1 for b in single)   # + M12's gate
    await assert_reduces(api, sid)


async def test_uneven_sides_never_quote_a_teammate(api: Api) -> None:
    """2 v 1: the rebuttal runs P, O, P. The third slot's (Mei's) state quotes Victor, not her teammate."""
    sid = await debate(api, sides=TWO_V_ONE)
    await api.drive(120000)
    reb = args(await messages(api, sid), "rebuttal")
    assert reb[1]["author"]["characterId"] == VICTOR
    third = [b for b in plan_requests(api) if set(b["questions"]) == {f"emotion_line:{MEI}", f"docs:{MEI}"}
             or set(b["questions"]) == {f"emotion_line:{AMARA}", f"docs:{AMARA}"}]
    for body in third:
        st = body.get("state") or {}
        lo = (st.get("quoted_arguments") or {}).get("last_opposing")
        if lo:
            assert lo.startswith("Victor")


# ── 3.4: the timeline ──
async def test_a_quick_pick_is_announced_when_jev_answers_with_no_turn_gap(api: Api) -> None:
    sid = await debate(api)
    jev_answers(api, member_rebuttal=(MEI, 0.9))
    assert api.rt.fake is not None
    release = api.rt.fake.park_question("member_rebuttal")
    end = await first_rebuttal_end(api, sid)
    await until(api, sid, lambda: _true(api.rt.fake.decision_parked.is_set()), step=1)  # type: ignore[union-attr]
    t_end = ms_from_iso(end["at"])
    await api.drive(420 - (ms_from_iso(api.rt.clock.now().isoformat()) - t_end))
    release.set()
    await api.drive(60000)
    nxt = next_after(await events(api, sid), end["seq"])
    assert nxt["payload"]["nextSpeakerId"] == MEI
    assert 420 <= ms_from_iso(nxt["at"]) - t_end < 430
    reb = args(await messages(api, sid), "rebuttal")
    assert [m["author"]["characterId"] for m in reb][:2] == [VICTOR, MEI]
    tr = reb[1]["trace"]
    assert tr["routing"]["question"] == "who answers it?" and tr["routing"]["selected"] == MEI
    assert tr["routing"]["forcedBy"] == "round_order"
    assert tr["routing"]["reason"] == "Side by the debate order; speaker chosen by Jev"
    member = next(r for r in tr["system1"]["questions"] if r["id"] == "member_rebuttal")
    assert (member["purpose"], member["answer"], member["result"], member["action"]) == (
        "debate_plan", MEI, "used", "speaks")
    await assert_reduces(api, sid)


async def _true(v: bool) -> bool:
    return v


async def test_a_late_answer_announces_fixed_order_at_the_deadline(api: Api) -> None:
    sid = await debate(api)
    jev_answers(api, member_rebuttal=(MEI, 0.9))
    assert api.rt.fake is not None
    release = api.rt.fake.park_question("member_rebuttal")
    end = await first_rebuttal_end(api, sid)
    await api.drive(800)
    nxt = next_after(await events(api, sid), end["seq"])
    assert nxt["payload"]["nextSpeakerId"] == AMARA
    assert 735 <= ms_from_iso(nxt["at"]) - ms_from_iso(end["at"]) < 745   # the measured deadline (M15 8.13)
    release.set()
    await api.drive(60000)
    reb = args(await messages(api, sid), "rebuttal")
    assert reb[1]["author"]["characterId"] == AMARA
    tr = reb[1]["trace"]
    assert tr["routing"]["reason"] == "Side by the debate order; speaker chosen by Jev, next in order: Jev was late"
    member = next(r for r in tr["system1"]["questions"] if r["id"] == "member_rebuttal")
    assert member["result"] == "fallback"
    await assert_reduces(api, sid)


async def test_unsure_announces_the_first_eligible(api: Api) -> None:
    sid = await debate(api)
    jev_answers(api, member_rebuttal=(MEI, 0.3))
    await api.drive(120000)
    reb = args(await messages(api, sid), "rebuttal")
    assert [m["author"]["characterId"] for m in reb] == [VICTOR, AMARA, MEI]
    tr = reb[1]["trace"]
    assert tr["routing"]["reason"] == "Side by the debate order; speaker chosen by Jev, next in order: Jev was unsure"
    member = next(r for r in tr["system1"]["questions"] if r["id"] == "member_rebuttal")
    assert (member["result"], member["action"]) == ("below_threshold", "next in order (unsure)")


async def test_a_late_member_still_gets_an_on_time_face(api: Api) -> None:
    sid = await debate(api)
    jev_answers(api, member_rebuttal=(MEI, 0.9), **{f"emotion_line:{AMARA}": ("happy", 0.95)})
    assert api.rt.fake is not None
    release = api.rt.fake.park_question("member_rebuttal")
    end = await first_rebuttal_end(api, sid)
    await api.drive(900)
    release.set()
    await api.drive(60000)
    reb = args(await messages(api, sid), "rebuttal")
    amara = reb[1]
    assert amara["author"]["characterId"] == AMARA
    assert next_after(await events(api, sid), end["seq"])["payload"]["nextSpeakerId"] == AMARA
    assert amara["emotion"] == "happy" and amara["emotionSource"] == "classifier"
    face = next(r for r in amara["trace"]["system1"]["questions"]
                if r["id"] == "emotion_line" and r.get("about") == AMARA)
    assert face["result"] == "used"


async def test_too_late_for_the_face_keeps_the_fallback_and_writes_the_late_rows(api: Api) -> None:
    from tests.sessions.test_deep_m12 import measured_deadlines

    measured_deadlines(api)          # D-113: with `docsWaitAll` on, a plan with Amara's gate is waited for
    sid = await debate(api)
    jev_answers(api, **{f"emotion_line:{AMARA}": ("happy", 0.95)})
    assert api.rt.fake is not None
    release = api.rt.fake.park_question("member_rebuttal")
    end = await first_rebuttal_end(api, sid)

    async def started() -> bool:
        return any(e["type"] == "turn.start" and e["seq"] > end["seq"] for e in await events(api, sid))
    await until(api, sid, started, step=50)
    release.set()
    await api.drive(60000)
    amara = args(await messages(api, sid), "rebuttal")[1]
    assert amara["author"]["characterId"] == AMARA
    face = amara["trace"]["emotion"]          # the reply's own face (a face check's clash may switch it, D-112)
    assert face["chosen"] != "happy" and face["source"] != "classifier"            # a kept (or faded) face
    rows = [r for r in amara["trace"]["system1"]["questions"] if r["purpose"] == "debate_plan"]
    late = [r for r in rows if r["id"] == "emotion_line" and r.get("about") == AMARA and r["result"] == "fallback"
            and r.get("answer") == "happy"]
    assert late, json.dumps(rows, indent=1)
    # audit D-05: the late call itself is on the trace, beside the deadline's fallback entry
    calls = [c for c in amara["trace"]["calls"] if c["purpose"] == "debate_plan"]
    assert any(not c.get("fallback") and c["latencyMs"] > 0 for c in calls), calls
    await assert_reduces(api, sid)


# ── 3.8: clear() cancels ──
async def test_ending_during_a_plan_records_the_call_cancelled(api: Api) -> None:
    sid = await debate(api)
    assert api.rt.fake is not None
    release = api.rt.fake.park_question("member_rebuttal")
    await first_rebuttal_end(api, sid)
    await api.drive(100)
    await command(api, sid, "debate/end", {"withVerdict": False})
    await api.drive(2000)
    release.set()
    await api.drive(5000)
    rows = [r for r in await ledger(api) if r["purpose"] == "debate_plan"]
    assert rows[-1]["finish_reason"] == "cancelled"
    assert (await api.json(f"{API}/sessions/{sid}"))["session"]["status"] == "ended"
    await assert_reduces(api, sid)


# ── 3.5: the fingerprint, one part at a time ──
def _fp(**kw: Any) -> tuple[Any, ...]:
    from horizon.sessions.debate_plan import fingerprint_of

    base: dict[str, Any] = {"epoch": 1, "reply_epoch": 0,
                            "msgs": [{"seq": 4, "author": {"type": "character"}}, {"seq": 5, "author": {"type": "user"}}],
                            "emotion_mode": "auto", "parts": [(AMARA, True, False, "neutral")],
                            "target": ("rebuttal", 1)}
    base.update(kw)
    return fingerprint_of(**base)


def test_every_fingerprint_part_moves_it_and_a_banner_or_host_line_does_not() -> None:
    same = _fp()
    assert _fp() == same
    assert _fp(epoch=2) != same
    assert _fp(reply_epoch=1) != same
    assert _fp(msgs=[{"seq": 4, "author": {"type": "character"}}, {"seq": 6, "author": {"type": "user"}}]) != same
    assert _fp(emotion_mode="manual") != same
    assert _fp(parts=[(AMARA, False, False, "neutral")]) != same       # asleep / topped up
    assert _fp(parts=[(AMARA, True, True, "neutral")]) != same         # muted
    assert _fp(parts=[(AMARA, True, False, "happy")]) != same          # a face
    assert _fp(target=("rebuttal", 2)) != same
    assert _fp(target=("closing", 1)) != same
    later = [{"seq": 4, "author": {"type": "character"}}, {"seq": 5, "author": {"type": "user"}},
             {"seq": 6, "author": {"type": "system"}}, {"seq": 7, "author": {"type": "host"}}]
    assert _fp(msgs=later) == same                                     # a banner, a host line, a system note


# ── 3.5 / 3.6: the phase's first slot ──
async def test_a_banner_and_a_host_line_dont_spoil_the_first_slots_plan(api: Api) -> None:
    """2 v 1: the plan made at the last opening's `turn.end` picks the rebuttal's first Proposition speaker; the
    banner and the host's narration land in between, and the turn uses the stored plan."""
    sid = await debate(api, sides=TWO_V_ONE, moderator="auto_host")
    jev_answers(api, member_rebuttal=(MEI, 0.9), **{f"emotion_line:{MEI}": ("angry", 0.95)})
    await api.drive(120000)
    msgs = await messages(api, sid)
    reb = args(msgs, "rebuttal")
    assert reb[0]["author"]["characterId"] == MEI
    assert reb[0]["emotion"] == "angry"
    tr = reb[0]["trace"]
    assert tr["routing"]["question"] == "who answers it?" and tr["routing"]["selected"] == MEI
    first = [b for b in plan_requests(api) if "member_rebuttal" in b["questions"]]
    assert len(first) == 1                       # planned once, at the boundary, not again at the turn
    assert any(m["kind"] == "narration" for m in msgs)
    await assert_reduces(api, sid)


async def test_extend_discards_the_plan_and_the_extended_rounds_first_slot_plans_at_its_turn(api: Api) -> None:
    sid = await debate(api, sides=TWO_V_ONE, phases=["opening", "rebuttal", "closing"])
    jev_answers(api, member_rebuttal=(MEI, 0.9))
    assert api.rt.fake is not None

    async def three_rebuttals() -> bool:
        return len(args(await messages(api, sid), "rebuttal")) >= 3
    await until(api, sid, three_rebuttals, step=50, limit=300000)
    stored = (await api.rt.sessions.get(sid)).mode.debate_plan
    assert stored is not None and stored.target == ("closing", 1)
    await command(api, sid, "debate/extend-round")
    await api.drive(300000)
    reb = [m for m in args(await messages(api, sid), "rebuttal") if m["debate"]["iteration"] == 2]
    assert reb and reb[0]["author"]["characterId"] == MEI
    assert reb[0]["trace"]["routing"]["question"] == "who answers it?"
    # the closing's stored plan was dropped (it had settled, so its row stays `final`); the extended round asked anew
    assert len([b for b in plan_requests(api) if "member_rebuttal" in b["questions"]]) == 2
    await assert_reduces(api, sid)


async def test_the_closings_first_slot_uses_the_plan_stored_before_the_bridge(api: Api) -> None:
    sid = await debate(api, sides=TWO_V_ONE, phases=["opening", "rebuttal", "closing"], moderator="auto_host")
    jev_answers(api, member_closing=(MEI, 0.9))
    await api.drive(400000)
    clo = args(await messages(api, sid), "closing")
    assert clo[0]["author"]["characterId"] == MEI
    assert clo[0]["trace"]["routing"]["question"] == "who sums up?"
    assert len([b for b in plan_requests(api) if "member_closing" in b["questions"]]) == 1


# ── 3.5 / 3.7: an Ask in the pause ──
async def test_an_ask_in_the_pause_keeps_the_member_and_asks_the_face_again(api: Api) -> None:
    sid = await debate(api)
    jev_answers(api, member_rebuttal=(MEI, 0.9))
    end = await first_rebuttal_end(api, sid)

    async def announced() -> bool:
        return any(e["type"] == "turn.next" and e["seq"] > end["seq"] for e in await events(api, sid))
    await until(api, sid, announced, step=5)
    assert next_after(await events(api, sid), end["seq"])["payload"]["nextSpeakerId"] == MEI
    await command(api, sid, "debate/ask", {"characterId": VICTOR, "text": "Victor, what about weekends?"})
    await api.drive(120000)
    cm = chars(await messages(api, sid))
    first = next(i for i, m in enumerate(cm) if m["id"] == end["payload"]["messageId"])
    after = cm[first + 1:]
    assert after[0]["author"]["characterId"] == VICTOR and after[0].get("forcedSpeaker")
    assert after[1]["author"]["characterId"] == MEI
    rows = after[1]["trace"]["system1"]["questions"]
    member = next(r for r in rows if r["id"] == "member_rebuttal")
    assert member["purpose"] == "debate_plan" and member["result"] == "used"
    face = next(r for r in rows if r["id"] == "emotion_line" and r.get("about") == MEI)
    assert face["purpose"] == "turn_plan"           # asked again at Mei's turn
    await assert_reduces(api, sid)


async def test_pause_drops_the_stored_faces_and_play_asks_them_again(api: Api) -> None:
    sid = await debate(api)
    jev_answers(api, member_rebuttal=(MEI, 0.9))
    end = await first_rebuttal_end(api, sid)

    async def announced() -> bool:
        return any(e["type"] == "turn.next" and e["seq"] > end["seq"] for e in await events(api, sid))
    await until(api, sid, announced, step=5)
    await command(api, sid, "debate/pause")
    await api.drive(5000)
    await command(api, sid, "debate/resume")
    await api.drive(120000)
    mei = args(await messages(api, sid), "rebuttal")[1]
    assert mei["author"]["characterId"] == MEI
    face = next(r for r in mei["trace"]["system1"]["questions"] if r["id"] == "emotion_line" and r.get("about") == MEI)
    assert face["purpose"] == "turn_plan"

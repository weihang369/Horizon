"""Cancel storms on the paths M11 adds (debate design D2; session-runtime "New cancel paths leave the writer free").

Every new cancel path is stormed twice: while it writes (`storm_during_write`) and while it waits on a parked Jev or
DeepSeek call (`storm_during_call`). Afterwards the writer is free, the clock settles and the log reduces. Phase 0
proves the helpers on an M10 path; each later phase adds its own."""

from __future__ import annotations

from horizon.sessions.actor import SessionActor
from horizon.sessions.modes.common import message_event, note
from tests.conftest import Api
from tests.helpers.storm import park_next_chat, storm_during_call, storm_during_write
from tests.sessions.kit import command, ledger


async def test_the_storm_helpers_on_the_watch_plan_made_ahead(api: Api) -> None:
    """Task 0.2: the plan made ahead waits on a parked Jev answer; a storm on it leaves the writer free and records the
    call `cancelled` (M9 D8). Then storms on a note's append, landing in its write."""
    from tests.sessions.test_watch_plan import _until_turn_end, agent_watch

    sid = await agent_watch(api, manual=True, maxTurns=10, paceMs=1500)
    assert api.rt.fake is not None
    release = api.rt.fake.park_decision(api.rt.fake.counts["decisions"] + 2)
    await _until_turn_end(api, sid, 1)
    await api.drive(100)
    actor: SessionActor = await api.rt.sessions.get(sid)
    ahead = list(actor._named.get("plan_ahead", ()))
    assert len(ahead) == 1
    await storm_during_call(api, sid, ahead[0], release)
    assert [r for r in await ledger(api) if r["purpose"] == "turn_plan"][-1]["finish_reason"] == "cancelled"

    await command(api, sid, "watch/pause")
    await api.drive(100)

    async def append() -> None:
        await actor.emit(message_event(note(actor, "A storm note.")))

    cut = await storm_during_write(api, sid, append, storms=12)
    assert 0 <= cut <= 12


async def test_a_chat_request_can_be_parked_by_purpose(api: Api) -> None:
    """The fake holds the next chat request with the parked purpose until released (debate D2: host lines and verdicts),
    and answers others at once."""
    from tests.sessions.test_recap import watch

    sid = await watch(api)
    release = park_next_chat(api.rt, "episode_summary")
    await command(api, sid, "watch/summarise")
    await api.drive(5000)
    assert api.rt.fake is not None and api.rt.fake.chat_parked.is_set()
    assert not [r for r in await ledger(api) if r["purpose"] == "episode_summary"]
    release.set()
    await api.drive(5000)
    assert [r for r in await ledger(api) if r["purpose"] == "episode_summary"]


async def test_a_storm_on_the_asleep_side_pause_leaves_the_writer_free(api: Api) -> None:
    """Task 2.10 (D2, D4): the pause writes each asleep member's note, the side's note and `session.paused`; storms
    landing anywhere in those writes leave the writer free and the log reducing."""
    from horizon.sessions.modes import debate as mode
    from tests.sessions.test_debate_slots import VICTOR, debate, drain

    await drain(api, VICTOR)
    sid = await debate(api, autoAdvance=False)
    await api.drive(15000)
    actor: SessionActor = await api.rt.sessions.get(sid)

    async def pause() -> None:
        await mode.pause_side(actor, "opp", (VICTOR,))

    cut = await storm_during_write(api, sid, pause, storms=20, window_s=0.25)
    print(f"\nstorms on the asleep-side pause: {cut} of 20 cut before it finished")
    assert 0 < cut < 20   # the storms hit both sides of the writes


async def test_storms_on_a_stored_debate_plan(api: Api) -> None:
    """Task 3.10 (D2, D8): a stored debate plan cut by `clear()` while its Jev answer is parked (the call recorded
    `cancelled`), by storms landing in the plan's start and its `turn.next` write, and by a fingerprint change (an
    Interject) at the turn's start. The writer stays free each time."""
    from types import SimpleNamespace

    from horizon.sessions.modes import debate as mode
    from tests.sessions.test_debate_plan import debate, first_rebuttal_end, jev_answers

    sid = await debate(api)
    jev_answers(api, member_rebuttal=("chr_seedMei", 0.9))
    assert api.rt.fake is not None
    release = api.rt.fake.park_question("member_rebuttal")
    await first_rebuttal_end(api, sid)
    await api.drive(100)
    actor: SessionActor = await api.rt.sessions.get(sid)
    hold = list(actor._named.get("debate_plan", ()))
    assert len(hold) == 1 and actor.mode.debate_plan is not None
    await storm_during_call(api, sid, hold[0], release)
    await api.drive(2000)
    assert "cancelled" in {r["finish_reason"] for r in await ledger(api) if r["purpose"] == "debate_plan"}

    await command(api, sid, "debate/pause")
    await api.drive(100)

    async def plan_and_announce() -> None:
        await mode.after_argument(actor, SimpleNamespace(ended_at=api.rt.clock.now()))

    cut = await storm_during_write(api, sid, plan_and_announce, storms=12, window_s=0.4)
    print(f"\nstorms on the debate plan's start (cut in the turn gap): {cut} of 12 cut before it finished")
    await actor.clear()
    await api.drive(100)
    assert actor.mode.debate_plan is None and not actor._named.get("debate_plan")

    async def write_turn_next() -> None:
        try:
            await actor.emit({"type": "turn.next", "payload": {"nextSpeakerId": "chr_seedMei"}})
        finally:
            await actor.clear()

    cut = await storm_during_write(api, sid, write_turn_next, storms=20, window_s=0.02)
    print(f"storms on the turn.next write with clear(): {cut} of 20 cut before it finished")
    assert actor.mode.debate_plan is None

    # a fingerprint change: the moderator interjects after the plan is stored; the turn drops it and asks again
    sid2 = await debate(api)
    release2 = api.rt.fake.park_question("emotion_line:")
    await first_rebuttal_end(api, sid2)
    await api.drive(100)
    await command(api, sid2, "debate/interject", {"text": "Please keep to the evidence."})
    release2.set()
    await api.drive(60000)
    from tests.helpers.storm import after_storm

    await after_storm(api, sid2)


async def test_storms_on_a_host_line(api: Api) -> None:
    """Task 6.5 (D2, D11): a host line cut while its DeepSeek answer is parked, by storms landing in its write, and by
    Extend and Skip dropping a line made for something else. The writer stays free each time."""
    from horizon.ai.contexts import HostKey
    from horizon.sessions import debate_host
    from tests.sessions.test_debate_host import debate

    sid = await debate(api)
    assert api.rt.fake is not None
    release = park_next_chat(api.rt, "host")             # the welcome, asked at Start
    await api.drive(200)
    actor: SessionActor = await api.rt.sessions.get(sid)
    pending = list(actor._named.get("host_line", ()))
    assert len(pending) == 1
    await storm_during_call(api, sid, pending[0], release)
    await api.drive(3000)
    assert "cancelled" in {r["finish_reason"] for r in await ledger(api) if r["purpose"] == "host"}

    await command(api, sid, "debate/pause")
    await api.drive(100)

    async def show() -> None:
        await debate_host.show(actor, HostKey(kind="bridge", phase="rebuttal"), api.rt.clock.now())

    cut = await storm_during_write(api, sid, show, storms=20, window_s=0.03)
    print(f"\nstorms on a host line's write: {cut} of 20 cut before it finished")

    for name in ("debate/extend-round", "debate/skip-to-closing"):   # a line asked for something else is dropped
        rel = park_next_chat(api.rt, "host")
        debate_host.request(actor, HostKey(kind="bridge", phase="closing"))
        await api.drive(50)
        await command(api, sid, name)
        debate_host.request(actor, HostKey(kind="extended", phase="rebuttal", iteration=2))
        from tests.helpers.storm import after_storm

        await after_storm(api, sid)
        rel.set()
        await api.drive(100)
    debate_host.drop(actor)
    await api.drive(100)


async def test_storms_on_the_verdict_work(api: Api) -> None:
    """Task 7.12 (D2, D14): the verdict work cut while its rubric answer is parked, by Extend, Skip and End without
    verdict; End with verdict landing in a turn's writes; a resume landing in the re-run's writes. The writer stays
    free each time."""
    from horizon.sessions import debate_verdict
    from horizon.sessions.modes import debate as mode
    from tests.helpers.storm import after_storm
    from tests.sessions.test_debate_verdict import can, debate, jev_scores, prose

    for cut in ("debate/extend-round", "debate/skip-to-closing", "end"):
        sid = await debate(api, phases=["opening", "rebuttal"] if cut != "debate/skip-to-closing" else ["opening",
                                                                                                        "closing"])
        jev_scores(api)
        can(api, prose())
        assert api.rt.fake is not None
        release = api.rt.fake.park_question("rubric_")
        api.rt.fake.decision_parked.clear()
        while not api.rt.fake.decision_parked.is_set():
            await api.drive(20)
        actor: SessionActor = await api.rt.sessions.get(sid)
        work = actor.mode.verdict_work
        assert work is not None and not work.task.done()
        if cut == "end":
            await command(api, sid, "debate/end", {"withVerdict": False})
        else:
            await command(api, sid, cut)
        await api.drive(100)
        assert work.task.cancelled()
        await after_storm(api, sid)
        release.set()
        await api.drive(2000)
        if cut == "end":
            continue
        await command(api, sid, "debate/end", {"withVerdict": False})
        await api.drive(1000)

    sid = await debate(api, phases=["opening", "closing"])
    jev_scores(api)
    can(api, prose())
    await api.drive(3000)
    actor = await api.rt.sessions.get(sid)

    async def end_now() -> None:
        await mode.end_debate(actor, True)

    cut_n = await storm_during_write(api, sid, end_now, storms=1, window_s=0.02)
    await api.drive(60000)
    await after_storm(api, sid)
    print(f"\nstorms on End with verdict: {cut_n} of 1 cut")

    async def rerun() -> None:
        debate_verdict.resume(actor)
        await actor.rt.clock.sleep(0)

    await storm_during_write(api, sid, rerun, storms=5, window_s=0.02)

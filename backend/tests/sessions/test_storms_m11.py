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

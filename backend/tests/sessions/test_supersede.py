"""Doc 07 G5: a user message cancels the previous message's unannounced replies (group-watch tasks 5.1, 5.2; design
D12; session-runtime "A user message supersedes unannounced replies", "Superseded work ends at its boundaries";
session-modes "Sent in the gap", "Announced reply finishes"). No network.

(The mock parity check is the portable contract test "a message sent in the gap supersedes …", milestone M10.)"""

from __future__ import annotations

import asyncio
import random
from typing import Any

from horizon.sessions.actor import SessionActor
from horizon.sessions.modes.common import message_event, user_message
from tests.conftest import Api
from tests.sessions.kit import API, assert_reduces, chars, command, create, events, ledger, messages

AMARA, MEI, VICTOR = "chr_seedAmara", "chr_seedMei", "chr_seedVictor"
TRIO = [AMARA, MEI, VICTOR]


async def scripted_group(api: Api) -> str:
    await api.set_key()
    sid: str = (await create(api, "group", TRIO))["session"]["id"]
    await api.drive(6000)
    return sid


def users_and_nexts(evs: list[dict[str, Any]]) -> tuple[list[int], list[dict[str, Any]]]:
    users = [e["seq"] for e in evs if e["type"] == "message" and e["payload"]["message"]["author"]["type"] == "user"]
    return users, [e for e in evs if e["type"] == "turn.next"]


# ── 5.1: the check and the write share the lock ──
async def test_never_between_the_check_and_the_write(api: Api) -> None:
    """A `turn.next` checked against the epoch and a user message that supersedes it, started at the same moment a
    thousand times in random interleavings: the `turn.next` is either before the message or absent, never after."""
    sid = await scripted_group(api)
    actor: SessionActor = await api.rt.sessions.get(sid)
    rng = random.Random(10)
    announced = 0

    async def yields(n: int) -> None:
        for _ in range(n):
            await asyncio.sleep(0)

    for i in range(1000):
        epoch = actor.reply_epoch
        a_wait, m_wait = rng.randint(0, 4), rng.randint(0, 4)

        async def announce(epoch: int = epoch, wait: int = a_wait) -> list[dict[str, Any]]:
            await yields(wait)
            return await actor.emit_checked({"type": "turn.next", "payload": {"nextSpeakerId": AMARA}},
                                            lambda _s: epoch == actor.reply_epoch)

        async def message(i: int = i, wait: int = m_wait) -> list[dict[str, Any]]:
            await yields(wait)
            await actor.supersede()
            return await actor.emit(message_event(user_message(actor, f"m{i}")))

        got, msg = await asyncio.gather(announce(), message())
        if got:
            assert got[0]["seq"] < msg[0]["seq"]
            announced += 1
    print(f"\nG5 races: {announced} of 1000 announced before the message, {1000 - announced} never announced")
    assert 0 < announced < 1000


# ── 5.2: cooperative ends ──
async def test_sent_in_the_gap_gives_no_second_reply_to_the_first_message(api: Api) -> None:
    sid = await scripted_group(api)
    start = len(await events(api, sid))
    await command(api, sid, "send", {"text": "What should we cook tonight?"})   # scripted Auto: two replies
    for _ in range(400):
        await api.drive(25)
        if any(e["type"] == "turn.end" for e in (await events(api, sid))[start:]):
            break
    await command(api, sid, "send", {"text": "Actually, dessert?"})
    await api.drive(40000)
    evs = (await events(api, sid))[start:]
    users, nexts = users_and_nexts(evs)
    assert len([n for n in nexts if n["seq"] < users[1]]) == 1
    assert len([n for n in nexts if n["seq"] > users[1]]) == 2
    await assert_reduces(api, sid)


async def test_an_announced_reply_finishes_before_the_new_message_is_answered(api: Api) -> None:
    sid = await scripted_group(api)
    start = len(await events(api, sid))
    await command(api, sid, "send", {"text": "What should we cook tonight?"})
    for _ in range(400):
        await api.drive(10)
        evs = (await events(api, sid))[start:]
        if any(e["type"] == "turn.next" for e in evs):
            break
    assert not any(e["type"] == "turn.start" for e in evs)   # announced, no token yet
    await command(api, sid, "send", {"text": "Actually, dessert?"})
    await api.drive(40000)
    evs = (await events(api, sid))[start:]
    users, nexts = users_and_nexts(evs)
    first = nexts[0]["payload"]["nextSpeakerId"]
    end = next(e for e in evs if e["type"] == "turn.end")
    assert end["payload"]["status"] == "complete" and end["seq"] < nexts[1]["seq"]
    assert [n["seq"] > users[1] for n in nexts] == [False, True, True]
    replies = chars(await messages(api, sid))
    assert any(m["author"]["characterId"] == first and m["status"] == "complete" for m in replies)


async def test_a_step_in_during_a_scene_turns_gap_keeps_its_turn_count(api: Api) -> None:
    await api.set_key()
    sid: str = (await create(api, "watch", TRIO, config={"premise": "A storm traps everyone at the inn.",
                                                          "maxTurns": 20, "paceMs": 1500}))["session"]["id"]
    for _ in range(2000):
        await api.drive(25)
        if any(e["type"] == "turn.end" for e in await events(api, sid)):
            break
    await command(api, sid, "send", {"text": "Wait, who left the door open?"})   # watch: Step in
    await api.drive(40000)
    evs = await events(api, sid)
    taken = [e["payload"]["turnsTaken"] for e in evs if e["type"] == "watch.state"]
    assert 1 in taken                                         # the scene turn's increment wasn't lost
    users, nexts = users_and_nexts(evs)
    assert len([n for n in nexts if n["seq"] > users[0]]) >= 1   # the Step in is answered


async def test_a_superseded_follow_plan_is_cancelled_and_the_new_message_answered(api: Api) -> None:
    from tests.sessions.test_follow_plan import drive_until_turn_end, first_is_amara
    from tests.sessions.test_turn_plan import agent

    sid = await agent(api, "group", TRIO)
    await first_is_amara(api)
    assert api.rt.fake is not None
    release = api.rt.fake.park_decision(api.rt.fake.counts["decisions"] + 2)   # call 1, then the follow plan
    await command(api, sid, "send", {"text": "I'm moving to Lisbon next month."})
    end = await drive_until_turn_end(api, sid)
    await command(api, sid, "send", {"text": "Anyway. Lunch?"})
    await api.drive(30000)
    release.set()
    await api.drive(2000)
    reasons = [r["finish_reason"] for r in await ledger(api) if r["purpose"] == "follow_plan"]
    assert "cancelled" in reasons                             # the first message's (the second's ran normally)
    evs = await events(api, sid)
    users, nexts = users_and_nexts(evs)
    assert len([n for n in nexts if end["seq"] < n["seq"] < users[-1]]) == 0   # no second reply to the first message
    assert len([n for n in nexts if n["seq"] > users[-1]]) >= 1
    await assert_reduces(api, sid)


async def test_everyone_then_a_send_skips_the_unannounced_speakers(api: Api) -> None:
    """Everyone's run captured the epoch when queued; a send supersedes its remaining speakers (and its prefetches)."""
    sid = await scripted_group(api)
    await command(api, sid, "send", {"text": "Hello all"})
    await api.drive(40000)
    start = len(await events(api, sid))
    await command(api, sid, "everyone-answer")
    for _ in range(400):
        await api.drive(25)
        if any(e["type"] == "turn.end" for e in (await events(api, sid))[start:]):
            break
    await command(api, sid, "send", {"text": "Ok, just one of you."})
    await api.drive(40000)
    evs = (await events(api, sid))[start:]
    users, nexts = users_and_nexts(evs)
    assert len([n for n in nexts if n["seq"] < users[0]]) == 1
    actor: SessionActor = await api.rt.sessions.get(sid)
    assert not actor.prefetches
    assert (await api.json(f"{API}/sessions/{sid}"))["session"]["status"] == "active"
    await assert_reduces(api, sid)

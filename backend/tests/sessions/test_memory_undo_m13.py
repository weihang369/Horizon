"""The undo and Forget (memory design D20, D21; long-term-memory "A changed read message is undone and read again",
"Forget clears stored query rewrites", "A run commits its memories with its checkpoint"; session-runtime "A blocked
reply is scrubbed")."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from sqlalchemy import text

from horizon.ai.contexts import TurnContext
from horizon.ai.ports import GuardrailResult, Insert, MemoryDraft, Supersede
from horizon.ai.profile import ProfileSpec
from horizon.domain import vclock
from horizon.services.ai_meta import store_rewrite, stored_rewrite
from horizon.services.memory.stretch import WriterResult
from tests.conftest import Api
from tests.helpers.storm import after_storm, storm
from tests.sessions.kit import API, chars, command, create, messages
from tests.sessions.test_deep_m12 import chats, nouls
from tests.sessions.test_gates_m12 import agent, gate, send

AMARA, MERIDIAN = "chr_seedAmara", "wld_seedMeridian"


class Recorder:
    """A writer that records each stretch and writes nothing (or holds until released)."""

    def __init__(self, hold: bool = False) -> None:
        self.seen: list[Any] = []
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        if not hold:
            self.release.set()
        self.ops: dict[str, list[Any]] = {}

    async def on_stretch(self, stretch: Any, ctx: Any) -> WriterResult:
        self.seen.append(stretch)
        self.entered.set()
        holder = vclock.current_holder()   # give the run's token up while held, so the clock can move meanwhile
        if holder is not None:
            holder.drop()
        try:
            await self.release.wait()
        finally:
            if holder is not None:
                holder.hold()
        return WriterResult(ops=dict(self.ops))


def writing(api: Api, writer: Any) -> None:
    api.rt.set_profile(ProfileSpec(profile="naive", test_mode=True))
    api.rt.ai.override("memory_writer", writer)


async def chat(api: Api, n: int = 2) -> tuple[str, str]:
    """A read 1:1 chat: (session id, the last reply's id). The checkpoint is at the last message."""
    await api.set_key()
    sid = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    for i in range(n):
        await command(api, sid, "send", {"text": f"My exams start soon, part {i}."})
        await api.drive(15_000)
    api.rt.memory_runs.request(sid)
    await api.rt.memory_runs.drain()
    reply = chars(await messages(api, sid))[-1]
    assert await checkpoint(api, sid) == int(reply["seq"])
    return sid, str(reply["id"])


async def checkpoint(api: Api, sid: str) -> int:
    async with api.rt.db.read() as conn:
        return int((await conn.execute(text("SELECT memory_seq FROM sessions WHERE id = :s"), {"s": sid})).scalar_one())


async def reread(api: Api, sid: str) -> list[str]:
    async with api.rt.db.read() as conn:
        raw = (await conn.execute(text("SELECT memory_reread FROM sessions WHERE id = :s"), {"s": sid})).scalar_one()
    return list(json.loads(raw) if isinstance(raw, str) else raw or [])


async def plant_b_over_a(api: Api, sid: str, source: str) -> tuple[str, str]:
    """A from an earlier session, B (sourced from `source`) superseding it."""
    [a] = await api.rt.memory.apply(AMARA, MERIDIAN, [Insert(MemoryDraft("fact", "Kai studies law.", 0.6))])
    [b] = await api.rt.memory.apply(AMARA, MERIDIAN, [Supersede([a], MemoryDraft(
        "fact", "Kai studies law and sleeps badly before exams.", 0.6, source_session_id=sid, source_message_id=source,
        source_variant_id=f"{source}_v1", source_mode="one_on_one"))])
    return a, b


async def state_of(api: Api, mid: str) -> str:
    async with api.rt.db.read() as conn:
        row = (await conn.execute(text("SELECT superseded_by FROM memory_items WHERE id = :m"), {"m": mid})).first()
    return "gone" if row is None else ("current" if row[0] is None else "superseded")


# ── 4.1 the undo ──
async def test_a_regenerate_undoes_b_restores_a_and_queues_the_new_variant(api: Api) -> None:
    w = Recorder()
    writing(api, w)
    sid, reply = await chat(api)
    a, b = await plant_b_over_a(api, sid, reply)
    seq = await checkpoint(api, sid)
    await command(api, sid, "regenerate", {"messageId": reply})
    await api.drive(15_000)
    assert await state_of(api, b) == "gone" and await state_of(api, a) == "current"
    assert await checkpoint(api, sid) == seq and await reread(api, sid) == [reply]
    w.seen.clear()
    await command(api, sid, "send", {"text": "Thanks, that helps."})   # a re-read rides the next run's piece
    await api.drive(15_000)
    api.rt.memory_runs.request(sid)
    await api.rt.memory_runs.drain()
    [piece] = w.seen
    [line] = [ln for ln in piece.lines if ln.reread]
    m = next(x for x in await messages(api, sid) if x["id"] == reply)
    assert line.message_id == reply and line.variant_id == m["activeVariantId"] != f"{reply}_v1"
    assert await reread(api, sid) == [] and await checkpoint(api, sid) >= seq


async def test_an_unread_reply_regenerates_with_nothing_undone(api: Api) -> None:
    writing(api, Recorder())
    await api.set_key()
    sid = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    await command(api, sid, "send", {"text": "Hello there."})
    await api.drive(15_000)
    reply = chars(await messages(api, sid))[-1]["id"]
    _a, b = await plant_b_over_a(api, sid, reply)
    await command(api, sid, "regenerate", {"messageId": reply})
    await api.drive(15_000)
    assert await state_of(api, b) == "current" and await reread(api, sid) == []


# ── 4.2 the blocked regenerate ──
async def test_a_blocked_regenerate_keeps_older_memories(api: Api) -> None:
    writing(api, Recorder())
    sid, reply = await chat(api)
    a, b = await plant_b_over_a(api, sid, reply)

    class Block:
        async def check(self, ctx: TurnContext, text_: str) -> GuardrailResult:
            return GuardrailResult("block", [{"name": "sfw", "verdict": "block", "p": 0.99}])

    api.rt.ai.override("guardrail", Block())
    await command(api, sid, "regenerate", {"messageId": reply})
    await api.drive(15_000)
    m = next(x for x in await messages(api, sid) if x["id"] == reply)
    assert any(v.get("status") == "error" or m["status"] == "error" for v in (m.get("variants") or [m]))
    assert await state_of(api, b) == "gone" and await state_of(api, a) == "current"


async def test_a_blocked_new_reply_undoes_only_what_it_sourced(api: Api) -> None:
    planted: list[tuple[str, str]] = []

    class BlockAndPlant:
        async def check(self, ctx: TurnContext, text_: str) -> GuardrailResult:
            if ctx.message_id and not planted:
                planted.append(await plant_b_over_a(api, ctx.session.session_id, ctx.message_id))
            return GuardrailResult("block", [{"name": "sfw", "verdict": "block", "p": 0.99}])

    writing(api, Recorder())
    await api.set_key()
    api.rt.ai.override("guardrail", BlockAndPlant())
    sid = (await create(api, "one_on_one", [AMARA]))["session"]["id"]
    await api.drive(6000)
    await command(api, sid, "send", {"text": "Tell me something."})
    await api.drive(15_000)
    [(a, b)] = planted
    assert await state_of(api, b) == "gone" and await state_of(api, a) == "current"


# ── 4.3 Forget clears the stored rewrites ──
async def test_forget_clears_the_characters_stored_rewrites_in_the_world(api: Api) -> None:
    writing(api, Recorder())
    sid, reply = await chat(api)
    user = next(m for m in await messages(api, sid) if m["author"]["type"] == "user")
    assert await store_rewrite(api.rt, user["id"], AMARA, "exam sleep tips")
    assert await store_rewrite(api.rt, user["id"], "chr_seedMei", "kept for Mei")
    a, _b = await plant_b_over_a(api, sid, reply)
    assert (await api.client.delete(f"{API}/memory/{a}")).status_code == 204
    assert await stored_rewrite(api.rt, user["id"], AMARA) is None
    assert await stored_rewrite(api.rt, user["id"], "chr_seedMei") == "kept for Mei"


async def test_the_undo_clears_the_stored_rewrites_too(api: Api) -> None:
    writing(api, Recorder())
    sid, reply = await chat(api)
    user = next(m for m in await messages(api, sid) if m["author"]["type"] == "user")
    await plant_b_over_a(api, sid, reply)
    assert await store_rewrite(api.rt, user["id"], AMARA, "exam sleep tips")
    await command(api, sid, "regenerate", {"messageId": reply})
    await api.drive(15_000)
    assert await stored_rewrite(api.rt, user["id"], AMARA) is None


async def test_a_regenerate_after_a_forget_makes_a_new_rewrite_call(api: Api) -> None:
    sid = await agent(api, "one_on_one", [AMARA])
    gate(api, AMARA, 0.8)
    nouls(api, standalone=0.06)
    await send(api, sid, "How much worse is fatigue after long shift blocks?")
    [reply] = await send(api, sid, "and nights?")
    n = len(chats(api, "query_rewrite"))
    [mem] = await api.rt.memory.apply(AMARA, MERIDIAN, [Insert(MemoryDraft("fact", "Kai works nights.", 0.5))])
    assert (await api.client.delete(f"{API}/memory/{mem}")).status_code == 204
    await command(api, sid, "regenerate", {"messageId": reply["id"]})
    await api.drive(15_000)
    assert len(chats(api, "query_rewrite")) == n + 1


# ── 4.4 the undo storms ──
async def test_a_regenerate_during_a_run_is_dropped_by_the_variant_check_and_read_again(api: Api) -> None:
    w = Recorder()
    writing(api, w)
    sid, reply = await chat(api)
    # one more exchange, so the next run reads lines after the reply
    await command(api, sid, "send", {"text": "Also, my sister is a nurse."})
    await api.drive(15_000)
    held = Recorder(hold=True)
    held.ops = {AMARA: [Insert(MemoryDraft("fact", "From the old variant.", 0.5, source_session_id=sid,
                                           source_message_id=reply, source_variant_id=f"{reply}_v1",
                                           source_mode="one_on_one"))]}
    api.rt.ai.override("memory_writer", held)
    api.rt.memory_runs.request(sid)
    await asyncio.wait_for(held.entered.wait(), 5)
    await command(api, sid, "regenerate", {"messageId": reply})   # the undo runs before it streams, without the lock
    await api.drive(15_000)
    held.release.set()
    await api.rt.memory_runs.drain()
    async with api.rt.db.read() as conn:
        n = (await conn.execute(text("SELECT count(*) FROM memory_items WHERE text = 'From the old variant.'"))
             ).scalar_one()
    assert n == 0 and reply in await reread(api, sid)
    await after_storm(api, sid)


async def test_a_regenerate_storm_during_a_held_run(api: Api) -> None:
    w = Recorder()
    writing(api, w)
    sid, reply = await chat(api)
    await plant_b_over_a(api, sid, reply)
    await command(api, sid, "send", {"text": "One more line."})
    await api.drive(15_000)
    held = Recorder(hold=True)
    api.rt.ai.override("memory_writer", held)
    api.rt.memory_runs.request(sid)
    await asyncio.wait_for(held.entered.wait(), 5)
    from horizon.services.memory.undo import undo_read

    for _ in range(10):   # the undo's transaction, cut at random points
        task = asyncio.ensure_future(undo_read(api.rt, sid, reply))
        await storm(task)
        await after_storm(api, sid)
    held.release.set()
    await api.rt.memory_runs.drain()
    await after_storm(api, sid)


async def test_forget_during_a_run_commits_the_rest_and_a_never_comes_back(api: Api) -> None:
    w = Recorder()
    writing(api, w)
    sid, _reply = await chat(api)
    [a] = await api.rt.memory.apply(AMARA, MERIDIAN, [Insert(MemoryDraft("fact", "Kai's sister is a nurse.", 0.6))])
    await command(api, sid, "send", {"text": "My sister works nights in Ipoh."})
    await api.drive(15_000)
    msg = chars(await messages(api, sid))[-1]
    held = Recorder(hold=True)
    held.ops = {AMARA: [
        Supersede([a], MemoryDraft("fact", "Kai's sister is a nurse in Ipoh, on nights.", 0.6, source_session_id=sid,
                                   source_message_id=msg["id"], source_mode="one_on_one")),
        Insert(MemoryDraft("event", "Kai mentioned his sister's night shifts.", 0.5, source_session_id=sid,
                           source_message_id=msg["id"], source_mode="one_on_one"))]}
    api.rt.ai.override("memory_writer", held)
    api.rt.memory_runs.request(sid)
    await asyncio.wait_for(held.entered.wait(), 5)
    forget = asyncio.ensure_future(api.client.delete(f"{API}/memory/{a}"))
    for _ in range(50):
        await asyncio.sleep(0)
    assert not forget.done()          # Forget takes the character's lock: it waits for the run's commit (D10)
    held.release.set()
    await api.rt.memory_runs.drain()
    assert (await forget).status_code == 204
    async with api.rt.db.read() as conn:
        texts = set((await conn.execute(text("SELECT text FROM memory_items WHERE character_id = :c AND is_seed = 0"),
                                        {"c": AMARA})).scalars())
    assert "Kai's sister is a nurse." not in texts and "Kai's sister is a nurse in Ipoh, on nights." not in texts
    assert "Kai mentioned his sister's night shifts." in texts
    await after_storm(api, sid)

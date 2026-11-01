"""Memory pause runs (memory design D7–D11; long-term-memory "Memories are written when a session pauses" and its
neighbours; session-runtime "Daily cap pauses live sessions"; budget-caps "Memory work counts against the cap but never
pauses"; event-streams "A session stream left empty is noticed")."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from sqlalchemy import text

from horizon.ai.llm import llm_request
from horizon.events.bus import GLOBAL
from horizon.gateway.context import call_ctx
from horizon.gateway.errors import ProviderError
from horizon.gateway.pipeline import RecordResult
from horizon.services.memory.stretch import Msg, build_stretch
from tests.conftest import Api
from tests.jobs.kit import cancel_overlay_jobs
from tests.sessions.kit import API, chars, command, create, ledger, messages, snapshot


def _drain(sub: Any) -> list[dict[str, Any]]:
    out = []
    while not sub.queue.empty():
        x = sub.queue.get_nowait()
        if isinstance(x, dict):
            out.append(x)
    return out


# ── 2.9 the cap ──
async def test_a_refused_memory_call_pauses_nothing_and_a_refused_reply_still_does(api: Api) -> None:
    await api.set_key()
    await cancel_overlay_jobs(api)
    sid = (await create(api, "one_on_one", ["chr_seedAmara"]))["session"]["id"]
    await api.drive(6000)
    spent = (await api.json(f"{API}/settings"))["spentTodayUsd"]
    cap = spent + 0.000001   # any call's estimate is over what is left
    assert (await api.client.patch(f"{API}/settings", json={"budget": {"dailyCapUsd": cap}})).status_code == 200
    rt = api.rt
    req = llm_request(rt.runtime_cfg.runtime.llm("memory"), rt.prices.chat.model,
                      [{"role": "system", "content": "x"}, {"role": "user", "content": "y"}], max_tokens=200)
    sub = rt.bus.subscribe(GLOBAL)
    ctx = call_ctx("memory", world_id="wld_seedMeridian", session_id=sid, pauses_sessions=False)
    with pytest.raises(ProviderError) as e:
        await rt.gateway.chat_complete(req, ctx)
    assert e.value.code == "daily_budget_exceeded"
    await api.drive(2000)
    # pass 2 J1-02: the event says nothing paused, so the dialog doesn't claim it
    assert [g["paused"] for g in _drain(sub) if g["type"] == "budget.reached"] == [False]
    assert (await snapshot(api, sid))["session"]["status"] == "active"
    # the control: the same refusal for a reply pauses the live session (session-runtime, unchanged)
    with pytest.raises(ProviderError):
        await rt.gateway.chat_complete(req, call_ctx("reply", world_id="wld_seedMeridian", session_id=sid))
    await api.drive(2000)
    assert [g["paused"] for g in _drain(sub) if g["type"] == "budget.reached"] == [True]
    assert (await snapshot(api, sid))["session"]["pausedReason"] == "daily_budget"


async def test_a_memory_call_crossing_the_cap_pauses_nothing(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    manager = api.rt.sessions
    paused: list[bool] = []
    monkeypatch.setattr(manager, "pause_all_for_cap", lambda: paused.append(True))
    cap = api.rt.caps().daily_cap_usd
    crossing = RecordResult(row_id="use_x", spent_before=cap - 0.001, spent_after=cap + 0.001)
    manager.on_spend(call_ctx("memory", world_id="wld_seedMeridian", pauses_sessions=False), crossing)
    manager.on_spend(call_ctx("importance", world_id="wld_seedMeridian", pauses_sessions=False), crossing)
    assert paused == []
    manager.on_spend(call_ctx("reply", world_id="wld_seedMeridian"), crossing)
    assert paused == [True]


# ── 2.6 the stretch (pure) ──

NAMES = {"chr_a": "Amara", "chr_k": "Kai"}


def _m(seq: int, author: str, text: str = "", *, kind: str = "chat", status: str = "complete", cid: str | None = None,
       phase: str | None = None) -> Msg:
    return Msg(id=f"msg_{seq:03d}", seq=seq, author_type=author, character_id=cid or ("chr_a" if author == "character"
                                                                                   else None),
               kind=kind, content=text or f"line {seq}", status=status, variant_id=f"msg_{seq:03d}_v1", phase=phase)


def _build(msgs: list[Msg], *, from_seq: int = 0, mode: str = "one_on_one", reread: list[str] | None = None,
           piece_tokens: int = 8000) -> tuple[list[Any], int]:
    return build_stretch(session_id="ses_a", world_id="wld_a", world_name="Meridian", user_name="Kai", mode=mode,
                         header="", msgs=msgs, from_seq=from_seq, reread_ids=reread or [], present=[], names=NAMES,
                         piece_tokens=piece_tokens)


def test_a_user_line_during_a_stream_stops_the_bound_before_the_streaming_reply() -> None:
    msgs = [_m(1, "user"), _m(2, "character"), _m(3, "user"), _m(4, "character", status="streaming"), _m(5, "user")]
    pieces, upto = _build(msgs)
    assert upto == 3
    assert [ln.seq for ln in pieces[0].lines] == [1, 2, 3] and pieces[0].upto_seq == 3


def test_notes_directions_and_failed_replies_are_not_heard() -> None:
    msgs = [_m(1, "user", "Set the scene in the rain.", kind="direction"), _m(2, "system", kind="system_note"),
            _m(3, "character", status="interrupted"), _m(4, "character", status="error"), _m(5, "user", "hi"),
            _m(6, "character", "hello"), _m(7, "host", kind="narration")]
    pieces, _ = _build(msgs, mode="watch")
    assert [ln.seq for ln in pieces[0].lines] == [5, 6]
    assert "rain" not in " ".join(ln.text for ln in pieces[0].lines)


def test_debate_moderator_lines_and_phases_are_labelled() -> None:
    msgs = [_m(1, "character", "Shorter weeks help.", phase="opening"), _m(2, "user", "Evidence?", kind="steer"),
            _m(3, "user", "Time!", kind="interject"), _m(4, "character", "Yes.", cid="chr_k", phase="rebuttal")]
    pieces, _ = _build(msgs, mode="debate")
    assert [ln.speaker for ln in pieces[0].lines] == ["Amara (opening)", "Moderator (the user)", "Moderator (the user)",
                                                      "Kai (rebuttal)"]


def test_a_long_stretch_runs_in_pieces_each_with_its_own_checkpoint() -> None:
    long_text = "word " * 1500          # ≈ 2,500 tokens a line by bytes / 3
    msgs = [_m(i, "user" if i % 2 else "character", long_text) for i in range(1, 9)]
    pieces, upto = _build(msgs, piece_tokens=8000)
    assert len(pieces) == 3 and upto == 8
    assert [(p.from_seq, p.upto_seq) for p in pieces] == [(0, 3), (3, 6), (6, 8)]
    assert len(pieces[1].context) == 3   # the kept lines before the piece, at most 6


def test_below_the_minimum_nothing_moves() -> None:
    pieces, upto = _build([_m(1, "character"), _m(2, "character")], mode="watch")
    assert pieces == [] and upto == 2
    pieces, _ = _build([_m(i, "character") for i in range(1, 5)], mode="watch")
    assert len(pieces) == 1   # 4 character lines are enough


def test_a_reread_rides_the_first_piece_with_its_two_earlier_lines() -> None:
    msgs = [_m(i, "user" if i % 2 else "character") for i in range(1, 11)]
    pieces, _ = _build(msgs, from_seq=8, reread=["msg_004"])
    first = pieces[0]
    assert [(ln.seq, ln.reread) for ln in first.lines] == [(4, True), (9, False), (10, False)]
    assert first.reread_context["msg_004"] == ["Amara: line 2", "Kai: line 3"]


# ── 2.3 the scheduler ──
async def _turns(n: int = 30) -> None:
    for _ in range(n):
        await asyncio.sleep(0)


async def test_runs_go_two_at_a_time_and_high_priority_first(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    runs = api.rt.memory_runs
    gates: dict[str, asyncio.Event] = {}
    started: list[str] = []

    async def fake_go(sid: str) -> None:
        started.append(sid)
        gates.setdefault(sid, asyncio.Event())
        await gates[sid].wait()

    monkeypatch.setattr(runs, "_go", fake_go)
    for sid in ("ses_1", "ses_2", "ses_3"):
        runs.request(sid)
    runs.request("ses_4", high=True)
    await _turns()
    assert started == ["ses_1", "ses_2"]
    runs.request("ses_1")                      # during its run: one more afterwards
    runs.request("ses_1")
    gates["ses_1"].set()
    await _turns()
    assert started == ["ses_1", "ses_2", "ses_4"]   # high before the queued normal one
    gates["ses_2"].set()
    await _turns()
    gates["ses_4"].set()
    await _turns()
    assert started[3:] == ["ses_3", "ses_1"]          # then the normal queue, then ses_1's one rerun
    for g in gates.values():
        g.set()
    gates.setdefault("ses_1", asyncio.Event()).set()
    await runs.drain()
    assert started.count("ses_1") == 2


# ── 2.1 the stream-left grace ──
async def test_the_last_stream_subscriber_leaving_starts_the_grace(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    from horizon.events.bus import session_channel

    runs = api.rt.memory_runs
    asked: list[str] = []
    monkeypatch.setattr(runs, "request", lambda sid, **k: asked.append(sid))
    bus, ch = api.rt.bus, session_channel("ses_x")
    a, b = bus.subscribe(ch), bus.subscribe(ch)
    bus.unsubscribe(a)
    await api.drive(31_000)
    assert asked == []                          # one tab still open
    bus.unsubscribe(b)
    await api.drive(5_000)
    c = bus.subscribe(ch)                       # a reload at 5 s cancels the grace
    await api.drive(40_000)
    assert asked == []
    bus.unsubscribe(c)
    await api.drive(31_000)
    assert asked == ["ses_x"]


# ── 2.4, 2.5 the triggers and the start checks ──
async def _chat(api: Api, n: int = 2) -> str:
    sid = (await create(api, "one_on_one", ["chr_seedAmara"]))["session"]["id"]
    await api.drive(6000)
    for i in range(n):
        await command(api, sid, "send", {"text": f"Tell me something about sleep, part {i}."})
        await api.drive(15_000)
    return str(sid)


async def _seq(api: Api, sid: str) -> tuple[int, int]:
    async with api.rt.db.read() as conn:
        row = (await conn.execute(text("SELECT memory_seq, (SELECT MAX(seq) FROM messages WHERE session_id = :s) "
                                       "FROM sessions WHERE id = :s"), {"s": sid})).one()
    return int(row[0]), int(row[1] or 0)


class StubWriter:
    """Records each stretch; returns no ops (or fails / refuses, when told)."""

    def __init__(self, *, fail: int = 0, refuse: bool = False) -> None:
        self.seen: list[Any] = []
        self.fail = fail
        self.refuse = refuse

    async def on_stretch(self, stretch: Any, ctx: Any) -> Any:
        from horizon.services.memory.stretch import WriterResult

        self.seen.append(stretch)
        assert ctx.call("memory").pauses_sessions is False
        if self.refuse:
            raise ProviderError("daily_budget_exceeded")
        if self.fail:
            self.fail -= 1
            return WriterResult(failed=True)
        return WriterResult()


def _writing(api: Api, writer: Any) -> None:
    from horizon.ai.profile import ProfileSpec

    api.rt.set_profile(ProfileSpec(profile="naive", test_mode=True))
    api.rt.ai.override("memory_writer", writer)


async def test_ten_replies_in_an_open_session_make_no_memory_call(api: Api) -> None:
    await api.set_key()
    writer = StubWriter()
    _writing(api, writer)
    await _chat(api, n=3)
    await api.rt.memory_runs.drain()
    assert writer.seen == []
    assert [r for r in await ledger(api) if r["purpose"] in ("memory", "importance", "memory_guard")] == []


async def test_leave_runs_once_over_the_settled_lines(api: Api) -> None:
    await api.set_key()
    writer = StubWriter()
    _writing(api, writer)
    sid = await _chat(api)
    assert (await api.post(f"{API}/sessions/{sid}/leave", {})).status_code in (200, 202, 204)
    await api.drive(2000)
    await api.rt.memory_runs.drain()
    assert len(writer.seen) == 1
    seq, top = await _seq(api, sid)
    assert seq == top and writer.seen[0].upto_seq == top


async def test_end_requests_a_run(api: Api) -> None:
    await api.set_key()
    writer = StubWriter()
    _writing(api, writer)
    sid = await _chat(api)
    assert (await api.post(f"{API}/sessions/{sid}/end", {})).status_code in (200, 202, 204)
    await api.drive(2000)
    await api.rt.memory_runs.drain()
    assert len(writer.seen) == 1


def test_the_turn_cap_and_a_debates_end_request_runs(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    runs = api.rt.memory_runs
    asked: list[str] = []
    monkeypatch.setattr(runs, "request", lambda sid, **k: asked.append(k.get("reason", "")))
    runs.on_events("ses_w", [{"type": "session.paused", "payload": {"reason": "turn_cap"}}])
    runs.on_events("ses_d", [{"type": "session.state", "payload": {"status": "ended", "state": {}}}])
    runs.on_events("ses_p", [{"type": "session.paused", "payload": {"reason": "user"}}])   # a user pause: no
    assert asked == ["turn_cap", "ended"]


async def test_a_new_session_with_a_shared_character_runs_the_old_one_first(api: Api) -> None:
    await api.set_key()
    writer = StubWriter()
    _writing(api, writer)
    old = await _chat(api)
    runs = api.rt.memory_runs
    high: list[str] = []
    real = runs.request
    runs.request = lambda sid, **k: (high.append(sid) if k.get("high") else None, real(sid, **k))[1]   # type: ignore[method-assign]
    await create(api, "group", ["chr_seedAmara", "chr_seedMei"])
    await api.drive(3000)
    await runs.drain()
    assert old in high and len(writer.seen) >= 1 and writer.seen[0].session_id == old


async def test_the_start_up_sweep_and_seed_sessions(api: Api) -> None:
    await api.set_key()
    writer = StubWriter()
    _writing(api, writer)
    sid = await _chat(api)
    await api.rt.memory_runs.sweep()
    await api.rt.memory_runs.drain()
    assert [s.session_id for s in writer.seen] == [sid]           # seed sessions never run
    seq, top = await _seq(api, sid)
    assert seq == top


async def test_scripted_advances_with_no_call_and_no_key_defers(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    await api.set_key()
    sid = await _chat(api)            # the test profile is explicitly scripted: no call, whatever the key
    await api.post(f"{API}/sessions/{sid}/leave", {})
    await api.drive(2000)
    await api.rt.memory_runs.drain()
    seq, top = await _seq(api, sid)
    assert seq == top                                             # advanced, nothing called
    from horizon.ai.profile import ProfileSpec

    api.rt.set_profile(ProfileSpec(profile="naive", test_mode=True))
    sid2 = await _chat(api)
    monkeypatch.setattr(api.rt.keys, "status", lambda: "missing")   # the key goes: the naive profile defers
    await api.post(f"{API}/sessions/{sid2}/end", {})
    await api.drive(2000)
    await api.rt.memory_runs.drain()
    seq2, top2 = await _seq(api, sid2)
    assert seq2 == 0 and top2 > 0
    assert api.rt.memory_runs.log[-1]["outcome"] == "deferred"


# ── 2.8 failures ──
async def test_three_failed_tries_skip_the_piece_and_a_refusal_is_not_a_try(api: Api) -> None:
    await api.set_key()
    writer = StubWriter(refuse=True)
    _writing(api, writer)
    sid = await _chat(api)
    runs = api.rt.memory_runs
    runs.request(sid)
    await runs.drain()
    async with api.rt.db.read() as conn:
        tries = (await conn.execute(text("SELECT memory_tries FROM sessions WHERE id = :s"), {"s": sid})).scalar_one()
    assert tries == 0 and runs.log[-1]["outcome"] == "refused at the cap"
    writer.refuse, writer.fail = False, 3
    for expected in (1, 2):
        runs.request(sid)
        await runs.drain()
        async with api.rt.db.read() as conn:
            tries = (await conn.execute(text("SELECT memory_tries FROM sessions WHERE id = :s"), {"s": sid})).scalar_one()
        assert tries == expected and (await _seq(api, sid))[0] == 0
    runs.request(sid)
    await runs.drain()
    seq, top = await _seq(api, sid)
    assert seq == top and runs.log[-1]["outcome"] == "skipped"


async def test_a_failed_commit_retries_once_without_a_second_call(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    await api.set_key()
    writer = StubWriter()
    _writing(api, writer)
    sid = await _chat(api)
    store = api.rt.memory
    real = store.apply_run
    calls = {"n": 0}

    async def flaky(*a: Any, **k: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("disk hiccup")
        return await real(*a, **k)

    monkeypatch.setattr(store, "apply_run", flaky)
    api.rt.memory_runs.request(sid)
    await api.rt.memory_runs.drain()
    assert calls["n"] == 2 and len(writer.seen) == 1
    seq, top = await _seq(api, sid)
    assert seq == top


# ── 2.7 apply_run ──
def _draft(text_: str, **k: Any) -> Any:
    from horizon.ai.ports import MemoryDraft

    return MemoryDraft(kind="fact", text=text_, importance=0.6, **k)


async def test_two_runs_from_one_checkpoint_only_one_commits(api: Api) -> None:
    from horizon.ai.ports import Insert
    from horizon.services.memory.store import LostRace

    await api.set_key()
    sid = await _chat(api)
    _, top = await _seq(api, sid)
    store = api.rt.memory
    ops = {"chr_seedAmara": [Insert(_draft("Kai asked about sleep twice."))]}
    first = await store.apply_run("wld_seedMeridian", ops, session_id=sid, from_seq=0, upto_seq=top)
    assert first.changed == ["chr_seedAmara"]
    with pytest.raises(LostRace):
        await store.apply_run("wld_seedMeridian", ops, session_id=sid, from_seq=0, upto_seq=top)
    async with api.rt.db.read() as conn:
        n = (await conn.execute(text("SELECT count(*) FROM memory_items WHERE text = 'Kai asked about sleep twice.'")))
    assert n.scalar_one() == 1


async def test_a_forgotten_target_is_dropped_and_the_rest_commits(api: Api) -> None:
    from horizon.ai.ports import Insert, Reinforce, Supersede
    from horizon.services.memory.forget import forget

    await api.set_key()
    sid = await _chat(api)
    _, top = await _seq(api, sid)
    store = api.rt.memory
    [a] = await store.apply("chr_seedAmara", "wld_seedMeridian", [Insert(_draft("Kai's sister Mia works nights."))])
    await forget(api.rt, a)                                      # the user forgets A while the run is out
    ops = {"chr_seedAmara": [Supersede([a], _draft("Kai's sister Mia works nights in Ipoh.")), Reinforce(a, 0.9),
                             Insert(_draft("Kai is learning to swim."))]}
    res = await store.apply_run("wld_seedMeridian", ops, session_id=sid, from_seq=0, upto_seq=top)
    assert {d["why"] for d in res.dropped} == {"target forgotten"} and len(res.dropped) == 2
    texts = [m["text"] for m in (await api.client.get(f"{API}/characters/chr_seedAmara/memory")).json()]
    assert "Kai is learning to swim." in texts and not any("Mia" in x for x in texts)
    assert (await _seq(api, sid))[0] == top


async def test_a_draft_from_a_replaced_variant_is_dropped(api: Api) -> None:
    from horizon.ai.ports import Insert

    await api.set_key()
    sid = await _chat(api)
    _, top = await _seq(api, sid)
    reply = chars(await messages(api, sid))[-1]
    async with api.rt.db.write() as tx:   # a regenerate during the run made another variant active
        await tx.conn.execute(text("UPDATE messages SET active_variant_id = :v WHERE id = :m"),
                              {"v": f"{reply['id']}_v2", "m": reply["id"]})
    ops = {"chr_seedAmara": [Insert(_draft("From the old variant.", source_message_id=reply["id"],
                                           source_variant_id=f"{reply['id']}_v1")),
                             Insert(_draft("From the user's line."))]}
    res = await api.rt.memory.apply_run("wld_seedMeridian", ops, session_id=sid, from_seq=0, upto_seq=top)
    assert [d["why"] for d in res.dropped] == ["source variant replaced"] and len(res.created["chr_seedAmara"]) == 1


async def test_runs_sharing_characters_take_their_locks_in_one_order(api: Api) -> None:
    store = api.rt.memory
    order: list[str] = []

    async def hold(name: str, ids: list[str]) -> None:
        async with store.run_locks(ids):
            order.append(f"{name} in")
            await asyncio.sleep(0.01)
            order.append(f"{name} out")

    await asyncio.wait_for(asyncio.gather(hold("one", ["chr_b", "chr_a"]), hold("two", ["chr_a", "chr_b"])), 5)
    assert order == ["one in", "one out", "two in", "two out"]   # serialised, and no deadlock


async def test_the_idle_release_requests_a_run(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    await api.set_key()
    sid = await _chat(api)
    runs = api.rt.memory_runs
    asked: list[str] = []
    monkeypatch.setattr(runs, "request", lambda s, **k: asked.append(k.get("reason", "")))
    await api.drive(api.rt.runtime_cfg.runtime.idle_release_ms + 5000)
    assert "idle release" in asked and api.rt.sessions.peek(sid) is None


def test_a_kept_turn_is_read_again_when_it_ends(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    runs = api.rt.memory_runs
    asked: list[str] = []
    runs._after_turn.add("ses_k")             # a leave or end arrived while this session's reply streamed
    monkeypatch.setattr(runs, "request", lambda s, **k: asked.append(k.get("reason", "")))
    runs.on_events("ses_k", [{"type": "token", "payload": {}}])
    assert asked == []
    runs.on_events("ses_k", [{"type": "turn.end", "payload": {"status": "complete"}}])
    runs.on_events("ses_k", [{"type": "turn.end", "payload": {"status": "complete"}}])   # only once
    assert asked == ["kept turn ended"]

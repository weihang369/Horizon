"""Session lifecycle (session-lifecycle spec; design D8, D14): create, rename, leave, end, delete.

`create` ports the MockClient's `createSession`: cast validation, the per-mode defaults, one transaction for the rows,
then the opening `session.state` and one `energy` per participant through the new session's actor, then the greeting,
the debate start or the watch premise through its queue. Delete stops the actor first, deletes in one transaction, then
queues the AI purge and announces the change.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, select, update

from horizon.api.errors import HorizonHTTPError, not_found, validation
from horizon.contract import mappers as mp
from horizon.db import tables as t
from horizon.domain.ids import new_id
from horizon.events.bus import GLOBAL
from horizon.services.memory.refs import refs_from_trace
from horizon.sessions.context import characters, energy_of
from horizon.sessions.modes import debate, one_on_one, watch
from horizon.sessions.modes.common import message_event, note
from horizon.sessions.preconditions import check_generating, check_no_other_live

if TYPE_CHECKING:
    from horizon.runtime import Runtime
    from horizon.sessions.actor import SessionActor

Wire = dict[str, Any]
DEFAULT_RUBRIC = [{"id": "evidence", "label": "Evidence"}, {"id": "rebuttal", "label": "Rebuttal"},
                  {"id": "clarity", "label": "Clarity"}, {"id": "persuasion", "label": "Persuasion"}]


def _first(name: str) -> str:
    for w in name.split(" "):
        if not re.match(r"^(dr|prof)\.?$", w, flags=re.IGNORECASE):
            return w
    return name


def default_title(mode: str, cast: list[Any], config: Wire | None) -> str:
    names = [_first(str(c["profile"].get("name", c["id"]))) for c in cast]
    if mode == "one_on_one":
        return f"Chat with {names[0]}"
    if mode == "group":
        return ", ".join(names)
    if mode == "debate":
        motion = (config or {}).get("motion")
        if motion is None:
            return "Debate: Untitled"
        return f"Debate: {re.sub(r'^this house (would|believes)\s*', '', str(motion), flags=re.IGNORECASE)[:48]}"
    premise = (config or {}).get("premise")
    return re.split(r"[.!?]", str(premise))[0][:40] if premise is not None else "Scene"


async def create(rt: Runtime, body: Wire) -> Wire:
    """`POST /sessions`: validate, write the rows, open the session through its actor. Returns the snapshot."""
    manager = rt.sessions
    async with manager.lock_create:
        await check_generating(manager, rt.keys.status())
        mode = str(body["mode"])
        ids = list(body["characterIds"])
        async with rt.db.read() as conn:
            w = (await conn.execute(select(t.worlds).where(t.worlds.c.id == body["worldId"]))).mappings().first()
        if w is None:
            raise not_found("World")
        rows = await characters(rt, ids)
        cast = []
        for cid in ids:
            row = rows.get(cid)
            if row is None or row["deleted_at"] is not None:
                raise not_found("Character")
            cast.append(row)
        if any(c["world_id"] != w["id"] for c in cast):
            raise not_found("Character")  # NFR-23: never "exists elsewhere"
        if any(c["status"] != "approved" for c in cast):
            raise validation("Drafts and archived characters can't join sessions.")
        lo, hi = (1, 1) if mode == "one_on_one" else (2, 5)
        if not lo <= len(cast) <= hi:
            raise validation(f"This mode needs {lo}–{hi} characters.",
                             {"field": "characterIds", "min": lo, "max": hi, "got": len(cast)})
        check_no_other_live(manager, None)
        session = _new_session(rt, body, w, cast)
        cfg_def = {"group": "GroupConfig", "debate": "DebateConfig", "watch": "WatchConfig"}.get(mode)
        if cfg_def is not None:
            problems = rt.schema.errors(cfg_def, session["config"])
            if problems:
                raise validation(f"Invalid {mode} config.", {"field": "config", "problems": problems[:3]})
        now = session["createdAt"]
        srow, prows = mp.session_rows(session, is_seed=False)
        async with rt.db.write() as tx:
            await tx.conn.execute(t.sessions.insert().values(**srow))
            await tx.conn.execute(t.participants.insert(), prows)
            await tx.conn.execute(update(t.worlds).where(t.worlds.c.id == w["id"]).values(last_active_at=now))
            tx.publish(GLOBAL, {"type": "entity.changed", "kind": "world", "id": w["id"], "worldId": w["id"]})
        actor = await manager.get(session["id"])

        async def open_session() -> None:
            st = session.get("state")
            opening: list[Wire] = [{"type": "session.state", "payload": {
                "status": "active", **({"state": st} if st else {}), "participants": session["participants"]}}]
            for c in cast:
                e = energy_of(rt, c)
                opening.append({"type": "energy", "payload": {"characterId": c["id"], "current": e["current"],
                                                              "max": e["max"], "state": e["state"]}})
            if body.get("seedSummary"):
                opening.append(message_event(note(actor, str(body["seedSummary"]), "summary")))
            await actor.emit(*opening)
            if mode == "one_on_one":
                one_on_one.greet(actor)
            elif mode == "debate":
                debate.start(actor)
            elif mode == "watch":
                watch.start(actor)

        await actor.submit(open_session)
        return await snapshot(rt, session["id"])


def _new_session(rt: Runtime, body: Wire, w: Any, cast: list[Any]) -> Wire:
    s = rt.settings_doc()
    chat = s.get("chat", {})
    mode = str(body["mode"])
    cfg_in: Wire = dict(body.get("config") or {})
    config: Wire | None = None
    state: Wire | None = None
    music = body.get("musicPolicy") or "character_theme"
    if mode == "group":
        config = {"responderPolicy": chat.get("responderDefault", "auto"), "maxAutoResponders": 2, **cfg_in}
        music = body.get("musicPolicy") or "follow_speaker"
    elif mode == "debate":
        preset = cfg_in.get("roundsPreset") or "standard"
        sides = cfg_in.get("sides")
        if sides is None and body.get("sides"):
            sides = {"prop": [c["id"] for c in cast if body["sides"].get(c["id"]) == "prop"],
                     "opp": [c["id"] for c in cast if body["sides"].get(c["id"]) == "opp"]}
        fmt = cfg_in.get("format") or "two_sided"
        verdict_by = "arbiter" if fmt == "panel" and cfg_in.get("verdictBy") == "user" else cfg_in.get("verdictBy") or "arbiter"
        config = {"motion": cfg_in.get("motion") or "This house would adopt a four-day work week", "format": fmt,
                  **({"sides": sides} if sides else {}), "roundsPreset": preset,
                  "phases": cfg_in.get("phases") or (["opening", "closing"] if preset == "quick"
                                                     else ["opening", "rebuttal", "closing"]),
                  "turnLength": cfg_in.get("turnLength") or ("short" if len(cast) >= 5 else "medium"),
                  "moderator": cfg_in.get("moderator") or "user", "verdictBy": verdict_by,
                  "rubric": cfg_in.get("rubric") or DEFAULT_RUBRIC,
                  "autoAdvance": cfg_in["autoAdvance"] if cfg_in.get("autoAdvance") is not None
                  else bool(chat.get("debateAutoAdvance", True)),
                  "pauseMs": cfg_in.get("pauseMs") if cfg_in.get("pauseMs") is not None else 1500}
        state = {"phase": "setup", "round": 0, "iteration": 1}
        music = body.get("musicPolicy") or "arena"
    elif mode == "watch":
        config = {"premise": cfg_in.get("premise") or "An ordinary afternoon.", "maxTurns": cfg_in.get("maxTurns") or 20,
                  "paceMs": cfg_in.get("paceMs") or 1500, "openingSpeaker": cfg_in.get("openingSpeaker") or "auto"}
        state = {"status": "paused", "turnsTaken": 0, "turnLimit": config["maxTurns"]}
        music = body.get("musicPolicy") or "follow_speaker"
    two_sided = mode == "debate" and config is not None and config.get("format") == "two_sided"
    sides = (config or {}).get("sides") or {}

    def side(cid: str) -> str | None:
        if not two_sided:
            return None
        return "prop" if cid in (sides.get("prop") or []) else "opp" if cid in (sides.get("opp") or []) else None

    participants: list[Wire] = []
    for c in cast:
        p: Wire = {"characterId": c["id"], "role": "debater" if mode == "debate" else "speaker"}
        if mode == "debate":
            p["side"] = side(c["id"])  # a debater always carries `side` (null on a panel), as the stored wire does
        participants.append({**p, "currentEmotion": "neutral", "mutedByUser": False})
    title = str(body.get("title") or "").strip()
    now = rt.now_iso()
    session: Wire = {
        "id": new_id("ses"), "worldId": w["id"], "title": title or default_title(mode, cast, config),
        "titleIsCustom": bool(title), "mode": mode, "status": "active", "participants": participants,
        "emotionMode": body.get("emotionMode") or chat.get("defaultEmotionMode", "llm"), "musicPolicy": music,
        "readableMode": bool(chat.get("readableDefault", False)), "config": config, "state": state,
        **({"continuedFrom": body["continuedFrom"]} if body.get("continuedFrom") else {}),
        "isSeed": False, "costUsd": 0, "messageCount": 0, "createdAt": now, "updatedAt": now}
    return session


async def snapshot(rt: Runtime, sid: str) -> Wire:
    from horizon.services import reads

    async with rt.db.read() as conn:
        return await reads.session_snapshot(conn, sid)


# ── rename, leave, end, delete ──
async def rename(rt: Runtime, sid: str, title: str) -> Wire:
    clean = title.strip()[:80]
    if not clean:
        raise validation("Title can't be empty.", {"field": "title"})
    actor = await rt.sessions.get(sid)

    async def run() -> None:
        await actor.emit({"type": "session.state", "payload": {"settings": {"title": clean, "titleIsCustom": True}}})

    await actor.submit(run)
    s: Wire = actor.session
    return s


async def leave(rt: Runtime, sid: str) -> None:
    """Pause an active non-seed session with `navigated_away` (a reply already streaming finishes); others: nothing."""
    actor = await rt.sessions.get(sid)

    async def run() -> None:
        s = actor.session
        if s["isSeed"] or s["status"] != "active":
            return
        await actor.clear(keep_current=True)
        actor.held = True
        await actor.emit({"type": "session.paused", "payload": {"reason": "navigated_away"}})

    await actor.submit(run)


async def end(rt: Runtime, sid: str) -> None:
    actor = await rt.sessions.get(sid)

    async def run() -> None:
        s = actor.session
        if s["isSeed"]:
            raise HorizonHTTPError("conflict", "Seed sessions are replay-only.")
        if s["status"] == "ended":
            return
        await actor.clear(keep_current=True)
        await actor.emit({"type": "session.state", "payload": {"status": "ended"}})

    await actor.submit(run)


async def delete_session(rt: Runtime, sid: str) -> None:
    """Stop the running work, delete everything under the session in one commit, queue the purge, announce it.
    Ledger rows keep their amounts (`usage_records.session_id` is set NULL by the foreign key)."""
    async with rt.db.read() as conn:
        row = (await conn.execute(select(t.sessions.c.world_id).where(t.sessions.c.id == sid))).first()
    if row is None:
        raise not_found("Session")
    actor = rt.sessions.peek(sid)
    if actor is not None:
        await rt.sessions.release(sid, actor)
    await rt.gateway.drain_background()
    async with rt.db.write() as tx:
        await tx.conn.execute(delete(t.sessions).where(t.sessions.c.id == sid))
        await tx.conn.execute(t.ai_purge_queue.insert().values(scope="session", ids=[sid], created_at=rt.now_iso(),
                                                               attempts=0, done_at=None))
        tx.publish(GLOBAL, {"type": "entity.changed", "kind": "session", "id": sid, "worldId": row[0]})
    rt.purge.notify()


def actor_of(rt: Runtime, sid: str) -> SessionActor | None:
    a: SessionActor | None = rt.sessions.peek(sid)
    return a


async def fork(rt: Runtime, sid: str, at_seq: int | None) -> Wire:
    """`POST /sessions/{id}/fork`: a new live session from the source's events up to `atSeq` (design D8), written in
    one transaction; then the opening `session.state` through the new session's actor."""
    from horizon.services.runtime.reducer import ordered_messages
    from horizon.sessions.fork import fork_events

    manager = rt.sessions
    await check_generating(manager, rt.keys.status())
    async with rt.db.read() as conn:
        srow = (await conn.execute(select(t.sessions).where(t.sessions.c.id == sid))).mappings().first()
        if srow is None:
            raise not_found("Session")
        parts = (await conn.execute(select(t.participants).where(t.participants.c.session_id == sid))).mappings().all()
        erows = (await conn.execute(select(t.session_events).where(t.session_events.c.session_id == sid)
                                    .order_by(t.session_events.c.seq))).mappings().all()
    source = mp.session_wire(srow, parts)
    new_sid = new_id("ses")
    events, final = fork_events([mp.event_wire(e) for e in erows], source, at_seq, new_sid, rt.now_iso())
    session = final["session"]
    messages = ordered_messages(final)
    row, prows = mp.session_rows(session, is_seed=False)
    async with rt.db.write() as tx:
        await tx.conn.execute(t.sessions.insert().values(**row))
        await tx.conn.execute(t.participants.insert(), prows)
        if events:
            await tx.conn.execute(t.session_events.insert(), [mp.event_row(e) for e in events])
        if messages:
            await tx.conn.execute(t.messages.insert(), [mp.message_row(m) for m in messages])
        traces = [{"message_id": m["id"], "trace": m["trace"], "engine": "fork", "engine_version": None,
                   "prompt_version": None, "created_at": m["createdAt"]} for m in messages if m.get("trace")]
        if traces:
            await tx.conn.execute(t.turn_traces.insert(), traces)
            refs = [r for x in traces for r in refs_from_trace(x["message_id"], x["trace"])]
            if refs:  # M5 design D14: Forget must reach the fork's copies too
                await tx.conn.execute(t.trace_memory_refs.insert(), refs)
        cites = [r for m in messages for r in mp.citation_rows(m)]
        if cites:
            await tx.conn.execute(t.message_citations.insert(), cites)
        tx.publish(GLOBAL, {"type": "entity.changed", "kind": "session", "id": new_sid, "worldId": session["worldId"]})
    actor = await manager.get(new_sid)
    multi = session["mode"] in ("debate", "watch")
    actor.held = multi
    if session["status"] != "ended":
        if multi:
            payload: Wire = {"status": "paused", "pausedReason": "user"}
            if session["mode"] == "watch" and session.get("state"):
                payload["state"] = {**session["state"], "status": "paused"}
        else:
            payload = {"status": "active"}

        async def open_fork() -> None:
            await actor.emit({"type": "session.state", "payload": payload})

        await actor.submit(open_fork)
    return await snapshot(rt, new_sid)

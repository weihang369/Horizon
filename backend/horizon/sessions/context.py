"""Builds the frozen AI contexts from a live session (doc 05 §4): one read transaction for the cast, the world and the
latest rolling summary; messages come from the actor's reduced state (active variants only)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from horizon.ai.contexts import CharacterView, MemoryLine, MessageView, ParticipantView, SessionContext, WorldView
from horizon.ai.scripted.ports import estimate_tokens
from horizon.contract import mappers as mp
from horizon.db import tables as t
from horizon.domain.energy import read_energy
from horizon.services.runtime.reducer import ordered_messages

if TYPE_CHECKING:
    from horizon.runtime import Runtime
    from horizon.sessions.actor import SessionActor


async def _latest_summary(rt: Runtime, sid: str) -> tuple[int, str | None]:
    S = t.session_summaries.c
    async with rt.db.read() as conn:
        r = (await conn.execute(select(S.upto_seq, S.text).where(S.session_id == sid).where(S.kind == "rolling")
                                .order_by(S.upto_seq.desc(), S.id.desc()).limit(1))).first()
    return (int(r[0]), str(r[1])) if r is not None else (0, None)


def _views(msgs: list[Any], names: dict[str, Any]) -> list[MessageView]:
    return [MessageView(id=m["id"], seq=m["seq"], author_type=m["author"]["type"],
                        character_id=m["author"].get("characterId"),
                        name=str(names.get(m["author"].get("characterId") or "", "") or m["author"]["type"]),
                        kind=m["kind"], content=m["content"], emotion=m.get("emotion")) for m in msgs]


async def characters(rt: Runtime, ids: list[str]) -> dict[str, Any]:
    async with rt.db.read() as conn:
        rows = (await conn.execute(select(t.characters).where(t.characters.c.id.in_(ids)))).mappings().all()
    return {r["id"]: r for r in rows}


async def document_titles(rt: Runtime, world_id: str, ids: list[str]) -> dict[str, list[str]]:
    """M12 (rag D6): each character's searchable sources (`indexed` or `keyword_only`, the states K2 searches), titled
    without their file extension, newest first. Read-only and bound to the world; a character with none is left out."""
    from horizon.ai.embedder import strip_extension

    if not ids:
        return {}
    K = t.knowledge_sources.c
    async with rt.db.read() as conn:
        rows = (await conn.execute(select(K.character_id, K.title).where(
            K.world_id == world_id, K.character_id.in_(ids), K.status.in_(("indexed", "keyword_only")))
            .order_by(K.added_at.desc(), K.id))).all()
    out: dict[str, list[str]] = {}
    for cid, title in rows:
        out.setdefault(str(cid), []).append(strip_extension(str(title)))
    return out


def energy_of(rt: Runtime, row: Any) -> dict[str, Any]:
    p = rt.energy_params()
    return read_energy(mp.stored_energy(row), p.now_ms, frozen=p.frozen, est_reply_points=p.est_reply_points,
                       utc_offset_min=p.utc_offset_min)


async def session_context(rt: Runtime, actor: SessionActor, *, recent: int | None = None,
                          before_message: str | None = None) -> SessionContext:
    """`recent` is the history window (the messages after the latest rolling summary), or its last `recent` items.
    `before_message` (a regenerate: the message whose new variant is written) ends the history before that message,
    so the reply being replaced is never read back as already said (v1 test stage, audit 04-01)."""
    s = actor.session
    ids = [p["characterId"] for p in s["participants"]]
    chars = await characters(rt, ids)
    async with rt.db.read() as conn:
        w = (await conn.execute(select(t.worlds).where(t.worlds.c.id == s["worldId"]))).mappings().first()
    upto, summ = await _latest_summary(rt, actor.sid)
    names = {cid: (chars[cid]["profile"].get("name") if cid in chars else cid) for cid in ids}
    parts = [ParticipantView(character_id=p["characterId"], name=str(names.get(p["characterId"]) or p["characterId"]),
                             role=p["role"], side=p.get("side"), muted=bool(p.get("mutedByUser")),
                             character_role=str(chars[p["characterId"]]["profile"].get("role") or "")
                             if p["characterId"] in chars else "",
                             emotion=str(p.get("currentEmotion") or "neutral"),
                             energy=energy_of(rt, chars[p["characterId"]]) if p["characterId"] in chars else {})
             for p in s["participants"]]
    msgs = ordered_messages(actor.state)
    cut = actor.state["messages"].get(before_message) if before_message else None
    if cut is not None:
        msgs = [m for m in msgs if m["seq"] < cut["seq"]]
    views = _views([m for m in msgs if m["seq"] > upto and m["status"] != "streaming"], names)
    # docs/ai/05 X2 (persona-context D10): never more than twice the mode's window of history, for every caller
    # (turns, prefetches, the router, host and verdict); older lines are only hidden until the summary lands.
    from horizon.ai.naive.window import ceiling
    views = ceiling(views, 2 * rt.runtime_cfg.runtime.window_tokens.for_mode(s["mode"]))
    if recent is not None:
        views = views[-recent:]
    settings = rt.settings_doc()
    return SessionContext(
        session_id=actor.sid, seed=actor.seed,
        world=WorldView(id=s["worldId"], name=str(w["name"]) if w else "", you=w["you"] if w else None),
        mode=s["mode"], title=s["title"], config=s.get("config"), state=s.get("state"), participants=parts,
        recent=views, summary=summ, emotion_mode=s["emotionMode"], content_rating=str(settings.get("contentRating", "sfw")),
        period=rt.clock.pricing_period(), history_tokens=sum(estimate_tokens(m["content"]) for m in msgs))


async def speaker_view(rt: Runtime, actor: SessionActor, row: Any) -> CharacterView:
    """M13 (memory D22, D23): the speaker's view with its memory list, for `agent` replies only. The list is read the
    first time this sitting builds the character's view and frozen in `actor.memory_blocks`, so system message 1 stays
    byte-identical (and cached) across the sitting; Forget and a run's commit drop it, and the next turn reads it again."""
    view = character_view(row)
    if not agent_turns(rt):
        return view
    block, _ = await memory_block(rt, actor, str(row["id"]))
    return view.model_copy(update={"memories": list(block)})


def agent_turns(rt: Runtime) -> bool:
    return bool(rt.ai.impl("turn", key_set=rt.keys.status() == "set") == "agent")


async def memory_block(rt: Runtime, actor: SessionActor, cid: str) -> tuple[list[MemoryLine], bool]:
    """M13 (memory D22, D23): the character's frozen list for this sitting and whether it has an overflow."""
    block = actor.memory_blocks.get(cid)
    while block is None:
        from horizon.services.memory.block import memory_list

        gen = actor.memory_gen.get(cid, 0)
        async with rt.db.read() as conn:
            listed, overflow = await memory_list(conn, cid, str(actor.session["worldId"]), rt.clock.now(),
                                                 rt.runtime_cfg.runtime.memory)
        fresh = [MemoryLine(id=m.id, kind=m.kind, text=m.text) for m in listed]
        if actor.memory_gen.get(cid, 0) != gen:   # a Forget or a commit dropped it while we read: read again
            continue
        block = actor.memory_blocks[cid] = fresh
        actor.memory_overflow[cid] = overflow
    return block, bool(actor.memory_overflow.get(cid))


async def recallable(rt: Runtime, actor: SessionActor, cids: list[str]) -> list[str]:
    """M13 (memory D26): the candidates with something earlier to search: everyone when the session has indexed lines
    (up to the latest summary's bound), else those with an overflow. `agent` turns only."""
    if not cids or not agent_turns(rt):
        return []
    from horizon.services.memory.corpora import session_has_lines

    upto, _ = await _latest_summary(rt, actor.sid)
    if upto and await session_has_lines(rt, actor.sid, upto):
        return list(cids)
    out = []
    for cid in cids:
        _, overflow = await memory_block(rt, actor, cid)
        if overflow:
            out.append(cid)
    return out


async def recall_scope(rt: Runtime, actor: SessionActor, cid: str) -> dict[str, Any]:
    """M13 (memory D34): what a speaker's recall searches: the session's lines up to the latest summary's bound, and
    its overflow (every current memory not in its frozen list)."""
    upto, _ = await _latest_summary(rt, actor.sid)
    block, overflow = await memory_block(rt, actor, cid)
    return {"upto_seq": upto, "block_ids": [m.id for m in block], "has_overflow": overflow}


def character_view(row: Any) -> CharacterView:
    return CharacterView(id=row["id"], name=str(row["profile"].get("name", row["id"])), profile=dict(row["profile"]),
                         appearance_summary=str((row["appearance"] or {}).get("appearanceSummary") or ""),
                         advisory=bool(row["advisory"]))


def reply_cap(rt: Any, sctx: SessionContext, plan: Any = None) -> int:
    """The reply's `max_tokens`, chosen AFTER retrieval and the turn plan (docs/ai/03 C4; session-runtime "The reply
    cap is chosen after the plan"; design D14). A plan that made the turn deep raises a 1:1 cap; with no plan (M7:
    `naive` has no Jev call 1) the turn is quick. Debate takes the session's turn length."""
    caps = rt.runtime_cfg.runtime.reply_max_tokens
    cfg = sctx.config or {}
    deep = bool(getattr(plan, "deep", False))
    return int(caps.for_mode(sctx.mode, str(cfg.get("turnLength")) if sctx.mode == "debate" else None, deep=deep))

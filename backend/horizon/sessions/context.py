"""Builds the frozen AI contexts from a live session (doc 05 §4): one read transaction for the cast, the world and the
latest rolling summary; messages come from the actor's reduced state (active variants only)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from horizon.ai.contexts import CharacterView, MessageView, ParticipantView, SessionContext, WorldView
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


async def maintain_window(rt: Runtime, actor: SessionActor) -> None:
    """The history window (design D11): past `windowTokens`, drop the oldest half in one step and store a refreshed
    rolling summary at that boundary (a session row, written under the actor's write lock)."""
    from horizon.ai.naive.window import plan_window, summary_lines

    upto, previous = await _latest_summary(rt, actor.sid)
    msgs = [m for m in ordered_messages(actor.state) if m["status"] != "streaming"]
    ids = sorted({m["author"].get("characterId") for m in msgs if m["author"].get("characterId")})
    names = {cid: r["profile"].get("name", cid) for cid, r in (await characters(rt, ids)).items()}
    plan = plan_window(_views(msgs, names), upto, rt.runtime_cfg.runtime.window_tokens)
    if plan.upto_seq is None:
        return
    text = rt.ai.summariser(rt.keys.status() == "set").rolling(previous, summary_lines(plan.dropped))
    async with actor.write_lock, rt.db.write() as tx:
        await tx.conn.execute(t.session_summaries.insert().values(session_id=actor.sid, upto_seq=plan.upto_seq,
                                                                  kind="rolling", character_id=None, text=text,
                                                                  created_at=rt.now_iso()))


async def characters(rt: Runtime, ids: list[str]) -> dict[str, Any]:
    async with rt.db.read() as conn:
        rows = (await conn.execute(select(t.characters).where(t.characters.c.id.in_(ids)))).mappings().all()
    return {r["id"]: r for r in rows}


def energy_of(rt: Runtime, row: Any) -> dict[str, Any]:
    p = rt.energy_params()
    return read_energy(mp.stored_energy(row), p.now_ms, frozen=p.frozen, est_reply_points=p.est_reply_points,
                       utc_offset_min=p.utc_offset_min)


async def session_context(rt: Runtime, actor: SessionActor, *, recent: int | None = None) -> SessionContext:
    """`recent` is the history window (the messages after the latest rolling summary), or its last `recent` items."""
    s = actor.session
    ids = [p["characterId"] for p in s["participants"]]
    chars = await characters(rt, ids)
    async with rt.db.read() as conn:
        w = (await conn.execute(select(t.worlds).where(t.worlds.c.id == s["worldId"]))).mappings().first()
    upto, summ = await _latest_summary(rt, actor.sid)
    names = {cid: (chars[cid]["profile"].get("name") if cid in chars else cid) for cid in ids}
    parts = [ParticipantView(character_id=p["characterId"], name=str(names.get(p["characterId"]) or p["characterId"]),
                             role=p["role"], side=p.get("side"), muted=bool(p.get("mutedByUser")),
                             emotion=str(p.get("currentEmotion") or "neutral"),
                             energy=energy_of(rt, chars[p["characterId"]]) if p["characterId"] in chars else {})
             for p in s["participants"]]
    msgs = ordered_messages(actor.state)
    views = _views([m for m in msgs if m["seq"] > upto and m["status"] != "streaming"], names)
    if recent is not None:
        views = views[-recent:]
    settings = rt.settings_doc()
    return SessionContext(
        session_id=actor.sid, seed=actor.seed,
        world=WorldView(id=s["worldId"], name=str(w["name"]) if w else "", you=w["you"] if w else None),
        mode=s["mode"], title=s["title"], config=s.get("config"), state=s.get("state"), participants=parts,
        recent=views, summary=summ, emotion_mode=s["emotionMode"], content_rating=str(settings.get("contentRating", "sfw")),
        period=rt.clock.pricing_period(), history_tokens=sum(estimate_tokens(m["content"]) for m in msgs))


def character_view(row: Any) -> CharacterView:
    return CharacterView(id=row["id"], name=str(row["profile"].get("name", row["id"])), profile=dict(row["profile"]))

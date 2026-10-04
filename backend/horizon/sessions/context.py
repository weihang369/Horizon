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

RECENT = 40


async def characters(rt: Runtime, ids: list[str]) -> dict[str, Any]:
    async with rt.db.read() as conn:
        rows = (await conn.execute(select(t.characters).where(t.characters.c.id.in_(ids)))).mappings().all()
    return {r["id"]: r for r in rows}


def energy_of(rt: Runtime, row: Any) -> dict[str, Any]:
    p = rt.energy_params()
    return read_energy(mp.stored_energy(row), p.now_ms, frozen=p.frozen, est_reply_points=p.est_reply_points,
                       utc_offset_min=p.utc_offset_min)


async def session_context(rt: Runtime, actor: SessionActor, *, recent: int = RECENT) -> SessionContext:
    s = actor.session
    ids = [p["characterId"] for p in s["participants"]]
    chars = await characters(rt, ids)
    async with rt.db.read() as conn:
        w = (await conn.execute(select(t.worlds).where(t.worlds.c.id == s["worldId"]))).mappings().first()
        summ = (await conn.execute(select(t.session_summaries.c.text).where(
            t.session_summaries.c.session_id == actor.sid).where(t.session_summaries.c.kind == "rolling")
            .order_by(t.session_summaries.c.upto_seq.desc(), t.session_summaries.c.id.desc()).limit(1))).scalar()
    names = {cid: (chars[cid]["profile"].get("name") if cid in chars else cid) for cid in ids}
    parts = [ParticipantView(character_id=p["characterId"], name=str(names.get(p["characterId"]) or p["characterId"]),
                             role=p["role"], side=p.get("side"), muted=bool(p.get("mutedByUser")),
                             energy=energy_of(rt, chars[p["characterId"]]) if p["characterId"] in chars else {})
             for p in s["participants"]]
    msgs = ordered_messages(actor.state)
    views = [MessageView(id=m["id"], seq=m["seq"], author_type=m["author"]["type"],
                         character_id=m["author"].get("characterId"),
                         name=str(names.get(m["author"].get("characterId") or "", "") or m["author"]["type"]),
                         kind=m["kind"], content=m["content"], emotion=m.get("emotion")) for m in msgs[-recent:]]
    settings = rt.settings_doc()
    return SessionContext(
        session_id=actor.sid, seed=actor.seed,
        world=WorldView(id=s["worldId"], name=str(w["name"]) if w else "", you=w["you"] if w else None),
        mode=s["mode"], title=s["title"], config=s.get("config"), state=s.get("state"), participants=parts,
        recent=views, summary=summ, emotion_mode=s["emotionMode"], content_rating=str(settings.get("contentRating", "sfw")),
        period=rt.clock.pricing_period(), history_tokens=sum(estimate_tokens(m["content"]) for m in msgs))


def character_view(row: Any) -> CharacterView:
    return CharacterView(id=row["id"], name=str(row["profile"].get("name", row["id"])), profile=dict(row["profile"]))

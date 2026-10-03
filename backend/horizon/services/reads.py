"""Read services (http-api spec "Read routes"): rows → wire shapes, with the MockClient's orderings and the
documented read-time derivations. Every function takes an open read connection.

Isolation (NFR-23): world-scoped lists require their world to exist and filter by it; retrieval re-binds
`world_id`/`character_id` (see `fts_search`).
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from horizon.api.errors import not_found, validation
from horizon.contract import mappers as mp
from horizon.db import tables as t
from horizon.domain.energy import read_energy
from horizon.domain.timeutil import to_iso

Wire = dict[str, Any]

DEFAULT_LIMIT = 200
MAX_LIMIT = 1000


class ReadContext:
    """What a read needs from the runtime: the clock, demo mode and the energy threshold for this instant."""

    def __init__(self, now_ms: int, est_reply_points: float, demo_mode: bool = True) -> None:
        self.now_ms = now_ms
        self.est = est_reply_points
        self.demo = demo_mode


# ── Cursors ──────────────────────────────────────────────────────────────────
def encode_cursor(value: Any) -> str:
    return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> Any:
    if cursor is None or cursor == "":
        return None
    try:
        pad = "=" * (-len(cursor) % 4)
        return json.loads(base64.urlsafe_b64decode(cursor + pad))
    except (ValueError, binascii.Error) as e:
        raise validation("Invalid cursor.", {"field": "cursor"}) from e


def check_limit(limit: int | None) -> int:
    n = DEFAULT_LIMIT if limit is None else limit
    if n < 1 or n > MAX_LIMIT:
        raise validation(f"limit must be between 1 and {MAX_LIMIT}.", {"field": "limit", "max": MAX_LIMIT})
    return n


def _seq_cursor(cursor: str | None) -> int:
    v = decode_cursor(cursor)
    if v is None:
        return 0
    if not isinstance(v, dict) or not isinstance(v.get("seq"), int):
        raise validation("Invalid cursor.", {"field": "cursor"})
    return int(v["seq"])


# ── Worlds ───────────────────────────────────────────────────────────────────
async def _character_counts(conn: AsyncConnection, world_ids: Sequence[str]) -> dict[str, int]:
    if not world_ids:
        return {}
    c = t.characters.c
    rows = (await conn.execute(select(c.world_id, func.count()).where(
        and_(c.world_id.in_(world_ids), c.status == "approved", c.deleted_at.is_(None))).group_by(c.world_id))).all()
    return {r[0]: int(r[1]) for r in rows}


async def world_row(conn: AsyncConnection, world_id: str) -> RowMapping:
    row = (await conn.execute(select(t.worlds).where(t.worlds.c.id == world_id))).mappings().first()
    if row is None:
        raise not_found("World")
    return row


async def list_worlds(conn: AsyncConnection) -> list[Wire]:
    rows = (await conn.execute(select(t.worlds).order_by(t.worlds.c.last_active_at.desc(), t.worlds.c.id))).mappings().all()
    counts = await _character_counts(conn, [r["id"] for r in rows])
    return [mp.world_wire(r, counts.get(r["id"], 0)) for r in rows]


async def get_world(conn: AsyncConnection, world_id: str) -> Wire:
    r = await world_row(conn, world_id)
    return mp.world_wire(r, (await _character_counts(conn, [world_id])).get(world_id, 0))


# ── Characters ───────────────────────────────────────────────────────────────
async def _assets_for(conn: AsyncConnection, character_ids: Sequence[str]) -> dict[str, list[RowMapping]]:
    out: dict[str, list[RowMapping]] = {cid: [] for cid in character_ids}
    if character_ids:
        rows = (await conn.execute(select(t.image_assets).where(t.image_assets.c.character_id.in_(character_ids)))).mappings().all()
        for a in rows:
            out.setdefault(a["character_id"], []).append(a)
    return out


def _character(r: RowMapping, assets: list[RowMapping], rc: ReadContext) -> Wire:
    energy = read_energy(mp.stored_energy(r), rc.now_ms, frozen=rc.demo, est_reply_points=rc.est)
    return mp.character_wire(r, assets, energy)


async def character_row(conn: AsyncConnection, character_id: str, *, allow_tombstone: bool = True) -> RowMapping:
    row = (await conn.execute(select(t.characters).where(t.characters.c.id == character_id))).mappings().first()
    if row is None or (not allow_tombstone and row["deleted_at"] is not None):
        raise not_found("Character")
    return row


async def list_characters(conn: AsyncConnection, rc: ReadContext, world_id: str, include_archived: bool) -> list[Wire]:
    await world_row(conn, world_id)
    c = t.characters.c
    q = select(t.characters).where(and_(c.world_id == world_id, c.deleted_at.is_(None)))
    if not include_archived:
        q = q.where(c.status != "archived")
    rows = (await conn.execute(q.order_by(c.is_seed.desc(), c.created_at, c.id))).mappings().all()
    assets = await _assets_for(conn, [r["id"] for r in rows])
    return [_character(r, assets[r["id"]], rc) for r in rows]


async def get_character(conn: AsyncConnection, rc: ReadContext, character_id: str) -> Wire:
    r = await character_row(conn, character_id)
    return _character(r, (await _assets_for(conn, [character_id]))[character_id], rc)


async def character_assets(conn: AsyncConnection, character_id: str) -> list[Wire]:
    await character_row(conn, character_id)
    a = t.image_assets.c
    rows = (await conn.execute(select(t.image_assets).where(and_(a.character_id == character_id, a.kind == "emotion"))
                               .order_by(a.emotion, a.variant, a.version))).mappings().all()
    return [mp.emotion_asset_wire(r) for r in rows]


async def character_song(conn: AsyncConnection, character_id: str) -> Wire | None:
    r = await character_row(conn, character_id, allow_tombstone=False)
    if not r["theme_song_id"]:
        return None
    song = (await conn.execute(select(t.theme_songs).where(t.theme_songs.c.id == r["theme_song_id"]))).mappings().first()
    return mp.song_wire(song) if song else None


async def character_memory(conn: AsyncConnection, character_id: str) -> list[Wire]:
    r = await character_row(conn, character_id)
    m = t.memory_items.c
    rows = (await conn.execute(select(t.memory_items).where(and_(
        m.character_id == character_id, m.world_id == r["world_id"], m.superseded_by.is_(None)))
        .order_by(m.created_at.desc(), m.id))).mappings().all()
    return [mp.memory_wire(x) for x in rows]


async def _cited_counts(conn: AsyncConnection, source_ids: Sequence[str]) -> dict[str, int]:
    if not source_ids:
        return {}
    mc = t.message_citations.c
    rows = (await conn.execute(select(mc.source_id, func.count()).where(mc.source_id.in_(source_ids)).group_by(mc.source_id))).all()
    return {r[0]: int(r[1]) for r in rows}


async def character_knowledge(conn: AsyncConnection, character_id: str) -> list[Wire]:
    r = await character_row(conn, character_id)
    k = t.knowledge_sources.c
    rows = (await conn.execute(select(t.knowledge_sources).where(and_(
        k.character_id == character_id, k.world_id == r["world_id"])).order_by(k.added_at, k.id))).mappings().all()
    cited = await _cited_counts(conn, [x["id"] for x in rows])
    return [mp.knowledge_source_wire(x, cited.get(x["id"], 0)) for x in rows]


async def knowledge_source(conn: AsyncConnection, source_id: str) -> Wire:
    src = (await conn.execute(select(t.knowledge_sources).where(t.knowledge_sources.c.id == source_id))).mappings().first()
    if src is None:
        raise not_found("Source")
    kc = t.knowledge_chunks.c
    chunks = (await conn.execute(select(t.knowledge_chunks).where(and_(
        kc.source_id == source_id, kc.character_id == src["character_id"], kc.world_id == src["world_id"]))
        .order_by(kc.idx))).mappings().all()
    cited = await _cited_counts(conn, [source_id])
    return {"source": mp.knowledge_source_wire(src, cited.get(source_id, 0)), "chunks": [mp.chunk_wire(c) for c in chunks]}


async def fts_search(conn: AsyncConnection, *, world_id: str, character_id: str, query: str, limit: int = 20) -> list[Wire]:
    """Keyword retrieval within one character (BM25). The join back re-binds world and character (NFR-23)."""
    rows = (await conn.execute(text(
        "SELECT c.* FROM knowledge_fts f JOIN knowledge_chunks c ON c.rid = f.rowid "
        "WHERE knowledge_fts MATCH :q AND c.world_id = :w AND c.character_id = :c ORDER BY bm25(knowledge_fts) LIMIT :n"),
        {"q": query, "w": world_id, "c": character_id, "n": limit})).mappings().all()
    return [mp.chunk_wire(r) for r in rows]


async def memory_fts_search(conn: AsyncConnection, *, world_id: str, character_id: str, query: str, limit: int = 20) -> list[Wire]:
    rows = (await conn.execute(text(
        "SELECT m.* FROM memory_fts f JOIN memory_items m ON m.rid = f.rowid "
        "WHERE memory_fts MATCH :q AND m.world_id = :w AND m.character_id = :c ORDER BY bm25(memory_fts) LIMIT :n"),
        {"q": query, "w": world_id, "c": character_id, "n": limit})).mappings().all()
    return [mp.memory_wire(r) for r in rows]


# ── Sessions ─────────────────────────────────────────────────────────────────
async def session_row(conn: AsyncConnection, session_id: str) -> RowMapping:
    row = (await conn.execute(select(t.sessions).where(t.sessions.c.id == session_id))).mappings().first()
    if row is None:
        raise not_found("Session")
    return row


async def _participants(conn: AsyncConnection, session_ids: Sequence[str]) -> dict[str, list[RowMapping]]:
    out: dict[str, list[RowMapping]] = {s: [] for s in session_ids}
    if session_ids:
        for p in (await conn.execute(select(t.participants).where(t.participants.c.session_id.in_(session_ids)))).mappings().all():
            out[p["session_id"]].append(p)
    return out


async def list_sessions(conn: AsyncConnection, world_id: str) -> list[Wire]:
    await world_row(conn, world_id)
    s = t.sessions.c
    rows = (await conn.execute(select(t.sessions).where(s.world_id == world_id)
                               .order_by(func.coalesce(s.last_message_at, s.updated_at).desc(), s.id))).mappings().all()
    parts = await _participants(conn, [r["id"] for r in rows])
    return [mp.session_wire(r, parts[r["id"]]) for r in rows]


async def get_session(conn: AsyncConnection, session_id: str) -> Wire:
    r = await session_row(conn, session_id)
    return mp.session_wire(r, (await _participants(conn, [session_id]))[session_id])


async def last_event_seq(conn: AsyncConnection, session_id: str) -> int:
    e = t.session_events.c
    return int((await conn.execute(select(func.coalesce(func.max(e.seq), 0)).where(e.session_id == session_id))).scalar_one())


async def session_snapshot(conn: AsyncConnection, session_id: str) -> Wire:
    session = await get_session(conn, session_id)
    m = t.messages.c
    rows = (await conn.execute(select(t.messages).where(m.session_id == session_id).order_by(m.seq))).mappings().all()
    return {"session": session, "messages": [mp.message_wire(r) for r in rows],
            "lastSeq": await last_event_seq(conn, session_id)}


async def _traces(conn: AsyncConnection, message_ids: Iterable[str]) -> dict[str, Wire]:
    ids = list(message_ids)
    if not ids:
        return {}
    rows = (await conn.execute(select(t.turn_traces.c.message_id, t.turn_traces.c.trace)
                               .where(t.turn_traces.c.message_id.in_(ids)))).all()
    return {r[0]: r[1] for r in rows}


async def session_messages_page(conn: AsyncConnection, session_id: str, cursor: str | None, limit: int | None) -> Wire:
    await session_row(conn, session_id)
    n = check_limit(limit)
    after = _seq_cursor(cursor)
    m = t.messages.c
    rows = (await conn.execute(select(t.messages).where(and_(m.session_id == session_id, m.seq > after))
                               .order_by(m.seq).limit(n + 1))).mappings().all()
    page = rows[:n]
    traces = await _traces(conn, [r["id"] for r in page])
    nxt = encode_cursor({"seq": page[-1]["seq"]}) if len(rows) > n else None
    return {"items": [mp.message_wire(r, traces.get(r["id"])) for r in page], "nextCursor": nxt}


async def session_events_page(conn: AsyncConnection, session_id: str, cursor: str | None, limit: int | None) -> Wire:
    await session_row(conn, session_id)
    n = check_limit(limit)
    after = _seq_cursor(cursor)
    rows = await events_after(conn, session_id, after, n + 1)
    page = rows[:n]
    nxt = encode_cursor({"seq": page[-1]["seq"]}) if len(rows) > n else None
    return {"items": page, "nextCursor": nxt}


async def events_after(conn: AsyncConnection, session_id: str, after_seq: int, limit: int) -> list[Wire]:
    e = t.session_events.c
    rows = (await conn.execute(select(t.session_events).where(and_(e.session_id == session_id, e.seq > after_seq))
                               .order_by(e.seq).limit(limit))).mappings().all()
    return [mp.event_wire(r) for r in rows]


async def message_trace(conn: AsyncConnection, message_id: str) -> Wire | None:
    return (await _traces(conn, [message_id])).get(message_id)


# ── Usage ────────────────────────────────────────────────────────────────────
async def usage_page(conn: AsyncConnection, rc: ReadContext, since_days: float | None, cursor: str | None,
                     limit: int | None) -> Wire:
    n = check_limit(limit)
    u = t.usage_records.c
    q = select(t.usage_records)
    if since_days:
        q = q.where(u.at >= to_iso(_from_ms(rc.now_ms - since_days * 86_400_000)))
    cur = decode_cursor(cursor)
    if cur is not None:
        if not (isinstance(cur, list) and len(cur) == 2 and all(isinstance(x, str) for x in cur)):
            raise validation("Invalid cursor.", {"field": "cursor"})
        q = q.where(or_(u.at > cur[0], and_(u.at == cur[0], u.id > cur[1])))
    rows = (await conn.execute(q.order_by(u.at, u.id).limit(n + 1))).mappings().all()
    page = rows[:n]
    nxt = encode_cursor([page[-1]["at"], page[-1]["id"]]) if len(rows) > n else None
    return {"items": [mp.usage_wire(r) for r in page], "nextCursor": nxt}


def _from_ms(ms: float) -> Any:
    from horizon.domain.timeutil import from_ms

    return from_ms(ms)


def _round6(n: float) -> float:
    return round(n + 0.0, 6)


async def usage_summary(conn: AsyncConnection, *, spent_today: float, cap_usd: float) -> Wire:
    """The MockClient's summary semantics: totals over the whole ledger, `estimatedUsd` falls back to the cost."""
    cats = ("chat", "decision", "image", "music", "profile", "summary", "memory", "embedding", "energy_topup")
    by_category = dict.fromkeys(cats, 0.0)
    by_character: dict[str, float] = {}
    by_session: dict[str, float] = {}
    total = est = 0.0
    for r in (await conn.execute(select(t.usage_records).order_by(t.usage_records.c.at))).mappings().all():
        cost = float(r["cost_usd"])
        total += cost
        est += float(r["estimated_cost_usd"]) if r["estimated_cost_usd"] is not None else cost
        by_category[r["category"]] = _round6(by_category[r["category"]] + cost)
        if r["character_id"]:
            by_character[r["character_id"]] = _round6(by_character.get(r["character_id"], 0.0) + cost)
        if r["session_id"]:
            by_session[r["session_id"]] = _round6(by_session.get(r["session_id"], 0.0) + cost)
    return {"todayUsd": spent_today, "totalUsd": _round6(total), "capUsd": cap_usd, "byCategory": by_category,
            "byCharacter": by_character, "bySession": by_session, "estimatedUsd": _round6(est), "actualUsd": _round6(total)}


# ── Jobs ─────────────────────────────────────────────────────────────────────
async def _jobs(conn: AsyncConnection, rows: Sequence[RowMapping]) -> list[Wire]:
    ids = [r["id"] for r in rows]
    tasks: dict[str, list[RowMapping]] = {i: [] for i in ids}
    if ids:
        for tr in (await conn.execute(select(t.generation_tasks).where(t.generation_tasks.c.job_id.in_(ids)))).mappings().all():
            tasks[tr["job_id"]].append(tr)
    return [mp.job_wire(r, tasks[r["id"]]) for r in rows]


async def get_job(conn: AsyncConnection, job_id: str) -> Wire:
    row = (await conn.execute(select(t.generation_jobs).where(t.generation_jobs.c.id == job_id))).mappings().first()
    if row is None:
        raise not_found("Job")
    return (await _jobs(conn, [row]))[0]


async def active_jobs(conn: AsyncConnection) -> list[Wire]:
    j = t.generation_jobs.c
    rows = (await conn.execute(select(t.generation_jobs).where(j.status.in_(("queued", "running")))
                               .order_by(j.created_at, j.id))).mappings().all()
    return await _jobs(conn, rows)


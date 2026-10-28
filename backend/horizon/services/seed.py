"""Seed import and reset-demo (doc 02 §4–§5, design D5/D12). One code path: importing into an empty database is
a reset-demo with nothing to preserve.

`load_seed()` reads `seed/**` (plus the default-scenario `seed/_mock/**` overlays when asked: every run since D-104,
OQ-6; the runtime drops their fixture jobs outside test mode), validates
every entity against `schema.json`, normalises nothing yet, and asserts that reducing each session's events gives
exactly its shipped session and messages. Any failure raises `SeedError` naming the file or session, before a row
is written.

`apply_seed()` upserts the dataset in the caller's writer transaction. Worlds, characters and sessions are found by
the seed dataset's ids and keep the wire `isSeed` they ship with (the `_mock` overlays ship `isSeed: false`);
memory, knowledge, jobs and ledger rows have no wire flag, so their `is_seed` column means "shipped, restored by reset":
- seed worlds, characters and songs are upserted in place (user forks may reference them);
- seed sessions keep their row (so forks keep `continuedFrom`) while their events/messages are replaced;
- seed memory, knowledge, jobs and ledger rows are replaced; user rows (`is_seed = 0`) are never touched;
- non-seed emotion asset versions of seed characters are deactivated, never deleted (OQ-13).

D-110 (`seed/rows/**`, built from the real run by `horizon demo export --rows`): the documents as the app stored them
(sections, pieces, their vectors and the stored originals in `seed/knowledge/files/`), the memories' vectors and recall
counts, recall's line index, the stored query rewrites and safety answers, and the full ledger rows. Rows replace what
would otherwise be synthesised from the wire files; vectors go in only when the install's active embedding space is the
one they were made in (a fresh install is), with fresh `rid`s on every import, so install, Reset demo and Delete all
data each restore them at $0. On another space the documents stay `keyword_only` (D-91's Index upgrades them).
"""

from __future__ import annotations

import base64
import copy
import json
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import Table, and_, delete, insert, select, text, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from horizon.contract import mappers as mp
from horizon.contract.validate import ContractSchema
from horizon.db import spaces
from horizon.db import tables as t
from horizon.domain.timeutil import normalise_iso
from horizon.services.memory.refs import refs_from_trace
from horizon.services.runtime.reducer import initial_runtime, ordered_messages, reduce_all

Wire = dict[str, Any]


class SeedError(RuntimeError):
    """The shipped seed is invalid; nothing was imported."""


@dataclass
class SeedSession:
    session: Wire
    events: list[Wire]
    messages: list[Wire]


@dataclass
class SeedRows:
    """D-110: the real run's stored rows, by seed id (`seed/rows/**`)."""
    space: str
    knowledge: dict[str, Wire] = field(default_factory=dict)   # source id → {source, files, sections, chunks}
    memory: dict[str, Wire] = field(default_factory=dict)
    message_index: list[Wire] = field(default_factory=list)
    ai_meta: list[Wire] = field(default_factory=list)
    usage: dict[str, Wire] = field(default_factory=dict)
    files_dir: Path | None = None


@dataclass
class SeedData:
    worlds: list[Wire] = field(default_factory=list)
    characters: list[Wire] = field(default_factory=list)
    songs: list[Wire] = field(default_factory=list)
    sessions: list[SeedSession] = field(default_factory=list)
    memory: list[Wire] = field(default_factory=list)
    knowledge: list[Wire] = field(default_factory=list)
    chunks: dict[str, list[Wire]] = field(default_factory=dict)
    ledger: list[Wire] = field(default_factory=list)
    jobs: list[Wire] = field(default_factory=list)
    rows: SeedRows | None = None

    @property
    def world_names(self) -> dict[str, str]:
        return {w["id"]: w["name"] for w in self.worlds}


def _read(path: Path) -> Any:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise SeedError(f"{path}: unreadable ({e})") from e
    if not isinstance(doc, dict) or "data" not in doc:
        raise SeedError(f"{path}: expected {{ schemaVersion, data }}")
    return doc["data"]


def _check(schema: ContractSchema, def_name: str, value: Any, where: Path | str) -> None:
    problems = schema.errors(def_name, value)
    if problems:
        raise SeedError(f"{where}: not a valid {def_name}: " + "; ".join(problems[:3]))


def seed_base_session(final: Wire) -> Wire:
    """The session a seed recording starts from (as `scripts/seed-build` builds it); its events set the rest."""
    base = copy.deepcopy(final)
    base.update(status="active", state=None, costUsd=0, messageCount=0, updatedAt=base["createdAt"])
    base.pop("lastMessageAt", None)
    base.pop("pausedReason", None)
    return base


def _load_dir(root: Path, data: SeedData, schema: ContractSchema, *, overlay: bool) -> None:
    for p in sorted((root / "worlds").glob("*.json")) if not overlay else []:
        w = _read(p)
        _check(schema, "World", w, p)
        data.worlds.append(w)
    for p in sorted((root / "characters").glob("*.json")):
        c = _read(p)
        _check(schema, "Character", c, p)
        data.characters.append(c)
    for p in sorted((root / "songs").glob("*.json")):
        s = _read(p)
        _check(schema, "ThemeSong", s, p)
        data.songs.append(s)
    for d in sorted(x for x in (root / "sessions").glob("*") if x.is_dir()):
        sess = _read(d / "session.json")
        _check(schema, "Session", sess, d / "session.json")
        events = _read(d / "events.json") if (d / "events.json").is_file() else []
        messages = _read(d / "messages.json") if (d / "messages.json").is_file() else []
        for i, e in enumerate(events):
            _check(schema, "SessionEvent", e, f"{d / 'events.json'}[{i}]")
        for i, m in enumerate(messages):
            _check(schema, "Message", m, f"{d / 'messages.json'}[{i}]")
        data.sessions.append(SeedSession(sess, events, messages))
    for p in sorted((root / "memory").glob("*.json")) if not overlay else []:
        for i, m in enumerate(_read(p)):
            _check(schema, "MemoryItem", m, f"{p}[{i}]")
            data.memory.append(m)
    for p in sorted((root / "knowledge").glob("*.json")) if not overlay else []:
        for i, k in enumerate(_read(p)):
            _check(schema, "KnowledgeSource", k, f"{p}[{i}]")
            data.knowledge.append(k)
    for p in sorted((root / "knowledge" / "chunks").glob("*.json")) if not overlay else []:
        for i, ch in enumerate(_read(p)):
            _check(schema, "KnowledgeChunk", ch, f"{p}[{i}]")
            data.chunks.setdefault(ch["sourceId"], []).append(ch)
    ledger = root / "usage" / "ledger.json"
    if ledger.is_file():
        for i, u in enumerate(_read(ledger)):
            _check(schema, "UsageRecord", u, f"{ledger}[{i}]")
            data.ledger.append(u)
    for p in sorted((root / "jobs").glob("*.json")):
        j = _read(p)
        _check(schema, "GenerationJob", j, p)
        data.jobs.append(j)
    if not overlay and (root / "rows" / "space.json").is_file():
        rows = SeedRows(space=str(_read(root / "rows" / "space.json")["id"]), files_dir=root / "knowledge" / "files")
        for p in sorted((root / "rows" / "knowledge").glob("*.json")):
            rows.knowledge[p.stem] = _read(p)
        rows.memory = {m["id"]: m for m in _read(root / "rows" / "memory.json")}
        rows.message_index = _read(root / "rows" / "message-index.json")
        rows.ai_meta = _read(root / "rows" / "ai-meta.json")
        rows.usage = {u["id"]: u for u in _read(root / "rows" / "usage.json")}
        data.rows = rows


def _assert_reductions(data: SeedData) -> None:
    for s in data.sessions:
        sid = s.session["id"]
        final = reduce_all(initial_runtime(seed_base_session(s.session)), s.events)
        if ordered_messages(final) != s.messages:
            raise SeedError(f"seed session {sid}: reducing events.json does not give messages.json")
        if final["session"] != s.session:
            raise SeedError(f"seed session {sid}: reducing events.json does not give session.json")


def _assert_references(data: SeedData) -> None:
    worlds = {w["id"] for w in data.worlds}
    chars = {c["id"] for c in data.characters}
    sessions = {s.session["id"] for s in data.sessions}
    ids: set[str] = set()
    for kind, items in (("world", data.worlds), ("character", data.characters), ("song", data.songs),
                        ("memory", data.memory), ("knowledge", data.knowledge), ("usage", data.ledger), ("job", data.jobs)):
        for x in items:
            if x["id"] in ids:
                raise SeedError(f"duplicate seed id {x['id']} ({kind})")
            ids.add(x["id"])
    for c in data.characters:
        if c["worldId"] not in worlds:
            raise SeedError(f"character {c['id']}: unknown world {c['worldId']}")
    for s in data.sessions:
        for p in s.session["participants"]:
            if p["characterId"] not in chars:
                raise SeedError(f"session {s.session['id']}: unknown participant {p['characterId']}")
    for u in data.ledger:
        if u.get("characterId") and u["characterId"] not in chars:
            raise SeedError(f"ledger {u['id']}: unknown character {u['characterId']}")
        if u.get("sessionId") and u["sessionId"] not in sessions:
            raise SeedError(f"ledger {u['id']}: unknown session {u['sessionId']}")


ISO_INSTANT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$")


def deep_normalise(v: Any) -> Any:
    """Every ISO instant anywhere in a seed value → the stored millisecond form (doc 02 §1), nested JSON included,
    so events, messages and traces stay consistent with each other."""
    if isinstance(v, str):
        return normalise_iso(v) if ISO_INSTANT.match(v) else v
    if isinstance(v, list):
        return [deep_normalise(x) for x in v]
    if isinstance(v, dict):
        return {k: deep_normalise(x) for k, x in v.items()}
    return v


def _normalise(data: SeedData) -> None:
    for name in ("worlds", "characters", "songs", "memory", "knowledge", "ledger", "jobs"):
        setattr(data, name, deep_normalise(getattr(data, name)))
    data.chunks = deep_normalise(data.chunks)
    data.sessions = [SeedSession(deep_normalise(s.session), deep_normalise(s.events), deep_normalise(s.messages))
                     for s in data.sessions]


def load_seed(seed_dir: Path, schema: ContractSchema, *, include_mock: bool = False) -> SeedData:
    if not (seed_dir / "worlds").is_dir():
        raise SeedError(f"{seed_dir}: no seed worlds")
    data = SeedData()
    _load_dir(seed_dir, data, schema, overlay=False)
    if include_mock and (seed_dir / "_mock").is_dir():
        _load_dir(seed_dir / "_mock", data, schema, overlay=True)
    _assert_references(data)
    _assert_reductions(data)
    _normalise(data)
    return data


# ── Writing ──────────────────────────────────────────────────────────────────
async def _upsert(conn: AsyncConnection, table: Table, rows: list[dict[str, Any]], key: str = "id") -> None:
    for row in rows:
        stmt = sqlite_insert(table).values(**row)
        stmt = stmt.on_conflict_do_update(index_elements=[key], set_={k: stmt.excluded[k] for k in row if k != key})
        await conn.execute(stmt)


async def _insert(conn: AsyncConnection, table: Table, rows: list[dict[str, Any]]) -> None:
    if rows:
        await conn.execute(insert(table), rows)


async def apply_seed(conn: AsyncConnection, data: SeedData, *, energy_day: Callable[[str], str],
                     local_day: Callable[[str], str]) -> list[str]:
    """Upsert the seed into the database (inside the caller's writer transaction). Returns the seed session ids."""
    await conn.execute(text("PRAGMA defer_foreign_keys = ON"))
    rows = data.rows
    vec_space = await _vector_space(conn, rows)

    # Worlds.
    await _upsert(conn, t.worlds, [mp.world_row(w, is_seed=bool(w["isSeed"])) for w in data.worlds])

    # Jobs (test-mode overlays only). Before characters: deleting a job nulls `characters.active_job_id`,
    # and the character upsert below puts the shipped pointer back.
    await conn.execute(delete(t.generation_jobs).where(t.generation_jobs.c.is_seed.is_(True)))
    for j in data.jobs:
        jrow, trows = mp.job_rows(j, is_seed=True)
        await _insert(conn, t.generation_jobs, [jrow])
        await _insert(conn, t.generation_tasks, trows)

    # Characters + their seed assets. Seed asset ids replace in place; other versions are deactivated (OQ-13).
    char_rows, asset_rows = [], []
    for c in data.characters:
        row, assets = mp.character_rows(c, is_seed=bool(c["isSeed"]), energy_day=energy_day)
        char_rows.append(row)
        asset_rows.extend(assets)
    seed_chars = [c["id"] for c in data.characters]
    seed_assets = [a["id"] for a in asset_rows]
    await _upsert(conn, t.characters, char_rows)
    if seed_chars:
        await conn.execute(update(t.image_assets).where(and_(t.image_assets.c.character_id.in_(seed_chars),
                                                             t.image_assets.c.id.not_in(seed_assets),
                                                             t.image_assets.c.kind == "emotion")).values(is_active=False))
        # M4: user-generated candidate batches of seed characters go, so the shipped candidates show again (a locked
        # one survives as an inactive neutral version pointing at the same file).
        await conn.execute(delete(t.image_assets).where(and_(t.image_assets.c.character_id.in_(seed_chars),
                                                             t.image_assets.c.kind == "candidate",
                                                             t.image_assets.c.job_id.is_not(None))))
        await conn.execute(delete(t.image_assets).where(t.image_assets.c.id.in_(seed_assets)))
    await _insert(conn, t.image_assets, asset_rows)

    # Songs.
    created = {c["id"]: normalise_iso(c["createdAt"]) for c in data.characters}
    await _upsert(conn, t.theme_songs, [mp.song_row(s, is_seed=True, created_at=created.get(s["characterId"], "1970-01-01T00:00:00.000Z"))
                                        for s in data.songs])

    # Sessions: keep the row, replace what is derived from the events.
    sids = [s.session["id"] for s in data.sessions]
    if sids:
        for tbl in (t.session_events, t.messages, t.participants, t.session_summaries):
            await conn.execute(delete(tbl).where(tbl.c.session_id.in_(sids)))
    for s in data.sessions:
        srow, parts = mp.session_rows(s.session, is_seed=bool(s.session["isSeed"]))
        await _upsert(conn, t.sessions, [srow])
        await _insert(conn, t.participants, parts)
        await _insert(conn, t.session_events, [mp.event_row(e) for e in s.events])
        await _insert(conn, t.messages, [mp.message_row(m) for m in s.messages])
        traces = [{"message_id": m["id"], "trace": m["trace"], "engine": "seed", "engine_version": None,
                   "prompt_version": None, "created_at": normalise_iso(m["createdAt"])} for m in s.messages if m.get("trace")]
        await _insert(conn, t.turn_traces, traces)
        await _insert(conn, t.message_citations, [r for m in s.messages for r in mp.citation_rows(m)])
        refs = [r for m in s.messages for r in refs_from_trace(m["id"], m.get("trace"))]   # the M5 shared helper (D14)
        await _insert(conn, t.trace_memory_refs, refs)
    if rows is not None:   # D-110: what the AI stored per user message, and recall's line index (cascaded away above)
        shipped = {m["id"] for s in data.sessions for m in s.messages}
        for a in (a for a in rows.ai_meta if a["message_id"] in shipped):
            await conn.execute(text("INSERT OR REPLACE INTO message_ai_meta(message_id, rewrites, updated_at, safety) "
                                    "VALUES (:m, :r, :u, :s)"),
                               {"m": a["message_id"], "r": a["rewrites"], "u": a["updated_at"], "s": a["safety"]})
        msg_vec = spaces.message_vec_table(vec_space) if vec_space else None
        for line in (x for x in rows.message_index if x["message_id"] in shipped):
            await conn.execute(insert(t.message_index).values(**{k: v for k, v in line.items() if k != "vector"}))
            if msg_vec and line.get("vector"):
                rid = (await conn.execute(select(t.message_index.c.rid).where(
                    t.message_index.c.message_id == line["message_id"]))).scalar_one()
                await _put_vector(conn, msg_vec, "session_id", int(rid), line["session_id"], line["vector"])

    # Memory: seed rows replaced; user-earned memories (is_seed = 0) survive.
    await conn.execute(delete(t.memory_items).where(t.memory_items.c.is_seed.is_(True)))
    # M13 (memory D5): an imported recording's history is never mined, like a migrated session's (doc 09 M2), so each
    # starts its memory checkpoint at its last message (the test-mode mock sessions are imported as non-seed)
    for s in data.sessions:
        top = max((int(m["seq"]) for m in s.messages), default=0)
        await conn.execute(update(t.sessions).where(t.sessions.c.id == s.session["id"]).values(
            memory_seq=top, memory_tries=0, memory_reread=[]))
    modes = {s.session["id"]: s.session["mode"] for s in data.sessions}
    await _insert(conn, t.memory_items, [mp.memory_row(m, is_seed=True, source_mode=modes.get(m.get("sourceSessionId") or ""))
                                         for m in data.memory])
    if rows is not None:   # D-110: the columns the wire doesn't carry, and the vectors
        mem_vec = spaces.vec_tables(vec_space)[0] if vec_space else None
        M = t.memory_items.c
        for m in data.memory:
            r = rows.memory.get(m["id"])
            if r is None:
                continue
            await conn.execute(update(t.memory_items).where(M.id == m["id"]).values(
                **{k: r[k] for k in ("source_mode", "source_variant_id", "about_character_id", "last_recalled_at",
                                     "recall_count", "superseded_by")}))
            if mem_vec and r.get("vector"):
                rid = (await conn.execute(select(M.rid).where(M.id == m["id"]))).scalar_one()
                await _put_vector(conn, mem_vec, "character_id", int(rid), m["characterId"], r["vector"])

    # Knowledge: seed sources replaced (cascade clears sections, chunks, FTS and vectors).
    await conn.execute(delete(t.knowledge_sources).where(t.knowledge_sources.c.is_seed.is_(True)))
    for k in data.knowledge:
        stored = rows.knowledge.get(k["id"]) if rows is not None else None
        if stored is not None:
            await _stored_source(conn, k, stored, vec_space)
            continue
        chunks = data.chunks.get(k["id"], [])
        await _insert(conn, t.knowledge_sources, [mp.knowledge_source_row(k, is_seed=True, chunk_count=len(chunks))])
        sections, crow = mp.chunk_rows(chunks, k, lambda ch: "ksec_" + ch["id"].split("_", 1)[1])
        await _insert(conn, t.knowledge_sections, sections)
        await _insert(conn, t.knowledge_chunks, crow)

    # Ledger: seed rows replaced.
    await conn.execute(delete(t.usage_records).where(t.usage_records.c.is_seed.is_(True)))
    await _insert(conn, t.usage_records, [_usage_row(u, rows, local_day) for u in data.ledger])

    bad = (await conn.execute(text("PRAGMA foreign_key_check"))).all()
    if bad:
        raise SeedError(f"seed violates foreign keys: {bad[:3]}")
    return sids


async def _vector_space(conn: AsyncConnection, rows: SeedRows | None) -> str | None:
    """The space the shipped vectors go into: the active one, if they were made in it (D-110)."""
    if rows is None:
        return None
    active = await spaces.active(conn)
    return active.id if active.id == rows.space else None


async def _put_vector(conn: AsyncConnection, table: str, part: str, rid: int, key: str, b64: str) -> None:
    await conn.execute(text(f"INSERT INTO {table}(rid, {part}, embedding) VALUES (:r, :p, :e)"),
                       {"r": rid, "p": key, "e": base64.b64decode(b64)})


async def _stored_source(conn: AsyncConnection, k: Wire, stored: Wire, vec_space: str | None) -> None:
    """D-110: a shipped document as the app stored it: its sections and pieces, and their vectors when `vec_space` is
    set (then `indexed`, as after an upload; else `keyword_only` until D-91's Index)."""
    src = stored["source"]
    row = mp.knowledge_source_row(k, is_seed=True, chunk_count=len(stored["chunks"]))
    row.update({c: src[c] for c in ("mime", "original_name", "sha256", "extractor_version", "chunker_version", "tokenizer")})
    row["has_original"] = any(f.startswith("original.") for f in stored["files"])
    await _insert(conn, t.knowledge_sources, [row])
    await _insert(conn, t.knowledge_sections, stored["sections"])
    await _insert(conn, t.knowledge_chunks, [{c: v for c, v in ch.items() if c != "vector"} for ch in stored["chunks"]])
    if vec_space is None or row["status"] != "keyword_only" or not all(ch.get("vector") for ch in stored["chunks"]):
        return
    C = t.knowledge_chunks.c
    rids = dict((await conn.execute(select(C.id, C.rid).where(C.source_id == k["id"]))).all())
    table = spaces.vec_tables(vec_space)[1]
    for ch in stored["chunks"]:
        await _put_vector(conn, table, "character_id", int(rids[ch["id"]]), k["characterId"], ch["vector"])
    await conn.execute(update(t.knowledge_sources).where(t.knowledge_sources.c.id == k["id"]).values(
        status="indexed", embedding_space_id=vec_space, indexed_at=src["indexed_at"]))


def _usage_row(u: Wire, rows: SeedRows | None, local_day: Callable[[str], str]) -> dict[str, Any]:
    """A ledger row: the real run's full row when shipped (D-110: purpose, message, generation id, finish reason...),
    else the wire record's columns."""
    full = rows.usage.get(u["id"]) if rows is not None else None
    if full is None:
        return mp.usage_row(u, is_seed=True, local_day=local_day)
    at = normalise_iso(full["at"])
    return {**full, "at": at, "local_day": local_day(at), "is_seed": True}


def install_knowledge_files(data: SeedData, knowledge_dir: Path, only: set[str] | None = None) -> None:
    """D-110: each shipped document's stored files (its original, `extracted.md`) in its folder, where an upload leaves
    them, so a continued demo can show, re-chunk or re-embed it like any upload. Run after `apply_seed` commits.
    `only`: just these source ids (the ones still in the database)."""
    if data.rows is None or data.rows.files_dir is None:
        return
    for k in data.knowledge:
        if only is not None and k["id"] not in only:
            continue
        stored = data.rows.knowledge.get(k["id"])
        if not stored or not stored["files"]:
            continue
        dst = knowledge_dir / k["worldId"] / k["characterId"] / k["id"]
        shutil.rmtree(dst, ignore_errors=True)
        dst.mkdir(parents=True)
        for name in stored["files"]:
            shutil.copy2(data.rows.files_dir / k["id"] / name, dst / name)


async def has_worlds(conn: AsyncConnection) -> bool:
    return (await conn.execute(select(t.worlds.c.id).limit(1))).first() is not None

"""REST routes for M1b (doc 03 §3): every read, world CRUD, the admin resets, `/health` and the test-only routes.

Routes for later milestones are simply absent (404 `not_found`); the HttpClient never calls them (http-client spec
"Methods without a backend yet").
"""

from __future__ import annotations

import importlib.util
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from horizon import SCHEMA_VERSION, __version__
from horizon.api.common import check, json_response, read_ctx, rt_of
from horizon.api.errors import HorizonHTTPError, validation
from horizon.domain.clock import FrozenClock, SystemClock
from horizon.domain.timeutil import parse_iso
from horizon.services import reads
from horizon.services import settings as settings_svc
from horizon.services import worlds as worlds_svc

router = APIRouter()


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Cover(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["preset", "upload", "generated"]
    presetId: str | None = None
    url: str | None = None


class YouCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    displayName: str
    about: str | None = None


class WorldInput(_Model):
    name: str
    cover: Cover
    you: YouCard | None = None


class WorldPatch(_Model):
    name: str | None = None
    cover: Cover | None = None
    you: YouCard | None = None


def _dump(m: BaseModel | None) -> dict[str, Any] | None:
    return None if m is None else m.model_dump(exclude_none=True)


# ── Settings ─────────────────────────────────────────────────────────────────
@router.get("/settings")
async def get_settings(request: Request) -> Response:
    rt = rt_of(request)
    async with rt.db.read() as conn:
        body = await settings_svc.app_settings(conn, seed=rt.seed_settings, local=rt.local_settings(), clock=rt.clock)
    return json_response(rt, body, def_name="AppSettings")


# ── Worlds ───────────────────────────────────────────────────────────────────
@router.get("/worlds")
async def list_worlds(request: Request) -> Response:
    rt = rt_of(request)
    async with rt.db.read() as conn:
        return json_response(rt, await reads.list_worlds(conn), items="World")


@router.post("/worlds", status_code=201)
async def create_world(request: Request, body: WorldInput) -> Response:
    rt = rt_of(request)
    seed = await rt.load_seed()
    async with rt.db.write() as tx:
        world = await worlds_svc.create_world(tx, schema=rt.schema, now=rt.now_iso(), seed_names=seed.world_names,
                                              name=body.name, cover=_dump(body.cover) or {}, you=_dump(body.you))
    return json_response(rt, world, status=201, def_name="World")


@router.get("/worlds/{world_id}")
async def get_world(request: Request, world_id: str) -> Response:
    rt = rt_of(request)
    async with rt.db.read() as conn:
        return json_response(rt, await reads.get_world(conn, world_id), def_name="World")


@router.patch("/worlds/{world_id}")
async def update_world(request: Request, world_id: str, body: WorldPatch) -> Response:
    rt = rt_of(request)
    seed = await rt.load_seed()
    patch: dict[str, Any] = {}
    if body.name is not None:
        patch["name"] = body.name
    if body.cover is not None:
        patch["cover"] = _dump(body.cover)
    if "you" in body.model_fields_set:
        patch["you"] = _dump(body.you)
    async with rt.db.write() as tx:
        world = await worlds_svc.update_world(tx, world_id, schema=rt.schema, now=rt.now_iso(), seed_names=seed.world_names,
                                              patch=patch)
    return json_response(rt, world, def_name="World")


@router.delete("/worlds/{world_id}", status_code=204)
async def delete_world(request: Request, world_id: str) -> Response:
    rt = rt_of(request)
    async with rt.db.write() as tx:
        await worlds_svc.delete_world(tx, world_id, now=rt.now_iso())
    worlds_svc.remove_world_files(rt.cfg.data_dir, world_id)
    return Response(status_code=204)


# ── Characters, memory, knowledge ────────────────────────────────────────────
@router.get("/worlds/{world_id}/characters")
async def list_characters(request: Request, world_id: str, includeArchived: bool = False) -> Response:
    rt = rt_of(request)
    async with rt.db.read() as conn:
        body = await reads.list_characters(conn, read_ctx(rt), world_id, includeArchived)
    return json_response(rt, body, items="Character")


@router.get("/characters/{character_id}")
async def get_character(request: Request, character_id: str) -> Response:
    rt = rt_of(request)
    async with rt.db.read() as conn:
        return json_response(rt, await reads.get_character(conn, read_ctx(rt), character_id), def_name="Character")


@router.get("/characters/{character_id}/assets")
async def character_assets(request: Request, character_id: str) -> Response:
    rt = rt_of(request)
    async with rt.db.read() as conn:
        return json_response(rt, await reads.character_assets(conn, character_id), items="EmotionAsset")


@router.get("/characters/{character_id}/song")
async def character_song(request: Request, character_id: str) -> Response:
    rt = rt_of(request)
    async with rt.db.read() as conn:
        return json_response(rt, await reads.character_song(conn, character_id), def_name="ThemeSong")


@router.get("/characters/{character_id}/memory")
async def character_memory(request: Request, character_id: str) -> Response:
    rt = rt_of(request)
    async with rt.db.read() as conn:
        return json_response(rt, await reads.character_memory(conn, character_id), items="MemoryItem")


@router.get("/characters/{character_id}/knowledge")
async def character_knowledge(request: Request, character_id: str) -> Response:
    rt = rt_of(request)
    async with rt.db.read() as conn:
        return json_response(rt, await reads.character_knowledge(conn, character_id), items="KnowledgeSource")


@router.get("/knowledge/{source_id}")
async def knowledge_source(request: Request, source_id: str) -> Response:
    rt = rt_of(request)
    async with rt.db.read() as conn:
        body = await reads.knowledge_source(conn, source_id)
    check(rt, "KnowledgeSource", body["source"])
    for c in body["chunks"]:
        check(rt, "KnowledgeChunk", c)
    return json_response(rt, body)


# ── Sessions ─────────────────────────────────────────────────────────────────
@router.get("/worlds/{world_id}/sessions")
async def list_sessions(request: Request, world_id: str) -> Response:
    rt = rt_of(request)
    async with rt.db.read() as conn:
        return json_response(rt, await reads.list_sessions(conn, world_id), items="Session")


@router.get("/sessions/{session_id}")
async def get_session(request: Request, session_id: str) -> Response:
    rt = rt_of(request)
    async with rt.db.read() as conn:
        body = await reads.session_snapshot(conn, session_id)
    return json_response(rt, body, def_name="SessionSnapshot" if rt.schema.has("SessionSnapshot") else None)


Limit = Annotated[int | None, Query(ge=1, le=reads.MAX_LIMIT)]


@router.get("/sessions/{session_id}/messages")
async def session_messages(request: Request, session_id: str, cursor: str | None = None, limit: Limit = None) -> Response:
    rt = rt_of(request)
    async with rt.db.read() as conn:
        return json_response(rt, await reads.session_messages_page(conn, session_id, cursor, limit), page_of="Message")


@router.get("/sessions/{session_id}/events")
async def session_events(request: Request, session_id: str, cursor: str | None = None, limit: Limit = None) -> Response:
    rt = rt_of(request)
    async with rt.db.read() as conn:
        return json_response(rt, await reads.session_events_page(conn, session_id, cursor, limit), page_of="SessionEvent")


@router.get("/messages/{message_id}/trace")
async def message_trace(request: Request, message_id: str) -> Response:
    rt = rt_of(request)
    async with rt.db.read() as conn:
        return json_response(rt, await reads.message_trace(conn, message_id), def_name="TurnTrace")


# ── Usage, jobs ──────────────────────────────────────────────────────────────
@router.get("/usage")
async def usage_list(request: Request, sinceDays: float | None = None, cursor: str | None = None,
                     limit: Limit = None) -> Response:
    rt = rt_of(request)
    async with rt.db.read() as conn:
        return json_response(rt, await reads.usage_page(conn, read_ctx(rt), sinceDays, cursor, limit), page_of="UsageRecord")


@router.get("/usage/summary")
async def usage_summary(request: Request) -> Response:
    rt = rt_of(request)
    async with rt.db.read() as conn:
        spent = await settings_svc.spent_today(conn, rt.clock)
        cap = settings_svc.deep_merge(rt.seed_settings, rt.local_settings())["budget"]["dailyCapUsd"]
        body = await reads.usage_summary(conn, spent_today=spent, cap_usd=cap)
    return json_response(rt, body, def_name="UsageSummary" if rt.schema.has("UsageSummary") else None)


@router.get("/jobs")
async def list_jobs(request: Request, active: bool = False) -> Response:
    rt = rt_of(request)
    if not active:
        raise validation("Only ?active=true is supported.", {"field": "active"})
    async with rt.db.read() as conn:
        return json_response(rt, await reads.active_jobs(conn), items="GenerationJob")


@router.get("/jobs/{job_id}")
async def get_job(request: Request, job_id: str) -> Response:
    rt = rt_of(request)
    async with rt.db.read() as conn:
        return json_response(rt, await reads.get_job(conn, job_id), def_name="GenerationJob")


# ── Admin ────────────────────────────────────────────────────────────────────
class ResetDemoBody(_Model):
    confirm: Literal[True]


class FactoryResetBody(_Model):
    confirm: Literal["DELETE EVERYTHING"]


@router.post("/admin/reset-demo", status_code=204)
async def reset_demo(request: Request, body: ResetDemoBody) -> Response:
    await rt_of(request).reset_demo()
    return Response(status_code=204)


@router.post("/admin/factory-reset", status_code=204)
async def factory_reset(request: Request, body: FactoryResetBody) -> Response:
    await rt_of(request).factory_reset()
    return Response(status_code=204)


# ── Health ───────────────────────────────────────────────────────────────────
def docling_status(models_dir: Any) -> str:
    if importlib.util.find_spec("docling") is None:
        return "not_installed"
    return "ready" if models_dir.is_dir() and any(models_dir.iterdir()) else "models_missing"


@router.get("/health")
async def health(request: Request) -> Response:
    rt = rt_of(request)
    db = vec = "error"
    if rt.started:
        try:
            async with rt.db.read() as conn:
                await conn.execute(text("SELECT 1"))
                db = "ok"
                await conn.execute(text("SELECT vec_version()"))
                vec = "ok"
        except Exception:  # health reports, never raises
            pass
    body = {"ok": db == "ok" and vec == "ok", "version": __version__, "schemaVersion": SCHEMA_VERSION, "db": db, "vec": vec,
            "docling": docling_status(rt.cfg.data_dir / "models")}
    return json_response(rt, body)


# ── Test-only (HORIZON_TEST=1) ───────────────────────────────────────────────
test_router = APIRouter(prefix="/_test")

SCENARIOS: dict[str, str] = {}  # id → description. Empty in M1b; scenarios arrive with M2/M3 (design D13).
SCENARIO_MILESTONE = {"character_exhausted": "M2", "rush_hour": "M2", "stream_cut": "M3", "image_fail_partial": "M4",
                      "network_down": "M6", "no_worlds": "M6"}


class ClockBody(_Model):
    freezeAt: str | None = None
    advanceMs: float | None = Field(default=None, ge=0)
    release: bool = False


@test_router.post("/clock")
async def test_clock(request: Request, body: ClockBody) -> Response:
    rt = rt_of(request)
    if body.release:
        rt.clock = SystemClock(rt.clock.calendar)
    if body.freezeAt is not None:
        try:
            at: datetime = parse_iso(body.freezeAt)
        except ValueError as e:
            raise validation("freezeAt must be an ISO-8601 instant.", {"field": "freezeAt"}) from e
        if isinstance(rt.clock, FrozenClock):
            rt.clock.set(at)
        else:
            rt.clock = FrozenClock(rt.clock.calendar, at)
    if body.advanceMs:
        if not isinstance(rt.clock, FrozenClock):
            rt.clock = FrozenClock(rt.clock.calendar, rt.clock.now())
        rt.clock.advance(body.advanceMs)
    return json_response(rt, {"now": rt.now_iso(), "frozen": isinstance(rt.clock, FrozenClock)})


class ScenarioBody(_Model):
    id: str


@test_router.post("/scenario")
async def test_scenario(request: Request, body: ScenarioBody) -> Response:
    if body.id not in SCENARIOS:
        raise HorizonHTTPError("validation", f"Scenario {body.id!r} is not available on the backend yet.", status=422,
                               details={"field": "id", "availableIn": SCENARIO_MILESTONE.get(body.id, "later")})
    return Response(status_code=204)

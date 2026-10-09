"""REST routes for M1b (doc 03 §3): every read, world CRUD, the admin resets, `/health` and the test-only routes.

Routes for later milestones are simply absent (404 `not_found`); the HttpClient never calls them (http-client spec
"Methods without a backend yet").
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from horizon import SCHEMA_VERSION, __version__
from horizon.api.common import check, json_response, read_ctx, rt_of
from horizon.api.errors import HorizonHTTPError, validation
from horizon.domain.clock import FrozenClock
from horizon.domain.timeutil import parse_iso, to_iso
from horizon.events.bus import GLOBAL
from horizon.runtime import Runtime
from horizon.services import energy_writes, probes, reads
from horizon.services import settings as settings_svc
from horizon.services import worlds as worlds_svc
from horizon.services.keys import write_json_atomic
from horizon.services.ledger import LedgerWriter

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
async def settings_body(rt: Runtime) -> dict[str, Any]:
    async with rt.db.read() as conn:
        return await settings_svc.app_settings(conn, seed=rt.seed_settings, local=rt.local_settings(), clock=rt.clock,
                                               key_status=rt.keys.status())


@router.get("/settings")
async def get_settings(request: Request) -> Response:
    rt = rt_of(request)
    return json_response(rt, await settings_body(rt), def_name="AppSettings")


@router.patch("/settings")
async def patch_settings(request: Request, body: Annotated[dict[str, Any], Body()]) -> Response:
    """Deep-merge the editable fields into data/settings.local.json; computed and config-owned fields are ignored."""
    rt = rt_of(request)
    async with rt.settings_lock:
        local = settings_svc.deep_merge(rt.local_settings(), settings_svc.strip_read_only(body))
        candidate = settings_svc.deep_merge(rt.seed_settings, local)
        problems = rt.schema.errors("AppSettings", candidate)
        fields = settings_svc.range_problems(candidate)
        if problems or fields:
            raise validation("Invalid settings.", {"fields": [{"field": f, "problem": "out of range"} for f in fields]
                                                   + [{"field": "body", "problem": p} for p in problems[:5]]})
        write_json_atomic(rt.cfg.settings_local_path, local)
        rt.publish(GLOBAL, {"type": "entity.changed", "kind": "settings"})
    return json_response(rt, await settings_body(rt), def_name="AppSettings")


@router.post("/settings/test-connection")
async def post_test_connection(request: Request) -> Response:
    rt = rt_of(request)
    return json_response(rt, await probes.probe_connection(rt.gateway))


class ModelBody(_Model):
    role: probes.Role


@router.post("/settings/test-model")
async def post_test_model(request: Request, body: ModelBody) -> Response:
    rt = rt_of(request)
    return json_response(rt, await probes.probe_model(rt.gateway, rt.settings_doc(), body.role))


class PointsBody(_Model):
    points: Annotated[int, Field(gt=0, le=1_000_000)]


@router.post("/characters/{character_id}/energy/top-up")
async def post_top_up(request: Request, character_id: str, body: PointsBody) -> Response:
    """D-76: needs a usable key (mock parity, OQ-L); gated by today's budget; an `energy_topup` row at $0."""
    rt = rt_of(request)
    rt.gateway.core.require_key()
    p = rt.energy_params()
    now = rt.clock.now()
    day = rt.clock.calendar.today(now).isoformat()
    async with rt.energy_locks.lock(character_id), rt.db.write() as tx:
        spent = await LedgerWriter.spent_on(tx.conn, day) + rt.clock.spend_bias_usd   # bias: `daily_cap` (test mode)
        wire = await energy_writes.top_up(tx, character_id, body.points, p, energy_writes.TopUpBudget(
            spent_today_usd=spent, daily_cap_usd=rt.caps().daily_cap_usd, local_day=day, at=to_iso(now)))
    return json_response(rt, wire, def_name="Energy")


@router.put("/characters/{character_id}/energy/max")
async def put_energy_max(request: Request, character_id: str, body: PointsBody) -> Response:
    """No key needed; in demo mode the settle is frozen (no regeneration is applied by the write)."""
    rt = rt_of(request)
    p = rt.energy_params()
    async with rt.energy_locks.lock(character_id), rt.db.write() as tx:
        wire = await energy_writes.set_max(tx, character_id, body.points, p)
    return json_response(rt, wire, def_name="Energy")


class KeyBody(_Model):
    key: str | None  # required; null deletes the secrets file


@router.put("/settings/key")
async def put_settings_key(request: Request, body: KeyBody) -> Response:
    """Format check only, no network (testConnection does that). PUT, so the body never reaches the idempotency store."""
    rt = rt_of(request)
    rt.keys.set_key(body.key)
    return json_response(rt, await settings_body(rt), def_name="AppSettings")


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
    await rt.ingest.cancel_for(world_id=world_id)  # M5 design D18: indexing stops before its rows go
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
    """`ready` needs Docling installed **and** the completion marker of `horizon models fetch` (M5 design D5)."""
    from horizon.ai.converter import readiness

    return readiness(models_dir)


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
            "docling": docling_status(rt.cfg.models_dir)}
    return json_response(rt, body)


# ── Test-only (HORIZON_TEST=1) ───────────────────────────────────────────────
test_router = APIRouter(prefix="/_test")

SCENARIOS: dict[str, str] = {  # id → description (design D15)
    "character_exhausted": "Reset demo data (seed only), then Takeshi at 0 energy (the exhausted_takeshi variant).",
    "rush_hour": "Peak pricing whatever the clock says.",
    "stream_cut": "The next character turn cuts after 24 tokens with a network error.",
    # M4 (generation-jobs design D12): for jobs started afterwards, until a factory reset; failures land at 60 %.
    "image_fail_partial": "The second image task of each job fails on its first attempt (Retry succeeds).",
    "image_fail_all": "Every image task fails, every attempt.",
    "song_fails": "Theme-song tasks fail on their first attempt.",
    # M6 (http-client-parity design D4, D5).
    "no_worlds": "Delete every world, user worlds included (World Select empty state); Reset demo data restores the seed.",
    "daily_cap": "Today's spend equals the daily cap (a bias, no ledger row): generation and top-ups are refused.",
}
JOB_FAULTS = {"image_fail_partial": "partial", "image_fail_all": "all", "song_fails": "song"}
# Simulated by the client harness (a failing fetch), never by the backend (M6 design D2).
CLIENT_SIDE_SCENARIOS = frozenset({"network_down"})


class ClockBody(_Model):
    freezeAt: str | None = None
    advanceMs: float | None = Field(default=None, ge=0)
    release: bool = False


@test_router.post("/clock")
async def test_clock(request: Request, body: ClockBody) -> Response:
    """Virtual time (session-runtime D2): an advance fires due timers in order and returns once their work settled."""
    rt = rt_of(request)
    if not isinstance(rt.clock, FrozenClock):  # a test-mode runtime normally starts with a released FrozenClock
        rt.clock = FrozenClock(rt.clock.calendar, released=True)
    clock = rt.clock
    if body.release:
        clock.release()
    if body.freezeAt is not None:
        try:
            at: datetime = parse_iso(body.freezeAt)
        except ValueError as e:
            raise validation("freezeAt must be an ISO-8601 instant.", {"field": "freezeAt"}) from e
        clock.set(at)
    if body.advanceMs:
        await clock.advance(body.advanceMs)
    return json_response(rt, {"now": rt.now_iso(), "frozen": clock.frozen})


class ScenarioBody(_Model):
    id: str


@test_router.post("/scenario")
async def test_scenario(request: Request, body: ScenarioBody) -> Response:
    rt = rt_of(request)
    if body.id in CLIENT_SIDE_SCENARIOS:
        raise HorizonHTTPError("validation", f"Scenario {body.id!r} is simulated by the client, not the backend.", status=422,
                               details={"field": "id", "clientSide": True})
    if body.id not in SCENARIOS:
        raise HorizonHTTPError("validation", f"Scenario {body.id!r} is not available on the backend.", status=422,
                               details={"field": "id"})
    rt.clear_scenario_state()   # scenarios replace each other, as on the MockClient (M6 design D3)
    if body.id == "character_exhausted":
        await rt.reset_demo()
        await apply_variant(rt, "exhausted_takeshi")
    elif body.id == "rush_hour":
        rt.clock.period_override = "peak"
        rt.publish(GLOBAL, {"type": "entity.changed", "kind": "settings"})
    elif body.id == "stream_cut":
        rt.stream_faults.append(24)
    elif body.id in JOB_FAULTS:
        rt.job_faults = JOB_FAULTS[body.id]
    elif body.id == "no_worlds":
        await rt.delete_all_worlds()
    elif body.id == "daily_cap":
        async with rt.db.read() as conn:
            spent = await settings_svc.spent_today(conn, rt.clock)
        rt.clock.spend_bias_usd = max(0.0, rt.caps().daily_cap_usd - spent)
        rt.publish(GLOBAL, {"type": "entity.changed", "kind": "settings"})
    return Response(status_code=204)


async def apply_variant(rt: Runtime, variant_id: str) -> None:
    """A `_mock/variants` energy patch (the mock's overlay): current set, regeneration counted from now."""
    import json

    from sqlalchemy import update

    from horizon.db import tables as t

    doc = json.loads((rt.cfg.seed_dir / "_mock" / "variants" / f"{variant_id}.json").read_text(encoding="utf-8"))
    p = rt.energy_params()
    async with rt.db.write() as tx:
        for patch in doc["data"].get("characterPatches", []):
            e = patch.get("energy")
            if not e:
                continue
            await tx.conn.execute(update(t.characters).where(t.characters.c.id == patch["characterId"]).values(
                energy_current=float(e["current"]), energy_as_of=rt.now_iso(), energy_day=p.energy_day()))
            tx.publish(GLOBAL, {"type": "entity.changed", "kind": "character", "id": patch["characterId"]})


class AiProfileBody(_Model):
    profile: Literal["scripted", "naive"] | None = None
    overrides: dict[Literal["turn", "router", "reactions", "host", "director", "summariser", "guardrail", "drafter",
                            "image", "song", "embedder", "knowledge_retriever", "memory_retriever", "converter"],
                    Literal["scripted", "naive"]] | None = None


@test_router.post("/ai-profile")
async def test_ai_profile(request: Request, body: AiProfileBody) -> Response:
    """Test mode: the AI profile for subsequent turns, optionally per port (design D15, OQ-14)."""
    from horizon.ai.profile import ProfileSpec

    rt = rt_of(request)
    overrides: dict[str, Literal["scripted", "naive"]] = {str(k): v for k, v in (body.overrides or {}).items()}
    rt.set_profile(ProfileSpec(profile=body.profile, overrides=overrides, test_mode=rt.cfg.test_mode))
    return Response(status_code=204)


class FixtureAnswer(_Model):
    choice: str | None = None
    confidence: float | None = None
    probabilities: dict[str, float] | None = None
    p: float | None = None
    score: float | None = None


class FixtureItem(_Model):
    purpose: str
    question: str
    answer: FixtureAnswer


class DeciderFixturesBody(_Model):
    set: list[FixtureItem] | None = None
    clear: bool = False


@test_router.post("/decider-fixtures")
async def test_decider_fixtures(request: Request, body: DeciderFixturesBody) -> Response:
    """Test mode: scripted Decider answers keyed by purpose and question (no request, no ledger row)."""
    from horizon.ai.decider import ChoiceAnswer, NoulAnswer, ScoreAnswer

    rt = rt_of(request)
    if body.clear:
        rt.decider_fixtures.clear()
    for item in body.set or []:
        a = item.answer
        answer: ChoiceAnswer | NoulAnswer | ScoreAnswer
        if a.choice is not None:
            answer = ChoiceAnswer(choice=a.choice, confidence=a.confidence, probabilities=a.probabilities)
        elif a.p is not None:
            answer = NoulAnswer(p=a.p)
        elif a.score is not None:
            answer = ScoreAnswer(score=a.score, confidence=a.confidence, probabilities=a.probabilities)
        else:
            raise validation("A fixture answer needs choice, p or score.", {"field": "answer"})
        rt.decider_fixtures.set(item.purpose, item.question, answer)
    return Response(status_code=204)

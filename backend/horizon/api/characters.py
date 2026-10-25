"""Character write routes (http-api "Character write routes"; character-lifecycle spec; doc 03 Characters)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from horizon.api.common import json_response, read_ctx, rt_of
from horizon.api.errors import validation
from horizon.services import characters as svc

router = APIRouter()


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DraftBody(_Model):
    seedPrompt: Annotated[str, Field(min_length=1, max_length=2000)]
    intent: Literal["expert", "companion", "other"]


class LockBody(_Model):
    candidateId: str


PATCH_KEYS = frozenset({*svc.PATCH_FIELDS, "profile", "appearance"})


@router.post("/worlds/{world_id}/characters", status_code=201)
async def create_draft(request: Request, world_id: str, body: DraftBody) -> Response:
    rt = rt_of(request)
    out = await svc.create_draft(rt, read_ctx(rt), world_id, body.seedPrompt, body.intent)
    from horizon.api.common import check

    check(rt, "Character", out["character"])
    check(rt, "GenerationJob", out["job"])
    return json_response(rt, out, status=201)


@router.patch("/characters/{character_id}")
async def patch_character(request: Request, character_id: str, body: Annotated[dict[str, Any], Body()]) -> Response:
    """`CharacterPatch`: the allow-listed top-level fields, plus partial `profile` and `appearance` (deep merge)."""
    rt = rt_of(request)
    unknown = sorted(set(body) - PATCH_KEYS)
    if unknown:
        raise validation(f"Unknown field: {unknown[0]}.", {"fields": [{"field": k, "problem": "not editable"} for k in unknown]})
    for k in ("profile", "appearance"):
        if k in body and body[k] is not None and not isinstance(body[k], dict):
            raise validation(f"{k} must be an object.", {"field": k})
    return json_response(rt, await svc.update_character(rt, read_ctx(rt), character_id, body), def_name="Character")


@router.post("/characters/{character_id}/lock-portrait")
async def lock_portrait(request: Request, character_id: str, body: LockBody) -> Response:
    rt = rt_of(request)
    return json_response(rt, await svc.lock_portrait(rt, read_ctx(rt), character_id, body.candidateId), def_name="Character")


@router.post("/characters/{character_id}/approve")
async def approve(request: Request, character_id: str) -> Response:
    rt = rt_of(request)
    return json_response(rt, await svc.approve(rt, read_ctx(rt), character_id), def_name="Character")


@router.post("/characters/{character_id}/archive")
async def archive(request: Request, character_id: str) -> Response:
    rt = rt_of(request)
    return json_response(rt, await svc.archive(rt, read_ctx(rt), character_id), def_name="Character")


@router.post("/characters/{character_id}/restore")
async def restore(request: Request, character_id: str) -> Response:
    rt = rt_of(request)
    return json_response(rt, await svc.restore(rt, read_ctx(rt), character_id), def_name="Character")


@router.delete("/characters/{character_id}", status_code=204)
async def delete_character(request: Request, character_id: str) -> Response:
    await svc.delete_character(rt_of(request), character_id)
    return Response(status_code=204)


@router.post("/assets/{asset_id}/accept")
async def accept_asset(request: Request, asset_id: str) -> Response:
    rt = rt_of(request)
    return json_response(rt, await svc.accept_asset_version(rt, read_ctx(rt), asset_id), def_name="Character")

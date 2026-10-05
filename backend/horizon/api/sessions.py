"""Session write routes and command routes (http-api "Session write routes", "Session command routes"; doc 03 §3).

Every command answers 202 `{}` once the session's actor accepted it; its effects arrive on the session stream. The
pre-202 rejections are in `sessions/preconditions.py`.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from horizon.api.common import json_response, rt_of
from horizon.sessions import commands, lifecycle
from horizon.sessions.export import export_markdown

router = APIRouter()

Emotion = Literal["neutral", "happy", "sad", "angry", "surprised", "thinking", "embarrassed"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateSessionBody(_Model):
    worldId: str
    mode: Literal["one_on_one", "group", "debate", "watch"]
    characterIds: list[str]
    title: str | None = None
    emotionMode: Literal["llm", "user"] | None = None
    musicPolicy: Literal["character_theme", "follow_speaker", "arena", "scene_bed"] | None = None
    config: dict[str, Any] | None = None
    sides: dict[str, Literal["prop", "opp"]] | None = None
    continuedFrom: str | None = None
    seedSummary: str | None = None


class RenameBody(_Model):
    title: str


class ForkBody(_Model):
    atSeq: int | None = Field(default=None, ge=0)


# ── lifecycle ──
@router.post("/sessions", status_code=201)
async def create_session(request: Request, body: CreateSessionBody) -> Response:
    rt = rt_of(request)
    snap = await lifecycle.create(rt, body.model_dump(exclude_none=True))
    return json_response(rt, snap, status=201, def_name="SessionSnapshot")


@router.patch("/sessions/{session_id}")
async def rename_session(request: Request, session_id: str, body: RenameBody) -> Response:
    rt = rt_of(request)
    return json_response(rt, await lifecycle.rename(rt, session_id, body.title), def_name="Session")


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(request: Request, session_id: str) -> Response:
    await lifecycle.delete_session(rt_of(request), session_id)
    return Response(status_code=204)


@router.post("/sessions/{session_id}/fork", status_code=201)
async def fork_session(request: Request, session_id: str,
                       body: Annotated[ForkBody | None, Body()] = None) -> Response:
    rt = rt_of(request)
    snap = await lifecycle.fork(rt, session_id, body.atSeq if body else None)
    return json_response(rt, snap, status=201, def_name="SessionSnapshot")


@router.post("/sessions/{session_id}/leave", status_code=204)
async def leave_session(request: Request, session_id: str) -> Response:
    await lifecycle.leave(rt_of(request), session_id)
    return Response(status_code=204)


@router.post("/sessions/{session_id}/end", status_code=204)
async def end_session(request: Request, session_id: str) -> Response:
    await lifecycle.end(rt_of(request), session_id)
    return Response(status_code=204)


@router.get("/sessions/{session_id}/export")
async def export_session(request: Request, session_id: str) -> Response:
    rt = rt_of(request)
    from sqlalchemy import select

    from horizon.db import tables as t
    from horizon.services import reads

    async with rt.db.read() as conn:
        snap = await reads.session_snapshot(conn, session_id)
        ids = [p["characterId"] for p in snap["session"]["participants"]]
        ids += [m["author"]["characterId"] for m in snap["messages"] if m["author"].get("characterId")]
        rows = (await conn.execute(select(t.characters.c.id, t.characters.c.profile)
                                   .where(t.characters.c.id.in_(sorted(set(ids)))))).all()
    names = {r[0]: str(r[1].get("name", r[0])) for r in rows}
    md = export_markdown(snap["session"], snap["messages"], names)
    return Response(md, media_type="text/markdown; charset=utf-8")


# ── commands ──
class SendBody(_Model):
    text: str
    mentions: list[str] | None = None


class RegenerateBody(_Model):
    messageId: str


class SetEmotionBody(_Model):
    characterId: str
    emotion: Emotion


class EmotionModeBody(_Model):
    mode: Literal["llm", "user"]


class ResponderPolicyBody(_Model):
    policy: Literal["auto", "everyone", "mentioned"]


class MusicPolicyBody(_Model):
    policy: Literal["character_theme", "follow_speaker", "arena", "scene_bed"]


class OnBody(_Model):
    on: bool


class NextSpeakerBody(_Model):
    characterId: str | None = None


class MuteBody(_Model):
    characterId: str
    muted: bool


class AskBody(_Model):
    characterId: str
    text: str


class TextBody(_Model):
    text: str


class EndBody(_Model):
    withVerdict: bool


class PickBody(_Model):
    side: Literal["prop", "opp"]


class PaceBody(_Model):
    paceMs: Literal[500, 1500, 3000]


class ExtendBody(_Model):
    turns: int | None = Field(default=None, ge=1, le=1000)


COMMAND_BODIES: dict[str, type[BaseModel] | None] = {
    "send": SendBody, "stop": None, "regenerate": RegenerateBody, "set-emotion": SetEmotionBody,
    "set-emotion-mode": EmotionModeBody, "set-responder-policy": ResponderPolicyBody, "set-music-policy": MusicPolicyBody,
    "set-readable-mode": OnBody, "everyone-answer": None, "next-speaker": NextSpeakerBody, "mute": MuteBody,
    "debate/pause": None, "debate/resume": None, "debate/next": None, "debate/auto-advance": OnBody, "debate/ask": AskBody,
    "debate/interject": TextBody, "debate/extend-round": None, "debate/skip-to-closing": None, "debate/end": EndBody,
    "debate/pick": PickBody, "watch/play": None, "watch/pause": None, "watch/step": None, "watch/pace": PaceBody,
    "watch/direct": TextBody, "watch/step-in": TextBody, "watch/extend": ExtendBody, "watch/summarise": None,
}


def _command_route(name: str, model: type[BaseModel] | None) -> None:
    async def run(request: Request, session_id: str, data: dict[str, Any]) -> Response:
        rt = rt_of(request)
        await commands.run_command(rt, session_id, name, data)
        return json_response(rt, {}, status=202)

    if model is None:
        async def endpoint(request: Request, session_id: str) -> Response:
            return await run(request, session_id, {})
    else:
        async def endpoint(request: Request, session_id: str, body: Any) -> Response:  # type: ignore[misc]
            return await run(request, session_id, body.model_dump(exclude_none=True))

        endpoint.__annotations__["body"] = model
    endpoint.__annotations__["request"] = Request
    endpoint.__annotations__["session_id"] = str
    endpoint.__annotations__["return"] = Response
    endpoint.__name__ = "command_" + name.replace("/", "_").replace("-", "_")
    router.add_api_route(f"/sessions/{{session_id}}/{name}", endpoint, methods=["POST"], status_code=202)


for _name, _model in COMMAND_BODIES.items():
    _command_route(_name, _model)

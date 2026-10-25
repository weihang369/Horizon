"""Job write routes (generation-jobs spec; http-api "Job write routes"; doc 03 Jobs).

`POST /jobs` refuses before anything is stored (key → character → one active job → caps). `Idempotency-Key` replays
survive a restart (the idempotency middleware stores the response), so a retried `POST /jobs` never pays twice.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from horizon.api.common import json_response, rt_of
from horizon.api.errors import validation

router = APIRouter()

Emotion = Literal["neutral", "happy", "sad", "angry", "surprised", "thinking", "embarrassed"]
JobKind = Literal["profile_draft", "profile_regenerate", "portrait_candidates", "portrait_tweak", "emotion_set",
                  "emotion_regenerate", "song"]


class StartJobBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    characterId: str
    kind: JobKind
    targetField: Annotated[str, Field(max_length=60)] | None = None
    emotions: Annotated[list[Emotion], Field(min_length=1, max_length=7)] | None = None
    technique: Literal["per_emotion", "expression_sheet"] | None = None
    prompt: Annotated[str, Field(max_length=500)] | None = None
    brief: dict[str, Any] | None = None


def job_input(request: Request, body: StartJobBody) -> dict[str, Any]:
    rt = rt_of(request)
    data = body.model_dump(exclude_none=True)
    if body.brief is not None:
        problems = rt.schema.errors("SongBrief", body.brief)
        if problems:
            raise validation("Invalid song brief.", {"field": "brief", "problems": problems[:3]})
    if body.kind == "profile_regenerate" and not body.targetField:
        raise validation("profile_regenerate needs a targetField.", {"field": "targetField"})
    return data


@router.post("/jobs/estimate")
async def estimate_job(request: Request, body: StartJobBody) -> Response:
    rt = rt_of(request)
    return json_response(rt, {"estimatedCostUsd": await rt.jobs.estimate(job_input(request, body))})


@router.post("/jobs", status_code=201)
async def start_job(request: Request, body: StartJobBody) -> Response:
    rt = rt_of(request)
    job = await rt.jobs.start(job_input(request, body))
    return json_response(rt, job, status=201, def_name="GenerationJob")


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(request: Request, job_id: str) -> Response:
    rt = rt_of(request)
    return json_response(rt, await rt.jobs.cancel(job_id), def_name="GenerationJob")


@router.post("/jobs/{job_id}/tasks/{task_id}/retry")
async def retry_task(request: Request, job_id: str, task_id: str) -> Response:
    rt = rt_of(request)
    return json_response(rt, await rt.jobs.retry(job_id, task_id), def_name="GenerationJob")

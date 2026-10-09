"""Knowledge and memory write routes (http-api "Knowledge and memory write routes", "Knowledge upload limit is
enforced while reading"; knowledge-sources spec; design D3).

`POST /characters/{id}/knowledge` dispatches on `Content-Type`:
- `multipart/form-data`: one `file` part, streamed into `data/tmp/{uuid}.upload` while it is counted (413 past 10 MB,
  before reading when the declared length is already over), then judged by its name and its bytes;
- `application/json`: `{ "type": "text", "title", "text" }` (pasted text, at most 200 KB);
- anything else: 422 `validation`.
A tombstoned or unknown character is 404. A created source is 201 with `status: "indexing"`, announced on the global
stream, and handed to the ingestion worker.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, ValidationError

from horizon.api.common import json_response, rt_of
from horizon.api.errors import validation
from horizon.api.uploads import ENVELOPE, MAX_KNOWLEDGE, stream_file_part, too_large
from horizon.services import reads
from horizon.services.knowledge import sources
from horizon.services.knowledge import validate as v

router = APIRouter()


class TextBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["text"]
    title: str
    text: str


async def _json_body(request: Request, path: str) -> Any:
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > MAX_KNOWLEDGE + ENVELOPE:
            raise too_large(path)
    try:
        return json.loads(bytes(data) or b"null")
    except ValueError as e:
        raise validation("The body isn't valid JSON.", {"field": "body"}) from e


@router.post("/characters/{character_id}/knowledge")
async def add_knowledge(request: Request, character_id: str) -> Response:
    rt = rt_of(request)
    async with rt.db.read() as conn:
        await reads.character_row(conn, character_id, allow_tombstone=False)
    ctype = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if ctype == "multipart/form-data":
        wire = await _add_file(request, character_id)
    elif ctype == "application/json":
        try:
            body = TextBody.model_validate(await _json_body(request, request.url.path))
        except ValidationError as e:
            raise validation("Send pasted text as { type: \"text\", title, text }.", {"field": "body"}) from e
        pasted = v.check_text(body.title, body.text)
        wire = await sources.create_source(rt, character_id, kind=None, title=pasted.title, type_="text",
                                           original_name=None, data=pasted.data)
    else:
        raise validation("Send a file as multipart/form-data, or pasted text as JSON.", {"field": "body"})
    rt.ingest.submit(wire["id"])
    return json_response(rt, wire, status=201, def_name="KnowledgeSource")


async def _add_file(request: Request, character_id: str) -> dict[str, Any]:
    rt = rt_of(request)
    rt.cfg.tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp = rt.cfg.tmp_dir / f"{uuid.uuid4().hex}.upload"
    try:
        with tmp.open("wb") as f:
            part = await stream_file_part(request, limit=MAX_KNOWLEDGE, write=f.write, err=too_large(request.url.path))
        kind = v.kind_of(part.filename, part.content_type)
        await asyncio.to_thread(v.check_content, tmp, kind)
        name = (part.filename or f"upload.{kind}").replace("\\", "/").rsplit("/", 1)[-1][: v.TITLE_MAX]
        return await sources.create_source(rt, character_id, kind=kind, title=name, type_="file", original_name=name,
                                           upload=tmp)
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)


@router.delete("/knowledge/{source_id}")
async def delete_knowledge(request: Request, source_id: str) -> Response:
    await sources.delete_source(rt_of(request), source_id)
    return Response(status_code=204)


@router.post("/knowledge/{source_id}/reindex")
async def reindex_knowledge(request: Request, source_id: str) -> Response:
    rt = rt_of(request)
    return json_response(rt, await sources.reindex_source(rt, source_id), def_name="KnowledgeSource")


@router.delete("/memory/{memory_item_id}")
async def forget_memory(request: Request, memory_item_id: str) -> Response:
    """Forget (long-term-memory spec; doc 02 §3.7): the memory, its versions and every copy of its text."""
    from horizon.services.memory.forget import forget

    await forget(rt_of(request), memory_item_id)
    return Response(status_code=204)

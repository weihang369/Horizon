"""World cover upload (worlds "Upload a world cover"; http-api "Cover upload route"; generation-jobs design D10).

`POST /worlds/{id}/cover` takes `multipart/form-data` with one `file` part:
1. a declared `Content-Length` over 5 MB (plus a 64 KB envelope) is refused before the body is read (413);
2. the body is streamed through a counting multipart parser, so an upload without a length can't pass the limit
   either (413), and the request is never spooled in full;
3. the type is judged by magic bytes (PNG, JPEG, WebP), Pillow verifies it, and it is re-encoded to a 1600×900 WebP
   with a new immutable name (`cover_v{n}.webp`);
4. one transaction stores the `cover` asset row and `worlds.cover = {kind: "upload", url}`, then announces the world.
No key is needed. The idempotency middleware applies the same limit when it buffers a keyed request.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request, Response
from python_multipart.multipart import MultipartParser, parse_options_header
from sqlalchemy import update

from horizon.api.common import json_response, rt_of
from horizon.api.errors import HorizonHTTPError, validation
from horizon.contract import mappers as mp
from horizon.db import tables as t
from horizon.domain.ids import new_id
from horizon.events.bus import GLOBAL
from horizon.services import assets, reads
from horizon.storage.atomic import write_atomic
from horizon.storage.images import ImageRejected, cover_webp, sniff

router = APIRouter()

MAX_COVER = 5 * 1024 * 1024
ENVELOPE = 64 * 1024
ACCEPTED = ["image/png", "image/jpeg", "image/webp"]


def body_limit(path: str) -> int | None:
    """The most a request body may be on this path (the idempotency middleware buffers keyed POSTs)."""
    parts = path.rstrip("/").split("/")
    return MAX_COVER + ENVELOPE if len(parts) >= 3 and parts[-1] == "cover" and parts[-3] == "worlds" else None


def too_large() -> HorizonHTTPError:
    return HorizonHTTPError("validation", "Covers can be at most 5 MB.", status=413,
                            details={"field": "file", "limit": MAX_COVER})


class _TooLarge(Exception):
    pass


async def read_file_part(request: Request, *, limit: int) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit + ENVELOPE:
        raise too_large()
    ctype, params = parse_options_header(request.headers.get("content-type", ""))
    boundary = params.get(b"boundary")
    if ctype != b"multipart/form-data" or not boundary:
        raise validation("Send the cover as multipart/form-data with a file part.", {"field": "file"})
    state: dict[str, Any] = {"field": b"", "value": b"", "name": None, "headers": {}, "file": None}
    chunks: list[bytes] = []
    size = 0

    def on_header_field(data: bytes, start: int, end: int) -> None:
        state["field"] += data[start:end]

    def on_header_value(data: bytes, start: int, end: int) -> None:
        state["value"] += data[start:end]

    def on_header_end() -> None:
        state["headers"][state["field"].lower()] = state["value"]
        state["field"], state["value"] = b"", b""

    def on_headers_finished() -> None:
        _disp, opts = parse_options_header(state["headers"].get(b"content-disposition", b""))
        state["name"] = opts.get(b"name")
        state["headers"] = {}

    def on_part_data(data: bytes, start: int, end: int) -> None:
        nonlocal size
        if state["name"] != b"file":
            return
        size += end - start
        if size > limit:
            raise _TooLarge()
        chunks.append(data[start:end])

    def on_part_end() -> None:
        if state["name"] == b"file":
            state["file"] = True
        state["name"] = None

    parser = MultipartParser(boundary, {"on_header_field": on_header_field, "on_header_value": on_header_value,
                                        "on_header_end": on_header_end, "on_headers_finished": on_headers_finished,
                                        "on_part_data": on_part_data, "on_part_end": on_part_end})
    total = 0
    try:
        async for chunk in request.stream():
            total += len(chunk)
            if total > limit + ENVELOPE:
                raise _TooLarge()
            parser.write(chunk)
        parser.finalize()
    except _TooLarge as e:
        raise too_large() from e
    except ValueError as e:
        raise validation("The upload isn't valid multipart/form-data.", {"field": "file"}) from e
    if not state["file"]:
        raise validation("Add the image as a `file` part.", {"field": "file"})
    return b"".join(chunks)


@router.post("/worlds/{world_id}/cover")
async def upload_cover(request: Request, world_id: str) -> Response:
    rt = rt_of(request)
    async with rt.db.read() as conn:
        await reads.world_row(conn, world_id)
    data = await read_file_part(request, limit=MAX_COVER)
    if sniff(data) is None:
        raise validation("Covers must be PNG, JPEG or WebP.", {"field": "file", "accepted": ACCEPTED})
    try:
        derived = await asyncio.to_thread(cover_webp, data)
    except ImageRejected as e:
        raise validation(str(e), {"field": "file", "reason": e.reason}) from e
    async with rt.db.write() as tx:
        await reads.world_row(tx.conn, world_id)
        version = await assets.next_cover_version(tx.conn, world_id)
        rel = assets.cover_rel(world_id, version)
        await asyncio.to_thread(write_atomic, rt.cfg.assets_dir / rel, derived.data)
        now = rt.now_iso()
        await tx.conn.execute(t.image_assets.insert().values(
            id=new_id("emo"), world_id=world_id, character_id=None, job_id=None, kind="cover", emotion=None,
            variant="default", status="ready", rel_path=rel, width=derived.width, height=derived.height, format="webp",
            bytes=derived.size, vfx_preset="none", generation=None, version=version, is_active=True, selected=False,
            ord=0, created_at=now))
        await tx.conn.execute(update(t.worlds).where(t.worlds.c.id == world_id).values(
            cover={"kind": "upload", "url": mp.rel_to_url(rel)}, updated_at=now))
        tx.publish(GLOBAL, {"type": "entity.changed", "kind": "world", "id": world_id, "worldId": world_id})
        world = await reads.get_world(tx.conn, world_id)
    return json_response(rt, world, def_name="World")

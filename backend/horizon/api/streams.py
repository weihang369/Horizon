"""SSE streams (doc 03 §4, event-streams spec).

- `GET /events` (global): `data:` = one `GlobalEvent`; not stored, no replay.
- `GET /sessions/{id}/stream`: `id:` = event seq, `event:` = type, `data:` = the whole `SessionEvent` (`{ id, sessionId,
  seq, at, type, payload }`; the client needs `at` and the event id, which the SSE fields can't carry). The live queue is
  registered **first**; then stored events above `max(sinceSeq, Last-Event-ID)` are replayed in short read
  transactions; then the queue is drained, skipping `seq ≤ lastSent`. An unknown session is a 404 before streaming.

Both send a keepalive comment every `rt.sse_ping_sec` (15 s) with `Cache-Control: no-cache` and
`X-Accel-Buffering: no`, so proxies (Vite) don't buffer.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from horizon.api.common import check, rt_of
from horizon.events.bus import GLOBAL, session_channel
from horizon.services import reads

router = APIRouter()

HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
REPLAY_PAGE = 200


def _dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"))


@router.get("/events")
async def global_stream(request: Request) -> EventSourceResponse:
    rt = rt_of(request)
    sub = rt.bus.subscribe(GLOBAL)

    async def gen() -> AsyncIterator[dict[str, str]]:
        try:
            while True:
                event = await sub.get()
                if event is None:
                    return
                yield {"data": _dumps(event)}
        finally:
            rt.bus.unsubscribe(sub)

    return EventSourceResponse(gen(), ping=rt.sse_ping_sec, headers=HEADERS)


def _parse_last_event_id(request: Request) -> int:
    raw = request.headers.get("last-event-id")
    try:
        return int(raw) if raw else 0
    except ValueError:
        return 0


@router.get("/sessions/{session_id}/stream")
async def session_stream(request: Request, session_id: str, sinceSeq: int = 0) -> EventSourceResponse:
    rt = rt_of(request)
    async with rt.db.read() as conn:
        await reads.session_row(conn, session_id)  # 404 before the stream opens
    start = max(sinceSeq, _parse_last_event_id(request))
    sub = rt.bus.subscribe(session_channel(session_id))  # register the live queue before replaying

    def frame(e: dict[str, Any]) -> dict[str, str]:
        check(rt, "SessionEvent", e)
        return {"id": str(e["seq"]), "event": e["type"], "data": _dumps(e)}

    async def gen() -> AsyncIterator[dict[str, str]]:
        last = start
        try:
            while True:
                async with rt.db.read() as conn:
                    page = await reads.events_after(conn, session_id, last, REPLAY_PAGE)
                for e in page:
                    yield frame(e)
                    last = e["seq"]
                if len(page) < REPLAY_PAGE:
                    break
            while True:
                live = await sub.get()
                if live is None:
                    return
                if live["seq"] <= last:
                    continue
                yield frame(live)
                last = live["seq"]
        finally:
            rt.bus.unsubscribe(sub)

    return EventSourceResponse(gen(), ping=rt.sse_ping_sec, headers=HEADERS)

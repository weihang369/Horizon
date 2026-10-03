"""ASGI middleware (pure ASGI, so SSE streams aren't buffered).

- `RequestContext`: a `request_id` per request (echoed as `X-Request-Id`), a JSON access-log line, and the
  lifecycle gate (requests wait while a factory reset runs). Streams are logged but never counted as in-flight.
- `Idempotency` (doc 03 §1, design D10): `POST` + `Idempotency-Key` → stored in `idempotency_keys` (24 h, survives
  restarts). Same key + same body → the stored status and body; a different body → 409; while the first request is
  still in flight → wait for it. A 5xx result is not kept, so a retry runs again.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from horizon.api.errors import conflict
from horizon.db import tables as t
from horizon.domain.timeutil import to_iso
from horizon.logs import request_id_var

log = logging.getLogger("horizon.http")

STREAM_SUFFIXES = ("/events", "/stream")
UNGATED_SUFFIXES = ("/admin/factory-reset", "/health")
TTL = timedelta(hours=24)


def _is_stream(path: str) -> bool:
    return path.endswith(STREAM_SUFFIXES)


class RequestContext:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        rid = uuid.uuid4().hex[:16]
        token = request_id_var.set(rid)
        started = time.perf_counter()
        status = {"code": 500}

        async def _send(msg: Message) -> None:
            if msg["type"] == "http.response.start":
                status["code"] = msg["status"]
                msg["headers"] = [*msg.get("headers", []), (b"x-request-id", rid.encode())]
            await send(msg)

        rt = scope["app"].state.rt
        path: str = scope["path"]
        try:
            if _is_stream(path) or path.endswith(UNGATED_SUFFIXES):
                await self.app(scope, receive, _send)
            else:
                async with rt.gate.request():
                    await self.app(scope, receive, _send)
        finally:
            log.info("%s %s %s", scope["method"], path, status["code"],
                     extra={"method": scope["method"], "path": path, "status": status["code"],
                            "ms": round((time.perf_counter() - started) * 1000, 1)})
            request_id_var.reset(token)


class Idempotency:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._waiting: dict[str, asyncio.Event] = {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or scope["method"] != "POST" or "/_test/" in path or path.endswith("/admin/factory-reset"):
            await self.app(scope, receive, send)
            return
        key = next((v.decode() for k, v in scope["headers"] if k == b"idempotency-key"), None)
        if not key:
            await self.app(scope, receive, send)
            return
        rt = scope["app"].state.rt
        body = b""
        more = True
        while more:
            msg = await receive()
            body += msg.get("body", b"")
            more = bool(msg.get("more_body", False))
        sha = hashlib.sha256(body).hexdigest()

        while True:
            async with rt.db.write() as tx:
                row = (await tx.conn.execute(select(t.idempotency_keys).where(t.idempotency_keys.c.key == key))).mappings().first()
                now = rt.now_iso()
                if row is not None and row["expires_at"] < now:
                    await tx.conn.execute(delete(t.idempotency_keys).where(t.idempotency_keys.c.key == key))
                    row = None
                if row is None:
                    await tx.conn.execute(t.idempotency_keys.insert().values(
                        key=key, method="POST", path=path, body_sha256=sha, status=None, response=None, content_type=None,
                        state="in_flight", created_at=now, expires_at=to_iso(rt.clock.now() + TTL)))
                    self._waiting[key] = asyncio.Event()
                    break
            if row["body_sha256"] != sha or row["path"] != path:
                err = conflict("This Idempotency-Key was used for a different request.", {"field": "Idempotency-Key"})
                await _send_raw(send, err.status, json.dumps(err.body(), separators=(",", ":")), "application/json")
                return
            if row["state"] == "done":
                await _send_raw(send, int(row["status"]), row["response"] or "", row["content_type"])
                return
            ev = self._waiting.get(key)
            if ev is not None:
                await ev.wait()
            else:
                await asyncio.sleep(0.05)

        captured: dict[str, Any] = {"status": 500, "ctype": None, "body": b""}

        async def _receive() -> Message:
            return {"type": "http.request", "body": body, "more_body": False}

        async def _send(msg: Message) -> None:
            if msg["type"] == "http.response.start":
                captured["status"] = msg["status"]
                captured["ctype"] = next((v.decode() for k, v in msg.get("headers", []) if k == b"content-type"), None)
            elif msg["type"] == "http.response.body":
                captured["body"] += msg.get("body", b"")
            await send(msg)

        try:
            await self.app(scope, _receive, _send)
        finally:
            async with rt.db.write() as tx:
                if captured["status"] >= 500:
                    await tx.conn.execute(delete(t.idempotency_keys).where(t.idempotency_keys.c.key == key))
                else:
                    await tx.conn.execute(t.idempotency_keys.update().where(t.idempotency_keys.c.key == key).values(
                        state="done", status=captured["status"], response=captured["body"].decode("utf-8"),
                        content_type=captured["ctype"]))
            ev = self._waiting.pop(key, None)
            if ev is not None:
                ev.set()


async def _send_raw(send: Send, status: int, body: str, ctype: str | None) -> None:
    headers = [(b"content-type", (ctype or "application/json").encode()), (b"idempotent-replay", b"true")]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body.encode("utf-8")})

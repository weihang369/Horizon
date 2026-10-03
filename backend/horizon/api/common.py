"""Shared route helpers: the runtime, a read context, and contract-checked JSON responses (design D1).

In test mode every JSON body is validated against its `schema.json` definition before it is sent; a mismatch is a
500 that names the definition, so the whole test suite enforces "every response validates".
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from horizon.api.errors import HorizonHTTPError
from horizon.domain.timeutil import to_ms
from horizon.runtime import Runtime
from horizon.services.reads import ReadContext


def rt_of(request: Request) -> Runtime:
    rt: Runtime = request.app.state.rt
    return rt


def read_ctx(rt: Runtime) -> ReadContext:
    return ReadContext(now_ms=to_ms(rt.clock.now()), est_reply_points=rt.est_reply_points(), demo_mode=True)


def check(rt: Runtime, def_name: str, value: Any) -> None:
    if not rt.cfg.test_mode:
        return
    problems = rt.schema.errors(def_name, value)
    if problems:
        raise HorizonHTTPError("provider_error", f"Response failed contract {def_name}: {problems[:3]}", status=500,
                               retryable=False)


def check_many(rt: Runtime, def_name: str, values: list[Any]) -> None:
    for v in values:
        check(rt, def_name, v)


def json_response(rt: Runtime, body: Any, *, status: int = 200, def_name: str | None = None, items: str | None = None,
                  page_of: str | None = None) -> Response:
    """Return JSON, contract-checked in test mode: `def_name` (one value), `items` (a list) or `page_of`
    (`{ items, nextCursor }`). `None` is sent as JSON `null` (e.g. `trace` and `song` may be null)."""
    if body is not None:
        if def_name:
            check(rt, def_name, body)
        if items:
            check_many(rt, items, body)
        if page_of:
            if rt.cfg.test_mode and set(body) != {"items", "nextCursor"}:
                raise HorizonHTTPError("provider_error", "Malformed page", status=500, retryable=False)
            check_many(rt, page_of, body["items"])
    return JSONResponse(body, status_code=status)

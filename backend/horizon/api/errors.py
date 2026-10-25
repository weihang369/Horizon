"""The error envelope (doc 03 §2): every non-2xx body is `{ "error": { code, message, retryable, retryAfterSec?, details? } }`.

`code` is a contract `ErrorCode`. Defaults for `retryable` and the HTTP status come from one table, which a test
compares with `frontend/src/contract/errors.ts` through `tests/fixtures/errors/codes.json`.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from horizon.gateway.errors import ProviderError
from horizon.gateway.redact import redact, redact_obj

log = logging.getLogger("horizon.api")

DEFAULT_RETRYABLE: dict[str, bool] = {
    "missing_key": False, "invalid_key": False, "insufficient_credits": True, "rate_limited": True,
    "content_refused": True, "provider_error": True, "daily_budget_exceeded": False, "creation_budget_exceeded": False,
    "energy_exhausted": False, "timeout": True, "network": True, "not_found": False, "validation": False, "conflict": False,
}
DEFAULT_STATUS: dict[str, int | None] = {
    "missing_key": 400, "invalid_key": 401, "insufficient_credits": 402, "rate_limited": 429, "content_refused": 451,
    "provider_error": 502, "daily_budget_exceeded": 402, "creation_budget_exceeded": 402, "energy_exhausted": 402,
    "timeout": 504, "network": None, "not_found": 404, "validation": 422, "conflict": 409,
}


class HorizonHTTPError(Exception):
    def __init__(self, code: str, message: str, *, status: int | None = None, retryable: bool | None = None,
                 details: dict[str, Any] | None = None, retry_after: int | None = None) -> None:
        super().__init__(message)
        if code not in DEFAULT_RETRYABLE:
            raise ValueError(f"unknown ErrorCode {code!r}")
        self.code = code
        self.message = message
        self.status = status if status is not None else (DEFAULT_STATUS[code] or 500)
        self.retryable = DEFAULT_RETRYABLE[code] if retryable is None else retryable
        self.details = details
        self.retry_after = retry_after

    def body(self) -> dict[str, Any]:
        # Redacted on the way out (NFR-12): provider messages and details may echo the key.
        err: dict[str, Any] = {"code": self.code, "message": redact(self.message), "retryable": self.retryable}
        if self.retry_after is not None:
            err["retryAfterSec"] = self.retry_after
        if self.details is not None:
            err["details"] = redact_obj(self.details)
        return {"error": err}


def not_found(what: str = "Record") -> HorizonHTTPError:
    return HorizonHTTPError("not_found", f"{what} not found.")


def validation(message: str, details: dict[str, Any] | None = None, *, status: int = 422) -> HorizonHTTPError:
    return HorizonHTTPError("validation", message, status=status, details=details)


def conflict(message: str, details: dict[str, Any] | None = None) -> HorizonHTTPError:
    return HorizonHTTPError("conflict", message, details=details)


def unavailable(milestone: str) -> HorizonHTTPError:
    return HorizonHTTPError("validation", "Not available on the local backend yet.", status=400,
                            details={"availableIn": milestone})


def error_response(err: HorizonHTTPError) -> JSONResponse:
    headers = {"Retry-After": str(err.retry_after)} if err.retry_after is not None else None
    return JSONResponse(err.body(), status_code=err.status, headers=headers)


def from_provider(e: ProviderError) -> HorizonHTTPError:
    """A gateway failure as the API's error envelope (doc 03 §2 statuses; the message is already redacted)."""
    return HorizonHTTPError(e.code, e.message, retry_after=e.retry_after)


def install(app: FastAPI) -> None:
    @app.exception_handler(HorizonHTTPError)
    async def _horizon(_req: Request, exc: HorizonHTTPError) -> JSONResponse:
        return error_response(exc)

    @app.exception_handler(ProviderError)
    async def _provider(_req: Request, exc: ProviderError) -> JSONResponse:
        return error_response(from_provider(exc))

    @app.exception_handler(RequestValidationError)
    async def _invalid(_req: Request, exc: RequestValidationError) -> JSONResponse:
        fields = []
        for e in exc.errors():
            loc = [str(x) for x in e.get("loc", ()) if x not in ("body", "query", "path", "header")]
            fields.append({"field": ".".join(loc) or "body", "problem": str(e.get("msg", "invalid"))})
        first = fields[0]["field"] if fields else "body"
        return error_response(validation(f"Invalid request: {first}.", {"fields": fields}))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_req: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            return error_response(not_found("Route"))
        if exc.status_code == 405:
            return error_response(validation("Method not allowed.", status=405))
        code = "validation" if 400 <= exc.status_code < 500 else "provider_error"
        return error_response(HorizonHTTPError(code, str(exc.detail), status=exc.status_code))

    @app.exception_handler(Exception)
    async def _unhandled(req: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error on %s %s", req.method, req.url.path)
        return error_response(HorizonHTTPError("provider_error", "Something went wrong on the Horizon server.",
                                               status=500, retryable=False))

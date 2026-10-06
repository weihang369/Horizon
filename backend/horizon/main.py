"""The app factory (doc 01). `uvicorn horizon.main:create_app --factory` (via `horizon serve`) builds one app with one
Runtime; the lifespan runs startup and shutdown.
"""

from __future__ import annotations

import copy
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse

from horizon import __version__
from horizon.api import assets, characters, errors, jobs, routes, sessions, streams, uploads
from horizon.api.middleware import Idempotency, RequestContext
from horizon.config import Config, load_config
from horizon.runtime import Runtime

API = "/api/v1"


def create_app(cfg: Config | None = None, runtime: Runtime | None = None) -> FastAPI:
    rt = runtime or Runtime(cfg or load_config())

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await rt.start()
        try:
            yield
        finally:
            await rt.stop()

    app = FastAPI(title="Horizon", version=__version__, docs_url="/api/docs",
                  openapi_url="/api/openapi.json", lifespan=lifespan)
    app.state.rt = rt
    errors.install(app)
    app.include_router(routes.router, prefix=API)
    app.include_router(sessions.router, prefix=API)
    app.include_router(jobs.router, prefix=API)
    app.include_router(characters.router, prefix=API)
    app.include_router(uploads.router, prefix=API)
    app.include_router(streams.router, prefix=API)
    if rt.cfg.test_mode:
        app.include_router(routes.test_router, prefix=API)
    app.include_router(assets.router)
    app.add_middleware(Idempotency)
    app.add_middleware(RequestContext)
    app.openapi = lambda: _openapi(app, rt)  # type: ignore[method-assign]
    if rt.cfg.static_dir:
        _mount_spa(app, rt.cfg.static_dir)
    return app


def _openapi(app: FastAPI, rt: Runtime) -> dict[str, Any]:
    """OpenAPI with the contract's `$defs` as component schemas (design D1)."""
    if app.openapi_schema:
        return app.openapi_schema
    spec = get_openapi(title=app.title, version=app.version, routes=app.routes)
    comps = spec.setdefault("components", {}).setdefault("schemas", {})
    defs = copy.deepcopy(rt.schema.defs)
    comps.update(json.loads(json.dumps(defs).replace("#/$defs/", "#/components/schemas/")))
    app.openapi_schema = spec
    return spec


def _mount_spa(app: FastAPI, dist: Path) -> None:
    """`npm run demo`: serve the built frontend on the same port; unknown paths fall back to index.html."""
    index = dist / "index.html"

    @app.get("/{full:path}", include_in_schema=False)
    def spa(full: str) -> FileResponse:  # sync: FastAPI runs it in a thread (filesystem checks)
        if full.startswith("api/"):
            raise errors.not_found("Route")
        target = (dist / full).resolve()
        if full and target.is_relative_to(dist.resolve()) and target.is_file():
            return FileResponse(target)
        return FileResponse(index)

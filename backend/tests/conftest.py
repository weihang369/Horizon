"""Shared fixtures: an app on a temporary `data/` directory, driven in-process through httpx's ASGI transport.

`api` runs in test mode (`HORIZON_TEST=1`: response validation on, `_mock` overlays loaded, `/_test/*` mounted);
`api_normal` runs like a user's install. The clock is frozen at the MockClient harness's START
(Saturday 2026-10-03 11:00 MYT, off-peak) so derived values are deterministic.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI

from horizon.config import Config, load_config
from horizon.domain.clock import FrozenClock, calendar_for
from horizon.main import create_app
from horizon.runtime import Runtime

START = datetime(2026, 10, 3, 3, 0, tzinfo=UTC)
SEED_DIR = Path(__file__).resolve().parents[2] / "seed"


@dataclass
class Api:
    client: httpx.AsyncClient
    rt: Runtime
    app: FastAPI
    data_dir: Path

    async def get(self, path: str, **kw: Any) -> httpx.Response:
        return await self.client.get(path, **kw)

    async def json(self, path: str, status: int = 200, **kw: Any) -> Any:
        r = await self.client.get(path, **kw)
        assert r.status_code == status, f"{path}: {r.status_code} {r.text[:300]}"
        return r.json()


def make_config(data_dir: Path, *, test_mode: bool) -> Config:
    env = {"HORIZON_DATA_DIR": str(data_dir)}
    if test_mode:
        env["HORIZON_TEST"] = "1"
    return load_config(environ=env)


@pytest.fixture
async def make_api(tmp_path: Path) -> AsyncIterator[Callable[..., Any]]:
    opened: list[tuple[httpx.AsyncClient, LifespanManager]] = []

    async def factory(*, test_mode: bool = True, data_dir: Path | None = None) -> Api:
        cfg = make_config(data_dir or tmp_path / "data", test_mode=test_mode)
        rt = Runtime(cfg, clock=FrozenClock(calendar_for(cfg.tz), START))
        app = create_app(cfg, runtime=rt)
        mgr = LifespanManager(app, startup_timeout=60, shutdown_timeout=60)
        await mgr.__aenter__()
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                                     base_url="http://127.0.0.1")
        opened.append((client, mgr))
        return Api(client=client, rt=rt, app=app, data_dir=cfg.data_dir)

    yield factory
    for client, mgr in reversed(opened):
        await client.aclose()
        await mgr.__aexit__(None, None, None)


@pytest.fixture
async def api(make_api: Callable[..., Any]) -> Api:
    a: Api = await make_api(test_mode=True)
    return a


@pytest.fixture
async def api_normal(make_api: Callable[..., Any]) -> Api:
    a: Api = await make_api(test_mode=False)
    return a


# ── A real server (SSE can't be tested through httpx's ASGI transport, which buffers whole responses) ──
@dataclass
class Live:
    base: str
    rt: Runtime

    def publish(self, channel: str, event: dict[str, Any]) -> None:
        assert self.rt.loop is not None
        self.rt.loop.call_soon_threadsafe(self.rt.bus.publish, channel, event)


def _free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def live(tmp_path: Path) -> Any:
    import threading
    import time

    import uvicorn

    cfg = make_config(tmp_path / "live-data", test_mode=True)
    rt = Runtime(cfg, clock=FrozenClock(calendar_for(cfg.tz), START))
    rt.sse_ping_sec = 0.2
    app = create_app(cfg, runtime=rt)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None, lifespan="on"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 60
    while not server.started:
        assert time.time() < deadline, "server did not start"
        time.sleep(0.05)
    yield Live(base=f"http://127.0.0.1:{port}", rt=rt)
    server.should_exit = True
    thread.join(timeout=30)

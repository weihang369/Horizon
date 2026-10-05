"""Manual live session check (M3 task 10.5, design D11/D12). NEVER part of CI.

Runs only with `HORIZON_LIVE=1` and an OpenRouter key in the environment or the repo's `.env` (put there by you; never
pasted into chat). With a key and no `HORIZON_AI_PROFILE`, the profile is `naive`: one 1:1 reply from the DeepSeek
TurnEngine, then one group send routed by the Jev router, on the real clock. It prints the summed `cost_usd` of the
run's ledger rows (`is_seed = 0`) and asserts it is ≤ $0.05.

    PowerShell:  $env:HORIZON_LIVE=1; uv run pytest -m live -s tests/live/test_live_sessions.py
    bash:        HORIZON_LIVE=1 uv run pytest -m live -s tests/live/test_live_sessions.py
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager
from sqlalchemy import text

from horizon.config import load_config
from horizon.main import create_app
from horizon.runtime import Runtime

pytestmark = pytest.mark.live
BUDGET_USD = 0.05
API = "/api/v1"


async def _wait_reply(client: httpx.AsyncClient, sid: str, count: int, wait_s: float = 90) -> list[dict[str, Any]]:
    loop = asyncio.get_running_loop()
    end = loop.time() + wait_s
    while loop.time() < end:
        msgs = (await client.get(f"{API}/sessions/{sid}/messages", params={"limit": 1000})).json()["items"]
        replies = [m for m in msgs if m["author"]["type"] == "character"]
        if len(replies) >= count and all(m["status"] != "streaming" for m in replies):
            await asyncio.sleep(1.5)  # let the turn's trace and any second responder land
            return [m for m in (await client.get(f"{API}/sessions/{sid}/messages", params={"limit": 1000})).json()["items"]
                    if m["author"]["type"] == "character"]
        await asyncio.sleep(0.5)
    raise AssertionError(f"no reply within {wait_s}s")


async def test_live_naive_sessions(tmp_path: Path) -> None:
    cfg = load_config()  # env > .env, normal mode (test mode never reads a key)
    if os.environ.get("HORIZON_LIVE") != "1" or cfg.openrouter_key is None:
        pytest.skip("live run: set HORIZON_LIVE=1 and OPENROUTER_API_KEY (env or .env)")
    cfg = replace(cfg, data_dir=tmp_path / "live-sessions", test_mode=False, ai_env={})
    rt = Runtime(cfg)
    app = create_app(cfg, runtime=rt)
    async with LifespanManager(app, startup_timeout=60, shutdown_timeout=60), httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1", timeout=60) as client:
        assert rt.ai.impl("turn", key_set=True) == "naive" and rt.ai.impl("router", key_set=True) == "naive"
        one = (await client.post(f"{API}/sessions", json={"worldId": "wld_seedMeridian", "mode": "one_on_one",
                                                          "characterIds": ["chr_seedAmara"]})).json()
        sid = one["session"]["id"]
        await _wait_reply(client, sid, 1)  # the greeting
        r = await client.post(f"{API}/sessions/{sid}/send", json={"text": "Quick one: is coffee after a night shift ok?"})
        assert r.status_code == 202, r.text
        replies = await _wait_reply(client, sid, 2)
        reply = replies[-1]
        print(f"\n[1:1] {reply['emotion']} ({reply.get('emotionSource')}): {reply['content'][:160]!r}")
        assert reply["status"] == "complete" and reply["content"]
        await client.post(f"{API}/sessions/{sid}/leave")
        group = (await client.post(f"{API}/sessions", json={"worldId": "wld_seedSunnyHollow", "mode": "group",
                                                            "characterIds": ["chr_seedHana", "chr_seedTakeshi"]})).json()
        gid = group["session"]["id"]
        assert (await client.post(f"{API}/sessions/{gid}/send", json={"text": "What should we cook tonight?"})).status_code == 202
        greplies = await _wait_reply(client, gid, 1)
        routing = greplies[0]["trace"]["routing"]
        print(f"[group] routed to {routing['selected']} (fallback: {routing.get('reason') == 'fallback'}), "
              f"candidates: {routing.get('candidates')}")
        async with rt.db.read() as conn:
            spent = float((await conn.execute(text("SELECT COALESCE(SUM(cost_usd), 0) FROM usage_records WHERE is_seed = 0")))
                          .scalar_one())
        print(f"[spend] ${spent:.6f} for the run")
        assert spent <= BUDGET_USD

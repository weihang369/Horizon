"""Manual live embedding check (knowledge-memory-storage task 10.3, D-64). NEVER part of CI.

Runs only with `HORIZON_LIVE=1` and an OpenRouter key in the environment or the repo's `.env` (put there by you; never
pasted into chat; this test only checks that a key is present and never prints it). In `naive`, on the real clock, it
sends ONE batch of 3 short texts through `QwenEmbedder` in the active embedding space and asserts:

- 1 024 dimensions per vector, each of unit norm (±1e-3);
- exactly one `embedding` ledger row, with the space's model;
- a recorded cost above $0 and below $0.001 (Qwen3 Embedding 8B is about $0.01 per million tokens).

    PowerShell:  $env:HORIZON_LIVE=1; uv run pytest -m live -s tests/live/test_live_embedding.py
    bash:        HORIZON_LIVE=1 uv run pytest -m live -s tests/live/test_live_embedding.py
"""

from __future__ import annotations

import math
import os
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from asgi_lifespan import LifespanManager
from sqlalchemy import text

from horizon.config import load_config
from horizon.db import spaces
from horizon.gateway.context import call_ctx
from horizon.main import create_app
from horizon.runtime import Runtime

pytestmark = pytest.mark.live
TEXTS = ["Hana keeps bees behind the bakery.", "The night shift starts at seven.", "Steep green tea for three minutes."]
MAX_USD = 0.001


async def test_live_qwen_embedding_batch(tmp_path: Path) -> None:
    cfg = load_config()  # env > .env, normal mode (test mode never reads a key)
    if os.environ.get("HORIZON_LIVE") != "1" or cfg.openrouter_key is None:
        pytest.skip("live run: set HORIZON_LIVE=1 and OPENROUTER_API_KEY (env or .env)")
    cfg = replace(cfg, data_dir=tmp_path / "live-embedding", test_mode=False, ai_env={})
    rt = Runtime(cfg)
    app = create_app(cfg, runtime=rt)
    async with LifespanManager(app, startup_timeout=60, shutdown_timeout=60), httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1", timeout=120):
        assert rt.keys.status() == "set"
        assert rt.ai.impl("embedder", key_set=True) == "naive"
        embedder = rt.ai.embedder(True)
        async with rt.db.read() as conn:
            space = await spaces.active(conn)
        assert space.dims == 1024
        out = await embedder.embed(TEXTS, kind="document", space=space,
                                   ctx=call_ctx("embed_doc", world_id="wld_seedSunnyHollow", character_id="chr_seedHana"))
        assert out.cached == [] and len(out.vectors) == len(TEXTS)
        for v in out.vectors:
            assert len(v) == 1024
            assert abs(math.sqrt(sum(x * x for x in v)) - 1.0) <= 1e-3
        async with rt.db.read() as conn:
            rows = [dict(r) for r in (await conn.execute(text(
                "SELECT category, model, cost_usd FROM usage_records WHERE category = 'embedding'"))).mappings()]
        assert len(rows) == 1, rows
        assert rows[0]["model"] == space.model
        cost = float(rows[0]["cost_usd"])
        assert 0 < cost < MAX_USD, cost
        print(f"\nlive embedding: model {space.model}, {len(TEXTS)} texts, cost ${cost:.8f}")

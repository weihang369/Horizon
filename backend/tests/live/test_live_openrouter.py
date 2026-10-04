"""Manual live verification (M2 task 13, design OQ-C). NEVER part of CI.

Runs only with `HORIZON_LIVE=1` and an OpenRouter key in the environment or the repo's `.env` (put there by you; never
pasted into chat). It checks the response shapes the recorded fixtures assume, through the real gateway, and writes a
redacted report to `data/live-report.json` (git-ignored). Total spend is asserted ≤ $0.05 from the ledger.

    PowerShell:  $env:HORIZON_LIVE=1; uv run pytest -m live -s
    bash:        HORIZON_LIVE=1 uv run pytest -m live -s
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from horizon.config import REPO_ROOT, load_config
from horizon.gateway.chat import ChatRequest
from horizon.gateway.context import call_ctx
from horizon.gateway.redact import redact_obj
from horizon.runtime import Runtime

pytestmark = pytest.mark.live
BUDGET_USD = 0.05
REPORT: dict[str, Any] = {}


def _keyed_config(tmp: Path) -> Any:
    cfg = load_config()  # env > .env, normal mode (test mode never reads a key)
    if os.environ.get("HORIZON_LIVE") != "1" or cfg.openrouter_key is None:
        pytest.skip("live run: set HORIZON_LIVE=1 and OPENROUTER_API_KEY (env or .env)")
    from dataclasses import replace
    return replace(cfg, data_dir=tmp / "live-data", test_mode=False)


@pytest.fixture(scope="module")
def tmp_module(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("live")


@pytest.fixture
async def rt(tmp_module: Path) -> AsyncIterator[Runtime]:
    r = Runtime(_keyed_config(tmp_module))
    await r.start()
    try:
        yield r
    finally:
        await r.stop()


def shape(value: Any, depth: int = 3) -> Any:
    """Keys and types, not values (the report must never carry content or the key)."""
    if depth == 0:
        return type(value).__name__
    if isinstance(value, dict):
        return {k: shape(v, depth - 1) for k, v in value.items()}
    if isinstance(value, list):
        return [shape(value[0], depth - 1)] if value else []
    return type(value).__name__


async def test_live_shapes_and_spend(rt: Runtime) -> None:
    gw = rt.gateway
    models = rt.seed_settings["models"]

    REPORT["key"] = shape(dict(await gw.meta.key_info()))
    REPORT["creditsUsd_is_number"] = isinstance(await gw.meta.credits(), float)
    listed = {m: await gw.meta.model_exists(m) for m in models.values()}
    REPORT["models_listed"] = listed

    probe = call_ctx("probe", category="chat")
    req = ChatRequest(model=models["chat"], messages=[{"role": "user", "content": "Say ok."}], max_tokens=1)
    r1 = await gw.chat_complete(req, probe)
    REPORT["chat"] = {"provider": r1.provider, "warning": r1.provider_warning, "cost_reported": r1.usage is not None
                      and r1.usage.cost_usd is not None, "cached_tokens_reported": r1.usage is not None
                      and r1.usage.tokens_cached is not None}
    r2 = await gw.chat_complete(ChatRequest(model=models["chat"], messages=req.messages, max_tokens=1, logprobs=True,
                                            top_logprobs=1), probe)
    REPORT["chat_logprobs_provider"] = r2.provider  # OQ: does require_parameters + logprobs leave DeepSeek?

    chunks = [c async for c in gw.chat_stream(ChatRequest(model=models["chat"], messages=req.messages, max_tokens=4), probe)]
    REPORT["stream"] = {"chunks": len(chunks), "same_generation_id": len({c.generation_id for c in chunks}) == 1,
                        "usage_on_last": chunks[-1].usage is not None if chunks else False}

    info = None
    for _ in range(30):  # OpenRouter indexes a generation ~13 s after the call
        info = await gw.meta.generation(r1.generation_id)
        if info:
            break
        await asyncio.sleep(3)
    REPORT["generation"] = {"found": info is not None, "cost_matches": info is not None and r1.usage is not None
                            and abs(info.cost_usd - (r1.usage.cost_usd or 0)) < 1e-6}

    qs = {"pick": {"type": "choice", "instructions": "Which word is a colour?",
                   "criteria": {"red": "the word red", "table": "the word table", "none": "neither"}},
          "yes": {"type": "noul", "instructions": "Is the sky usually blue in daytime?",
                  "criteria": {"true": "yes", "false": "no"}},
          "warm": {"type": "score", "instructions": "How warm is 'hello friend'?", "criteria": ["cold", "neutral", "warm"]}}
    d = await gw.decide({"note": "a connection check"}, qs, call_ctx("probe", category="decision"))
    REPORT["jev"] = {"answers": shape({k: dict(v) for k, v in d.answers.items()}),
                     "usage": d.usage.__dict__ if d.usage else None}

    vec = await gw.embed(["ping"], call_ctx("probe", category="embedding"), model=models["embedding"])
    REPORT["embedding_dims"] = len(vec[0])

    async with rt.db.read() as conn:
        # only this run's rows: the imported seed carries a demo ledger
        spent = (await conn.execute(text("SELECT COALESCE(SUM(cost_usd), 0) FROM usage_records WHERE is_seed = 0"))).scalar_one()
    REPORT["spent_usd"] = float(spent)
    out = REPO_ROOT / "data" / "live-report.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(redact_obj(REPORT), indent=2), encoding="utf-8")
    print(json.dumps(redact_obj(REPORT), indent=2))
    assert spent <= BUDGET_USD

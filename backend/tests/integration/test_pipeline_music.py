"""Music through the paid-call pipeline (creation-followups task 2.2; provider-gateway "Music request shape")."""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import text

from horizon.gateway.client import BASE_URL
from horizon.gateway.context import call_ctx
from horizon.gateway.errors import ProviderError
from horizon.storage.audio import silent_mp3
from tests.conftest import Api
from tests.gwkit import SlowStream, build_gateway

CHAT = f"{BASE_URL}/v1/chat/completions"
MODEL = "google/lyria-3-clip-preview"
JOB = "job_mockAoiEmotions"   # a seeded test-mode job, so the row's job_id has a target
CTX = call_ctx("song", world_id="wld_seedMeridian", character_id="chr_seedHana", job_id=JOB)


def clip_stream(cost: float | None = 0.04) -> httpx.Response:
    data = base64.b64encode(silent_mp3(4)).decode()
    parts = [{"id": "gen-song-1", "choices": [{"delta": {"audio": {"data": data}}}]},
             {"id": "gen-song-1", "choices": [{"delta": {}, "finish_reason": "stop"}],
              **({"usage": {"cost": cost}} if cost is not None else {})}]
    body = "".join(f"data: {json.dumps(p)}\n\n" for p in parts) + "data: [DONE]\n\n"
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body.encode())


async def rows(api: Api) -> list[Any]:
    async with api.rt.db.read() as conn:
        return list((await conn.execute(text(
            "SELECT * FROM usage_records WHERE is_seed = 0 AND category = 'music'"))).mappings())


@respx.mock
async def test_music_call_writes_one_music_row(api: Api) -> None:
    respx.post(CHAT).mock(return_value=clip_stream(0.04))
    gw = build_gateway(api)
    r = await gw.generate_music(CTX, model=MODEL, prompt="Instrumental theme")
    assert r.audio == silent_mp3(4)
    (row,) = await rows(api)
    assert row["category"] == "music" and row["purpose"] == "song" and row["job_id"] == JOB
    assert row["cost_usd"] == 0.04 and row["cost_source"] == "provider" and row["estimated_cost_usd"] == 0.04
    assert row["generation_id"] == "gen-song-1" and row["model"] == MODEL
    assert gw.book.total() == 0


@respx.mock
async def test_unavailable_model_writes_no_row(api: Api) -> None:
    respx.post(CHAT).mock(return_value=httpx.Response(503, json={"error": {"code": 503, "message": "no endpoints"}}))
    gw = build_gateway(api)
    with pytest.raises(ProviderError) as e:
        await gw.generate_music(CTX, model=MODEL, prompt="x")
    assert e.value.code == "provider_error" and await rows(api) == [] and gw.book.total() == 0


@respx.mock
async def test_timeout_after_send_is_recorded_at_the_song_estimate(api: Api) -> None:
    from dataclasses import replace

    respx.post(CHAT).mock(return_value=httpx.Response(200, headers={"content-type": "text/event-stream"},
                                                      stream=SlowStream([(0.0, ": OPENROUTER PROCESSING\n\n"), (1.0, "")])))
    gw = build_gateway(api)
    gw.cfg = replace(gw.cfg, timeouts=replace(gw.cfg.timeouts, music=0.2, chat_idle=0.2))
    gw.music.cfg = gw.cfg
    with pytest.raises(ProviderError) as e:
        await gw.generate_music(CTX, model=MODEL, prompt="x")
    assert e.value.code == "timeout"
    (row,) = await rows(api)
    assert row["cost_usd"] == 0.04 and row["cost_source"] == "estimate" and row["job_id"] == JOB

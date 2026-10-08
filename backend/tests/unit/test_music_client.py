"""Music client (creation-followups tasks 1.2, 2.1; provider-gateway "Music request shape", design D1–D2)."""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import respx

from horizon.gateway.client import BASE_URL, HttpCore
from horizon.gateway.errors import ProviderError
from horizon.gateway.music import MusicClient
from horizon.storage.audio import silent_mp3
from tests.gwkit import FakeKeys, SlowStream, gateway_config

URL = f"{BASE_URL}/v1/chat/completions"
MODEL = "google/lyria-3-clip-preview"
CLIP = silent_mp3(6)


def sse(*objs: Any, done: bool = True) -> str:
    out = "".join(o if isinstance(o, str) else f"data: {json.dumps(o)}\n\n" for o in objs)
    return out + ("data: [DONE]\n\n" if done else "")


def audio_chunk(data: str, gid: str = "gen-music-1") -> dict[str, Any]:
    return {"id": gid, "provider": "Google AI Studio", "choices": [{"delta": {"audio": {"data": data}}}]}


USAGE = {"id": "gen-music-1", "choices": [{"delta": {}, "finish_reason": "stop"}],
         "usage": {"prompt_tokens": 40, "completion_tokens": 0, "cost": 0.04}}


def thirds(b: bytes) -> list[str]:
    s = base64.b64encode(b).decode()
    n = len(s) // 3
    return [s[:n + 1], s[n + 1:2 * n + 5], s[2 * n + 5:]]   # split anywhere, not on 4-char boundaries


@pytest.fixture
async def music() -> AsyncIterator[MusicClient]:
    core = HttpCore(FakeKeys())
    yield MusicClient(core, gateway_config(music=0.3, chat_idle=0.3))
    await core.aclose()


def stream(text: str) -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=text.encode())


def test_music_timeout_comes_from_seed_pricing() -> None:
    assert gateway_config().timeouts.music == 120.0


@respx.mock
async def test_three_audio_chunks_are_joined_in_order(music: MusicClient) -> None:
    a, b, c = thirds(CLIP)
    respx.post(URL).mock(return_value=stream(sse(": OPENROUTER PROCESSING\n\n", audio_chunk(a), audio_chunk(b),
                                                 audio_chunk(c), USAGE)))
    r = await music.generate(model=MODEL, prompt="Instrumental theme")
    assert r.audio == CLIP and r.chunks == 3
    assert r.generation_id == "gen-music-1" and r.provider == "Google AI Studio"
    assert r.usage is not None and r.usage.cost_usd == 0.04


@respx.mock
async def test_separately_padded_pieces_also_decode(music: MusicClient) -> None:
    half = len(CLIP) // 2 + 1   # odd split: each piece carries its own `=` padding
    pieces = [base64.b64encode(CLIP[:half]).decode(), base64.b64encode(CLIP[half:]).decode()]
    respx.post(URL).mock(return_value=stream(sse(*(audio_chunk(p) for p in pieces), USAGE)))
    assert (await music.generate(model=MODEL, prompt="x")).audio == CLIP


@respx.mock
async def test_body_has_audio_modalities_and_no_main_llm_routing(music: MusicClient) -> None:
    route = respx.post(URL).mock(return_value=stream(sse(audio_chunk(base64.b64encode(CLIP).decode()), USAGE)))
    await music.generate(model=MODEL, prompt="Instrumental theme")
    body = json.loads(route.calls.last.request.content)
    assert body == {"model": MODEL, "messages": [{"role": "user", "content": "Instrumental theme"}],
                    "modalities": ["text", "audio"], "stream": True, "usage": {"include": True}}
    assert "provider" not in body and "models" not in body


@respx.mock
async def test_stream_without_audio_is_malformed_and_may_be_charged(music: MusicClient) -> None:
    respx.post(URL).mock(return_value=stream(sse({"id": "gen-empty", "choices": [{"delta": {"content": "ok"}}]}, USAGE)))
    with pytest.raises(ProviderError) as e:
        await music.generate(model=MODEL, prompt="x")
    assert e.value.code == "provider_error" and e.value.maybe_charged and e.value.generation_id == "gen-empty"


@respx.mock
async def test_error_chunk_is_a_provider_error(music: MusicClient) -> None:
    respx.post(URL).mock(return_value=stream(sse({"id": "gen-err", "error": {"code": 502, "message": "upstream"}})))
    with pytest.raises(ProviderError) as e:
        await music.generate(model=MODEL, prompt="x")
    assert e.value.code == "provider_error" and e.value.maybe_charged and "upstream" in (e.value.message or "")


@respx.mock
async def test_refusal_carries_its_cost(music: MusicClient) -> None:
    refused = {"id": "gen-ref", "choices": [{"delta": {}, "finish_reason": "content_filter"}], "usage": {"cost": 0.0}}
    respx.post(URL).mock(return_value=stream(sse(refused)))
    with pytest.raises(ProviderError) as e:
        await music.generate(model=MODEL, prompt="x")
    assert e.value.code == "content_refused" and e.value.cost_usd == 0.0 and not e.value.maybe_charged


@respx.mock
async def test_no_first_audio_before_the_deadline_is_a_charged_timeout(music: MusicClient) -> None:
    late = f"data: {json.dumps(audio_chunk(base64.b64encode(CLIP).decode()))}\n\n"
    respx.post(URL).mock(return_value=httpx.Response(200, headers={"content-type": "text/event-stream"},
                                                     stream=SlowStream([(0.0, ": OPENROUTER PROCESSING\n\n"), (0.8, late)])))
    with pytest.raises(ProviderError) as e:
        await music.generate(model=MODEL, prompt="x")
    assert e.value.code == "timeout" and e.value.maybe_charged


@respx.mock
async def test_http_errors_map_like_chat(music: MusicClient) -> None:
    respx.post(URL).mock(return_value=httpx.Response(503, json={"error": {"code": 503, "message": "unavailable"}}))
    with pytest.raises(ProviderError) as e:
        await music.generate(model=MODEL, prompt="x")
    assert e.value.code == "provider_error" and not e.value.maybe_charged

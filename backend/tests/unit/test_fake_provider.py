"""FakeOpenRouter (task 4.3): deterministic answers, 401 for sk-or-bad*, and no socket ever opened."""

from __future__ import annotations

import json
import socket
from collections.abc import Iterator

import pytest

from horizon.gateway.client import HttpCore
from horizon.gateway.errors import ProviderError
from horizon.gateway.fake import CHAT_COST, FakeOpenRouter
from tests.gwkit import FakeKeys, block_network


@pytest.fixture
def no_sockets(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    attempts = block_network(monkeypatch)
    yield
    assert attempts == []


def test_guard_blocks_real_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = block_network(monkeypatch)
    with pytest.raises(AssertionError):
        socket.create_connection(("openrouter.ai", 443), timeout=1)
    assert attempts == ["openrouter.ai"]


def core(key: str = "sk-or-test-0001", fake: FakeOpenRouter | None = None) -> tuple[HttpCore, FakeOpenRouter]:
    f = fake or FakeOpenRouter(models=["deepseek/deepseek-v4.1-flash", "bytedance-seed/seedream-5-0-flash"])
    return HttpCore(FakeKeys(key), transport=f.transport()), f


async def test_every_endpoint_answers(no_sockets: None) -> None:
    c, f = core()
    try:
        assert (await c.request("GET", "/v1/key", http_timeout=5)).json()["data"]["label"] == "fake"
        credits = (await c.request("GET", "/v1/credits", http_timeout=5)).json()["data"]
        assert round(credits["total_credits"] - credits["total_usage"], 6) == 4.21
        models = (await c.request("GET", "/v1/models", http_timeout=5)).json()["data"]
        assert {"id": "bytedance-seed/seedream-5-0-flash"} in models
        chat = (await c.request("POST", "/v1/chat/completions", json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
                                http_timeout=5)).json()
        assert chat["choices"][0]["message"]["content"] == "ok" and chat["usage"]["cost"] == CHAT_COST
        gen = (await c.request("GET", "/v1/generation", params={"id": chat["id"]}, http_timeout=5)).json()["data"]
        assert gen["total_cost"] == CHAT_COST
        dec = (await c.request("POST", "/alpha/decisions", json={"model": "typesafe/jev-1.13", "state": {"a": 1}, "questions": {
            "who": {"type": "choice", "instructions": "pick", "criteria": {"amara": "A", "none": "nobody"}},
            "gate": {"type": "noul", "instructions": "need?", "criteria": {"true": "yes", "false": "no"}},
            "tone": {"type": "score", "instructions": "how", "criteria": ["low", "mid", "high"]}}}, http_timeout=5)).json()
        assert dec["answers"]["who"]["choice"] == "amara" and dec["answers"]["gate"] == {"noul": 0.5}
        assert dec["answers"]["tone"]["score"] == 1 and dec["usage"]["output_tokens"] == 0
        emb = (await c.request("POST", "/v1/embeddings", json={"model": "q", "input": ["a", "b"], "dimensions": 8},
                               http_timeout=5)).json()
        assert [d["index"] for d in emb["data"]] == [0, 1] and len(emb["data"][0]["embedding"]) == 8
        assert abs(sum(x * x for x in emb["data"][0]["embedding"]) - 1) < 1e-9
        img = (await c.request("POST", "/v1/images", json={"model": "bytedance-seed/seedream-5-0-flash", "prompt": "p"},
                               http_timeout=5)).json()
        assert img["usage"]["cost"] == 0.018 and img["data"][0]["b64_json"]
    finally:
        await c.aclose()
    assert len(f.requests) == 8


async def test_streaming_chat_is_sse(no_sockets: None) -> None:
    c, _ = core()
    try:
        async with c.stream("POST", "/v1/chat/completions", json={"model": "m", "messages": [], "stream": True},
                            http_timeout=5) as r:
            lines = [ln async for ln in r.aiter_lines() if ln.startswith("data: ")]
    finally:
        await c.aclose()
    assert lines[-1] == "data: [DONE]"
    first = json.loads(lines[0][6:])
    last = json.loads(lines[-2][6:])
    assert first["id"] == last["id"] and last["usage"]["cost"] == CHAT_COST


async def test_bad_key_gets_401_everywhere(no_sockets: None) -> None:
    for path, method in (("/v1/key", "GET"), ("/v1/credits", "GET"), ("/v1/chat/completions", "POST")):
        c, _ = core("sk-or-bad-zzz")
        try:
            with pytest.raises(ProviderError) as e:
                await c.request(method, path, json={} if method == "POST" else None, http_timeout=5)
        finally:
            await c.aclose()
        assert e.value.code == "invalid_key", path


async def test_unknown_generation_is_404(no_sockets: None) -> None:
    c, _ = core()
    try:
        with pytest.raises(ProviderError) as e:
            await c.request("GET", "/v1/generation", params={"id": "gen-nope"}, http_timeout=5)
    finally:
        await c.aclose()
    assert e.value.status == 404


async def test_fake_image_is_a_decodable_portrait_and_counted(no_sockets: None) -> None:
    """provider-gateway "Fake image" (M4): a decodable image with a cost; the images counter goes up by one per call."""
    import io

    from PIL import Image

    from horizon.gateway.images import ImagesClient

    c, f = core()
    try:
        client = ImagesClient(c, 5)
        r1 = await client.generate(model="bytedance-seed/seedream-5-0-flash", prompt="Hana", aspect_ratio="3:4",
                                   refs=["data:image/png;base64,AAAA"])
        assert f.counts["images"] == 1
        r2 = await client.generate(model="bytedance-seed/seedream-5-0-flash", prompt="Hana", aspect_ratio="3:4")
        assert f.counts["images"] == 2 and f.counts["chat"] == 0
    finally:
        await c.aclose()
    with Image.open(io.BytesIO(r1.images[0])) as img:
        assert img.size == (832, 1110)
    assert r1.images[0] == r2.images[0]  # deterministic for the same prompt
    assert r1.usage is not None and r1.usage.cost_usd == 0.018
    body = json.loads(f.requests[0].content)
    assert body["input_references"][0]["type"] == "image_url"
    assert body["input_references"][0]["image_url"]["url"].startswith("data:image/")


async def test_park_holds_the_nth_image_request(no_sockets: None) -> None:
    import asyncio

    from horizon.gateway.images import ImagesClient

    c, f = core()
    gate = f.park_image(2)
    try:
        client = ImagesClient(c, 5)
        await client.generate(model="m", prompt="one")
        second = asyncio.ensure_future(client.generate(model="m", prompt="two"))
        await asyncio.wait_for(f.parked.wait(), 2)
        assert not second.done() and f.counts["images"] == 2
        gate.set()
        assert (await asyncio.wait_for(second, 2)).images
    finally:
        await c.aclose()


async def test_fake_music_streams_a_silent_mp3_and_counts_it(no_sockets: None) -> None:
    """creation-followups task 2.3: an audio-modality chat request gets an MP3 stub in three pieces, at $0.04."""
    from dataclasses import replace

    from horizon.gateway.music import MusicClient
    from horizon.storage.audio import is_mp3, mp3_duration
    from tests.gwkit import gateway_config

    c, f = core()
    cfg = gateway_config()
    try:
        client = MusicClient(c, cfg)
        r = await client.generate(model="google/lyria-3-clip-preview", prompt="Instrumental theme")
        assert is_mp3(r.audio) and mp3_duration(r.audio) == round(8 * 1152 / 44100, 3)
        assert r.chunks == 3 and r.usage is not None and r.usage.cost_usd == 0.04
        assert f.counts["music"] == 1 and f.counts["chat"] == 1

        f.music_mode = "fail"
        with pytest.raises(ProviderError) as e:
            await client.generate(model="m", prompt="x")
        assert e.value.code == "provider_error" and not e.value.maybe_charged

        f.music_mode = "not_mp3"
        assert not is_mp3((await client.generate(model="m", prompt="x")).audio)

        f.music_mode = "stall"
        quick = MusicClient(c, replace(cfg, timeouts=replace(cfg.timeouts, music=0.2)))
        with pytest.raises(ProviderError) as e:
            await quick.generate(model="m", prompt="x")
        assert e.value.code == "timeout" and e.value.maybe_charged
        assert f.counts["music"] == 4
    finally:
        await c.aclose()

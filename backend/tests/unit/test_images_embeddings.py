"""Images and embeddings clients (task 5.3): parsing, batching and order, and the shared error mapping."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import pytest
import respx

from horizon.gateway.client import BASE_URL, HttpCore
from horizon.gateway.embeddings import EmbeddingsClient, batches
from horizon.gateway.errors import ProviderError
from horizon.gateway.images import ImagesClient
from tests.gwkit import FakeKeys, response

IMG = f"{BASE_URL}/v1/images"
EMB = f"{BASE_URL}/v1/embeddings"


@pytest.fixture
async def core() -> AsyncIterator[HttpCore]:
    c = HttpCore(FakeKeys())
    yield c
    await c.aclose()


@respx.mock
async def test_image_generate(core: HttpCore) -> None:
    route = respx.post(IMG).mock(return_value=response("images_ok"))
    r = await ImagesClient(core, 180).generate(model="bytedance-seed/seedream-5-0-flash", prompt="a portrait",
                                               refs=["data:image/png;base64,AAAA"], aspect_ratio="3:4", seed=7)
    sent = json.loads(route.calls.last.request.content)
    # The D-61 shape (run.mjs): `input_references` of type image_url, `n: 1`; no unverified `images` field.
    assert sent["input_references"] == [{"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]
    assert sent["n"] == 1 and sent["aspect_ratio"] == "3:4" and sent["seed"] == 7
    assert "images" not in sent and "resolution" not in sent
    assert r.images[0].startswith(b"\x89PNG") and r.usage is not None and r.usage.cost_usd == 0.018
    assert r.generation_id == "gen-rec-000008"


@respx.mock
async def test_image_data_url_and_malformed(core: HttpCore) -> None:
    respx.post(IMG).mock(side_effect=[
        httpx.Response(200, json={"id": "gen-u", "data": [{"url": "data:image/png;base64,iVBORw0KGgo="}]}),
        httpx.Response(200, json={"id": "gen-m", "data": []}),
    ])
    c = ImagesClient(core, 180)
    assert (await c.generate(model="m", prompt="p")).images[0].startswith(b"\x89PNG")
    with pytest.raises(ProviderError) as e:
        await c.generate(model="m", prompt="p")
    assert e.value.code == "provider_error" and e.value.generation_id == "gen-m" and e.value.maybe_charged


def test_batches_of_32() -> None:
    assert [len(b) for b in batches([str(i) for i in range(70)], 32)] == [32, 32, 6]


@respx.mock
async def test_seventy_texts_three_requests_in_order(core: HttpCore) -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["provider"] == {"order": ["Nebius"], "allow_fallbacks": False}
        items = [{"index": i, "embedding": [float(t)]} for i, t in enumerate(body["input"])]
        return httpx.Response(200, json={"id": "gen-e", "data": list(reversed(items)), "usage": {"cost": 0.0}})

    route = respx.post(EMB).mock(side_effect=answer)
    c = EmbeddingsClient(core, provider="Nebius", batch_size=32, timeout_s=30)
    texts = [str(i) for i in range(70)]
    vectors = [v for b in batches(texts, 32) for v in (await c.embed_batch(b, model="qwen/qwen3-embedding-8b")).vectors]
    assert route.call_count == 3
    assert [v[0] for v in vectors] == [float(i) for i in range(70)]


@respx.mock
async def test_embedding_fixture_reorders(core: HttpCore) -> None:
    respx.post(EMB).mock(return_value=response("embeddings_ok"))
    r = await EmbeddingsClient(core, provider="Nebius", batch_size=32, timeout_s=30).embed_batch(["a", "b"], model="q", dimensions=4)
    assert r.vectors == [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]] and r.provider == "Nebius"


async def test_embedding_batch_limit(core: HttpCore) -> None:
    c = EmbeddingsClient(core, provider="Nebius", batch_size=32, timeout_s=30)
    with pytest.raises(ValueError):
        await c.embed_batch([str(i) for i in range(33)], model="q")


@pytest.mark.parametrize(("fixture", "code"), [("error_402", "insufficient_credits"), ("error_403_moderation", "content_refused")])
@respx.mock
async def test_errors(core: HttpCore, fixture: str, code: str) -> None:
    respx.post(IMG).mock(return_value=response(fixture))
    respx.post(EMB).mock(return_value=response(fixture))
    with pytest.raises(ProviderError) as e1:
        await ImagesClient(core, 180).generate(model="m", prompt="p")
    with pytest.raises(ProviderError) as e2:
        await EmbeddingsClient(core, provider="Nebius", batch_size=32, timeout_s=30).embed_batch(["a"], model="q")
    assert e1.value.code == e2.value.code == code

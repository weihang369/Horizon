"""Meta client (task 5.4, provider-gateway "Free metadata calls"): parsing; meta never needs the ledger or reservations."""

from __future__ import annotations

import ast
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import respx

from horizon.gateway.client import BASE_URL, HttpCore
from horizon.gateway.errors import ProviderError
from horizon.gateway.meta import MetaClient
from tests.gwkit import FakeKeys, response


@pytest.fixture
async def meta() -> AsyncIterator[MetaClient]:
    core = HttpCore(FakeKeys())
    yield MetaClient(core, 10)
    await core.aclose()


@respx.mock
async def test_key_and_credits(meta: MetaClient) -> None:
    respx.get(f"{BASE_URL}/v1/key").mock(return_value=response("key_ok"))
    respx.get(f"{BASE_URL}/v1/credits").mock(return_value=response("credits_ok"))
    assert (await meta.key_info())["is_free_tier"] is False
    assert await meta.credits() == 4.21


@respx.mock
async def test_credits_unavailable_is_none_but_bad_key_raises(meta: MetaClient) -> None:
    route = respx.get(f"{BASE_URL}/v1/credits").mock(return_value=response("error_500"))
    assert await meta.credits() is None
    route.mock(return_value=response("error_401"))
    with pytest.raises(ProviderError) as e:
        await meta.credits()
    assert e.value.code == "invalid_key"


@respx.mock
async def test_generation_lookup(meta: MetaClient) -> None:
    route = respx.get(f"{BASE_URL}/v1/generation").mock(side_effect=[response("generation_404"), response("generation_ok")])
    assert await meta.generation("gen-rec-000001") is None
    info = await meta.generation("gen-rec-000001")
    assert info is not None and info.cost_usd == 0.00041 and info.provider == "DeepSeek" and info.tokens_cached == 1024
    assert route.calls.last.request.url.params["id"] == "gen-rec-000001"


@respx.mock
async def test_model_exists(meta: MetaClient) -> None:
    respx.get(f"{BASE_URL}/v1/models").mock(return_value=response("models_ok"))
    assert await meta.model_exists("bytedance-seed/seedream-5-0-flash")
    assert not await meta.model_exists("nope/nothing")


@respx.mock
async def test_malformed_meta_is_not_charged(meta: MetaClient) -> None:
    respx.get(f"{BASE_URL}/v1/key").mock(return_value=httpx.Response(200, json={"weird": 1}))
    with pytest.raises(ProviderError) as e:
        await meta.key_info()
    assert e.value.code == "provider_error" and not e.value.maybe_charged


def test_meta_never_touches_ledger_or_reservations() -> None:
    src = Path(__file__).resolve().parents[2] / "horizon" / "gateway" / "meta.py"
    imported = {n.module for n in ast.walk(ast.parse(src.read_text(encoding="utf-8"))) if isinstance(n, ast.ImportFrom)}
    assert not any(m and ("ledger" in m or "reservations" in m or "pipeline" in m) for m in imported)

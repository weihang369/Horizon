"""HttpCore (task 4.2, provider-gateway "Retry only when nothing was charged", key guard)."""

from __future__ import annotations

import httpx
import pytest
import respx

from horizon.gateway.client import BASE_URL, HttpCore
from horizon.gateway.errors import ProviderError
from tests.gwkit import TEST_KEY, FakeKeys

URL = f"{BASE_URL}/v1/key"


@pytest.fixture(autouse=True)
def fast_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("horizon.gateway.client.RETRY_PAUSE_S", 0)


async def call(keys: FakeKeys | None = None) -> httpx.Response:
    core = HttpCore(keys or FakeKeys())
    try:
        return await core.request("GET", "/v1/key", http_timeout=5)
    finally:
        await core.aclose()


@respx.mock
async def test_bearer_header_and_success() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200, json={"data": {}}))
    r = await call()
    assert r.status_code == 200
    assert route.calls.last.request.headers["Authorization"] == f"Bearer {TEST_KEY}"


@respx.mock
async def test_connect_error_then_success_is_retried_once() -> None:
    route = respx.get(URL).mock(side_effect=[httpx.ConnectError("refused"), httpx.Response(200, json={})])
    assert (await call()).status_code == 200
    assert route.call_count == 2


@respx.mock
async def test_connect_error_twice_gives_up() -> None:
    route = respx.get(URL).mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(ProviderError) as e:
        await call()
    assert e.value.code == "provider_error" and not e.value.maybe_charged and route.call_count == 2


@respx.mock
async def test_503_empty_body_is_retried_once() -> None:
    route = respx.get(URL).mock(side_effect=[httpx.Response(503), httpx.Response(200, json={})])
    assert (await call()).status_code == 200
    assert route.call_count == 2


@respx.mock
async def test_503_with_a_body_is_not_retried() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(503, json={"error": {"message": "overloaded"}}))
    with pytest.raises(ProviderError) as e:
        await call()
    assert e.value.code == "provider_error" and route.call_count == 1


@respx.mock
async def test_read_error_after_send_is_not_retried_and_may_be_charged() -> None:
    route = respx.get(URL).mock(side_effect=httpx.ReadError("connection reset"))
    with pytest.raises(ProviderError) as e:
        await call()
    assert e.value.maybe_charged and route.call_count == 1


@respx.mock
async def test_read_timeout_is_timeout_and_may_be_charged() -> None:
    respx.get(URL).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(ProviderError) as e:
        await call()
    assert e.value.code == "timeout" and e.value.maybe_charged


@respx.mock
async def test_401_marks_the_key_rejected() -> None:
    respx.get(URL).mock(return_value=httpx.Response(401, json={"error": {"message": "No auth credentials found"}}))
    keys = FakeKeys()
    with pytest.raises(ProviderError) as e:
        await call(keys)
    assert e.value.code == "invalid_key" and keys.rejections == 1 and keys.status() == "invalid"


@respx.mock
async def test_key_guard_runs_before_sending() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200, json={}))
    with pytest.raises(ProviderError) as e:
        await call(FakeKeys(None))
    assert e.value.code == "missing_key"
    rejected = FakeKeys()
    rejected.rejected = True
    with pytest.raises(ProviderError) as e:
        await call(rejected)
    assert e.value.code == "invalid_key"
    assert route.call_count == 0

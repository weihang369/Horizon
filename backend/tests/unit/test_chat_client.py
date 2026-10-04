"""Chat client (task 5.1, provider-gateway "Pinned routing", "Streamed chat", "Per-purpose timeouts", error mapping)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import pytest
import respx

from horizon.gateway.chat import ChatChunk, ChatClient, ChatRequest
from horizon.gateway.client import BASE_URL, HttpCore
from horizon.gateway.errors import ProviderError
from tests.gwkit import FakeKeys, SlowStream, gateway_config, response

URL = f"{BASE_URL}/v1/chat/completions"
REQ = ChatRequest(model="deepseek/deepseek-v4.1-flash", messages=[{"role": "user", "content": "hi"}], max_tokens=64)


@pytest.fixture
async def chat() -> AsyncIterator[ChatClient]:
    core = HttpCore(FakeKeys())
    yield ChatClient(core, gateway_config(chat_first_token=0.2, chat_idle=0.2))
    await core.aclose()


async def drain(c: ChatClient) -> list[ChatChunk]:
    return [ch async for ch in c.stream(REQ)]


@respx.mock
async def test_request_body_pins_routing(chat: ChatClient) -> None:
    route = respx.post(URL).mock(return_value=response("chat_ok"))
    await chat.complete(REQ)
    body = json.loads(route.calls.last.request.content)
    assert body["provider"]["order"] == ["DeepSeek"]
    assert body["provider"]["require_parameters"] is True
    assert body["provider"]["data_collection"] == "allow"  # D-80
    assert body["provider"]["quantizations"] == ["bf16", "fp16", "fp32", "unknown"]
    assert body["usage"] == {"include": True}
    assert body["models"] == ["deepseek/deepseek-v4.1-flash", "deepseek/deepseek-v4-flash"]
    assert body["stream"] is False and "temperature" not in body


@respx.mock
async def test_stream_generation_id_on_every_chunk_and_usage_last(chat: ChatClient) -> None:
    respx.post(URL).mock(return_value=response("chat_stream_ok"))
    chunks = await drain(chat)
    assert len(chunks) == 5
    assert {c.generation_id for c in chunks} == {"gen-rec-000003"}
    assert "".join(c.content or "" for c in chunks) == "Honestly? It depends."
    assert chunks[-1].finish_reason == "stop" and chunks[-1].usage is not None
    assert chunks[-1].usage.cost_usd == 0.00042 and chunks[-1].usage.tokens_cached == 1024


@respx.mock
async def test_complete(chat: ChatClient) -> None:
    respx.post(URL).mock(return_value=response("chat_ok"))
    r = await chat.complete(REQ)
    assert r.content == "ok" and r.generation_id == "gen-rec-000002" and r.provider == "DeepSeek"
    assert r.usage is not None and r.usage.cost_usd == 0.000002 and r.provider_warning is None


@respx.mock
async def test_served_elsewhere_warns(chat: ChatClient) -> None:
    respx.post(URL).mock(return_value=response("chat_stream_chutes"))
    chunks = await drain(chat)
    assert chunks[-1].provider == "Chutes"
    assert chat.warning(chunks[-1].provider) is not None and "Chutes" in (chat.warning("Chutes") or "")


@respx.mock
async def test_midstream_error_keeps_partial_text(chat: ChatClient) -> None:
    respx.post(URL).mock(return_value=response("chat_stream_midstream_error"))
    seen: list[str] = []
    with pytest.raises(ProviderError) as e:
        async for ch in chat.stream(REQ):
            seen.append(ch.content or "")
    assert e.value.code == "provider_error" and e.value.partial_text == "Hello the"
    assert e.value.generation_id == "gen-rec-000005" and e.value.maybe_charged
    assert "".join(seen) == "Hello the"


@respx.mock
async def test_refusal_is_content_refused_with_its_cost(chat: ChatClient) -> None:
    respx.post(URL).mock(return_value=response("chat_stream_refusal"))
    with pytest.raises(ProviderError) as e:
        await drain(chat)
    assert e.value.code == "content_refused" and e.value.cost_usd == 0.0002 and not e.value.maybe_charged


@respx.mock
async def test_first_token_timeout(chat: ChatClient) -> None:
    first = 'data: {"id":"gen-slow","provider":"DeepSeek","choices":[{"delta":{"content":"late"}}]}\n\n'
    respx.post(URL).mock(return_value=httpx.Response(200, headers={"content-type": "text/event-stream"},
                                                     stream=SlowStream([(0.0, ": OPENROUTER PROCESSING\n\n"), (0.5, first)])))
    with pytest.raises(ProviderError) as e:
        await drain(chat)
    assert e.value.code == "timeout" and e.value.maybe_charged


@respx.mock
async def test_idle_timeout_after_first_token(chat: ChatClient) -> None:
    c1 = 'data: {"id":"gen-idle","provider":"DeepSeek","choices":[{"delta":{"content":"Hi "}}]}\n\n'
    c2 = 'data: {"id":"gen-idle","provider":"DeepSeek","choices":[{"delta":{"content":"there"}}]}\n\n'
    respx.post(URL).mock(return_value=httpx.Response(200, headers={"content-type": "text/event-stream"},
                                                     stream=SlowStream([(0.0, c1), (0.6, c2)])))
    with pytest.raises(ProviderError) as e:
        await drain(chat)
    assert e.value.code == "timeout" and e.value.partial_text == "Hi " and e.value.generation_id == "gen-idle"


@respx.mock
async def test_malformed_completion(chat: ChatClient) -> None:
    respx.post(URL).mock(return_value=response("chat_malformed"))
    with pytest.raises(ProviderError) as e:
        await chat.complete(REQ)
    assert e.value.code == "provider_error"


@pytest.mark.parametrize(("fixture", "code"), [
    ("error_401", "invalid_key"), ("error_402", "insufficient_credits"), ("error_403_moderation", "content_refused"),
    ("error_408", "timeout"), ("error_429", "rate_limited"), ("error_500", "provider_error"), ("error_502", "provider_error"),
])
@respx.mock
async def test_error_statuses(chat: ChatClient, fixture: str, code: str) -> None:
    respx.post(URL).mock(return_value=response(fixture))
    with pytest.raises(ProviderError) as e:
        await drain(chat)
    assert e.value.code == code and not e.value.maybe_charged
    if code == "rate_limited":
        assert e.value.retry_after == 12

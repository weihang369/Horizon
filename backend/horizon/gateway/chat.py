"""The chat client (doc backend/04 §1): `POST /api/v1/chat/completions`, streamed or complete.

- Every request carries the pinned routing block (DeepSeek first, `require_parameters`, full precision,
  `data_collection: allow`, D-80), `usage.include`, and the fallback model.
- **`generation_id`** comes from the first chunk and rides on every chunk, so a stopped stream can still be corrected.
- Timeouts: time to first token (20 s) until the first content arrives (OpenRouter's `: PROCESSING` comments don't
  count), then an idle timeout between chunks.
- A mid-stream error chunk raises `provider_error` with the partial text; a refusal finish reason raises
  `content_refused` (with the billed cost when reported).
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from horizon.gateway.client import HttpCore
from horizon.gateway.errors import ProviderError, malformed
from horizon.gateway.types import GatewayConfig, Usage, parse_usage, provider_warning

PATH = "/v1/chat/completions"
REFUSALS = {"content_filter", "refusal"}


@dataclass(frozen=True)
class ChatRequest:
    model: str
    messages: list[dict[str, Any]]
    max_tokens: int
    temperature: float | None = None
    reasoning: dict[str, Any] | None = None
    response_format: dict[str, Any] | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: Any = None
    logprobs: bool | None = None
    top_logprobs: int | None = None
    stop: list[str] | None = None
    extra: dict[str, Any] | None = None


@dataclass(frozen=True)
class ChatChunk:
    generation_id: str
    content: str | None = None
    reasoning: str | None = None
    tool_call: Any = None
    logprobs: Any = None
    finish_reason: str | None = None
    usage: Usage | None = None
    provider: str | None = None


@dataclass(frozen=True)
class ChatResult:
    generation_id: str
    content: str
    finish_reason: str | None
    usage: Usage | None
    provider: str | None
    model: str | None
    provider_warning: str | None
    latency_ms: int


class ChatClient:
    def __init__(self, core: HttpCore, cfg: GatewayConfig) -> None:
        self.core = core
        self.cfg = cfg

    def body(self, req: ChatRequest, *, stream: bool) -> dict[str, Any]:
        b: dict[str, Any] = {"model": req.model, "messages": req.messages, "max_tokens": req.max_tokens, "stream": stream,
                             "provider": dict(self.cfg.routing), "usage": {"include": True}}
        if req.model != self.cfg.fallback_model:
            b["models"] = [req.model, self.cfg.fallback_model]
        for k in ("temperature", "reasoning", "response_format", "tools", "tool_choice", "logprobs", "top_logprobs", "stop"):
            v = getattr(req, k)
            if v is not None:
                b[k] = v
        if req.extra:
            b.update(req.extra)
        return b

    def warning(self, provider: str | None) -> str | None:
        return provider_warning(provider, self.cfg.preferred_provider)

    async def stream(self, req: ChatRequest) -> AsyncIterator[ChatChunk]:
        t = self.cfg.timeouts
        gid: str | None = None
        text: list[str] = []
        first_deadline = time.monotonic() + t.chat_first_token
        got_content = False
        async with self.core.stream("POST", PATH, json=self.body(req, stream=True),
                                    http_timeout=t.chat_first_token + t.chat_idle) as resp:
            lines = resp.aiter_lines().__aiter__()
            while True:
                wait = max(0.0, first_deadline - time.monotonic()) if not got_content else t.chat_idle
                try:
                    line = await asyncio.wait_for(anext(lines), timeout=wait)
                except StopAsyncIteration:
                    return
                except TimeoutError as e:
                    raise ProviderError("timeout", maybe_charged=True, generation_id=gid, partial_text="".join(text)) from e
                except httpx.TimeoutException as e:
                    raise ProviderError("timeout", maybe_charged=True, generation_id=gid, partial_text="".join(text)) from e
                except httpx.TransportError as e:  # the connection broke while reading the body
                    raise ProviderError("provider_error", "The connection to OpenRouter broke.", maybe_charged=True,
                                        generation_id=gid, partial_text="".join(text)) from e
                if not line.startswith("data:"):
                    continue  # blank separators and `: OPENROUTER PROCESSING` keepalives
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                try:
                    obj = json.loads(data)
                except ValueError as e:
                    raise malformed("stream chunk", generation_id=gid) from e
                if gid is None:
                    gid = obj.get("id") if isinstance(obj, dict) else None
                    if not gid:
                        raise malformed("stream chunk (no generation id)")
                chunk = self._chunk(obj, gid)
                if isinstance(obj.get("error"), Mapping):
                    msg = obj["error"].get("message")
                    raise ProviderError("provider_error", f"The model stopped with an error: {msg}" if msg else None,
                                        maybe_charged=True, generation_id=gid, partial_text="".join(text))
                if chunk.content:
                    text.append(chunk.content)
                    got_content = True
                if chunk.finish_reason in REFUSALS:
                    raise ProviderError("content_refused", generation_id=gid, partial_text="".join(text),
                                        cost_usd=chunk.usage.cost_usd if chunk.usage else None,
                                        maybe_charged=chunk.usage is None or chunk.usage.cost_usd is None)
                yield chunk

    @staticmethod
    def _chunk(obj: Mapping[str, Any], gid: str) -> ChatChunk:
        choices = obj.get("choices")
        choice: Mapping[str, Any] = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], Mapping) else {}
        raw_delta = choice.get("delta")
        delta: Mapping[str, Any] = raw_delta if isinstance(raw_delta, Mapping) else {}
        calls = delta.get("tool_calls")
        return ChatChunk(
            generation_id=gid,
            content=delta.get("content") if isinstance(delta.get("content"), str) else None,
            reasoning=delta.get("reasoning") if isinstance(delta.get("reasoning"), str) else None,
            tool_call=calls[0] if isinstance(calls, list) and calls else None,
            logprobs=choice.get("logprobs"),
            finish_reason=choice.get("finish_reason") if isinstance(choice.get("finish_reason"), str) else None,
            usage=parse_usage(obj.get("usage")),
            provider=obj.get("provider") if isinstance(obj.get("provider"), str) else None,
        )

    async def complete(self, req: ChatRequest) -> ChatResult:
        t = self.cfg.timeouts
        started = time.monotonic()
        resp = await self.core.request("POST", PATH, json=self.body(req, stream=False),
                                       http_timeout=t.chat_first_token + t.chat_idle)
        try:
            obj = resp.json()
        except ValueError as e:
            raise malformed("completion") from e
        gid = obj.get("id") if isinstance(obj, dict) else None
        choices = obj.get("choices") if isinstance(obj, dict) else None
        if not gid or not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
            raise malformed("completion", generation_id=gid if isinstance(gid, str) else None)
        msg = choices[0].get("message") or {}
        finish = choices[0].get("finish_reason")
        usage = parse_usage(obj.get("usage"))
        if finish in REFUSALS:
            raise ProviderError("content_refused", generation_id=gid, cost_usd=usage.cost_usd if usage else None,
                                maybe_charged=usage is None or usage.cost_usd is None)
        provider = obj.get("provider") if isinstance(obj.get("provider"), str) else None
        return ChatResult(generation_id=gid, content=str(msg.get("content") or ""), finish_reason=finish, usage=usage,
                          provider=provider, model=obj.get("model"), provider_warning=self.warning(provider),
                          latency_ms=round((time.monotonic() - started) * 1000))

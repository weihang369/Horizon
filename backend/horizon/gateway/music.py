"""The music client (creation-followups design D1, D-87): Lyria 3 Clip through `POST /api/v1/chat/completions`.

OpenRouter returns audio only on a stream: the request asks for `modalities: ["text", "audio"]` and the clip arrives as
base64 pieces in `choices[0].delta.audio.data`, joined and decoded once at the end. The body carries NO main-LLM
routing block and NO fallback chat model (those would steer a Google music model towards DeepSeek or a text model).

- `generation_id` comes from the first chunk; usage (with `usage.cost`) from the last one that has it.
- Timeouts: `timeouts.music` until the first audio arrives (the clip may come late, after `: PROCESSING` comments),
  then `chat_idle` between chunks. A timeout after send may have been charged.
- An error chunk raises `provider_error`; a stream with no audio is malformed. Both may have been charged.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from horizon.gateway.client import HttpCore
from horizon.gateway.errors import ProviderError, malformed
from horizon.gateway.types import GatewayConfig, Usage, parse_usage

PATH = "/v1/chat/completions"
REFUSALS = {"content_filter", "refusal"}


@dataclass(frozen=True)
class MusicResult:
    generation_id: str | None
    audio: bytes
    usage: Usage | None
    provider: str | None
    chunks: int            # audio pieces received (the live check records it)
    latency_ms: int


def _decode(pieces: list[str]) -> bytes | None:
    """The joined base64 (OpenRouter's documented form: pieces split anywhere); else each piece padded on its own."""
    for attempt in ("".join(pieces),), tuple(pieces):
        try:
            return b"".join(base64.b64decode(p, validate=True) for p in attempt)
        except (binascii.Error, ValueError):
            continue
    return None


def music_body(model: str, prompt: str) -> dict[str, Any]:
    return {"model": model, "messages": [{"role": "user", "content": prompt}], "modalities": ["text", "audio"],
            "stream": True, "usage": {"include": True}}


class MusicClient:
    def __init__(self, core: HttpCore, cfg: GatewayConfig) -> None:
        self.core = core
        self.cfg = cfg

    async def generate(self, *, model: str, prompt: str) -> MusicResult:
        t = self.cfg.timeouts
        started = time.monotonic()
        gid: str | None = None
        pieces: list[str] = []
        usage: Usage | None = None
        provider: str | None = None
        first_deadline = started + t.music

        def fail(code: str, message: str | None = None) -> ProviderError:
            return ProviderError(code, message, maybe_charged=True, generation_id=gid)

        async with self.core.stream("POST", PATH, json=music_body(model, prompt), http_timeout=t.music + t.chat_idle) as resp:
            lines = resp.aiter_lines().__aiter__()
            while True:
                wait = max(0.0, first_deadline - time.monotonic()) if not pieces else t.chat_idle
                try:
                    line = await asyncio.wait_for(anext(lines), timeout=wait)
                except StopAsyncIteration:
                    break
                except (TimeoutError, httpx.TimeoutException) as e:
                    raise fail("timeout") from e
                except httpx.TransportError as e:
                    raise fail("provider_error", "The connection to OpenRouter broke.") from e
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except ValueError as e:
                    raise malformed("music stream chunk", generation_id=gid) from e
                if not isinstance(obj, Mapping):
                    raise malformed("music stream chunk", generation_id=gid)
                if gid is None and isinstance(obj.get("id"), str):
                    gid = obj["id"]
                if isinstance(obj.get("error"), Mapping):
                    msg = obj["error"].get("message")
                    raise fail("provider_error", f"The music model stopped with an error: {msg}" if msg else None)
                usage = parse_usage(obj.get("usage")) or usage
                provider = obj["provider"] if isinstance(obj.get("provider"), str) else provider
                choices = obj.get("choices")
                choice: Mapping[str, Any] = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], Mapping) else {}
                raw_delta = choice.get("delta")
                delta: Mapping[str, Any] = raw_delta if isinstance(raw_delta, Mapping) else {}
                raw_audio = delta.get("audio")
                audio: Mapping[str, Any] = raw_audio if isinstance(raw_audio, Mapping) else {}
                if isinstance(audio.get("data"), str) and audio["data"]:
                    pieces.append(audio["data"])
                if choice.get("finish_reason") in REFUSALS:
                    cost = usage.cost_usd if usage else None
                    raise ProviderError("content_refused", generation_id=gid, cost_usd=cost, maybe_charged=cost is None)
        if not pieces:
            raise malformed("music stream (no audio)", generation_id=gid)
        clip = _decode(pieces)
        if clip is None:
            raise malformed("music stream (bad audio data)", generation_id=gid)
        return MusicResult(generation_id=gid, audio=clip, usage=usage, provider=provider, chunks=len(pieces),
                           latency_ms=round((time.monotonic() - started) * 1000))

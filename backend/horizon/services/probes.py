"""Settings probes (openrouter-key "Connection test", "Model probe"; doc 03 settings; design D13).

- `probe_connection`: OpenRouter's key info (+ credits when available). Free: no reservation, no ledger row.
- `probe_model(role)`: the cheapest probe per role. chat: a 1-token completion; decision: one `noul` Jev question;
  embedding: one word. Those are paid calls through the pipeline (caps preflight, a ledger row with
  `purpose: "probe"`), never draining energy. image and music: a free metadata check only, never a generation.
The model probed is the role's override if set, else its configured model.
"""

from __future__ import annotations

import time
from typing import Any, Literal

from horizon.api.errors import HorizonHTTPError
from horizon.gateway.chat import ChatRequest
from horizon.gateway.context import call_ctx
from horizon.gateway.pipeline import Gateway

Role = Literal["chat", "decision", "image", "music", "embedding"]
PROBE = "probe"


def _ms(started: float) -> int:
    return max(1, round((time.monotonic() - started) * 1000))


async def probe_connection(gw: Gateway) -> dict[str, Any]:
    started = time.monotonic()
    await gw.meta.key_info()
    latency = _ms(started)
    credits = await gw.meta.credits()
    out: dict[str, Any] = {"ok": True, "latencyMs": latency}
    if credits is not None:
        out["creditsUsd"] = credits
    return out


def model_for(settings: dict[str, Any], role: Role) -> str:
    override = (settings.get("modelOverrides") or {}).get(role)
    return str(override) if isinstance(override, str) and override.strip() else str(settings["models"][role])


async def probe_model(gw: Gateway, settings: dict[str, Any], role: Role) -> dict[str, Any]:
    model = model_for(settings, role)
    started = time.monotonic()
    if role == "chat":
        req = ChatRequest(model=model, messages=[{"role": "user", "content": "ping"}], max_tokens=1)
        await gw.chat_complete(req, call_ctx(PROBE, category="chat"))
    elif role == "decision":
        q = {"probe": {"type": "noul", "instructions": "Is this message a connection test?",
                       "criteria": {"true": "it is a test", "false": "it is not a test"}}}
        await gw.decide({"message": "ping"}, q, call_ctx(PROBE, category="decision"), model=model)
    elif role == "embedding":
        await gw.embed(["ping"], call_ctx(PROBE, category="embedding"), model=model)
    elif not await gw.meta.model_exists(model):
        raise HorizonHTTPError("provider_error", f"{model} isn't available on OpenRouter.", retryable=False)
    return {"ok": True, "latencyMs": _ms(started), "model": model}

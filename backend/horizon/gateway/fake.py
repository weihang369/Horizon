"""FakeOpenRouter (design D14, provider-gateway "Test mode never reaches the network").

An `httpx.MockTransport` handler that answers every endpoint the gateway uses, in-process and deterministically. It is
the provider in test mode (`HORIZON_TEST=1`), so the TS HTTP contract suite and integration tests run the real
gateway code with no socket ever opened.

- A bearer starting `sk-or-bad` gets 401 everywhere (the portable "bad key" test).
- Chat answers "ok" (SSE or JSON) from provider DeepSeek; decisions take the first option / 0.5 / the middle level;
  embeddings are deterministic unit vectors; every paid answer carries a generation ID and `usage.cost`.

The response shapes follow the recorded fixtures in `tests/fixtures/openrouter/` (unverified until the live run).
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable
from typing import Any

import httpx

CHAT_COST = 0.000002
DECISION_COST_PER_M = 0.042
EMBED_COST_PER_M = 0.01
IMAGE_COST = 0.018
CREDITS_TOTAL = 5.0
CREDITS_USED = 0.79
DEFAULT_DIMS = 1024
# A 1×1 transparent PNG, the fake image result.
PNG_1PX = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


def _tokens(value: Any) -> int:
    return max(1, math.ceil(len(json.dumps(value, ensure_ascii=False).encode("utf-8")) / 4))


def unit_vector(text: str, dims: int) -> list[float]:
    raw = [b / 255 - 0.5 for b in hashlib.shake_256(text.encode("utf-8")).digest(dims)]
    norm = math.sqrt(sum(x * x for x in raw)) or 1.0
    return [x / norm for x in raw]


class FakeOpenRouter:
    def __init__(self, models: Iterable[str] = ()) -> None:
        self.models = set(models)
        self._n = 0
        self.costs: dict[str, float] = {}  # generation id → cost, for /generation lookups
        self.requests: list[httpx.Request] = []
        self.queued: list[httpx.Response] = []  # test hook: answered first, in order (e.g. a 500 or a 401)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def _gen(self, prefix: str, cost: float) -> str:
        self._n += 1
        gid = f"{prefix}-fake-{self._n:06d}"
        self.costs[gid] = cost
        return gid

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.queued:
            return self.queued.pop(0)
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer sk-or-") or auth.startswith("Bearer sk-or-bad"):
            return httpx.Response(401, json={"error": {"code": 401, "message": "No auth credentials found"}})
        path = request.url.path.removeprefix("/api")
        body: Any = json.loads(request.content) if request.content else None
        route = (request.method, path)
        if route == ("GET", "/v1/key"):
            return httpx.Response(200, json={"data": {"label": "fake", "usage": CREDITS_USED, "limit": None,
                                                      "limit_remaining": None, "is_free_tier": False}})
        if route == ("GET", "/v1/credits"):
            return httpx.Response(200, json={"data": {"total_credits": CREDITS_TOTAL, "total_usage": CREDITS_USED}})
        if route == ("GET", "/v1/models"):
            return httpx.Response(200, json={"data": [{"id": m} for m in sorted(self.models)]})
        if route == ("GET", "/v1/generation"):
            gid = request.url.params.get("id", "")
            if gid not in self.costs:
                return httpx.Response(404, json={"error": {"code": 404, "message": "Generation not found"}})
            return httpx.Response(200, json={"data": {"id": gid, "total_cost": self.costs[gid], "provider_name": "DeepSeek"}})
        if route == ("POST", "/v1/chat/completions"):
            return self._chat(body)
        if route == ("POST", "/alpha/decisions"):
            return self._decide(body)
        if route == ("POST", "/v1/embeddings"):
            return self._embed(body)
        if route == ("POST", "/v1/images"):
            gid = self._gen("gen", IMAGE_COST)
            return httpx.Response(200, json={"id": gid, "model": body.get("model"), "provider": "ByteDance",
                                             "data": [{"b64_json": PNG_1PX}], "usage": {"cost": IMAGE_COST}})
        return httpx.Response(404, json={"error": {"code": 404, "message": f"No fake for {request.method} {path}"}})

    def _chat(self, body: dict[str, Any]) -> httpx.Response:
        gid = self._gen("gen", CHAT_COST)
        prompt = _tokens(body.get("messages"))
        usage = {"prompt_tokens": prompt, "completion_tokens": 1, "total_tokens": prompt + 1,
                 "prompt_tokens_details": {"cached_tokens": 0}, "cost": CHAT_COST}
        base = {"id": gid, "model": body.get("model"), "provider": "DeepSeek"}
        if not body.get("stream"):
            return httpx.Response(200, json={**base, "object": "chat.completion", "usage": usage, "choices": [
                {"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}]})
        chunks = [
            {**base, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"role": "assistant", "content": "ok"},
                                                                       "finish_reason": None}]},
            {**base, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
             "usage": usage},
        ]
        text = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=text.encode("utf-8"))

    def _decide(self, body: dict[str, Any]) -> httpx.Response:
        answers: dict[str, Any] = {}
        for key, q in (body.get("questions") or {}).items():
            kind, crit = q.get("type"), q.get("criteria")
            if kind == "choice":
                opts = list(crit or {})
                p = 1 / len(opts) if opts else 1.0
                answers[key] = {"choice": opts[0] if opts else None, "confidence": p,
                                "probabilities": dict.fromkeys(opts, p)}
            elif kind == "noul":
                answers[key] = {"noul": 0.5}
            elif kind == "score":
                levels = list(crit or [])
                mid = (len(levels) - 1) / 2
                answers[key] = {"score": mid, "confidence": 1.0,
                                "probabilities": {str(i): (1.0 if i == round(mid) else 0.0) for i in range(len(levels))},
                                "legend": levels}
        tokens = _tokens(body.get("state")) + max((_tokens(q) for q in (body.get("questions") or {}).values()), default=0)
        cost = tokens * DECISION_COST_PER_M / 1e6
        gid = self._gen("dec", cost)
        return httpx.Response(200, json={"id": gid, "model": body.get("model"), "answers": answers,
                                         "usage": {"input_tokens": tokens, "output_tokens": 0, "cost": cost}})

    def _embed(self, body: dict[str, Any]) -> httpx.Response:
        inputs = body.get("input") or []
        dims = int(body.get("dimensions") or DEFAULT_DIMS)
        tokens = sum(_tokens(x) for x in inputs)
        cost = tokens * EMBED_COST_PER_M / 1e6
        gid = self._gen("gen", cost)
        return httpx.Response(200, json={
            "id": gid, "object": "list", "model": body.get("model"), "provider": "Nebius",
            "data": [{"object": "embedding", "index": i, "embedding": unit_vector(x, dims)} for i, x in enumerate(inputs)],
            "usage": {"prompt_tokens": tokens, "total_tokens": tokens, "cost": cost}})

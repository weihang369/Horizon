"""The meta client (doc backend/04 §1): free OpenRouter calls. No reservation, no ledger row, no cap.

- `key_info()`: `GET /api/v1/key` (testConnection).
- `credits()`: `GET /api/v1/credits` → remaining USD (`total_credits − total_usage`), None when unavailable.
- `generation(id)`: `GET /api/v1/generation?id=` → the actual cost of a past call; None while it isn't indexed yet
  (404), so the cost corrector retries with backoff.
- `model_exists(model)`: `GET /api/v1/models?output_modalities=all`, the free metadata probe for image and music
  (never a paid generation). Without the filter, OpenRouter lists text models only (live run, 2026-10-04).

Shapes confirmed by the live run on 2026-10-04 (design OQ-C): `/key` and `/credits` wrap in `data`; `/generation`
answers 404 for ~13 s after a call, then `data.total_cost` / `provider_name` / `tokens_*`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from horizon.gateway.client import HttpCore
from horizon.gateway.errors import ProviderError, malformed


@dataclass(frozen=True)
class GenerationInfo:
    generation_id: str
    cost_usd: float
    provider: str | None
    tokens_in: int | None
    tokens_out: int | None
    tokens_cached: int | None


def _data(obj: Any, what: str) -> Mapping[str, Any]:
    data = obj.get("data") if isinstance(obj, Mapping) else None
    if not isinstance(data, Mapping):
        raise malformed(what, maybe_charged=False)
    return data


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


class MetaClient:
    def __init__(self, core: HttpCore, timeout_s: float) -> None:
        self.core = core
        self.timeout_s = timeout_s

    async def key_info(self) -> Mapping[str, Any]:
        resp = await self.core.request("GET", "/v1/key", http_timeout=self.timeout_s)
        return _data(resp.json(), "key info")

    async def credits(self) -> float | None:
        try:
            resp = await self.core.request("GET", "/v1/credits", http_timeout=self.timeout_s)
        except ProviderError as e:
            if e.code in ("invalid_key", "missing_key"):
                raise
            return None  # credits are a nice-to-have on testConnection
        data = _data(resp.json(), "credits")
        total, used = _num(data.get("total_credits")), _num(data.get("total_usage"))
        return round(total - used, 6) if total is not None and used is not None else None

    async def generation(self, generation_id: str) -> GenerationInfo | None:
        try:
            resp = await self.core.request("GET", "/v1/generation", params={"id": generation_id}, http_timeout=self.timeout_s)
        except ProviderError as e:
            if e.status == 404:
                return None
            raise
        data = _data(resp.json(), "generation")
        cost = _num(data.get("total_cost"))
        if cost is None:
            return None

        def i(k: str) -> int | None:
            n = _num(data.get(k))
            return int(n) if n is not None else None

        prov = data.get("provider_name")
        return GenerationInfo(generation_id=generation_id, cost_usd=cost, provider=prov if isinstance(prov, str) else None,
                              tokens_in=i("tokens_prompt"), tokens_out=i("tokens_completion"),
                              tokens_cached=i("native_tokens_cached"))

    async def model_exists(self, model: str) -> bool:
        resp = await self.core.request("GET", "/v1/models", params={"output_modalities": "all"}, http_timeout=self.timeout_s)
        data = resp.json().get("data") if isinstance(resp.json(), Mapping) else None
        if not isinstance(data, list):
            raise malformed("model list", maybe_charged=False)
        return any(isinstance(m, Mapping) and m.get("id") == model for m in data)

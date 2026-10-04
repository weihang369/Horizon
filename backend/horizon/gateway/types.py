"""Shared gateway types: usage, the parsed gateway config, and the provider-warning rule."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Usage:
    tokens_in: int | None = None
    tokens_out: int | None = None
    tokens_cached: int | None = None
    cost_usd: float | None = None       # the provider's `usage.cost`; None = not reported (estimate + correction)


def _int(v: Any) -> int | None:
    return int(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def _float(v: Any) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def parse_usage(u: Any) -> Usage | None:
    """OpenAI-style (`prompt_tokens`…) or Jev-style (`input_tokens`…) usage; None when absent."""
    if not isinstance(u, Mapping):
        return None
    details = u.get("prompt_tokens_details")
    cached = details.get("cached_tokens") if isinstance(details, Mapping) else None
    return Usage(
        tokens_in=_int(u.get("prompt_tokens", u.get("input_tokens"))),
        tokens_out=_int(u.get("completion_tokens", u.get("output_tokens"))),
        tokens_cached=_int(cached),
        cost_usd=_float(u.get("cost")),
    )


@dataclass(frozen=True)
class Timeouts:
    chat_first_token: float
    chat_idle: float
    image: float
    embedding: float
    meta: float
    decision: Mapping[str, float] = field(default_factory=dict)

    def for_decision(self, purpose: str) -> float:
        return self.decision.get(purpose, self.decision.get("default", 3.0))


@dataclass(frozen=True)
class GatewayConfig:
    """`seed/pricing.json` → `gateway` (design D9). Times are seconds here; the file stores milliseconds."""

    routing: Mapping[str, Any]
    fallback_model: str
    embedding_provider: str
    embed_batch: int
    timeouts: Timeouts

    @staticmethod
    def from_mapping(g: Mapping[str, Any]) -> GatewayConfig:
        t = g["timeoutsMs"]
        return GatewayConfig(
            routing=dict(g["routing"]),
            fallback_model=str(g["fallbackModel"]),
            embedding_provider=str(g["embeddingProvider"]),
            embed_batch=int(g["embedBatch"]),
            timeouts=Timeouts(
                chat_first_token=t["chatFirstToken"] / 1000, chat_idle=t["chatIdle"] / 1000, image=t["image"] / 1000,
                embedding=t["embedding"] / 1000, meta=t["meta"] / 1000,
                decision={str(k): float(v) / 1000 for k, v in t["decision"].items()},
            ),
        )

    @property
    def preferred_provider(self) -> str:
        order = self.routing.get("order") or []
        return str(order[0]) if order else ""


def provider_warning(served_by: str | None, preferred: str) -> str | None:
    """A trace warning when the main LLM was served by someone other than the pinned provider (doc 04 §1)."""
    if not served_by or not preferred or served_by.lower() == preferred.lower():
        return None
    return f"Served by {served_by}, not {preferred}: prompt caching and the price assumptions may not hold."

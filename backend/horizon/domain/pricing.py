"""Cost estimates (doc backend/04 §3 "Estimates", design D10): pure functions over the committed `seed/pricing.json`.

Estimates are deliberately upper-bound-ish: they feed the cap preflight and the reservation book, and they are what an
interrupted call is recorded at until the provider's actual cost corrects it. Actual costs always come from the
provider's `usage.cost`.

Tokens are counted without a tokenizer: `ceil(utf8 bytes / 3)` over-counts English (~4 chars/token) and is close for
CJK, which is the safe direction for a budget check.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

PricePeriod = Literal["peak", "off_peak"]

DEFAULT_EXPECTED_OUT = 220
EXPECTED_OUT_WINDOW = 10
BYTES_PER_TOKEN = 3


@dataclass(frozen=True)
class ChatPrice:
    model: str
    provider: str
    input_per_m: float
    cached_input_per_m: float
    output_per_m: float


@dataclass(frozen=True)
class EmbeddingPrice:
    model: str
    provider: str
    input_per_m: float


@dataclass(frozen=True)
class PeakConfig:
    multiplier: float
    tz: str
    windows: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class PriceTable:
    chat: ChatPrice
    decision: ChatPrice
    embedding: EmbeddingPrice
    generation: Mapping[str, float]
    peak: PeakConfig
    gateway: Mapping[str, Any]

    @staticmethod
    def from_json(data: Mapping[str, Any]) -> PriceTable:
        def chat(d: Mapping[str, Any]) -> ChatPrice:
            return ChatPrice(str(d["model"]), str(d["provider"]), float(d["inputPerM"]),
                             float(d["cachedInputPerM"]), float(d["outputPerM"]))

        e = data["embedding"]
        p = data["peak"]
        return PriceTable(
            chat=chat(data["chat"]),
            decision=chat(data["decision"]),
            embedding=EmbeddingPrice(str(e["model"]), str(e["provider"]), float(e["inputPerM"])),
            generation={str(k): float(v) for k, v in data["generation"].items()},
            peak=PeakConfig(float(p["multiplier"]), str(p["tz"]),
                            tuple((int(a), int(b)) for a, b in p["windows"])),
            gateway=dict(data["gateway"]),
        )


def load_price_table(seed_dir: Path) -> PriceTable:
    doc = json.loads((seed_dir / "pricing.json").read_text(encoding="utf-8"))
    return PriceTable.from_json(doc["data"])


def count_tokens(text: str) -> int:
    n = len(text.encode("utf-8"))
    return 0 if n == 0 else math.ceil(n / BYTES_PER_TOKEN)


def multiplier(t: PriceTable, period: PricePeriod) -> float:
    return t.peak.multiplier if period == "peak" else 1.0


def p75(values: Sequence[int]) -> int:
    """Nearest-rank 75th percentile."""
    s = sorted(values)
    return s[max(0, math.ceil(0.75 * len(s)) - 1)]


def expected_out(max_tokens: int, recent_outs: Sequence[int]) -> int:
    """min(max_tokens, p75 of the character's last 10 replies); 220 stands in for the p75 when there is no history."""
    recent = list(recent_outs)[-EXPECTED_OUT_WINDOW:]
    base = p75(recent) if recent else DEFAULT_EXPECTED_OUT
    return max(0, min(max_tokens, base))


def estimate_chat(t: PriceTable, *, prefix_tokens: int, warm: bool, other_in: int, expected_out_tokens: int,
                  period: PricePeriod, price: ChatPrice | None = None) -> float:
    p = price or t.chat
    usd = (prefix_tokens * (p.cached_input_per_m if warm else p.input_per_m)
           + other_in * p.input_per_m + expected_out_tokens * p.output_per_m) / 1e6
    return usd * multiplier(t, period)


def estimate_decision(t: PriceTable, tokens: int) -> float:
    """Jev bills input only; no peak multiplier (D-66)."""
    return tokens * t.decision.input_per_m / 1e6


def estimate_image(t: PriceTable, kind: str = "portrait") -> float:
    return t.generation[kind]


def estimate_embedding(t: PriceTable, tokens: int) -> float:
    return tokens * t.embedding.input_per_m / 1e6

"""The embeddings client (doc backend/04 §1, D-64): `POST /api/v1/embeddings`, Qwen3 Embedding 8B on a pinned provider.

One request carries at most `embed_batch` (32) texts; the pipeline wraps each batch as one paid call, so each batch is
one ledger row. Vectors come back in input order whatever order the provider lists them in.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from horizon.gateway.client import HttpCore
from horizon.gateway.errors import malformed
from horizon.gateway.types import Usage, parse_usage

PATH = "/v1/embeddings"


@dataclass(frozen=True)
class EmbedBatch:
    generation_id: str | None
    vectors: list[list[float]]
    usage: Usage | None
    provider: str | None


def batches(texts: Sequence[str], size: int) -> list[list[str]]:
    return [list(texts[i:i + size]) for i in range(0, len(texts), size)]


class EmbeddingsClient:
    def __init__(self, core: HttpCore, *, provider: str, batch_size: int, timeout_s: float) -> None:
        self.core = core
        self.provider = provider
        self.batch_size = batch_size
        self.timeout_s = timeout_s

    async def embed_batch(self, texts: Sequence[str], *, model: str, dimensions: int | None = None) -> EmbedBatch:
        if not texts or len(texts) > self.batch_size:
            raise ValueError(f"an embedding request takes 1..{self.batch_size} texts")
        body: dict[str, Any] = {"model": model, "input": list(texts),
                                "provider": {"order": [self.provider], "allow_fallbacks": False}}
        if dimensions:
            body["dimensions"] = dimensions
        resp = await self.core.request("POST", PATH, json=body, http_timeout=self.timeout_s)
        try:
            obj = resp.json()
        except ValueError as e:
            raise malformed("embedding response") from e
        gid = obj.get("id") if isinstance(obj, Mapping) and isinstance(obj.get("id"), str) else None
        data = obj.get("data") if isinstance(obj, Mapping) else None
        if not isinstance(data, list) or len(data) != len(texts):
            raise malformed("embedding response", generation_id=gid)
        out: list[list[float] | None] = [None] * len(texts)
        for pos, item in enumerate(data):
            if not isinstance(item, Mapping) or not isinstance(item.get("embedding"), list):
                raise malformed("embedding response", generation_id=gid)
            idx = item.get("index", pos)
            if not isinstance(idx, int) or not 0 <= idx < len(texts) or out[idx] is not None:
                raise malformed("embedding response", generation_id=gid)
            out[idx] = [float(x) for x in item["embedding"]]
        provider = obj.get("provider") if isinstance(obj.get("provider"), str) else None
        return EmbedBatch(generation_id=gid, vectors=[v for v in out if v is not None], usage=parse_usage(obj.get("usage")),
                          provider=provider)

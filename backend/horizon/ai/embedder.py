"""The Embedder port (doc 05 §2.2; knowledge-memory-storage design D7; embedding-spaces spec).

The **active space decides** the model, provider and dimensions; `settings.models.embedding` never switches an
existing space (mixing models in one vec0 table corrupts KNN silently, D-95). Two forms:
- a query is sent as `Instruct: {space.query_instruction}\\nQuery: {text}`;
- a passage or memory is sent as its plain text.

Both implementations batch ≤ 32 texts per paid call and go through the gateway pipeline (key check, caps, holds, one
ledger row per batch, D-84 hooks):
- `QwenEmbedder` (naive): `gateway.embed_batch(model=space.model, dimensions=space.dims)`. A longer vector (a provider
  ignoring `dimensions`) is cut to `dims` and rescaled to unit length (Qwen3 is Matryoshka-trained); a shorter or
  non-finite one fails the batch as `malformed`.
- `HashEmbedder` (scripted, D-81): `gateway.simulated_embedding_batch`, deterministic unit vectors, no network.

An LRU (4 096 entries) keyed by `(space.id, kind, sha256(text))` serves repeats within one run with no request and no
row. A caller that stores vectors gets per-batch hooks (`BatchHooks`) for the batches actually sent; cached texts are
returned in `Embedded.cached` so the caller stores those itself.
"""

from __future__ import annotations

import hashlib
import math
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from sqlalchemy.ext.asyncio import AsyncConnection

from horizon.ai.scripted.ports import AiDeps
from horizon.db.spaces import SpaceSpec
from horizon.gateway.context import CallContext
from horizon.gateway.errors import malformed

Kind = Literal["query", "document"]
LRU_SIZE = 4096


@dataclass
class Batch:
    """One sent batch: the input positions it covers and, once the provider answered, their vectors."""

    indices: list[int]
    vectors: list[list[float]] = field(default_factory=list)


@dataclass(frozen=True)
class BatchHooks:
    before_send: Callable[[], Awaitable[None]] | None = None
    commit_with: Callable[[AsyncConnection, str, Batch], Awaitable[None]] | None = None


HooksFor = Callable[[Batch], BatchHooks]


@dataclass(frozen=True)
class Embedded:
    vectors: list[list[float]]
    cached: list[int]          # positions served from the cache (no call: the caller stores these itself)


class Embedder(Protocol):
    name: str

    async def embed(self, texts: Sequence[str], *, kind: Kind, space: SpaceSpec, ctx: CallContext,
                    hooks: HooksFor | None = None) -> Embedded: ...


def request_text(text: str, kind: Kind, space: SpaceSpec) -> str:
    if kind == "query" and space.query_instruction:
        return f"Instruct: {space.query_instruction}\nQuery: {text}"
    return text


def fit(vector: Sequence[float], dims: int) -> list[float]:
    """Cut a longer vector to `dims` and rescale it to unit length; refuse a shorter or non-finite one."""
    if len(vector) < dims or not all(math.isfinite(x) for x in vector):
        raise malformed("embedding vector")
    v = [float(x) for x in vector[:dims]]
    norm = math.sqrt(sum(x * x for x in v))
    if norm == 0:
        raise malformed("embedding vector")
    return [x / norm for x in v] if abs(norm - 1.0) > 1e-6 or len(vector) != dims else v


class _Lru:
    def __init__(self, size: int = LRU_SIZE) -> None:
        self.size = size
        self.items: OrderedDict[tuple[str, str, str], list[float]] = OrderedDict()

    @staticmethod
    def key(space: SpaceSpec, kind: Kind, text: str) -> tuple[str, str, str]:
        return space.id, kind, hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get(self, k: tuple[str, str, str]) -> list[float] | None:
        v = self.items.get(k)
        if v is not None:
            self.items.move_to_end(k)
        return v

    def put(self, k: tuple[str, str, str], v: list[float]) -> None:
        self.items[k] = v
        self.items.move_to_end(k)
        while len(self.items) > self.size:
            self.items.popitem(last=False)


class _BaseEmbedder:
    name = "base"

    def __init__(self, deps: AiDeps) -> None:
        self.deps = deps
        self.cache = _Lru()

    async def _send(self, texts: list[str], space: SpaceSpec, ctx: CallContext, batch: Batch,
                    hooks: BatchHooks) -> list[list[float]]:
        raise NotImplementedError

    async def embed(self, texts: Sequence[str], *, kind: Kind, space: SpaceSpec, ctx: CallContext,
                    hooks: HooksFor | None = None) -> Embedded:
        out: list[list[float] | None] = [None] * len(texts)
        cached: list[int] = []
        todo: list[int] = []
        for i, t in enumerate(texts):
            hit = self.cache.get(_Lru.key(space, kind, t))
            if hit is not None:
                out[i] = hit
                cached.append(i)
            else:
                todo.append(i)
        size = self.deps.gateway().cfg.embed_batch
        for start in range(0, len(todo), size):
            batch = Batch(indices=todo[start:start + size])
            bh = hooks(batch) if hooks is not None else BatchHooks()
            sent = [request_text(texts[i], kind, space) for i in batch.indices]
            vectors = await self._send(sent, space, ctx, batch, bh)
            for i, v in zip(batch.indices, vectors, strict=True):
                out[i] = v
                self.cache.put(_Lru.key(space, kind, texts[i]), v)
        return Embedded(vectors=[v for v in out if v is not None], cached=cached)

    @staticmethod
    def _wire(batch: Batch, hooks: BatchHooks, dims: int) -> tuple[Any, Any]:
        async def after(vectors: list[list[float]]) -> None:
            batch.vectors = [fit(v, dims) for v in vectors]

        async def commit(conn: AsyncConnection, row_id: str) -> None:
            if hooks.commit_with is not None:
                await hooks.commit_with(conn, row_id, batch)

        return after, commit


class QwenEmbedder(_BaseEmbedder):
    """Naive: Qwen3 Embedding 8B (D-64) through the gateway, with the space's dimensions."""

    name = "naive"

    async def _send(self, texts: list[str], space: SpaceSpec, ctx: CallContext, batch: Batch,
                    hooks: BatchHooks) -> list[list[float]]:
        after, commit = self._wire(batch, hooks, space.dims)
        await self.deps.gateway().embed_batch(texts, ctx, model=space.model, dimensions=space.dims,
                                              before_send=hooks.before_send, after_response=after, commit_with=commit)
        return batch.vectors


class HashEmbedder(_BaseEmbedder):
    """Scripted: deterministic unit vectors, billed as simulated spend through the same pipeline (D-81)."""

    name = "scripted"

    async def _send(self, texts: list[str], space: SpaceSpec, ctx: CallContext, batch: Batch,
                    hooks: BatchHooks) -> list[list[float]]:
        after, commit = self._wire(batch, hooks, space.dims)
        await self.deps.gateway().simulated_embedding_batch(
            texts, ctx, model=space.model, dimensions=space.dims, before_send=hooks.before_send, after_response=after,
            commit_with=commit)
        return batch.vectors

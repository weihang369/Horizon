"""The Embedder port (doc 05 §2.2; knowledge-memory-storage design D7; embedding-spaces spec; rag design D4, D11).

The **active space decides** the model, provider and dimensions; `settings.models.embedding` never switches an
existing space (mixing models in one vec0 table corrupts KNN silently, D-95). Three forms (`request_text`):
- a query is sent as `Instruct: {space.query_instruction}\\nQuery: {text}`;
- a knowledge piece (`knowledge`) is sent under the space's document template, when it has one (rag D4): its source's
  title without the file extension, its heading path (left out when empty or equal to the locator, as on seed rows),
  a blank line, then the text. A space without a template sends the plain text;
- a memory (`document`) is sent as its plain text.

Both implementations batch ≤ 32 texts per paid call and go through the gateway pipeline (key check, caps, holds, one
ledger row per batch, D-84 hooks):
- `QwenEmbedder` (naive): `gateway.embed_batch(model=space.model, dimensions=space.dims)`. A longer vector (a provider
  ignoring `dimensions`) is cut to `dims` and rescaled to unit length (Qwen3 is Matryoshka-trained); a shorter or
  non-finite one fails the batch as `malformed`.
- `HashEmbedder` (scripted, D-81): `gateway.simulated_embedding_batch`, deterministic unit vectors, no network.

An LRU (4 096 entries) keyed by `(space.id, kind, sha256(request text))` serves repeats within one run with no request
and no row; the key is the text actually sent, so a changed instruction or template never reuses an old vector. A miss
whose key is already being embedded by another call waits for that call instead of sending again (rag D11: one
embedding per user message for every speaker); if that call fails or is cancelled, the waiter sends its own. A caller
that stores vectors gets per-batch hooks (`BatchHooks`) for the batches actually sent; texts served from the cache or
another call are returned in `Embedded.cached` so the caller stores those itself.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from sqlalchemy.ext.asyncio import AsyncConnection

from horizon.ai.scripted.ports import AiDeps
from horizon.db.spaces import SpaceSpec
from horizon.domain import vclock
from horizon.gateway.context import CallContext
from horizon.gateway.errors import malformed

Kind = Literal["query", "document", "knowledge", "message"]   # M13: "message" is an indexed line, sent plain
LRU_SIZE = 4096
_EXT = re.compile(r"\.(pdf|docx|md|markdown|txt)$", re.IGNORECASE)
_FIELD = re.compile(r"\{(title|heading|text)\}")
Key = tuple[str, str, str]


@dataclass(frozen=True)
class PieceMeta:
    """What the document template reads about a knowledge piece (rag D4)."""

    title: str
    heading: str | None = None
    locator: str | None = None


@dataclass
class Batch:
    """One sent batch: the input positions it covers and, once the provider answered, their vectors."""

    indices: list[int]
    vectors: list[list[float]] = field(default_factory=list)


@dataclass(frozen=True)
class BatchHooks:
    before_send: Callable[[], Awaitable[None]] | None = None
    commit_with: Callable[[AsyncConnection, str, Batch], Awaitable[None]] | None = None
    store_ok: bool = False   # shipped seed text only (D31): the seed view may serve or keep this batch


HooksFor = Callable[[Batch], BatchHooks]


@dataclass(frozen=True)
class Embedded:
    vectors: list[list[float]]
    cached: list[int]          # positions not sent by this call (cache or another call): the caller stores these itself


class Embedder(Protocol):
    name: str

    async def embed(self, texts: Sequence[str], *, kind: Kind, space: SpaceSpec, ctx: CallContext,
                    hooks: HooksFor | None = None, meta: Sequence[PieceMeta] | None = None) -> Embedded: ...


def strip_extension(title: str) -> str:
    return _EXT.sub("", title.strip())


def request_text(text: str, kind: Kind, space: SpaceSpec, meta: PieceMeta | None = None) -> str:
    """The exact text sent for `text` (and the cache's key)."""
    if kind == "query" and space.query_instruction:
        return f"Instruct: {space.query_instruction}\nQuery: {text}"
    if kind == "knowledge" and space.doc_template and meta is not None:
        heading = (meta.heading or "").strip()
        if heading == (meta.locator or "").strip():
            heading = ""
        template = space.doc_template if heading else space.doc_template.replace("{heading}\n", "")
        values = {"title": strip_extension(meta.title), "heading": heading, "text": text}
        return _FIELD.sub(lambda m: values[m.group(1)], template)
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
        self.items: OrderedDict[Key, list[float]] = OrderedDict()

    @staticmethod
    def key(space: SpaceSpec, kind: Kind, sent: str) -> Key:
        return space.id, kind, hashlib.sha256(sent.encode("utf-8")).hexdigest()

    def get(self, k: Key) -> list[float] | None:
        v = self.items.get(k)
        if v is not None:
            self.items.move_to_end(k)
        return v

    def put(self, k: Key, v: list[float]) -> None:
        self.items[k] = v
        self.items.move_to_end(k)
        while len(self.items) > self.size:
            self.items.popitem(last=False)


class _Abandoned(Exception):
    """The call embedding a key failed or was cancelled: its waiters send their own."""


class _BaseEmbedder:
    name = "base"

    def __init__(self, deps: AiDeps) -> None:
        self.deps = deps
        self.cache = _Lru()
        self.inflight: dict[Key, asyncio.Future[list[float]]] = {}

    async def _send(self, texts: list[str], space: SpaceSpec, ctx: CallContext, batch: Batch,
                    hooks: BatchHooks) -> list[list[float]]:
        raise NotImplementedError

    async def embed(self, texts: Sequence[str], *, kind: Kind, space: SpaceSpec, ctx: CallContext,
                    hooks: HooksFor | None = None, meta: Sequence[PieceMeta] | None = None) -> Embedded:
        if meta is not None and len(meta) != len(texts):
            raise ValueError("meta must have one entry per text")
        sent = [request_text(t, kind, space, meta[i] if meta is not None else None) for i, t in enumerate(texts)]
        keys = [_Lru.key(space, kind, s) for s in sent]
        out: list[list[float] | None] = [None] * len(texts)
        cached: list[int] = []
        waits: list[tuple[int, asyncio.Future[list[float]]]] = []
        todo: list[int] = []
        mine: dict[Key, asyncio.Future[list[float]]] = {}
        loop = asyncio.get_running_loop()
        for i, k in enumerate(keys):
            hit = self.cache.get(k)
            if hit is not None:
                out[i] = hit
                cached.append(i)
            elif k in self.inflight and k not in mine:
                waits.append((i, self.inflight[k]))
            elif k in mine:
                waits.append((i, mine[k]))       # the same text twice in one call: sent once
            else:
                fut: asyncio.Future[list[float]] = loop.create_future()
                self.inflight[k] = mine[k] = fut
                todo.append(i)
        try:
            size = self.deps.gateway().cfg.embed_batch
            for start in range(0, len(todo), size):
                batch = Batch(indices=todo[start:start + size])
                bh = hooks(batch) if hooks is not None else BatchHooks()
                vectors = await self._send([sent[i] for i in batch.indices], space, ctx, batch, bh)
                for i, v in zip(batch.indices, vectors, strict=True):
                    out[i] = v
                    self.cache.put(keys[i], v)
                    self._settle(keys[i], mine, v)
        finally:
            for k in list(mine):
                self._settle(k, mine, None)
        retry: list[int] = []
        for i, fut in waits:
            # another call's request: this caller is idle until it lands (its token given up, as a held request's is,
            # so virtual time can pass a deadline; rag 11.5's early embedding is often the call being waited on)
            holder = vclock.current_holder()
            if holder is not None:
                holder.drop()
            try:
                out[i] = await fut
                cached.append(i)
            except _Abandoned:
                retry.append(i)
            finally:
                if holder is not None:
                    holder.hold()
        if retry:
            again = await self.embed([texts[i] for i in retry], kind=kind, space=space, ctx=ctx, hooks=None,
                                     meta=[meta[i] for i in retry] if meta is not None else None)
            for j, i in enumerate(retry):
                out[i] = again.vectors[j]
            cached.extend(retry)   # sent with no hooks: the caller stores these itself
        cached.sort()
        return Embedded(vectors=[v for v in out if v is not None], cached=cached)

    def _settle(self, k: Key, mine: dict[Key, asyncio.Future[list[float]]], v: list[float] | None) -> None:
        fut = mine.pop(k, None)
        if fut is None:
            return
        if self.inflight.get(k) is fut:
            del self.inflight[k]
        if not fut.done():
            if v is None:
                fut.set_exception(_Abandoned())
                fut.exception()   # retrieved, so a future nobody waits on doesn't warn
            else:
                fut.set_result(v)

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
                                              provider=space.provider, before_send=hooks.before_send,
                                              after_response=after, commit_with=commit,
                                              store_ok=hooks.store_ok)
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

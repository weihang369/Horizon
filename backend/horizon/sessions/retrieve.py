"""The retrieval step of a turn (retrieval spec; knowledge-memory-storage design D10, D12, D13).

**One query embedding per user message, only when it can pay off (D12).** When a 1:1 or group message is sent,
`start_query` spawns its embedding (in parallel with routing) only if the knowledge retriever uses vectors, a key is
set, and a possible responder has a source indexed in the active space. Every reply to that message reuses it. Debate
and watch turns never embed a query. A cap refusal or a provider failure just means no vector.

**Retrieval (D10).** Before a turn's engine runs, `retrieve` builds a `ScopedIndex` for the speaker's world and character
(from the runtime, never from the engine) and asks the memory and knowledge retrievers for hits, which go into the
frozen `TurnContext`. A reply waits for the query vector at most `retrieval.queryEmbedWaitMs` (400 ms; it runs in parallel with routing);
past that it uses keyword retrieval, and the late embedding is still recorded. The `query_embed` call is listed on the
first responder's `trace.calls`, like the route decision.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from horizon.ai.contexts import KnowledgeHit, MemoryHit, SessionContext
from horizon.ai.retrieval import QueryBundle
from horizon.db import spaces
from horizon.domain.vclock import wait_at_most
from horizon.gateway.context import call_ctx
from horizon.gateway.errors import ProviderError
from horizon.services.knowledge.index import ScopedIndex, has_vectors

if TYPE_CHECKING:
    from horizon.runtime import Runtime
    from horizon.sessions.actor import SessionActor

log = logging.getLogger("horizon.sessions")

@dataclass
class PendingQuery:
    text: str
    message_id: str
    task: asyncio.Task[dict[str, list[float]]]
    calls_listed: bool = False


@dataclass(frozen=True)
class Retrieved:
    query: str | None
    knowledge: list[KnowledgeHit] = field(default_factory=list)
    memory: list[MemoryHit] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)   # turn-level calls to list on this reply's trace


def start_query(actor: SessionActor, text: str, message_id: str, cast: list[str]) -> None:
    """Spawn the query embedding for a user message, when it can pay off (D12)."""
    rt = actor.rt
    actor.pending_query = None
    if not text.strip() or rt.keys.status() != "set" or not getattr(rt.ai.knowledge_retriever(True), "uses_vectors", False):
        return
    world_id = str(actor.session["worldId"])

    async def embed() -> dict[str, list[float]]:
        try:
            if not await has_vectors(rt, cast):
                return {}
            async with rt.db.read() as conn:
                space = await spaces.active(conn)
            ctx = call_ctx("query_embed", world_id=world_id, session_id=actor.sid, message_id=message_id)
            out = await rt.ai.embedder(True).embed([text], kind="query", space=space, ctx=ctx)
            return {space.id: out.vectors[0]}
        except ProviderError as e:
            log.info("query embedding skipped (%s); keyword retrieval only", e.code)
            return {}

    actor.pending_query = PendingQuery(text=text, message_id=message_id, task=rt.spawn(f"query:{actor.sid}", embed()))


def query_text(prompt: str, sctx: SessionContext) -> str:
    if prompt.strip():
        return prompt
    for m in reversed(sctx.recent):
        if m.content.strip():
            return m.content
    cfg = sctx.config or {}
    return str(cfg.get("motion") or cfg.get("premise") or "")


async def _vectors(rt: Runtime, actor: SessionActor, query: str) -> tuple[dict[str, list[float]], list[dict[str, Any]]]:
    pq = getattr(actor, "pending_query", None)
    if pq is None or pq.text != query:
        return {}, []
    vectors: dict[str, list[float]] = {}
    if await wait_at_most(rt.clock, pq.task, rt.runtime_cfg.runtime.retrieval.query_embed_wait_ms / 1000):
        vectors = pq.task.result() if not pq.task.cancelled() and pq.task.exception() is None else {}
    calls: list[dict[str, Any]] = []
    if pq.task.done() and not pq.calls_listed:
        pq.calls_listed = True
        calls = [c for c in await rt.ledger.calls_for_message(pq.message_id) if c["purpose"] == "query_embed"]
    return vectors, calls


async def retrieve(rt: Runtime, actor: SessionActor, sctx: SessionContext, character_id: str, prompt: str) -> Retrieved:
    """Memories and passages for one reply, bound to the speaker's world and character."""
    query = query_text(prompt, sctx)
    if not query.strip():
        return Retrieved(query=None)
    key_set = rt.keys.status() == "set"
    vectors, calls = await _vectors(rt, actor, query)
    index = ScopedIndex(rt, sctx.world.id, character_id, rt.space_id or "")
    bundle = QueryBundle(text=query, vectors=vectors)
    k = rt.runtime_cfg.runtime.retrieval
    knowledge = await rt.ai.knowledge_retriever(key_set).retrieve(index, bundle, k.knowledge_k)
    memory = await rt.ai.memory_retriever(key_set).recall(index, bundle, k.memory_k)
    return Retrieved(query=query, knowledge=list(knowledge), memory=list(memory), calls=calls)

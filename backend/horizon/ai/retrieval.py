"""Retrieval ports (doc 05 §2.2; retrieval spec; knowledge-memory-storage design D10, D12, D13).

The runtime runs retrieval, not the engine: before a turn it builds a `ScopedIndex` bound to the **speaker's** world
and character (`services/knowledge/index.py`, which re-binds both on every join back, NFR-23) and asks the retrievers
for hits, which it freezes into the `TurnContext`. A retriever is policy only (which candidates, how to fuse them); it
never touches rows itself.

- `fts_query(text)`: user text → a safe FTS5 query: Unicode word tokens of 2+ characters, lower-cased, de-duplicated,
  without the operator words (and, or, not, near), at most 16, each double-quoted and joined with OR. Quotes,
  operators and column filters in the text can't change it.
- Knowledge: scripted = FTS (BM25) top k; naive = FTS 20 ∪ vector KNN 20 fused by RRF (k = 60), top k, with the
  score scaled to [0, 1] (`rrf / (2 / 61)`: 1.0 means first in both lists).
- Memory: scripted = the k most recent current memories; naive = FTS top k over current memories.
- `QueryBundle`: one per triggering user message, its query vectors per space (D12).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from horizon.ai.contexts import KnowledgeHit, MemoryHit

MAX_TERMS = 16
RRF_K = 60
POOL = 20
_WORD = re.compile(r"\w+", re.UNICODE)
_OPERATORS = frozenset({"and", "or", "not", "near"})


def fts_query(text: str) -> str | None:
    seen: list[str] = []
    for w in _WORD.findall(text.lower()):
        w = w.replace("_", "")
        if len(w) >= 2 and w not in seen and w not in _OPERATORS:
            seen.append(w)
        if len(seen) >= MAX_TERMS:
            break
    return " OR ".join(f'"{w}"' for w in seen) if seen else None


@dataclass(frozen=True)
class QueryBundle:
    text: str
    vectors: dict[str, list[float]] = field(default_factory=dict)   # space id → query vector


@dataclass(frozen=True)
class Candidate:
    rid: int
    rank: int          # 0-based position in its list


class ScopedIndex(Protocol):
    """Read-only, pre-bound to one world and character (implemented in `services/knowledge/index.py`)."""

    world_id: str
    character_id: str
    active_space: str

    async def knowledge_fts(self, query: str, limit: int) -> list[Candidate]: ...
    async def knowledge_knn(self, vector: list[float], limit: int) -> list[Candidate]: ...
    async def knowledge_hits(self, rids: list[int], scores: dict[int, float]) -> list[KnowledgeHit]: ...
    async def memory_fts(self, query: str, limit: int) -> list[MemoryHit]: ...
    async def memory_recent(self, limit: int) -> list[MemoryHit]: ...


class KnowledgeRetriever(Protocol):
    uses_vectors: bool

    async def retrieve(self, index: ScopedIndex, query: QueryBundle, k: int) -> list[KnowledgeHit]: ...


class MemoryRetriever(Protocol):
    async def recall(self, index: ScopedIndex, query: QueryBundle, k: int) -> list[MemoryHit]: ...


def rank_score(rank: int) -> float:
    """A display score for a single ranked list: first → 0.95, decaying towards 0.5."""
    return round(0.5 + 0.45 / (1 + rank), 4)


class ScriptedKnowledgeRetriever:
    uses_vectors = False

    async def retrieve(self, index: ScopedIndex, query: QueryBundle, k: int) -> list[KnowledgeHit]:
        q = fts_query(query.text)
        if q is None:
            return []
        cands = await index.knowledge_fts(q, k)
        return await index.knowledge_hits([c.rid for c in cands], {c.rid: rank_score(c.rank) for c in cands})


class NaiveKnowledgeRetriever:
    uses_vectors = True

    async def retrieve(self, index: ScopedIndex, query: QueryBundle, k: int) -> list[KnowledgeHit]:
        q = fts_query(query.text)
        lists: list[list[Candidate]] = []
        if q is not None:
            lists.append(await index.knowledge_fts(q, POOL))
        vec = query.vectors.get(index.active_space)
        if vec is not None:
            lists.append(await index.knowledge_knn(vec, POOL))
        fused: dict[int, float] = {}
        for lst in lists:
            for c in lst:
                fused[c.rid] = fused.get(c.rid, 0.0) + 1.0 / (RRF_K + 1 + c.rank)
        best = sorted(fused.items(), key=lambda x: (-x[1], x[0]))[:k]
        top = 2.0 / (RRF_K + 1)
        return await index.knowledge_hits([rid for rid, _ in best],
                                          {rid: round(min(1.0, s / top), 4) for rid, s in best})


class ScriptedMemoryRetriever:
    async def recall(self, index: ScopedIndex, query: QueryBundle, k: int) -> list[MemoryHit]:
        return await index.memory_recent(k)


class NaiveMemoryRetriever:
    async def recall(self, index: ScopedIndex, query: QueryBundle, k: int) -> list[MemoryHit]:
        q = fts_query(query.text)
        return await index.memory_fts(q, k) if q is not None else []


def hits_json(hits: list[Any]) -> list[dict[str, Any]]:
    return [h.model_dump() for h in hits]

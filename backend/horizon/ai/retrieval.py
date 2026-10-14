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
- `QueryBundle`: one per triggering user message, its query vectors per space (D12). M12 (rag D10): the `agent` deep
  path fills the rest of it, one per speaker's search: what was searched and why, frozen into the plan.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Protocol

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


QuerySource = Literal["as_written", "rewritten", "fallback", "debate", "watch"]
DISPLAY_MAX = 120


@dataclass(frozen=True)
class QueryBundle:
    """What a search looks for. `naive` and `scripted` read `text` and `vectors` (one query text). M12's `agent` deep path
    fills the rest (rag D10): `dense_texts` (≤ 2, K4's table), `terms` (the BM25 terms, rarest first) and `dense`
    (`{space id: {dense text index: vector}}`, a vector missing when late or when the speaker has none)."""

    text: str
    vectors: dict[str, list[float]] = field(default_factory=dict)   # space id → query vector (naive, scripted)
    message_id: str | None = None          # the message being answered (debate, watch: the line being answered)
    speaker_id: str | None = None          # whose search this is
    mode: str = ""
    source: QuerySource = "as_written"
    message: str = ""                      # the text as written
    rewrite: str | None = None             # the accepted rewrite
    earlier: tuple[str, ...] = ()          # the two lines before the message, "Name: text"
    dense_texts: tuple[str, ...] = ()      # the texts embedded
    terms: tuple[str, ...] = ()            # the BM25 terms in order
    dense: dict[str, dict[int, list[float]]] = field(default_factory=dict)
    display: str = ""                      # `TurnTrace.knowledge.query`: ≤ 120 characters

    def to_json(self) -> dict[str, Any]:
        out = asdict(self)
        out["dense"] = {sp: {str(i): v for i, v in vs.items()} for sp, vs in self.dense.items()}
        out["earlier"], out["dense_texts"], out["terms"] = list(self.earlier), list(self.dense_texts), list(self.terms)
        return out

    @staticmethod
    def from_json(d: dict[str, Any]) -> QueryBundle:
        return QueryBundle(**{**d, "earlier": tuple(d.get("earlier") or ()),
                              "dense_texts": tuple(d.get("dense_texts") or ()), "terms": tuple(d.get("terms") or ()),
                              "dense": {sp: {int(i): list(v) for i, v in vs.items()}
                                        for sp, vs in (d.get("dense") or {}).items()},
                              "vectors": dict(d.get("vectors") or {})})

    def vectors_in(self, space_id: str) -> list[list[float]]:
        """The dense texts' vectors in one space, in dense-text order (missing ones left out)."""
        got = self.dense.get(space_id, {})
        return [got[i] for i in sorted(got)]


@dataclass(frozen=True)
class Candidate:
    rid: int
    rank: int          # 0-based position in its list
    vector: list[float] | None = field(default=None, compare=False)   # M12: a KNN hit's stored vector, read with it


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
    # M12 (rag D10, D12): the agent pipeline's reads
    async def term_counts(self, terms: list[str]) -> dict[str, int]: ...
    async def vectors(self, rids: list[int]) -> dict[int, list[float]]: ...
    async def piece_texts(self, rids: list[int]) -> dict[int, str]: ...


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


# ── M12: the shared search pipeline (doc 10 K5; rag design D12; retrieval "The agent search pipeline") ──
@dataclass(frozen=True)
class SearchParams:
    """The pipeline's numbers come from the caller: `agent` documents pass `retrieval.agent` (20, 8, 0.7); recall (M13)
    passes doc 09 M9's own (10, 6)."""

    pool: int = 20
    candidates: int = 8
    mmr_lambda: float = 0.7


@dataclass(frozen=True)
class Scored:
    rid: int
    score: float          # the fused score, min–max normalised within the pool
    order: int            # 0-based position in the fused order


@dataclass(frozen=True)
class SearchResult:
    space_id: str
    candidates: list[Scored]          # MMR's picks, in pick order
    pool: list[Scored]                # the fused top `pool`
    lists: dict[str, int] = field(default_factory=dict)   # how many each list returned (bm25, dense)


def rrf(lists: list[list[int]], k: int = RRF_K) -> list[tuple[int, float]]:
    """Reciprocal-rank fusion: Σ 1 / (k + 1 + rank) per list (rank 0-based); sorted best first, ties by rid."""
    fused: dict[int, float] = {}
    for lst in lists:
        for rank, rid in enumerate(lst):
            fused[rid] = fused.get(rid, 0.0) + 1.0 / (k + 1 + rank)
    return sorted(fused.items(), key=lambda x: (-x[1], x[0]))


def normalise(scored: list[tuple[int, float]]) -> list[tuple[int, float]]:
    """Min–max within the pool to [0, 1]; a single item, or all equal, is 1.0 (K5)."""
    if not scored:
        return []
    hi, lo = max(s for _, s in scored), min(s for _, s in scored)
    if hi == lo:
        return [(r, 1.0) for r, _ in scored]
    return [(r, (s - lo) / (hi - lo)) for r, s in scored]


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = math.sumprod(a, b)
    na, nb = math.sqrt(math.sumprod(a, a)), math.sqrt(math.sumprod(b, b))
    return dot / (na * nb) if na and nb else 0.0


def jaccard(a: str, b: str) -> float:
    wa, wb = set(_WORD.findall(a.lower())), set(_WORD.findall(b.lower()))
    return len(wa & wb) / len(wa | wb) if wa or wb else 0.0


def mmr(pool: list[Scored], n: int, lam: float, vectors: dict[int, list[float]], texts: dict[int, str]) -> list[Scored]:
    """MMR over the pool: relevance is the normalised score; similarity the stored vectors' cosine, or the Jaccard of
    lower-cased words when either piece has no vector. Ties go to the fused order (then rid, through `order`)."""
    left = list(pool)
    picked: list[Scored] = []
    norm = {r: math.sqrt(math.sumprod(v, v)) or 1.0 for r, v in vectors.items()}

    def sim(a: int, b: int) -> float:
        if a in vectors and b in vectors and len(vectors[a]) == len(vectors[b]):
            return math.sumprod(vectors[a], vectors[b]) / (norm[a] * norm[b])
        return jaccard(texts.get(a, ""), texts.get(b, ""))

    # each candidate's highest similarity to anything picked, updated with one comparison per pick
    nearest = {c.rid: 0.0 for c in left}
    while left and len(picked) < n:
        best = max(left, key=lambda c: (lam * c.score - (1 - lam) * nearest[c.rid], -c.order))
        picked.append(best)
        left.remove(best)
        for c in left:
            nearest[c.rid] = max(nearest[c.rid], sim(c.rid, best.rid))
    return picked


async def search(index: ScopedIndex, bundle: QueryBundle, params: SearchParams) -> SearchResult:
    """BM25 top `pool` over the bundle's terms; dense top `pool` per dense text with a vector in the index's space;
    the dense lists fused first (RRF), then RRF over BM25 and dense; min–max normalised; MMR picks `candidates`."""
    from horizon.ai.agent.query import fts_or

    q = fts_or(bundle.terms)
    bm25 = [c.rid for c in await index.knowledge_fts(q, params.pool)] if q is not None else []
    known: dict[int, list[float]] = {}   # vectors that came with the KNN hits (a vec0 lookup by rid is slow)
    dense_lists: list[list[int]] = []
    for v in bundle.vectors_in(index.active_space):
        hits = await index.knowledge_knn(v, params.pool)
        known.update({c.rid: c.vector for c in hits if c.vector is not None})
        dense_lists.append([c.rid for c in hits])
    dense = [rid for rid, _ in rrf(dense_lists)] if len(dense_lists) > 1 else (dense_lists[0] if dense_lists else [])
    fused = rrf([x for x in (bm25, dense) if x])[:params.pool]
    pool = [Scored(rid=rid, score=round(s, 6), order=i) for i, (rid, s) in enumerate(normalise(fused))]
    rids = [c.rid for c in pool]
    vectors = {r: known[r] for r in rids if r in known}
    missing = [r for r in rids if r not in vectors]
    if missing:
        vectors.update(await index.vectors(missing))
    texts = await index.piece_texts([r for r in rids if r not in vectors]) if len(vectors) < len(rids) else {}
    return SearchResult(space_id=index.active_space, candidates=mmr(pool, params.candidates, params.mmr_lambda,
                                                                     vectors, texts),
                        pool=pool, lists={"bm25": len(bm25), "dense": len(dense)})

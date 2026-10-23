"""Recall: the speaker's search over this session's earlier lines and its overflow memories, Jev call 2 and the keep
rule (docs/ai/09 M9; memory design D30–D35; session-recall spec).

**The search (D31).** Per corpus (`SessionLines`, `Overflow`): BM25 top `pool` ∪ dense top `pool` per query text with a
vector, RRF, min–max (`retrieval.search` with λ = 1.0, so its picks are the fused order). An overflow memory's score
is weighted by (0.5 + 0.5 × importance) × recency × mode weight (the list's own factors, D22); lines are unweighted.
At most `perCorpus` from each go into the merge, best weighted score first (ties: lines first, then the fused order).
MMR over the merge with `recall.mmrLambda` picks `candidates`, keyed `line:{rid}` / `mem:{rid}` since the two tables'
rids collide; similarity is the stored vectors' cosine (both in the active space), else the Jaccard of words.

**The query texts (D32).** The documents' bundle when that branch ran (the message, plus its rewrite); a recall-only
turn never rewrites: the message, and the message with its two earlier lines. The message's vector is waited for to the
end under `docsWaitAll` (U-56), else at most `queryEmbedWaitMs`; without one, BM25 only (`lists.dense == 0`).

**Jev call 2 (D33).** One `recall` request per candidate (≤ 6), all at once, each read by `recall.checkMs` from when it
was sent (U-56: to the end, under `retrieval.agent.docsWaitAll`, as the documents' checks); a 429 falls back at
once. Up to `keep` (3) at or above `t_recall` are kept, by p. Every answer missing: the top `fallbackKeep` (2) of the
merged order, unscored (`fallback`). Some back: only those decide (recall never
abstains, so partial evidence is safe).

**Phase 10 (the maintainer's choices, m13.md):** the session's lines are searched by vector only when the query has one
(`recall.linesDense`; BM25 matched chat noise: in-session hit@3 97 % dense-only against 75 % hybrid), and the overflow
stays hybrid. When nothing reaches `t_recall`, the top candidate is still kept if it stands out: p ≥
`recall.standoutP` (0.25) and ≥ `recall.standoutRatio` (3) × the runner-up (an indirect question about an overflow
memory gets p 0.2–0.45 while the rest get ≈ 0.03).
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from horizon.ai.agent import query as q
from horizon.ai.contexts import DeepRequest, RecallHit, RecallOutcome
from horizon.ai.decider import DecisionCall, NoulAnswer
from horizon.ai.questions import bank
from horizon.ai.retrieval import QueryBundle, SearchParams, jaccard, search

PURPOSE = "deep_check"
QUESTION = "recall"
LINE, MEMORY = "line", "memory"
DEFAULT_WEIGHTS = {"one_on_one": 1.0, "group": 1.0, "debate": 0.85, "watch": 0.7}


@dataclass(frozen=True)
class Item:
    """One candidate in the merge."""

    key: str                    # "line:{rid}" | "mem:{rid}"
    kind: str                   # line | memory
    rid: int
    score: float                # weighted, normalised
    order: int                  # its place in its corpus's fused order
    hit: RecallHit
    vector: list[float] | None = None


class DenseOnly:
    """A corpus with its keyword search switched off (the session's lines when the query has a vector)."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner

    async def fts(self, query: str, limit: int) -> list[Any]:
        return []

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


@dataclass
class Found:
    picked: list[Item]
    merged: list[Item]
    lists: dict[str, int]


def t_recall() -> float:
    return float(bank().get(QUESTION).thresholds.get("t_recall", 0.5))


def _iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo is not None else d.replace(tzinfo=UTC)


def memory_weight(importance: float, created_at: str, last_recalled_at: str | None, source_mode: str | None,
                  now: datetime, knobs: Any) -> float:
    """D31: (0.5 + 0.5 × importance) × recency × mode weight, with D22's recency and mode weights."""
    stamps = [d for d in (_iso(created_at), _iso(last_recalled_at)) if d is not None]
    days = max(0.0, (now - max(stamps)).total_seconds() / 86400.0) if stamps else 0.0
    floor = float(getattr(knobs, "recency_floor", 0.5))
    half = float(getattr(knobs, "half_life_days", 30.0))
    recency = max(floor, 0.5 ** (days / half))
    weigh = getattr(knobs, "weight", None)
    mode = float(weigh(source_mode)) if callable(weigh) else DEFAULT_WEIGHTS.get(source_mode or "", 1.0)
    return float((0.5 + 0.5 * float(importance)) * recency * mode)


def merge(lines: Sequence[Item], memories: Sequence[Item], per_corpus: int) -> list[Item]:
    """D31 step 4: ≤ `per_corpus` from each, by weighted score; ties go to lines, then the fused order."""
    pool = [*sorted(lines, key=lambda i: (-i.score, i.order))[:per_corpus],
            *sorted(memories, key=lambda i: (-i.score, i.order))[:per_corpus]]
    return sorted(pool, key=lambda i: (-i.score, 0 if i.kind == LINE else 1, i.order))


def mmr(items: Sequence[Item], n: int, lam: float) -> list[Item]:
    """D31 step 5: MMR over composite keys; cosine of stored vectors (same length), else the Jaccard of words."""
    left = list(items)
    picked: list[Item] = []
    nearest = {i.key: 0.0 for i in left}

    def sim(a: Item, b: Item) -> float:
        if a.vector is not None and b.vector is not None and len(a.vector) == len(b.vector):
            na, nb = math.sqrt(math.sumprod(a.vector, a.vector)), math.sqrt(math.sumprod(b.vector, b.vector))
            return math.sumprod(a.vector, b.vector) / (na * nb) if na and nb else 0.0
        return jaccard(a.hit.text, b.hit.text)

    rank = {i.key: n_ for n_, i in enumerate(items)}
    while left and len(picked) < n:
        best = max(left, key=lambda c: (lam * c.score - (1 - lam) * nearest[c.key], -rank[c.key]))
        picked.append(best)
        left.remove(best)
        for c in left:
            nearest[c.key] = max(nearest[c.key], sim(c, best))
    return picked


def _terms(texts: Sequence[str]) -> tuple[str, ...]:
    """Recall's BM25 terms: the texts' words in order, de-duplicated, ≤ 24 (never ranked against the documents)."""
    terms: list[str] = []
    for t_ in texts:
        terms += [w for w in q.words(t_) if w not in terms]
    return tuple(terms[:q.MAX_TERMS_REWRITTEN])


def recall_bundle(req: DeepRequest, docs: QueryBundle | None, dense: dict[int, list[float]], space_id: str) -> QueryBundle:
    """D32: the documents' texts and vectors when that branch ran; else the message and, with its earlier lines, its
    words. The documents' own terms are not reused: they are ranked against the speaker's documents and leave out
    words no passage holds (U-34), which are often what recall looks for ("my sister")."""
    if docs is not None:   # its own vector when the documents' search had none (no indexed documents)
        out = docs if docs.dense.get(space_id) or not dense else replace(docs, dense={space_id: dense})
        return replace(out, terms=_terms([t for t in (docs.rewrite, docs.message or docs.text) if t]))
    texts = [req.message, "\n".join([*req.earlier, req.message])] if req.earlier else [req.message]
    return QueryBundle(text=req.message, message_id=req.message_id, speaker_id=req.speaker.id,
                       mode=req.session.mode, source="as_written", message=req.message, earlier=tuple(req.earlier),
                       dense_texts=tuple(texts), terms=_terms(texts),
                       dense={space_id: dense} if dense else {}, display=q.display(req.message))


async def find(io: Any, req: DeepRequest, bundle: QueryBundle, knobs: Any, memory_knobs: Any,
               now: datetime) -> Found:
    """D31: both corpora searched, weighted, merged and picked."""
    space = io.active_space()
    params = SearchParams(pool=knobs.pool, candidates=knobs.pool, mmr_lambda=1.0)
    lines_c = io.lines(req.session.world.id, req.session.session_id, req.upto_seq, space)
    over_c = io.overflow(req.session.world.id, req.speaker.id, list(req.block_ids), space) if req.has_overflow else None
    dense_lines = bool(getattr(knobs, "lines_dense", False)) and bool(bundle.dense.get(space))
    got_lines = await search(DenseOnly(lines_c) if dense_lines else lines_c, bundle, params)
    got_mem = await search(over_c, bundle, params) if over_c is not None else None
    lists = {"lines_bm25": got_lines.lists.get("bm25", 0), "lines_dense": got_lines.lists.get("dense", 0)}
    line_rows = await lines_c.rows([c.rid for c in got_lines.candidates])
    line_vecs = await lines_c.vectors([c.rid for c in got_lines.candidates])
    lines = [Item(key=f"line:{c.rid}", kind=LINE, rid=c.rid, score=c.score, order=c.order, vector=line_vecs.get(c.rid),
                  hit=RecallHit(kind="line", id=r.message_id, text=r.text, before=r.before))
             for c in got_lines.candidates if (r := line_rows.get(c.rid)) is not None]
    memories: list[Item] = []
    if got_mem is not None and over_c is not None:
        lists.update(memories_bm25=got_mem.lists.get("bm25", 0), memories_dense=got_mem.lists.get("dense", 0))
        mrows = await over_c.rows([c.rid for c in got_mem.candidates])
        mvecs = await over_c.vectors([c.rid for c in got_mem.candidates])
        for c in got_mem.candidates:
            m = mrows.get(c.rid)
            if m is None:
                continue
            w = memory_weight(m.importance, m.created_at, m.last_recalled_at, m.source_mode, now, memory_knobs)
            memories.append(Item(key=f"mem:{c.rid}", kind=MEMORY, rid=c.rid, score=round(c.score * w, 6),
                                 order=c.order, vector=mvecs.get(c.rid),
                                 hit=RecallHit(kind="memory", id=m.id, text=m.text, memory_kind=m.kind,
                                               source_session_id=m.source_session_id)))
    merged = merge(lines, memories, knobs.per_corpus)
    return Found(picked=mmr(merged, knobs.candidates, knobs.mmr_lambda), merged=merged, lists=lists)


def _words(text: str, n: int) -> str:
    w = " ".join(text.split()).split(" ")
    return " ".join(w) if len(w) <= n else " ".join(w[:n]) + " …"


def candidate_text(hit: RecallHit, line_words: int) -> str:
    """D33's quoted_candidate: a line with the message before it, each ≤ 60 words; a memory's text."""
    if hit.kind == "line":
        return "\n".join(_words(x, line_words) for x in (hit.before, hit.text) if x)
    return hit.text


async def check(deps: Any, req: DeepRequest, bundle: QueryBundle, picked: Sequence[Item],
                knobs: Any, *, wait_ms: float | None = None) -> tuple[list[float | None], float | None]:
    """D33: one request per candidate, all started at once, each read by `checkMs` (U-56: `wait_ms`, to the end under
    `docsWaitAll`) from when it was sent. Returns each candidate's p (None: missing) and the slowest landing (ms)."""
    if not picked:
        return [], None
    decider = deps.decider()
    b = bank()
    ctx = req.session.call_ctx(PURPOSE, character_id=req.speaker.id, message_id=req.reply_message_id)
    name = req.speaker.name if len(req.speaker.name) <= 40 else req.speaker.first_name[:40]
    sent = deps.clock().now()
    at = sent + timedelta(milliseconds=knobs.check_ms if wait_ms is None else wait_ms)
    calls: list[DecisionCall] = []
    for it in picked:
        state = {"mode": req.session.mode, "candidate_kind": "earlier line" if it.kind == LINE else "memory",
                 "quoted_query": bundle.display or q.display(req.message),
                 "quoted_candidate": candidate_text(it.hit, knobs.line_words)}
        calls.append(decider.start(state, {f"{QUESTION}:{it.hit.id}": b.question(QUESTION, name=name, about=it.hit.id)},
                                   ctx, purpose=PURPOSE))
    ps: list[float | None] = []
    try:
        for it, dc in zip(picked, calls, strict=True):   # all in flight; reading against one instant is one wait
            try:
                res = await dc.by(at)
            except asyncio.CancelledError:
                raise
            except Exception:   # late, 429 (a hot path: no retry), failed: missing
                ps.append(None)
                continue
            a = res.answers.get(f"{QUESTION}:{it.hit.id}")
            ps.append(float(a.p) if isinstance(a, NoulAnswer) and a.source == "jev" else None)
    except asyncio.CancelledError:
        for dc in calls:
            dc.cancel()
        raise
    return ps, (deps.clock().now() - sent).total_seconds() * 1000


def keep(picked: Sequence[Item], merged: Sequence[Item], ps: Sequence[float | None], knobs: Any
         ) -> tuple[list[RecallHit], RecallOutcome]:
    """D33's rule. Every answer missing: the top `fallbackKeep` of the merged order, unscored."""
    if not picked:
        return [], "none"
    if all(p is None for p in ps):
        return [it.hit.model_copy(update={"p": None}) for it in list(merged)[:knobs.fallback_keep]], "fallback"
    th = t_recall()
    scored = sorted(((p, i, it) for i, (it, p) in enumerate(zip(picked, ps, strict=True)) if p is not None and p >= th),
                    key=lambda x: (-x[0], x[1]))
    if not scored:   # phase 10: a clear standout is kept even below t_recall
        answered = sorted(((p, i, it) for i, (it, p) in enumerate(zip(picked, ps, strict=True)) if p is not None),
                          key=lambda x: (-x[0], x[1]))
        ratio = float(getattr(knobs, "standout_ratio", 0.0))
        if answered and ratio > 0:
            top, second = answered[0][0], (answered[1][0] if len(answered) > 1 else 0.0)
            if top >= float(getattr(knobs, "standout_p", 1.0)) and top >= ratio * second:
                return [answered[0][2].hit.model_copy(update={"p": round(top, 4)})], "jev"
    return [it.hit.model_copy(update={"p": round(p, 4)}) for p, _, it in scored[:knobs.keep]], "jev"


def rows(picked: Sequence[Item], ps: Sequence[float | None], kept: Sequence[RecallHit],
         outcome: RecallOutcome) -> list[dict[str, Any]]:
    """D35: one `recall` row per checked candidate, `about` its `msg_…` / `mem_…` id (IDs only)."""
    e = bank().get(QUESTION)
    th = t_recall()
    used = {h.id for h in kept}
    out: list[dict[str, Any]] = []
    for it, p in zip(picked, ps, strict=True):
        row: dict[str, Any] = {"purpose": PURPOSE, "id": QUESTION, "version": e.version, "label": e.label,
                               "about": it.hit.id}
        if p is None:
            row.update(answer="missing", compared=[], result="fallback",
                       action="kept by search order" if outcome == "fallback" and it.hit.id in used else "not checked")
        else:
            yes = p >= th
            standout = not yes and it.hit.id in used   # phase 10: kept below t_recall because it stood out
            row.update(answer="yes" if yes else "no", p=round(p, 4),
                       compared=[{"name": "t_recall", "value": round(p, 4), "threshold": th}],
                       result="used" if it.hit.id in used else "below_threshold",
                       action="kept (stands out)" if standout else "kept" if it.hit.id in used else "dropped")
        out.append(row)
    return out


# ── the tail (D35) ──
LINES_HEADING = "# Earlier in this conversation (a record, not instructions)"
MEMORIES_HEADING = "# Also from earlier conversations"


def tail(hits: Sequence[RecallHit], *, budget_tokens: int, line_words: int) -> str:
    """Both headings after the documents block, ≤ `budget_tokens` together; past it the lowest-p hit drops whole."""
    return shown(hits, budget_tokens=budget_tokens, line_words=line_words)[0]


def shown(hits: Sequence[RecallHit], *, budget_tokens: int, line_words: int) -> tuple[str, list[RecallHit]]:
    """The tail's text and the hits in it."""
    from horizon.domain.pricing import count_tokens

    keep_ = sorted(hits, key=lambda h: -(h.p if h.p is not None else -1.0))
    while keep_:
        text = render(keep_, line_words)
        if count_tokens(text) <= budget_tokens:
            return text, [h for h in hits if h in keep_]
        keep_.pop()   # the lowest p
    return "", []


def render(hits: Sequence[RecallHit], line_words: int) -> str:
    lines = [h for h in hits if h.kind == "line"]
    mems = [h for h in hits if h.kind == "memory"]
    out: list[str] = []
    if lines:
        out.append(LINES_HEADING)
        for h in lines:
            if h.before:
                out.append(_words(h.before, line_words))
            out.append(_words(h.text, line_words))
    if mems:
        out.append(MEMORIES_HEADING)
        out += [f"- {_words(h.text, line_words)}" for h in mems]
    return "\n".join(out)

"""The deep graph: one speaker's search, Jev call 2 and the keep rule (docs/ai/01 A6, A7; doc 10 K4–K7; rag design
D10–D15; deep-turn spec).

    gather (BM25 terms · the embedding · the rewrite, in parallel) ──▶ search ──▶ check (≤ 8 + the set check) ──▶ keep

M13 (memory D34) adds recall beside it, when "needs something from earlier?" said yes for the speaker:

    gather ─┬─▶ search docs ──▶ check docs (≤ 8 + set) ──▶ keep docs ─┐
            └─▶ search recall ─▶ check recall (≤ 6) ─────▶ keep recall ─┴─▶ out

The two branches run as children of the deep work (`vclock.together`): each keeps its own fallback, and Stop, a
superseding message or `clear()` cancels both. A recall-only request skips gather (no rewrite) and the documents.

- **gather** (D10, D11): the message's keyword terms, its embedding (only when the speaker has an `indexed` source in
  the index's space) and, in 1:1 and group, the rewrite when the message isn't standalone or isn't English, all start
  together. A rewrite in time joins the terms; a failed or late one is a fallback query (the message, and the two
  earlier lines with it). The search waits for the message's vector at most `retrieval.agent.queryEmbedWaitMs`
  (200 ms, rag 11.9) from when it needs it; a late one is still recorded, and the search runs on keywords.
- **No wait for a text born after the gate** (rag 11.9, the user's choice): the rewrite's vector and the fallback's
  "earlier lines + message" vector are requested but never waited for. Check 2 measured the query embedding at p50
  6.8 s that evening, so that wait only ever added time; a vector already served (the LRU, on regenerate) is used.
- **The early start** (rag 11.5, the user's choice of 2026-10-15): from Malaysia a query embedding takes ≈ 1.1 s at
  the median, so the 1:1, cast (group) and follow plans start the user message's embedding with Jev call 1, for a
  candidate with vectors (`start_early_embedding`). In 1:1 the rewrite of a short message starts there too
  (`rewrite.start_early`, rag 11.9), and gather joins it. gather's own request for the same text joins it through the
  embedder's in-flight de-duplication and LRU, so no second call is made. Watch and debate start at the gate as before
  (their deep work runs ahead of the turn).
- **search** (D12): `retrieval.search` with `retrieval.agent`'s numbers, in the speaker's `ScopedIndex`.
- **check** (D13): one `deep_check` request per candidate, all started at once, each read by `deepCheckMs` from when
  it was sent; a 429 falls back at once (a hot-path purpose). The set check when no passage is found and two or more
  are usable.
- **keep** (D14): `keep.keep`, then the kept passages numbered [1]…[k].

Every Jev and DeepSeek call made here is cancelled with the caller (Stop, a superseding message, `clear()`), and its
request still settles and is recorded `cancelled` (M9 D8). A bug inside raises to the caller, which turns it into a
quick reply with a `fallback` row (`run_safely`).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import operator
from collections.abc import Sequence
from datetime import timedelta
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from horizon.ai.agent import keep as keeping
from horizon.ai.agent import query as q
from horizon.ai.agent import recall as rc
from horizon.ai.agent import rewrite as rw
from horizon.ai.agent.gates import thresholds
from horizon.ai.contexts import DeepRequest, DeepResult, KnowledgeHit, TurnContext
from horizon.ai.decider import DecisionCall, NoulAnswer, ScoreAnswer
from horizon.ai.embedder import strip_extension
from horizon.ai.questions import bank
from horizon.ai.retrieval import QueryBundle, ScopedIndex, SearchParams, SearchResult, search
from horizon.domain import vclock
from horizon.gateway.context import call_ctx
from horizon.gateway.pipeline import RECORDED_SINK
from horizon.tracing import TRACER, no_trace

log = logging.getLogger("horizon.ai.deep")

PURPOSE = "deep_check"
PASSAGE = "passage"
PASSAGE_SET = "passage_set"
LEVEL_ANSWER = {0: "doesn't help", 1: "partly", 2: "answers"}
NODES = ("gather", "search", "check", "keep")


class DeepRun(TypedDict, total=False):
    req: DeepRequest
    bundle: QueryBundle
    rewrite: rw.Rewrite | None
    result: SearchResult
    hits: dict[int, KnowledgeHit]
    checked: list[keeping.Checked]
    set_yes: bool | None
    set_info: dict[str, Any] | None
    pool_ids: dict[int, str]
    failed: bool
    rows: list[dict[str, Any]]
    calls: list[dict[str, Any]]
    slowest: float | None
    out: DeepResult
    path: Annotated[list[str], operator.add]


def _seconds(ms: float) -> float:
    return ms / 1000.0


class DeepSteps:
    """The graph's steps over the runtime's reads (`deps.deep_io()`) and the planner's Decider."""

    def __init__(self, deps: Any) -> None:
        self.deps = deps

    # ── helpers ──
    def knobs(self) -> Any:
        r = self.deps.retrieval()
        return r.agent if r is not None and r.agent is not None else None

    def index(self, req: DeepRequest) -> ScopedIndex:
        idx: ScopedIndex = self.deps.deep_io().index(req.session.world.id, req.speaker.id)
        return idx

    async def _embed(self, req: DeepRequest, texts: list[str], space: Any) -> dict[int, list[float]]:
        """The query embedding of `texts`, linked to the message being answered (never to the reply, so the sink that
        collects the deep work's rows for the reply leaves it alone)."""
        RECORDED_SINK.set(None)
        ctx = call_ctx("query_embed", world_id=req.session.world.id, session_id=req.session.session_id,
                       message_id=req.message_id)
        try:
            out = await self.deps.deep_io().embedder().embed(texts, kind="query", space=space, ctx=ctx)
        except Exception as e:   # a cap, a provider error: keywords only (the existing rule)
            log.info("query embedding skipped (%s); keywords only", getattr(e, "code", type(e).__name__))
            return {}
        return dict(enumerate(out.vectors))

    def _spawn(self, name: str, coro: Any) -> asyncio.Task[Any]:
        task: asyncio.Task[Any] = self.deps.spawn(name, coro)   # the runtime's tracked spawn (its only way)
        return task

    async def _wait(self, task: asyncio.Task[Any] | None, seconds: float) -> Any:
        if task is None:
            return None
        if await vclock.wait_at_most(self.deps.clock(), task, seconds):
            return None if task.cancelled() or task.exception() is not None else task.result()
        return None

    # ── gather ──
    async def gather(self, req: DeepRequest) -> tuple[QueryBundle, rw.Rewrite | None]:
        knobs = self.knobs()
        wait = _seconds(knobs.query_embed_wait_ms)
        index = self.index(req)
        io = self.deps.deep_io()
        space = await io.space(index.active_space)
        vec_ok = space is not None and io.key_set() and await io.has_vectors(req.speaker.id, index.active_space)
        th = thresholds()
        rewriting = req.rewrites and rw.needed(req.nouls.standalone if req.nouls else None,
                                                req.nouls.english if req.nouls else None,
                                                t_standalone=th["t_standalone"], t_english=th["english"])
        watch = req.kind in ("scene", "opening") or req.session.mode == "watch"
        with_earlier = "\n".join([*req.earlier, req.message]) if req.earlier else ""
        first_texts = [req.message, with_earlier] if watch and with_earlier else [req.message]
        tasks: list[asyncio.Task[Any]] = []
        try:
            embed = self._spawn(f"query-embed:{req.speaker.id}", self._embed(req, first_texts, space)) \
                if vec_ok else None
            if embed is not None:
                tasks.append(embed)
            rewrite: rw.Rewrite | None = None
            if rewriting:
                tctx = TurnContext(session=req.session, speaker=req.speaker, message_id=req.reply_message_id,
                                   max_tokens=1)
                rewrite = await rw.run(self.deps, tctx, timeout_s=_seconds(knobs.rewrite_ms),
                                       stored=req.stored_rewrite, early=rw.early_key(tctx, req.message_id))
            source: Any
            extra: dict[int, list[float]] = {}
            if req.session.mode == "debate":
                source = "debate"
                terms = await q.agent_terms(index, req.message)
            elif watch:
                source = "watch"
                terms = await q.agent_terms(index, req.message)
            elif rewrite is not None and rewrite.text:
                source = "rewritten"
                terms = await q.agent_terms(index, req.message, rewrite=rewrite.text)
                if vec_ok:
                    t2 = self._spawn(f"query-embed:{req.speaker.id}:rw", self._embed(req, [rewrite.text], space))
                    tasks.append(t2)
                    got = await self._wait(t2, 0.0)   # never waited for (rag 11.9)
                    if got:
                        extra[0] = got[0]
            elif rewrite is not None:
                source = "fallback"
                terms = await q.agent_terms(index, req.message, extra=req.previous_user)
                if vec_ok and with_earlier:
                    t2 = self._spawn(f"query-embed:{req.speaker.id}:fb", self._embed(req, [with_earlier], space))
                    tasks.append(t2)
                    got = await self._wait(t2, 0.0)   # never waited for (rag 11.9)
                    if got:
                        extra[1] = got[0]
            else:
                source = "as_written"
                terms = await q.agent_terms(index, req.message)
            first = await self._wait(embed, wait) or {}
        except asyncio.CancelledError:
            for t in tasks:
                t.cancel()
            raise
        dense: dict[int, list[float]] = {}
        if source == "rewritten":
            dense = {**extra, **({1: first[0]} if 0 in first else {})}
        elif source == "fallback":
            dense = {**({0: first[0]} if 0 in first else {}), **extra}
        else:
            dense = dict(first)
        bundle = q.bundle(source=source, mode=req.session.mode, speaker_id=req.speaker.id, message=req.message,
                          message_id=req.message_id, earlier=req.earlier,
                          rewrite=rewrite.text if rewrite is not None else None, terms=terms,
                          dense={index.active_space: dense} if dense else {})
        return bundle, rewrite

    # ── recall (M13, memory D31–D34) ──
    async def recall(self, req: DeepRequest, docs_bundle: QueryBundle | None) -> dict[str, Any]:
        """Recall's branch: its query (the documents' bundle, or the message and its earlier lines), the search over
        the session's lines and the overflow, Jev call 2 and the keep rule."""
        r = self.deps.retrieval()
        knobs = r.agent.recall
        io = self.deps.deep_io()
        space_id = io.active_space()
        dense: dict[int, list[float]] = {}
        # the message's own vector (the early start's, usually already served) when the documents' search had none
        if (docs_bundle is None or not docs_bundle.dense.get(space_id)) and io.key_set():
            space = await io.space(space_id)
            if space is not None:
                task = self._spawn(f"query-embed:{req.speaker.id}:recall", self._embed(req, [req.message], space))
                try:
                    dense = await self._wait(task, _seconds(self.knobs().query_embed_wait_ms)) or {}
                except asyncio.CancelledError:
                    task.cancel()
                    raise
        bundle = rc.recall_bundle(req, docs_bundle, dense, space_id)
        found = await rc.find(io, req, bundle, knobs, self.deps.memory_knobs(), self.deps.clock().now())
        ps, slowest = await rc.check(self.deps, req, bundle, found.picked, knobs)
        kept, outcome = rc.keep(found.picked, found.merged, ps, knobs)
        rows = rc.rows(found.picked, ps, kept, outcome)
        checks = [{"id": it.hit.id, "kind": it.kind, "order": i, "p": p} for i, (it, p) in
                  enumerate(zip(found.picked, ps, strict=True))]
        calls: list[dict[str, Any]] = []
        if outcome == "fallback":
            calls.append({"purpose": PURPOSE, "model": self.deps.prices.decision.model, "costUsd": 0.0,
                          "latencyMs": float(slowest or knobs.check_ms), "fallback": True})
        return {"recall": kept, "recall_outcome": outcome, "recall_rows": rows, "recall_checks": checks,
                "recall_lists": found.lists, "recall_calls": calls}

    async def docs_chain(self, req: DeepRequest, bundle: QueryBundle, rewrite: rw.Rewrite | None) -> DeepResult:
        """The documents branch end to end (search, check, keep), for a turn that also recalls."""
        result, hits = await self.search(req, bundle)
        pool = await self.pool_ids(req, result)
        checked, set_yes, failed, slowest, set_info = await self.check(req, bundle, result, hits)
        return self.keep(req, bundle, rewrite, result, hits, checked, set_yes, failed, slowest, set_info, pool)

    # ── search ──
    async def search(self, req: DeepRequest, bundle: QueryBundle) -> tuple[SearchResult, dict[int, KnowledgeHit]]:
        knobs = self.knobs()
        index = self.index(req)
        result = await search(index, bundle, SearchParams(pool=knobs.pool, candidates=knobs.candidates,
                                                          mmr_lambda=knobs.mmr_lambda))
        rids = [c.rid for c in result.candidates]
        hits = await index.knowledge_hits(rids, {c.rid: c.score for c in result.candidates})
        return result, {h.rid: h for h in hits if h.rid is not None}

    async def pool_ids(self, req: DeepRequest, result: SearchResult) -> dict[int, str]:
        """The fused pool's chunk ids (the evaluation's Recall@20; one small read)."""
        got: dict[int, str] = await self.index(req).chunk_ids([c.rid for c in result.pool])
        return got

    # ── check ──
    def _quoted_query(self, req: DeepRequest, bundle: QueryBundle) -> dict[str, Any]:
        if req.session.mode == "debate":
            return {"motion": req.motion, "argument": req.argument}
        if bundle.source == "rewritten" and bundle.rewrite:
            return {"message": req.message, "rewrite": bundle.rewrite}
        return {"message": req.message, "earlier": list(req.earlier)}

    async def check(self, req: DeepRequest, bundle: QueryBundle, result: SearchResult,
                    hits: dict[int, KnowledgeHit]
                    ) -> tuple[list[keeping.Checked], bool | None, bool, float | None, dict[str, Any] | None]:
        """Jev call 2. Returns the checked candidates, the set check's answer, whether call 2 failed as a whole, and
        the slowest check's latency (ms)."""
        knobs = self.knobs()
        th = self._passage_thresholds()
        decider = self.deps.decider()
        b = bank()
        ctx = req.session.call_ctx(PURPOSE, character_id=req.speaker.id, message_id=req.reply_message_id)
        qq = self._quoted_query(req, bundle)
        cands = [c for c in result.candidates if c.rid in hits]
        if not cands:
            return [], None, False, None, None
        sent = self.deps.clock().now()
        at = sent + timedelta(milliseconds=knobs.deep_check_ms)
        calls: list[DecisionCall] = []
        for c in cands:
            h = hits[c.rid]
            state = {"mode": req.session.mode, "quoted_query": qq,
                     "quoted_passage": {"title": strip_extension(h.title), "locator": h.locator or "", "text": h.text}}
            calls.append(decider.start(state, {f"{PASSAGE}:{h.chunk_id}": b.question(PASSAGE, about=h.chunk_id)}, ctx,
                                       purpose=PURPOSE))
        # Every request is already in flight; reading them one after another against the same instant is the same
        # wait (each read returns when its answer lands or at `at`), and the loop ends when the slowest has landed.
        # (Concurrent reads in child tasks would each give up this task's activity token.)
        results: list[Any] = []
        try:
            for dc in calls:
                try:
                    results.append(await dc.by(at))
                except asyncio.CancelledError:
                    raise
                except Exception as e:   # late, 429 (a hot path: no retry), failed: this check is missing
                    results.append(e)
        except asyncio.CancelledError:
            for dc in calls:
                dc.cancel()
            raise
        landed = {0: (self.deps.clock().now() - sent).total_seconds() * 1000}
        checked: list[keeping.Checked] = []
        for i, (c, res) in enumerate(zip(cands, results, strict=True)):
            if isinstance(res, asyncio.CancelledError):
                raise res
            key = f"{PASSAGE}:{hits[c.rid].chunk_id}"
            ans = None if isinstance(res, BaseException) else res.answers.get(key)
            if isinstance(ans, ScoreAnswer) and ans.source == "jev":
                pa, pp, unit = level_probs(ans)
                checked.append(keeping.Checked(rid=c.rid, order=i, p_answers=pa, p_partly=pp, unit=unit))
            else:
                checked.append(keeping.Checked(rid=c.rid, order=i))
        failed = not any(x.back for x in checked)
        slowest = max(landed.values()) if landed else None
        set_yes: bool | None = None
        set_info: dict[str, Any] | None = None
        if not failed and keeping.needs_set_check(checked, t_keep=th["t_keep"], t_found=th["t_found"]):
            use = keeping.best_first([x for x in checked if keeping.usable(x, th["t_keep"])])[:req.k]
            set_state: dict[str, Any] = {"mode": req.session.mode, "quoted_query": qq, "quoted_passages": [
                {"title": strip_extension(hits[x.rid].title), "locator": hits[x.rid].locator or "",
                 "text": hits[x.rid].text} for x in use]}
            started = self.deps.clock().now()
            call = decider.start(set_state, {PASSAGE_SET: b.question(PASSAGE_SET)}, ctx, purpose=PURPOSE)
            try:
                res = await call.by(started + timedelta(milliseconds=knobs.deep_check_ms))
                a = res.answers.get(PASSAGE_SET)
                set_info = {"chunkIds": [hits[x.rid].chunk_id for x in use], "p": None}
                if isinstance(a, NoulAnswer) and a.source == "jev":
                    set_yes = a.p >= th["t_set"]
                    set_info["p"] = a.p
            except asyncio.CancelledError:
                call.cancel()
                raise
            except Exception:   # late, refused or failed: the set check is missing (D7: partly)
                set_yes = None
        return checked, set_yes, failed, slowest, set_info

    @staticmethod
    def _passage_thresholds() -> dict[str, float]:
        b = bank()
        p, s = b.get(PASSAGE).thresholds, b.get(PASSAGE_SET).thresholds
        return {"t_keep": float(p.get("t_keep", 0.6)), "t_found": float(p.get("t_found", 0.6)),
                "t_set": float(s.get("t_set", 0.5))}

    # ── keep ──
    def keep(self, req: DeepRequest, bundle: QueryBundle, rewrite: rw.Rewrite | None, result: SearchResult,
             hits: dict[int, KnowledgeHit], checked: list[keeping.Checked], set_yes: bool | None, failed: bool,
             slowest: float | None, set_info: dict[str, Any] | None = None,
             pool_ids: dict[int, str] | None = None) -> DeepResult:
        th = self._passage_thresholds()
        k = keeping.keep(checked, k=req.k, t_keep=th["t_keep"], t_found=th["t_found"], set_yes=set_yes,
                         abstain_ok=req.abstain_ok, failed=failed)
        by_rid = {c.rid: c for c in checked}
        scores = {c.rid: c.score for c in result.candidates}
        kept_hits: list[KnowledgeHit] = []
        for rid in k.kept:
            h = hits.get(rid)
            if h is None:
                continue
            unit = by_rid[rid].unit if rid in by_rid and k.outcome != "fallback" else None
            kept_hits.append(h.model_copy(update={"score": round(unit, 4) if unit is not None else scores.get(rid, 0.0)}))
        n_of = {h.chunk_id: i + 1 for i, h in enumerate(kept_hits)}
        retrieved: list[dict[str, Any]] = []
        for c in result.candidates:
            h = hits.get(c.rid)
            if h is None:
                continue
            ch = by_rid.get(c.rid)
            score = ch.unit if ch is not None and ch.unit is not None and k.outcome != "fallback" else c.score
            item: dict[str, Any] = {"chunkId": h.chunk_id, "sourceId": h.source_id, "title": strip_extension(h.title),
                                    **({"locator": h.locator} if h.locator else {}), "text": h.text,
                                    "score": round(float(score), 4), "cited": False}
            if h.chunk_id in n_of:
                item["n"] = n_of[h.chunk_id]
            retrieved.append(item)
        rows = self.rows(checked, hits, k, set_yes)
        calls: list[dict[str, Any]] = []
        if k.outcome == "fallback":
            calls.append({"purpose": PURPOSE, "model": self.deps.prices.decision.model, "costUsd": 0.0,
                          "latencyMs": float(slowest or self.knobs().deep_check_ms), "fallback": True})
        new_rewrite = rewrite.text if rewrite is not None and rewrite.status == "ok" else None
        words = list(dict.fromkeys([*bundle.terms, *q.words(req.message)]))
        checks = [{"chunkId": hits[c.rid].chunk_id, "order": c.order, "p_answers": c.p_answers,
                   "p_partly": c.p_partly, "unit": c.unit} for c in checked if c.rid in hits]
        return DeepResult(query=bundle.to_json(), display=bundle.display, retrieved=retrieved, kept=kept_hits,
                          outcome=k.outcome, abstain=k.abstain, partly_line=k.partly_line, rows=rows, calls=calls,
                          rewrite=new_rewrite, rewrite_status=rewrite.status if rewrite is not None else None,
                          slowest_check_ms=slowest, quote_words=words, checks=checks,
                          set_check=set_info, pool=[ids[c.rid] for c in result.pool if c.rid in (ids := pool_ids or {})])

    def rows(self, checked: list[keeping.Checked], hits: dict[int, KnowledgeHit], k: keeping.Kept,
             set_yes: bool | None) -> list[dict[str, Any]]:
        """D20's passage rows (and the set row), grouped as "passages" by the System 1 section."""
        b = bank()
        th = self._passage_thresholds()
        pe, se = b.get(PASSAGE), b.get(PASSAGE_SET)
        kept = set(k.kept)
        usable = set(k.usable)
        # a usable passage that lost on rank says so (U-35): "0.99 ≥ 0.90 → dropped" read as a contradiction
        outranked = f"not in top {len(k.kept)}"
        out: list[dict[str, Any]] = []
        for c in checked:
            h = hits.get(c.rid)
            if h is None:
                continue
            row: dict[str, Any] = {"purpose": PURPOSE, "id": PASSAGE, "version": pe.version, "label": pe.label,
                                   "about": h.chunk_id}
            if not c.back:
                row.update(answer="missing", compared=[], result="fallback",
                           action="kept by search order" if c.rid in kept else "not checked")
            else:
                pa, pp = c.p_answers or 0.0, c.p_partly or 0.0
                probs = (1.0 - pa - pp, pp, pa)
                level = max(range(3), key=lambda i: (probs[i], i))
                use = pa + pp
                # the usable line first (the meter draws it), then the found line (U-36: p_answers was never shown)
                row.update(answer=LEVEL_ANSWER[level], p=round(use, 4), compared=[
                    {"name": "t_keep", "value": round(use, 4), "threshold": th["t_keep"]},
                    {"name": "t_found", "value": round(pa, 4), "threshold": th["t_found"]}],
                    result="used" if c.rid in kept else "below_threshold",
                    action="kept" if c.rid in kept else outranked if c.rid in usable else "dropped")
            out.append(row)
        if set_yes is not None or (k.outcome in ("partly", "found") and len(k.usable) >= 2 and not any(
                keeping.found(c, th["t_found"]) for c in checked)):
            row = {"purpose": PURPOSE, "id": PASSAGE_SET, "version": se.version, "label": se.label}
            if set_yes is None:
                row.update(answer="missing", compared=[], result="fallback", action="partly")
            else:
                row.update(answer="yes" if set_yes else "no", compared=[], result="used",
                           action="found together" if set_yes else "partly")
            out.append(row)
        return out


def level_probs(a: ScoreAnswer) -> tuple[float, float, float]:
    """(p_answers, p_partly, unit) from a 3-level score answer: the levels' probabilities when Jev gave them, else the
    chosen level at 1.0. `unit` = Σ k·p_k / 2 (W11)."""
    probs = {int(k): float(v) for k, v in (a.probabilities or {}).items() if str(k).isdigit()}
    if not probs:
        lvl = round(a.score)
        probs = {lvl: 1.0}
    p0, p1, p2 = probs.get(0, 0.0), probs.get(1, 0.0), probs.get(2, 0.0)
    total = p0 + p1 + p2 or 1.0
    p1, p2 = p1 / total, p2 / total
    return p2, p1, (p1 + 2 * p2) / 2


async def early_embedding(deps: Any, session: Any, who: Sequence[str], text: str, message_id: str | None,
                          any_space: bool = False) -> None:
    """The user message's query embedding, started with Jev call 1 (rag 11.5): once, for the first of `who` with
    vectors in the active space. A failure costs nothing: gather asks again at the gate. M13 (memory D32): with
    `any_space` (recall has earlier lines or overflow memories to search), whatever the documents."""
    RECORDED_SINK.set(None)   # its ledger row links to the message, never to a reply's sink
    io = deps.deep_io()
    try:
        if not io.key_set():
            return
        for cid in who:
            index = io.index(session.world.id, cid)
            space = await io.space(index.active_space)
            if space is not None and (any_space or await io.has_vectors(cid, index.active_space)):
                ctx = call_ctx("query_embed", world_id=session.world.id, session_id=session.session_id,
                               message_id=message_id)
                await io.embedder().embed([text], kind="query", space=space, ctx=ctx)
                return
    except asyncio.CancelledError:
        raise
    except Exception as e:   # a cap, a provider error: the gate's own request tries again
        log.info("the early query embedding failed (%s)", getattr(e, "code", type(e).__name__))


def start_early_embedding(deps: Any, session: Any, who: Sequence[str], text: str, message_id: str | None,
                          any_space: bool = False) -> None:
    """Spawn `early_embedding` on the runtime's tracked spawn (a plan never waits for it)."""
    if who and text.strip():
        deps.spawn(f"query-embed-early:{session.session_id}", early_embedding(deps, session, list(who), text,
                                                                               message_id, any_space))


def with_recall(out: DeepResult, got: dict[str, Any]) -> DeepResult:
    return out.model_copy(update={"recall": got["recall"], "recall_outcome": got["recall_outcome"],
                                  "recall_rows": got["recall_rows"], "recall_checks": got["recall_checks"],
                                  "recall_lists": got["recall_lists"], "calls": [*out.calls, *got["recall_calls"]]})


def build_deep_graph(steps: DeepSteps) -> Any:
    # LangGraph's node protocol names the parameter `state`; here it is the whole run
    async def both_node(state: DeepRun) -> DeepRun:
        """M13 (D34): both branches at once, as children of this run (a cancel reaches both)."""
        req = state["req"]
        try:
            docs, got = await vclock.together(steps.docs_chain(req, state["bundle"], state.get("rewrite")),
                                              steps.recall(req, state["bundle"]))
        except BaseExceptionGroup as eg:
            raise eg.exceptions[0] from None
        return {"out": with_recall(docs, got), "path": ["search", "check", "keep", "recall"]}

    async def recall_only_node(state: DeepRun) -> DeepRun:
        """M13 (D34): a recall-only request skips gather (no rewrite) and the documents branch."""
        got = await steps.recall(state["req"], None)
        return {"out": with_recall(DeepResult(docs=False, outcome="not_found"), got), "path": ["recall"]}

    async def gather_node(state: DeepRun) -> DeepRun:
        bundle, rewrite = await steps.gather(state["req"])
        return {"bundle": bundle, "rewrite": rewrite, "path": ["gather"]}

    async def search_node(state: DeepRun) -> DeepRun:
        result, hits = await steps.search(state["req"], state["bundle"])
        pool = await steps.pool_ids(state["req"], result)
        return {"result": result, "hits": hits, "pool_ids": pool, "path": ["search"]}

    async def check_node(state: DeepRun) -> DeepRun:
        checked, set_yes, failed, slowest, set_info = await steps.check(state["req"], state["bundle"],
                                                                        state["result"], state["hits"])
        return {"checked": checked, "set_yes": set_yes, "failed": failed, "slowest": slowest, "set_info": set_info,
                "path": ["check"]}

    async def keep_node(state: DeepRun) -> DeepRun:
        out = steps.keep(state["req"], state["bundle"], state.get("rewrite"), state["result"], state["hits"],
                         state["checked"], state.get("set_yes"), bool(state.get("failed")), state.get("slowest"),
                         state.get("set_info"), state.get("pool_ids"))
        return {"out": out, "path": ["keep"]}

    g = StateGraph(DeepRun)
    g.add_node("gather", gather_node)
    g.add_node("search", search_node)
    g.add_node("check", check_node)
    g.add_node("keep", keep_node)
    g.add_node("both", both_node)
    g.add_node("recall", recall_only_node)
    g.add_conditional_edges(START, lambda run: "gather" if run["req"].docs else "recall",
                            {"gather": "gather", "recall": "recall"})
    g.add_conditional_edges("gather", lambda run: "both" if run["req"].recall else "search",
                            {"both": "both", "search": "search"})
    g.add_edge("both", END)
    g.add_edge("recall", END)
    g.add_edge("search", "check")
    g.add_edge("check", "keep")
    g.add_edge("keep", END)
    return g.compile()


async def run_deep(graph: Any, req: DeepRequest) -> DeepResult:
    guard = contextlib.nullcontext() if TRACER.enabled else no_trace()
    with guard:
        out: DeepRun = await graph.ainvoke({"req": req, "path": []}, config={"recursion_limit": 10})
    res: DeepResult = out["out"].model_copy(update={"path": list(out.get("path") or [])})
    return res


def fallback_result(req: DeepRequest, deps: Any) -> DeepResult:
    """A bug inside the deep work: a quick turn, logged, with a `fallback` row (the port never raises)."""
    return DeepResult(outcome="fallback", calls=[{"purpose": PURPOSE, "model": deps.prices.decision.model,
                                                  "costUsd": 0.0, "latencyMs": 0.0, "fallback": True}],
                      rows=[{"purpose": PURPOSE, "id": PASSAGE, "version": bank().get(PASSAGE).version,
                             "label": bank().get(PASSAGE).label, "answer": "error", "compared": [],
                             "result": "fallback", "action": "quick reply"}])


async def run_safely(graph: Any, req: DeepRequest, deps: Any) -> DeepResult | None:
    """The deep work, never raising except CancelledError. None: it failed inside (a bug), so the turn goes quick."""
    try:
        return await run_deep(graph, req)
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("the deep work failed for %s; a quick reply", req.speaker.id)
        return None


class DeepCall:
    """A deep run started ahead of its turn (group, watch, debate: D15). `result()` waits for it; `cancel()` cuts it
    (every Decider call it made settles and is recorded `cancelled`). `rows` collects its ledger rows, so the runtime
    links them to the reply's message once it exists."""

    def __init__(self, deps: Any, graph: Any, req: DeepRequest, spawn: Any = None) -> None:
        self.req = req
        self.rows: list[str] = []
        self._deps = deps
        spawn = spawn or deps.spawn

        async def go() -> DeepResult | None:
            token = RECORDED_SINK.set(self.rows.append)
            try:
                return await run_safely(graph, req, deps)
            finally:
                RECORDED_SINK.reset(token)

        self.task: asyncio.Task[DeepResult | None] = spawn(f"deep:{req.speaker.id}", go())

    async def result(self) -> DeepResult | None:
        done: DeepResult | None = await vclock.join(self.task)
        return done

    def cancel(self) -> None:
        self.task.cancel()

    @property
    def done(self) -> bool:
        return self.task.done()

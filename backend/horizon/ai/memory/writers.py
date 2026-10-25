"""The `naive` and `agent` memory writers (docs/ai/09 M3–M5, M13; memory design D16–D18; ai-ports "The memory writer
port reads a stretch").

Both make the same `memory-1` call (D13). What they do with its changes differs:

- **add.** `naive`: importance from the weight hint, and an exact (case-folded) duplicate of a current memory is
  skipped. `agent`: Jev's importance; under `minImportance` it is dropped; a case-folded duplicate reinforces that
  memory instead, and so does a near one (cosine ≥ `dupCosine`, D16) that Jev calls the same fact (`same_fact`,
  phase 10: cosine alone can't tell a rewording from an extension with a new detail).
- **rewrite.** `naive`: Supersede, importance the higher of old and hint. `agent`: Jev's importance (the higher of
  old and new) and the guard: p ≥ `t_keep` → Supersede, else Insert beside.
- **confirm.** Both: Reinforce(importance + 0.05).

**The `agent` graph** (D17): a LangGraph `StateGraph` with no checkpointer (the checkpoint lives in SQL):

    rewrite ──▶ judge (per character in parallel: importance ∥ guard; and the duplicate check's one embedding) ──▶ ops

A per-run semaphore holds Jev requests to 10 in flight; cancelling the run cancels the graph and its reads. A bug
inside raises to the run, which counts a try. The duplicate check's vectors ride into `apply_run`, so each new text is
embedded once per space.

The writer reads the database only through `ctx.io` (the run's `MemoryIO`): the character's current memories, one
embedding of the adds in the active space, and one nearest-neighbour lookup per add.
"""

from __future__ import annotations

import asyncio
import contextlib
import operator
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Annotated, Any, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph

from horizon.ai.memory import all_of, jev
from horizon.ai.memory import rewrite as mem1
from horizon.ai.memory.rewrite import CallOutcome, Change
from horizon.ai.ports import Insert, MemoryDraft, MemoryOp, Reinforce, Supersede
from horizon.services.memory.stretch import Stretch, WriterResult
from horizon.tracing import TRACER, no_trace

CONFIRM_STEP = 0.05
JEV_IN_FLIGHT = 10


class MemoryIO(Protocol):
    """The run's reads for the writer (built by `horizon.services.memory.runs`)."""

    async def current(self, character_id: str) -> list[tuple[str, str, float]]: ...   # (id, text, importance)
    async def embed(self, texts: list[str]) -> tuple[str, list[list[float]]] | None: ...   # (active space, vectors)
    async def nearest(self, character_id: str, space_id: str, vector: list[float]) -> tuple[str, float, float] | None: ...


@dataclass
class Plan:
    """What the judge step found for one character's changes."""

    ops: list[MemoryOp] = field(default_factory=list)
    log: list[dict[str, Any]] = field(default_factory=list)


def _knobs(ctx: Any) -> Any:
    return ctx.knobs


def draft(stretch: Stretch, c: Change, importance: float) -> MemoryDraft:
    return MemoryDraft(kind=str(c.kind or (c.target.kind if c.target else "fact")), text=c.text,
                       importance=max(0.0, min(1.0, float(importance))), source_session_id=stretch.session_id,
                       source_message_id=c.line.message_id, source_variant_id=c.line.variant_id,
                       source_mode=stretch.mode, about_character_id=c.about_character_id)


def reinforce(memory_id: str, importance: float) -> Reinforce:
    return Reinforce(memory_id, round(min(1.0, float(importance) + CONFIRM_STEP), 4))


def source_text(stretch: Stretch, c: Change) -> str:
    """The guard's quoted_source: the source message and the one before it, "Name: text"."""
    before = next((f"{ln.speaker}: {' '.join(ln.text.split())}" for ln in stretch.lines if ln.n == c.line.n - 1), None)
    if before is None and c.line.reread:
        ctx = stretch.reread_context.get(c.line.message_id) or []
        before = ctx[-1] if ctx else None
    if before is None and c.line.n == min((ln.n for ln in stretch.lines), default=c.line.n) and stretch.context:
        before = stretch.context[-1]
    line = f"{c.line.speaker}: {' '.join(c.line.text.split())}"
    return f"{before}\n{line}" if before else line


def one_per_target(changes: Sequence[Change]) -> tuple[list[Change], list[dict[str, Any]]]:
    """A line is rewritten at most once per run (the higher weight stays), and a confirm of a rewritten line goes."""
    out: list[Change] = []
    log: list[dict[str, Any]] = []
    rewritten: dict[tuple[str, str], Change] = {}
    for c in changes:
        if c.op == "rewrite" and c.target is not None:
            k = (c.character_id, c.target.id)
            prev = rewritten.get(k)
            if prev is None or (c.weight or 0) > (prev.weight or 0):
                if prev is not None:
                    log.append({"step": "rewrite", "characterId": c.character_id, "why": "second rewrite of one line",
                                "text": prev.text})
                rewritten[k] = c
            else:
                log.append({"step": "rewrite", "characterId": c.character_id, "why": "second rewrite of one line",
                            "text": c.text})
    for c in changes:
        if c.op == "rewrite" and c.target is not None:
            if rewritten.get((c.character_id, c.target.id)) is c:
                out.append(c)
        elif c.op == "confirm" and c.target is not None and (c.character_id, c.target.id) in rewritten:
            log.append({"step": "rewrite", "characterId": c.character_id, "why": "confirm of a rewritten line"})
        else:
            out.append(c)
    return out, log


def by_character(stretch: Stretch, changes: Sequence[Change]) -> dict[str, list[Change]]:
    out: dict[str, list[Change]] = {p.character_id: [] for p in stretch.present}
    for c in changes:
        out.setdefault(c.character_id, []).append(c)
    return out


class _Base:
    def __init__(self, deps: Any) -> None:
        self.deps = deps

    async def _rewrite(self, stretch: Stretch, ctx: Any) -> CallOutcome:
        out = await mem1.call(self.deps, stretch, ctx)
        kept, log = one_per_target(out.changes)
        return CallOutcome(changes=kept, log=[*out.log, *log], failed=out.failed, calls=out.calls)


class NaiveMemoryWriter(_Base):
    """D18: the same call; importance from the hint; rewrites supersede with no guard; the exact-duplicate skip."""

    name = "naive"

    async def on_stretch(self, stretch: Stretch, ctx: Any) -> WriterResult:
        return await self.apply(stretch, ctx, await self._rewrite(stretch, ctx))

    async def apply(self, stretch: Stretch, ctx: Any, out: CallOutcome) -> WriterResult:
        """The ops from the rewrite call's outcome (M15: the memory suite's `naive` arm scores both, D14)."""
        if out.failed:
            return WriterResult(log=out.log, failed=True)
        knobs = _knobs(ctx)
        ops: dict[str, list[MemoryOp]] = {}
        log = list(out.log)
        for cid, cs in by_character(stretch, out.changes).items():
            if not cs:
                continue
            current = {text.casefold(): (mid, imp) for mid, text, imp in await ctx.io.current(cid)}
            mine: list[MemoryOp] = []
            for c in cs:
                if c.op == "confirm" and c.target is not None:
                    mine.append(reinforce(c.target.id, c.target.importance))
                elif c.op == "rewrite" and c.target is not None:
                    mine.append(Supersede([c.target.id], draft(stretch, c, max(c.target.importance, jev.hint(c.weight)))))
                else:
                    value = jev.hint(c.weight)
                    if value < float(knobs.min_importance):
                        log.append({"step": "importance", "characterId": cid, "why": "below minImportance",
                                    "text": c.text, "importance": value})
                    elif c.text.casefold() in current:
                        log.append({"step": "duplicate", "characterId": cid, "why": "exact duplicate", "text": c.text})
                    else:
                        mine.append(Insert(draft(stretch, c, value)))
            if mine:
                ops[cid] = mine
        return WriterResult(ops=ops, log=log)


class MemoryRun(TypedDict, total=False):
    stretch: Any
    ctx: Any
    rewrite: Any                                  # the CallOutcome
    plans: Any                                    # character id → Plan
    vectors: Any                                  # text → {space id: vector}
    result: Any                                   # the WriterResult
    path: Annotated[list[str], operator.add]


class AgentMemoryWriter(_Base):
    """D17: the graph. Jev scores importance and guards rewrites; the duplicate check embeds each add once."""

    name = "agent"

    def __init__(self, deps: Any) -> None:
        super().__init__(deps)
        self.graph = self._build()

    def _build(self) -> Any:
        async def rewrite_node(state: MemoryRun) -> MemoryRun:
            return {"rewrite": await self._rewrite(state["stretch"], state["ctx"]), "path": ["rewrite"]}

        async def judge_node(state: MemoryRun) -> MemoryRun:
            plans, vectors = await self._judge(state["stretch"], state["ctx"], state["rewrite"])
            return {"plans": plans, "vectors": vectors, "path": ["judge"]}

        async def ops_node(state: MemoryRun) -> MemoryRun:
            out: CallOutcome = state["rewrite"]
            plans: dict[str, Plan] = state.get("plans") or {}
            log = [*out.log, *[x for p in plans.values() for x in p.log]]
            ops = {cid: p.ops for cid, p in plans.items() if p.ops}
            return {"result": WriterResult(ops=ops, vectors=state.get("vectors") or {}, log=log), "path": ["ops"]}

        def after_rewrite(state: MemoryRun) -> str:
            out: CallOutcome = state["rewrite"]
            return "failed" if out.failed else "judge"

        async def failed_node(state: MemoryRun) -> MemoryRun:
            return {"result": WriterResult(log=state["rewrite"].log, failed=True), "path": ["failed"]}

        g = StateGraph(MemoryRun)
        g.add_node("rewrite", rewrite_node)
        g.add_node("judge", judge_node)
        g.add_node("ops", ops_node)
        g.add_node("failed", failed_node)
        g.add_edge(START, "rewrite")
        g.add_conditional_edges("rewrite", after_rewrite, {"judge": "judge", "failed": "failed"})
        g.add_edge("judge", "ops")
        g.add_edge("ops", END)
        g.add_edge("failed", END)
        return g.compile()

    async def on_stretch(self, stretch: Stretch, ctx: Any) -> WriterResult:
        guard_ = contextlib.nullcontext() if TRACER.enabled else no_trace()
        try:
            with guard_:
                out: MemoryRun = await self.graph.ainvoke({"stretch": stretch, "ctx": ctx, "path": []},
                                                          config={"recursion_limit": 10})
        except jev.Held as e:   # M14 (safety D15): an unchecked line is held: the piece is a failed try
            return WriterResult(log=[{"step": "instruction", "why": f"held: {e}"}], failed=True)
        result: WriterResult = out["result"]
        return result

    async def _judge(self, stretch: Stretch, ctx: Any,
                     out: CallOutcome) -> tuple[dict[str, Plan], dict[str, dict[str, list[float]]]]:
        sem = asyncio.Semaphore(JEV_IN_FLIGHT)
        knobs = _knobs(ctx)
        groups = by_character(stretch, out.changes)
        present = {p.character_id: p for p in stretch.present}
        currents = dict(zip(groups, await all_of(*(ctx.io.current(cid) for cid in groups)), strict=True))
        # the duplicate check's step 1 (free) first, then one embedding of every add left, beside the Jev requests
        same: dict[int, tuple[str, float]] = {}
        to_embed: list[Change] = []
        for cid, cs in groups.items():
            folded = {text.casefold(): (mid, imp) for mid, text, imp in currents[cid]}
            for c in cs:
                if c.op == "add":
                    hit = folded.get(c.text.casefold())
                    if hit is not None:
                        same[id(c)] = hit
                    else:
                        to_embed.append(c)

        async def embed() -> tuple[str, list[list[float]]] | None:
            texts = list(dict.fromkeys(c.text for c in to_embed))
            return await ctx.io.embed(texts) if texts else None

        async def one(cid: str, cs: list[Change]) -> tuple[list[jev.Scored], list[jev.Scored]]:
            p = present.get(cid)
            writes = [c for c in cs if c.op in ("add", "rewrite")]
            rewrites = [c for c in cs if c.op == "rewrite" and c.target is not None]
            if p is None:
                return [], []
            scores, guards = await all_of(
                jev.importance(self.deps, sem, ctx, p, stretch.user_name, [(c.text, c.weight) for c in writes]),
                all_of(*(jev.guard(self.deps, sem, ctx, cid, c.target.text if c.target else "", c.text,
                                           source_text(stretch, c)) for c in rewrites)))
            return scores, list(guards)

        judged, embedded = await all_of(all_of(*(one(cid, cs) for cid, cs in groups.items())), embed())
        vec_of: dict[str, list[float]] = {}
        space_id = ""
        if embedded is not None:
            space_id, vecs = embedded
            vec_of = dict(zip(dict.fromkeys(c.text for c in to_embed), vecs, strict=True))
        t_keep = jev.t_keep()
        plans: dict[str, Plan] = {}
        vectors: dict[str, dict[str, list[float]]] = {}
        for (cid, cs), (scores, guards) in zip(groups.items(), judged, strict=True):
            plan = Plan()
            plans[cid] = plan
            writes = [c for c in cs if c.op in ("add", "rewrite")]
            score_of = {id(c): s for c, s in zip(writes, scores, strict=True)}
            guard_of = {id(c): g for c, g in zip([c for c in cs if c.op == "rewrite" and c.target is not None], guards,
                                                  strict=True)}
            t_ins = jev.t_instruction()
            for c in cs:
                s = score_of.get(id(c))
                if s is not None and s.instruction is not None and s.instruction >= t_ins:
                    # M14 (safety D15; doc 11 S6): it reads as a rule or an order to the character: never written
                    plan.log.append({"step": "instruction", "characterId": cid, "why": "tries to change the rules: dropped",
                                     "text": c.text, "p": round(s.instruction, 4)})
                    continue
                if s is not None and s.source == "fallback":
                    plan.log.append({"step": "importance", "characterId": cid, "why": "Jev failed or late: the hint",
                                     "text": c.text, "importance": s.value})
                if c.op == "confirm" and c.target is not None:
                    plan.ops.append(reinforce(c.target.id, c.target.importance))
                elif c.op == "rewrite" and c.target is not None:
                    value = max(c.target.importance, s.value if s is not None else jev.hint(c.weight))
                    g = guard_of.get(id(c))
                    if g is not None and g.value >= t_keep:
                        plan.ops.append(Supersede([c.target.id], draft(stretch, c, value)))
                    else:
                        why = "guard said no" if g is not None and g.source != "fallback" else "guard failed or late"
                        plan.log.append({"step": "guard", "characterId": cid, "why": f"{why}: kept beside",
                                         "text": c.text, "p": g.value if g is not None else None})
                        plan.ops.append(Insert(draft(stretch, c, value)))
                elif c.op == "add":
                    value = s.value if s is not None else jev.hint(c.weight)
                    if value < float(knobs.min_importance):
                        plan.log.append({"step": "importance", "characterId": cid, "why": "below minImportance",
                                         "text": c.text, "importance": value})
                        continue
                    hit = same.get(id(c))
                    if hit is None and c.text in vec_of:
                        near = await ctx.io.nearest(cid, space_id, vec_of[c.text])
                        if near is not None and near[1] >= float(knobs.dup_cosine):
                            old = next((t for m, t, _ in currents[cid] if m == near[0]), "")
                            s_ = await jev.same_fact(self.deps, sem, ctx, cid, old, c.text)
                            if s_.value >= jev.t_same():
                                hit = (near[0], near[2])
                            else:
                                why = "near, but not the same fact: written" if s_.source != "fallback" else \
                                    "near; the same-fact check failed or was late: written"
                                plan.log.append({"step": "duplicate", "characterId": cid, "why": why, "text": c.text,
                                                 "memoryId": near[0], "cosine": round(near[1], 4), "p": s_.value})
                    if hit is not None:
                        plan.log.append({"step": "duplicate", "characterId": cid, "why": "duplicate: reinforced",
                                         "text": c.text, "memoryId": hit[0]})
                        plan.ops.append(reinforce(hit[0], hit[1]))
                        continue
                    plan.ops.append(Insert(draft(stretch, c, value)))
                    if c.text in vec_of:
                        vectors[c.text] = {space_id: vec_of[c.text]}
        return plans, vectors

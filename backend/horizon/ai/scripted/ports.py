"""Scripted AI ports (session-runtime design D10; ai-ports "Scripted placeholders are deterministic").

Every port is deterministic for the same session state and seed, never opens a connection, and bills simulated spend
through the gateway's scripted source, so caps, energy and Insight behave as on the MockClient. Pacing and usage follow
`turnScript.ts` (`buildLineScript`) with the shared timing table.
"""

from __future__ import annotations

import math
import random
import re
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from horizon.ai.contexts import (
    Assessment,
    CastPlan,
    CastRequest,
    DebateRequest,
    FollowRequest,
    HostKey,
    MessageView,
    PlanRequest,
    ReactionRequest,
    RouteContext,
    SessionContext,
    TurnContext,
    TurnPlan,
    VerdictRequest,
)
from horizon.ai.ports import (
    CitationMap,
    Emotion,
    GuardrailResult,
    Reaction,
    RoutingDecision,
    Token,
    TracePatch,
    TurnEvent,
)
from horizon.ai.scripted import bank
from horizon.ai.scripted.citations import live_citations
from horizon.domain.clock import Clock
from horizon.domain.pricing import PriceTable, chat_cost, decision_cost, multiplier
from horizon.domain.runtime_config import Timing
from horizon.gateway.errors import ProviderError
from horizon.gateway.pipeline import Gateway, SimulatedReply

ROUTE_DECISION_TOKENS = 600     # `cost.ts` ROUTE_DECISION_TOKENS
REACTION_DECISION_TOKENS = 600  # `cost.ts` REACTION_DECISION_TOKENS (M9 D21: the simulated `reaction` call)
REACTION_LATENCY_MS = 420       # Jev's measured p50 (group A)
FACE_CHECK_DECISION_TOKENS = 600   # `cost.ts` FACE_CHECK_DECISION_TOKENS (doc 13 W2: about 400–700)
TURN_PLAN_DECISION_TOKENS = 900    # `cost.ts` TURN_PLAN_DECISION_TOKENS (Jev call 1's state + one question)
PLANNED_FACE = ""                  # D25: the scripted emotion row's answer, filled at finish from the face shown
REACTION_EMOTIONS = ("thinking", "happy", "surprised", "neutral", "embarrassed", "sad", "angry")
LABEL = {"setup": "SETUP", "opening": "OPENING", "rebuttal": "REBUTTAL", "closing": "CLOSING", "verdict": "VERDICT",
         "ended": "ENDED"}
DEFAULT_RUBRIC = [{"id": "evidence", "label": "Evidence"}, {"id": "rebuttal", "label": "Rebuttal"},
                  {"id": "clarity", "label": "Clarity"}, {"id": "persuasion", "label": "Persuasion"}]


def js_round(x: float) -> int:
    return math.floor(x + 0.5)


def r3(x: float) -> float:
    return js_round(x * 1000) / 1000


def tokenize(text: str, chars_per_token: int = 4) -> list[str]:
    """`tokenize.ts`: ~4-character tokens with leading whitespace attached."""
    out: list[str] = []
    consumed = 0
    for m in re.finditer(r"(\s*)(\S+)", text):
        ws, word = m.group(1), m.group(2)
        for i in range(0, len(word), chars_per_token):
            out.append((ws if i == 0 else "") + word[i:i + chars_per_token])
        consumed = m.end()
    if consumed < len(text):
        tail = text[consumed:]
        if out:
            out[-1] += tail
        else:
            out.append(tail)
    return out


def chunk_tokens(tokens: list[str], per_chunk: int) -> list[str]:
    return ["".join(tokens[i:i + per_chunk]) for i in range(0, len(tokens), per_chunk)]


def estimate_tokens(text: str) -> int:
    return max(1, js_round(len(text) / 4))


@dataclass
class AiDeps:
    """What the AI ports reach: the gateway, the decider, prices, the clock and the timing table (accessors, because
    a factory reset rebuilds the gateway)."""

    gateway: Callable[[], Gateway]
    decider: Callable[[], Any]
    prices: PriceTable
    timing: Timing
    clock: Callable[[], Clock]
    palette_ids: Callable[[], Sequence[str]] = lambda: ()    # M4: the shipped palettes (drafts pick from these)
    schema: Callable[[], Any] = lambda: None                 # M4: the contract schema (the naive drafter validates)
    models_dir: Callable[[], Path] = lambda: Path("data/models")   # M5: the conversion models (D-62)
    convert_timeout_s: float = 600.0                        # M5: a document conversion's limit (design D4)
    llm: Callable[[str], Any] = lambda key: None             # M7: the `runtime.llm.calls` row for a call key (D13)
    system1_row: Callable[[str, str], dict[str, Any] | None] = lambda qid, answer: None   # M7: the shared fixture (D25)
    switch: Callable[[str], bool] = lambda name: False        # M8: a runtime.json dynamic-tail switch (P8, X5)
    windows: Callable[[], Mapping[str, int]] = lambda: {}    # M8: windowTokens per mode (X2); {} = X2's defaults
    emotion_fade: Callable[[], frozenset[str]] = lambda: frozenset({"surprised", "embarrassed"})   # M9: E3's set
    spawn: Callable[[str, Any], Any] | None = None             # M12: the runtime's tracked spawn (a late call still lands)
    retrieval: Callable[[], Any] = lambda: None               # M12: `runtime.retrieval` (the agent knobs)
    deep_io: Callable[[], Any] = lambda: None                 # M12 (rag D15): the runtime's reads for the deep work
    memory_block_tokens: Callable[[], int] = lambda: 1000     # M13 (memory D24): `memory.blockTokens`
    memory_knobs: Callable[[], Any] = lambda: None            # M13 (memory D31): the list's recency and mode weights


def emotion_candidates(chosen: str, rng: random.Random) -> list[dict[str, Any]]:
    top = r3(rng.uniform(0.55, 0.88))
    others = [e for e in bank.EMOTIONS if e != chosen]
    rng.shuffle(others)
    rest = 1 - top
    second = r3(rest * rng.uniform(0.55, 0.8))
    third = r3(max(0.01, rest - second - rng.uniform(0, max(0.0, rest - second)) * 0.5))
    return [{"label": chosen, "p": top}, {"label": others[0], "p": second}, {"label": others[1], "p": third}]


class NoMemoryWriter:
    """The scripted memory writer (memory D18): it remembers nothing. An explicitly `scripted` run never calls it (the
    checkpoint just advances); it stands in wherever the port resolves to scripted."""

    async def on_stretch(self, stretch: Any, ctx: Any) -> Any:
        from horizon.services.memory.stretch import WriterResult

        return WriterResult()


class ScriptedTurnEngine:
    name = "scripted"
    version = "1"
    prompt_version: str | None = None

    def __init__(self, deps: AiDeps) -> None:
        self.deps = deps

    def line(self, ctx: TurnContext, rng: random.Random) -> bank.Line:
        hint = ctx.line
        if hint.text:
            return bank.Line(hint.text, hint.emotion or "neutral")
        d = ctx.debate
        cfg = ctx.session.config or {}
        recent = [m.content for m in ctx.session.recent if m.character_id == ctx.speaker.id][-8:]
        return bank.pick_line(hint.kind, ctx.speaker.profile, rng=rng, prompt=ctx.prompt, recent=recent,
                              motion=d.motion if d else str(cfg.get("motion", "")), side=d.side if d else None,
                              phase=d.phase if d else "opening", index=ctx.turn_index,
                              premise=str(cfg.get("premise", "")), note=ctx.direction_note)

    def plan(self, ctx: TurnContext, rng: random.Random, text: str,
             knowledge_tokens: int = 0) -> tuple[SimulatedReply, dict[str, int]]:
        """The stream plan and its input breakdown (system, persona, mode, user, history, and the retrieved passages
        when the reply cites), as `buildLineScript`."""
        t = self.deps.timing
        prices = self.deps.prices
        tokens = tokenize(text, t.chars_per_token)
        chunks = chunk_tokens(tokens, t.tokens_per_event) or [text]
        used = {"system": 900, "persona": 700 + rng.randint(0, 120), "mode": 580 if ctx.debate else 220,
                "user": 40 + rng.randint(0, 40), "history": ctx.session.history_tokens, "knowledge": knowledge_tokens}
        tokens_in = sum(used.values())
        hist = used["history"]
        cached = math.floor((used["system"] + used["persona"] + hist * 0.9) * (1 if hist > 0 else 0.8))
        tokens_out = estimate_tokens(text)
        first = js_round(t.first_token_ms * rng.uniform(0.85, 1.15))
        total = first + js_round(len(tokens) / t.tokens_per_sec * 1000) + 80
        step = (total - 50 - first) / (len(chunks) - 1) if len(chunks) > 1 else 0.0
        tail = max(0.0, total - (first + step * (len(chunks) - 1)))
        cost = chat_cost(prices.chat, tokens_in=tokens_in, tokens_cached=cached, tokens_out=tokens_out,
                         mult=multiplier(prices, ctx.session.period))
        spec = SimulatedReply(chunks=chunks, first_token_ms=first, step_ms=step, tail_ms=tail, total_ms=total,
                              model=prices.chat.model, tokens_in=tokens_in, tokens_cached=cached, tokens_out=tokens_out,
                              cost_usd=cost)
        return spec, used

    async def run(self, ctx: TurnContext) -> AsyncIterator[TurnEvent]:
        rng = random.Random(f"{ctx.session.seed}:{ctx.turn_index}")
        line = self.line(ctx, rng)
        text, cited = line.text, None
        if ctx.knowledge:   # M5 (design D15): its own RNG stream, so a reply without hits is unchanged
            key = f"{ctx.session.session_id}:{ctx.message_id or ctx.turn_index}"
            cited = live_citations(key, line.text, ctx.prompt, list(ctx.knowledge),
                                   random.Random(f"{ctx.session.seed}:{ctx.turn_index}:cite"))
        knowledge_tokens = 0
        if cited is not None:
            text = cited[0]
            knowledge_tokens = sum(24 + estimate_tokens(r["text"]) for r in cited[2]["retrieved"])
        spec, used = self.plan(ctx, rng, text, knowledge_tokens)
        et = self.deps.timing.emotion_timing
        r = rng.random()
        timing = "before" if r < et["before"] else "early" if r < et["before"] + et["early"] else "late"
        delay = rng.uniform(80, 700) if timing == "early" else self.deps.timing.late_emotion_ms + rng.uniform(0, 400)
        at_chunk = 0 if timing == "before" else max(1, math.ceil(delay / spec.step_ms)) if spec.step_ms else 1
        emitted = False
        sent = 0
        clock = self.deps.clock()
        # The markers are in the text before streaming, so the tokens carry them. The map goes out just before the
        # first visible event: any engine event starts the message, and a cap refusal must leave none.
        pending_map = CitationMap(cited[1]) if cited is not None else None
        stream: Any = self.deps.gateway().simulated_stream(ctx.call_ctx("reply"), spec, clock.sleep)
        try:
            async for chunk in stream:
                if chunk.content is None:
                    if timing == "before":
                        emitted = True
                        if pending_map is not None:
                            yield pending_map
                            pending_map = None
                        yield Emotion(line.emotion)
                    continue
                if pending_map is not None:
                    yield pending_map
                    pending_map = None
                yield Token(chunk.content)
                sent += 1
                if not emitted and sent >= at_chunk:
                    emitted = True
                    yield Emotion(line.emotion)
        finally:
            await stream.aclose()  # a cut or a Stop records the estimate now, not when the generator is collected
        if not emitted:
            yield Emotion(line.emotion)
        patch: dict[str, Any] = {
            "emotion": {"chosen": line.emotion, "source": "llm", "candidates": emotion_candidates(line.emotion, rng)},
            "context": {"budget": 12000, "cacheHitPct": js_round(100 * spec.tokens_cached / max(1, spec.tokens_in)),
                        "used": {**used, "memory": 0}},
            "guardrail": {"checks": [{"name": "sfw", "verdict": "pass", "p": r3(rng.uniform(0.95, 0.995))},
                                     {"name": "advice_scope", "verdict": "pass"}]},
        }
        if cited is not None:
            patch["knowledge"] = cited[2]
        prior = [m for m in ctx.session.recent if m.author_type == "character" and m.character_id != ctx.speaker.id]
        if prior:
            last = prior[-1]
            patch["contextInSession"] = [{"text": f"{last.content[:60]}…", "messageId": last.id}]
        yield TracePatch(patch)


class ScriptedRouter:
    """The mock's scoring (`group.ts` pickResponders): random p in [0.2, 0.75] plus a name bonus; billed as one route
    decision of 600 tokens through the scripted source."""

    def __init__(self, deps: AiDeps) -> None:
        self.deps = deps

    async def route(self, ctx: RouteContext) -> RoutingDecision:
        rng = random.Random(f"{ctx.session.seed}:route:{ctx.turn_index}")
        lower = ctx.text.lower()
        candidates: list[dict[str, Any]] = []
        for cid in ctx.eligible:
            if cid in ctx.mentions:
                continue
            name = ctx.session.name_of(cid).lower()
            bonus = 0.3 if any(len(w) > 2 and w in lower for w in name.split(" ")) else 0.0
            candidates.append({"characterId": cid, "p": js_round(min(0.97, rng.uniform(0.2, 0.75) + bonus) * 100) / 100})
        candidates.sort(key=lambda c: -float(c["p"]))
        call = None
        if candidates:
            prices = self.deps.prices
            res = await self.deps.gateway().simulated_call(
                ctx.session.call_ctx("route"), cost_usd=decision_cost(prices.decision, ROUTE_DECISION_TOKENS),
                model=prices.decision.model, tokens_in=ROUTE_DECISION_TOKENS, latency_ms=240)
            call = {"purpose": "route", "model": res.model, "costUsd": res.cost_usd, "latencyMs": res.latency_ms}
        forced = [m for m in ctx.mentions if any(p.character_id == m for p in ctx.session.participants)]
        rest: list[str] = []
        if ctx.policy == "everyone":
            rest = [c["characterId"] for c in candidates]
        elif ctx.policy == "auto":
            rest = [c["characterId"] for c in candidates[:max(0, 2 - len(forced))]]
        row = self.deps.system1_row("route", str(candidates[0]["characterId"])) if candidates else None
        system1 = {"seed": f"{ctx.session.seed}:{ctx.turn_index}", "questions": [row]} if row else None
        return RoutingDecision(speakers=[*forced, *rest], candidates=candidates, call=call, system1=system1)


class ScriptedReactions:
    def __init__(self, deps: AiDeps, *, simulate: bool = True) -> None:
        self.deps = deps
        self.simulate = simulate   # M9 (design D21): False when standing in for `naive` under a key: no fake spend

    async def predict(self, req: ReactionRequest) -> list[Reaction]:
        """The mock's random reactions (same seeds, same output). With `simulate`, one simulated `reaction` decision
        per message with listeners, at the decision price (E5, D-81); never under `naive` with a key (D21)."""
        listeners = [lv.id for lv in req.listeners if lv.eligible]
        if not listeners:
            return []
        if self.simulate:
            prices = self.deps.prices
            await self.deps.gateway().simulated_call(
                req.session.call_ctx("reaction", character_id=req.speaker_id, message_id=req.message_id),
                cost_usd=decision_cost(prices.decision, REACTION_DECISION_TOKENS), model=prices.decision.model,
                tokens_in=REACTION_DECISION_TOKENS, latency_ms=REACTION_LATENCY_MS)
        t = self.deps.timing
        rng = random.Random(f"{req.seed}:react")
        out = []
        for cid in listeners:
            if rng.random() >= t.reaction_chance:
                continue
            out.append(Reaction(character_id=cid, emotion=rng.choice(REACTION_EMOTIONS), p=r3(rng.uniform(0.42, 0.9)),
                                delay_ms=rng.uniform(t.reaction_delay_ms[0], t.reaction_delay_ms[1])))
        return out


class ScriptedTurnPlanner:
    """The scripted turn plan (turn-plan-emotion D25): one simulated `turn_plan` decision when simulation is allowed
    (D-81, D5), and the fixture's emotion row with its answer left blank: the runtime fills it at `finish` from the face
    the reply showed ("the answer filled from what happened"). It leaves the face (`emotion` None) and retrieval
    (`branch` None) to the scripted engine and runtime. Its ledger row links to the message, so the trace lists it."""

    decides_retrieval = False

    def __init__(self, deps: AiDeps, *, simulate: bool = True) -> None:
        self.deps = deps
        self.simulate = simulate

    async def plan(self, req: PlanRequest) -> TurnPlan | None:
        qid = "emotion_greeting" if req.kind == "greeting" else "emotion_reply"
        if self.simulate:
            prices = self.deps.prices
            try:
                await self.deps.gateway().simulated_call(
                    req.session.call_ctx("turn_plan", character_id=req.speaker_id, message_id=req.message_id),
                    cost_usd=decision_cost(prices.decision, TURN_PLAN_DECISION_TOKENS), model=prices.decision.model,
                    tokens_in=TURN_PLAN_DECISION_TOKENS, latency_ms=REACTION_LATENCY_MS)
            except ProviderError:   # the port never raises (M10 found it raising a cap refusal out of the plan task):
                pass                # the reply's own preflight meets the same cap and takes the pause (M9 D7)
        row = self.deps.system1_row(qid, PLANNED_FACE)
        return TurnPlan(seed=f"{req.session.seed}:{req.turn_index}", kind=req.kind,
                        rows=[{**row, "about": req.speaker_id}] if row is not None else [])

    async def plan_cast(self, req: CastRequest) -> CastPlan | None:
        return None   # M10 (group-watch D3, D21): scripted keeps its own picks, as the MockClient does (G13)

    def start_follow(self, req: FollowRequest) -> None:
        return None

    def start_debate(self, req: DebateRequest) -> None:
        return None   # M11 (debate D5, V12): scripted fills debate slots in fixed order, as the MockClient does


class ScriptedFaceCheck:
    """The scripted face check (doc 13 W2; design D24): after `faceCheckMs`, the fixture row with answer `yes`, and
    one simulated `face_check` decision when simulation is allowed (D-81, D5)."""

    def __init__(self, deps: AiDeps, *, simulate: bool = True) -> None:
        self.deps = deps
        self.simulate = simulate

    async def check(self, ctx: SessionContext, message_id: str, speaker_id: str, face: str,
                    text: str) -> tuple[dict[str, Any], dict[str, Any] | None] | None:
        await self.deps.clock().sleep(self.deps.timing.face_check_ms / 1000)
        call = None
        if self.simulate:
            prices = self.deps.prices
            res = await self.deps.gateway().simulated_call(
                ctx.call_ctx("face_check", character_id=speaker_id, message_id=message_id),
                cost_usd=decision_cost(prices.decision, FACE_CHECK_DECISION_TOKENS), model=prices.decision.model,
                tokens_in=FACE_CHECK_DECISION_TOKENS, latency_ms=REACTION_LATENCY_MS)
            call = {"purpose": "face_check", "model": res.model, "costUsd": res.cost_usd, "latencyMs": res.latency_ms}
        row = self.deps.system1_row("face_check", "yes")
        return (row, call) if row is not None else None


LEAD_INS = {"arbiter": "Thank you all. The arbiter is weighing the arguments.",
            "user": "Thank you all. Now it's your call.",
            "none": "Thank you all. Here is the summary."}


class ScriptedDebateHost:
    def __init__(self, deps: AiDeps) -> None:
        self.deps = deps

    def round_note(self, phase: str, round_: int, iteration: int) -> str:
        return f"ROUND {round_} · {LABEL.get(phase, phase.upper())}{' · EXTENDED' if iteration > 1 else ''}"

    def fixed_line(self, key: HostKey, by: str, motion: str = "") -> str:
        """Today's sentence for the phase a line opens (an extended round and Skip's closing repeat it), or the verdict
        lead-in by `verdictBy` (M11, debate D11; the mock shows the same)."""
        if key.kind == "lead_in":
            return LEAD_INS.get(by, LEAD_INS["arbiter"])
        if key.phase == "opening":
            return f'Welcome. Tonight\'s motion: "{motion}". Opening statements, please.'
        if key.phase == "rebuttal":
            return "Thank you. Rebuttals now: engage with what you actually heard."
        return "Closing statements. Make them count."

    async def narration(self, ctx: SessionContext, key: HostKey, *,
                        finish: Callable[[], str | None] | None = None) -> str | None:
        """`scripted` keeps its fixed sentences, at once (mock parity)."""
        cfg = ctx.config or {}
        return self.fixed_line(key, str(cfg.get("verdictBy") or "arbiter"), str(cfg.get("motion", "")))

    async def assess(self, req: VerdictRequest) -> Assessment:
        """The mock's `makeVerdict` (M11, debate D15: the work); a verdict the user doesn't pick is a paid call first
        (as the mock charges it), none for a pick."""
        ctx, by = req.session, req.by
        if by != "user":
            prices = self.deps.prices
            await self.deps.gateway().simulated_call(
                ctx.call_ctx("verdict"), model=prices.chat.model, tokens_in=6200, tokens_cached=2400, tokens_out=420,
                cost_usd=chat_cost(prices.chat, tokens_in=6200, tokens_cached=2400, tokens_out=420,
                                   mult=multiplier(prices, ctx.period)), latency_ms=1800)
        return Assessment(by=by, two_sided=(ctx.config or {}).get("format") == "two_sided",
                          simulated=make_verdict(ctx, by, None))

    def deliver(self, a: Assessment, picked: str | None) -> dict[str, Any]:
        from horizon.ai.naive.verdict import deliver

        return deliver(a, picked)


def make_verdict(ctx: SessionContext, by: str, picked: str | None) -> dict[str, Any]:
    cfg = ctx.config or {}
    rng = random.Random(f"{ctx.seed}:verdict")
    rubric = cfg.get("rubric") or DEFAULT_RUBRIC
    two_sided = cfg.get("format") == "two_sided"
    msgs = [m for m in ctx.recent if m.author_type == "character"]
    side_of = {p.character_id: p.side for p in ctx.participants}

    def points(pred: Callable[[MessageView], bool]) -> list[str]:
        out = []
        for m in [x for x in msgs if pred(x)][:4]:
            first = m.content
            for i, ch in enumerate(m.content):
                if ch in ".!?" and i + 1 < len(m.content) and m.content[i + 1] == " ":
                    first = m.content[:i + 1]
                    break
            out.append(first[:110])
        return out

    def by_side(side: str) -> Callable[[MessageView], bool]:
        return lambda m: side_of.get(m.character_id or "") == side

    def by_speaker(cid: str) -> Callable[[MessageView], bool]:
        return lambda m: m.character_id == cid

    if two_sided:
        summary = [{"subjectId": s, "points": points(by_side(s))} for s in ("prop", "opp")]
    else:
        summary = [{"subjectId": p.character_id, "points": points(by_speaker(p.character_id))} for p in ctx.participants]
    disagreement = "Whether the measured gains generalise beyond the cases that were studied."
    if by == "none" or not two_sided:
        return {"decidedBy": "none" if by == "user" else by, "strongerCase": None, "summary": summary,
                "keyDisagreement": disagreement}
    arbiter: str | None = None if rng.random() < 0.15 else ("prop" if rng.random() < 0.5 else "opp")
    winner = picked if by == "user" else arbiter
    scores = []
    for s in ("prop", "opp"):
        for r in rubric:
            lo, hi = (6.5, 9) if s == arbiter else (6, 8) if arbiter is None else (4.5, 7.5)
            scores.append({"subjectId": s, "criterionId": r["id"], "value": js_round(rng.uniform(lo, hi))})
    rationale = ("Both sides argued well within their own framing; neither engaged the other's strongest point decisively."
                 if arbiter is None else
                 f"The {'proposition' if arbiter == 'prop' else 'opposition'} engaged the other side's evidence directly "
                 f"and kept its claims inside what that evidence supports.")
    return {"decidedBy": by, "strongerCase": winner, "scoresBy": "side", "scores": scores, "summary": summary,
            "keyDisagreement": disagreement, "rationale": rationale}


class ScriptedWatchDirector:
    def order(self, cast: list[str], opening: str | None) -> list[str]:
        if not cast:
            return []
        start = cast.index(opening) if opening in cast else 0
        return cast[start:] + cast[:start]


class ScriptedSummariser:
    def __init__(self, deps: AiDeps) -> None:
        self.deps = deps

    async def episode(self, ctx: SessionContext) -> str:
        prices = self.deps.prices
        await self.deps.gateway().simulated_call(
            ctx.call_ctx("episode_summary"), model=prices.chat.model, tokens_in=5200, tokens_cached=3000, tokens_out=260,
            cost_usd=chat_cost(prices.chat, tokens_in=5200, tokens_cached=3000, tokens_out=260,
                               mult=multiplier(prices, ctx.period)), latency_ms=1200)
        names = [p.name.split(" ")[0] for p in ctx.participants]
        cfg = ctx.config or {}
        turns = (ctx.state or {}).get("turnsTaken", 0)
        return (f'Episode summary: {", ".join(names)} spent the scene on "{cfg.get("premise", "")}". {turns} turns, no one '
                f"fully got their way, and everyone will remember it differently.")

    async def rolling(self, ctx: SessionContext, previous: str | None, lines: Sequence[str]) -> str:
        """The demo's summary keeps the last 12 lines (docs/ai/05 X3), but bills one simulated `rolling_summary` call
        per drop, priced from its input and output, so a scripted session's cost shape matches real use (D-81)."""
        kept = ([previous] if previous else []) + list(lines)
        text = "\n".join(kept[-12:])
        prices = self.deps.prices
        tokens_in = estimate_tokens("\n".join(kept)) + 180
        tokens_out = estimate_tokens(text)
        await self.deps.gateway().simulated_call(
            ctx.call_ctx("rolling_summary"), model=prices.chat.model, tokens_in=tokens_in, tokens_out=tokens_out,
            cost_usd=chat_cost(prices.chat, tokens_in=tokens_in, tokens_cached=0, tokens_out=tokens_out,
                               mult=multiplier(prices, ctx.period)), latency_ms=900)
        return text


class ScriptedGuardrail:
    async def check(self, ctx: TurnContext, text: str) -> GuardrailResult:
        return GuardrailResult("pass", [{"name": "sfw", "verdict": "pass"}, {"name": "advice_scope", "verdict": "pass"}])


__all__ = ["ScriptedDebateHost", "ScriptedGuardrail", "ScriptedReactions", "ScriptedRouter",
           "ScriptedSummariser", "ScriptedTurnEngine", "ScriptedWatchDirector"]

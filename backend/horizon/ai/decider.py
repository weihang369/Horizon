"""The Decider (doc backend/05 §3, D-66, decider spec; doc 13 W11; ai-foundation design D4–D9): the ONLY way the
backend asks a bounded question.

    call = start(state, questions, ctx, *, purpose, fallback=None, deadline=None) -> DecisionCall
    await call.by(deadline_at)   # the answers if back by that clock instant, else the fallback (run once)
    await call.final()           # the real answers whenever they land
    call.cancel()                # Stop / leave / cap pause: readers get DecisionCancelled; the request still settles
    ask(...) == start(...).by(now + timeout)

- **Fixtures first.** A scripted answer for (purpose, key) resolves both reads at once, with no request and no ledger
  row (tests, and the scripted AI profile).
- **One request per state, as a runtime task** (`spawn`, wired to `rt.spawn`), so a virtual-clock advance waits for
  it. Deadlines are read on the runtime clock, so a slow answer loses the race in virtual time exactly as in real time.
- **The size check** (design D7, group A A1): state + the longest question ≤ 30,000 tokens (UTF-8 bytes ÷ 3) and at
  most 64 questions. Over either, nothing is sent, reserved or recorded: the fallback answers with reason `too_large`.
  Jev reports oversize as HTTP 429, so this check must refuse first.
- **429s** (design D8): hot-path purposes fall back at once; `importance`, `memory_guard` and `rubric` wait
  max(1 s, Retry-After) up to 5 s and send once more if their deadline still allows it.
- **Bank questions carry their meta** (id, version, label, deadline key, declared state fields). The state is checked
  against the declared fields before anything is sent; free text outside a `quoted_*` field is refused (doc 11 S6).
- **Validation per answer.** Each answer is checked against its type and option set; the fallback runs only for the
  invalid ones. With no fallback, any failure raises `DecisionUnavailable` and the caller takes its hold path (R-13).
- **How the call ended** (`outcome()`, design D6) is read by the pipeline when it records the ledger row:
  `cancelled`, `late` (a deadline read already fell back), `on_time` (a deadline read is waiting), or `final`.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
from collections.abc import Awaitable, Callable, Coroutine, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from horizon.domain import vclock
from horizon.domain.pricing import count_tokens
from horizon.gateway.context import CallContext
from horizon.gateway.decisions import DecisionsResponse
from horizon.gateway.errors import ProviderError
from horizon.gateway.types import Timeouts

log = logging.getLogger("horizon.decider")

JEV_BUDGET_TOKENS = 30_000           # group A A1: Jev fails at ≈ 32k (state + longest question); refuse before that
MAX_QUESTIONS = 64                   # group A A1: the largest request tested
RETRY_429 = frozenset({"importance", "memory_guard", "rubric"})   # background purposes (design D8)
RETRY_MIN_S, RETRY_MAX_S = 1.0, 5.0
Source = Literal["jev", "fallback", "fixture"]
_ID = re.compile(r"^[A-Za-z0-9_:.\-]{1,80}$")


# ── questions ──
@dataclass(frozen=True)
class QMeta:
    """What the bank says about a compiled question (`horizon.ai.questions`)."""

    id: str
    version: int
    label: str
    purpose: str
    deadline: str
    state: Mapping[str, str]
    about: str | None = None
    label_max: int = 40


@dataclass(frozen=True)
class Choice:
    instructions: str
    options: Mapping[str, str]          # option → description (include an explicit "none" option)
    meta: QMeta | None = field(default=None, compare=False)


@dataclass(frozen=True)
class Noul:
    instructions: str
    true: str
    false: str
    meta: QMeta | None = field(default=None, compare=False)


@dataclass(frozen=True)
class Score:
    instructions: str
    levels: Sequence[str]               # 2..10 concrete levels
    meta: QMeta | None = field(default=None, compare=False)


Question = Choice | Noul | Score


def wire_question(q: Question) -> dict[str, Any]:
    if isinstance(q, Choice):
        return {"type": "choice", "instructions": q.instructions, "criteria": dict(q.options)}
    if isinstance(q, Noul):
        return {"type": "noul", "instructions": q.instructions, "criteria": {"true": q.true, "false": q.false}}
    return {"type": "score", "instructions": q.instructions, "criteria": list(q.levels)}


# ── answers ──
@dataclass(frozen=True)
class ChoiceAnswer:
    choice: str
    confidence: float | None = None
    probabilities: Mapping[str, float] | None = None
    source: Source = "jev"


@dataclass(frozen=True)
class NoulAnswer:
    p: float
    source: Source = "jev"


@dataclass(frozen=True)
class ScoreAnswer:
    score: float                        # an index into the levels, 0 … n−1 (doc 13 W11)
    confidence: float | None = None
    probabilities: Mapping[str, float] | None = None
    source: Source = "jev"

    def unit(self, levels: int) -> float:
        """W11's one scale: index / (n − 1)."""
        return self.score / (levels - 1) if levels > 1 else 0.0


Answer = ChoiceAnswer | NoulAnswer | ScoreAnswer
Answers = Mapping[str, Answer]
Fallback = Callable[[], Awaitable[Answers]]


@dataclass(frozen=True)
class DecisionResult:
    answers: Mapping[str, Answer]
    generation_id: str | None = None
    failure: str | None = None          # why the fallback was used for every non-fixture question, if it was

    @property
    def used_fallback(self) -> bool:
        return any(a.source == "fallback" for a in self.answers.values())


class DecisionUnavailable(Exception):  # the doc's name (doc 05 §3)
    """No valid answer and no fallback: the caller takes its hold path (R-13)."""


class DecisionCancelled(Exception):
    """The decision was cancelled (Stop, leave, cap pause, end): nothing should act on it."""


class StateError(ValueError):
    """The state doesn't match the bank's declared fields: a builder bug, refused before anything is sent."""


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def _probs(v: Any) -> Mapping[str, float] | None:
    if not isinstance(v, Mapping):
        return None
    out = {str(k): float(p) for k, p in v.items() if _num(p) is not None}
    return out or None


def validate(q: Question, raw: Mapping[str, Any] | None) -> Answer | None:
    """Jev's raw answer → a typed answer, or None when it doesn't fit the question's type and options."""
    if not isinstance(raw, Mapping):
        return None
    if isinstance(q, Choice):
        c = raw.get("choice")
        if isinstance(c, str) and c in q.options:
            return ChoiceAnswer(choice=c, confidence=_num(raw.get("confidence")), probabilities=_probs(raw.get("probabilities")))
        return None
    if isinstance(q, Noul):
        p = _num(raw.get("noul"))
        return NoulAnswer(p=p) if p is not None and 0.0 <= p <= 1.0 else None
    s = _num(raw.get("score"))
    if s is not None and 0.0 <= s <= len(q.levels) - 1:
        return ScoreAnswer(score=s, confidence=_num(raw.get("confidence")), probabilities=_probs(raw.get("probabilities")))
    return None


def check_state(state: Any, questions: Mapping[str, Question]) -> None:
    """Bank questions declare their state fields (doc 11 S6, design D2): no undeclared top-level field, and no free
    text outside a `quoted_*` field. Questions without bank meta (the probe, tests) are not checked."""
    metas = [q.meta for q in questions.values() if q.meta is not None]
    if not metas:
        return
    if not isinstance(state, Mapping):
        raise StateError("a bank question's state must be an object")
    declared: dict[str, str] = {}
    for m in metas:
        declared.update(m.state)
    label_max = min(m.label_max for m in metas)
    for k, v in state.items():
        kind = declared.get(k)
        if kind is None:
            raise StateError(f"state field {k!r} is not declared by {', '.join(sorted({m.id for m in metas}))}")
        if kind == "quoted":
            continue
        if kind == "label" and not (isinstance(v, str) and len(v) <= label_max and "\n" not in v):
            raise StateError(f"state field {k!r} must be a short label; put free text in a quoted_* field")
        if kind == "list_label" and not (isinstance(v, list) and all(
                isinstance(x, str) and len(x) <= label_max and "\n" not in x for x in v)):
            raise StateError(f"state field {k!r} must be a list of short labels")
        if kind == "number" and _num(v) is None:
            raise StateError(f"state field {k!r} must be a number")
        if kind == "bool" and not isinstance(v, bool):
            raise StateError(f"state field {k!r} must be true or false")
        if kind == "id" and not (isinstance(v, str) and _ID.match(v)):
            raise StateError(f"state field {k!r} must be an ID")


class DeciderFixtures:
    """Scripted answers keyed by (purpose, question key)."""

    def __init__(self) -> None:
        self._answers: dict[tuple[str, str], Answer] = {}

    def set(self, purpose: str, key: str, answer: Answer) -> None:
        self._answers[(purpose, key)] = replace(answer, source="fixture")

    def get(self, purpose: str, key: str) -> Answer | None:
        return self._answers.get((purpose, key))

    def clear(self) -> None:
        self._answers.clear()


Decide = Callable[..., Coroutine[Any, Any, DecisionsResponse]]
Spawn = Callable[[str, Coroutine[Any, Any, Any]], "asyncio.Task[Any]"]


def budget_tokens(state: Any, questions: Mapping[str, Mapping[str, Any]]) -> int:
    """Jev's limit counts the state plus the longest question (questions are answered in parallel)."""
    longest = max((count_tokens(json.dumps(q, ensure_ascii=False)) for q in questions.values()), default=0)
    return count_tokens(json.dumps(state, ensure_ascii=False)) + longest


class DecisionCall:
    """One request and its readers (design D4, D5). Built only by `Decider.start`."""

    def __init__(self, decider: Decider, *, purpose: str, fixed: dict[str, Answer], pending: Mapping[str, Question],
                 fallback: Fallback | None) -> None:
        self._d = decider
        self.purpose = purpose
        self._fixed = fixed
        self._pending = pending
        self._fallback = fallback
        self._signal: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._task: asyncio.Task[DecisionsResponse] | None = None
        self._refused: str | None = None     # a failure decided before sending (too_large)
        self._fb: Answers | None = None      # the fallback's answers, computed once
        self._fb_lock = asyncio.Lock()
        self._waiting = 0                    # deadline reads still racing the request
        self.missed = False                  # a deadline read already fell back
        self.cancelled = False

    # ── wiring ──
    def _attach(self, task: asyncio.Task[DecisionsResponse]) -> None:
        self._task = task
        task.add_done_callback(lambda _t: self._wake())

    def _wake(self) -> None:
        if not self._signal.done():
            self._signal.set_result(None)

    @property
    def sent(self) -> bool:
        return self._task is not None

    @property
    def landed(self) -> bool:
        """The request has settled (answered or failed), so a read now returns at once (M11, debate D8)."""
        return self._refused is not None or (self._task is not None and self._task.done())

    def outcome(self) -> str:
        """How the call ended, for its ledger row (design D6)."""
        if self.cancelled:
            return "cancelled"
        if self.missed:
            return "late"
        if self._waiting:
            return "on_time"
        return "final"

    def cancel(self) -> None:
        """Readers get `DecisionCancelled`; the request (already sent) still settles and is recorded at its cost."""
        self.cancelled = True
        self._wake()

    # ── reads ──
    async def by(self, at: datetime) -> DecisionResult:
        """The answers if they are back by clock instant `at`, else the fallback (run once across readers)."""
        if not self._pending:
            return DecisionResult(answers=dict(self._fixed))
        if self._refused is not None:
            return await self._fail(self._refused)
        self._check_cancel()
        self._waiting += 1
        try:
            seconds = max(0.0, (at - self._d.now()).total_seconds())
            done = await self._d.wait(self._signal, seconds)
        finally:
            self._waiting -= 1
        self._check_cancel()
        if not done or self._task is None or not self._task.done():
            self.missed = True
            return await self._fail("timeout")
        return await self._resolve()

    async def final(self) -> DecisionResult:
        """The real answers whenever they land (or the fallback for a failed call); raises when cancelled."""
        if not self._pending:
            return DecisionResult(answers=dict(self._fixed))
        if self._refused is not None:
            return await self._fail(self._refused)
        self._check_cancel()
        await asyncio.shield(self._signal)
        self._check_cancel()
        return await self._resolve()

    def _check_cancel(self) -> None:
        if self.cancelled:
            raise DecisionCancelled(self.purpose)

    async def _resolve(self) -> DecisionResult:
        assert self._task is not None and self._task.done()
        if self._task.cancelled():
            return await self._fail("cancelled")
        exc = self._task.exception()
        if exc is not None:
            return await self._fail(str(getattr(exc, "code", type(exc).__name__)))
        resp = self._task.result()
        answers = dict(self._fixed)
        invalid: list[str] = []
        for key, q in self._pending.items():
            a = validate(q, resp.answers.get(key))
            if a is None:
                invalid.append(key)
            else:
                answers[key] = a
        if invalid:
            if self._fallback is None:
                raise DecisionUnavailable(f"invalid answers for {', '.join(sorted(invalid))} and no fallback")
            fb = await self._fallback_answers()
            for key in invalid:
                if key not in fb:
                    raise DecisionUnavailable(f"the fallback has no answer for {key}")
                answers[key] = replace(fb[key], source="fallback")
        return DecisionResult(answers=answers, generation_id=resp.generation_id)

    async def _fallback_answers(self) -> Answers:
        assert self._fallback is not None
        async with self._fb_lock:
            if self._fb is None:
                self._fb = await self._fallback()
            return self._fb

    async def _fail(self, why: str) -> DecisionResult:
        if self._fallback is None:
            raise DecisionUnavailable(why)
        fb = await self._fallback_answers()
        answers = dict(self._fixed)
        for key in self._pending:
            if key not in fb:
                raise DecisionUnavailable(f"{why}; the fallback has no answer for {key}")
            answers[key] = replace(fb[key], source="fallback")
        return DecisionResult(answers=answers, failure=why)


class Decider:
    def __init__(self, decide: Decide, timeouts: Timeouts, fixtures: DeciderFixtures | None = None, *,
                 budget: int = JEV_BUDGET_TOKENS, clock: Any = None, spawn: Spawn | None = None) -> None:
        """`clock` (now/sleep/activity) and `spawn` come from the runtime; without them (unit tests) the Decider
        waits in real time and tracks its tasks with the caller's activity."""
        self._decide = decide
        self.timeouts = timeouts
        self.fixtures = fixtures or DeciderFixtures()
        self.budget = budget
        self.clock = clock
        self._spawn = spawn
        self._late: set[asyncio.Task[Any]] = set()
        self._n = 0

    # ── time ──
    def now(self) -> datetime:
        if self.clock is not None:
            now: datetime = self.clock.now()
            return now
        return datetime.now(UTC)

    async def wait(self, fut: asyncio.Future[Any], seconds: float) -> bool:
        if fut.done():
            return True
        if self.clock is not None:
            return await vclock.wait_at_most(self.clock, fut, seconds)
        done, _ = await asyncio.wait({fut}, timeout=seconds)
        return bool(done)

    async def sleep(self, seconds: float) -> None:
        await (self.clock.sleep(seconds) if self.clock is not None else asyncio.sleep(seconds))

    def timeout_for(self, deadline_key: str) -> float:
        return self.timeouts.for_decision(deadline_key)

    # ── asking ──
    def start(self, state: Any, questions: Mapping[str, Question], ctx: CallContext, *, purpose: str,
              fallback: Fallback | None = None) -> DecisionCall:
        if ctx.purpose != purpose or ctx.category != "decision":
            raise ValueError("the call context must be a decision context for this purpose")
        check_state(state, questions)
        fixed: dict[str, Answer] = {}
        pending: dict[str, Question] = {}
        for key, q in questions.items():
            fx = self.fixtures.get(purpose, key)
            if fx is not None:
                fixed[key] = fx
            else:
                pending[key] = q
        call = DecisionCall(self, purpose=purpose, fixed=fixed, pending=pending, fallback=fallback)
        if not pending:
            return call
        wire = {k: wire_question(q) for k, q in pending.items()}
        size = budget_tokens(state, wire)
        if size > self.budget or len(wire) > MAX_QUESTIONS:
            log.warning("decision %s refused before sending: %d tokens, %d questions (limit %d tokens, %d questions)",
                        purpose, size, len(wire), self.budget, MAX_QUESTIONS)
            call._refused = "too_large"
            return call
        deadline = max((q.meta.deadline for q in pending.values() if q.meta is not None), default=purpose,
                       key=self.timeout_for)
        self._n += 1
        task = self._start_task(f"decide:{purpose}:{self._n}", self._request(state, wire, ctx, purpose, deadline, call))
        call._attach(task)
        return call

    async def ask(self, state: Any, questions: Mapping[str, Question], ctx: CallContext, *, purpose: str,
                  timeout_ms: int | None = None, fallback: Fallback | None = None) -> DecisionResult:
        """`start(...).by(now + timeout)`: the timeout is the call's, else the longest deadline among the bank
        questions, else the purpose's."""
        call = self.start(state, questions, ctx, purpose=purpose, fallback=fallback)
        if timeout_ms is not None:
            seconds = timeout_ms / 1000
        else:
            keys = [q.meta.deadline for q in questions.values() if q.meta is not None] or [purpose]
            seconds = max(self.timeout_for(k) for k in keys)
        return await call.by(self.now() + timedelta(seconds=seconds))

    async def _request(self, state: Any, wire: Mapping[str, Mapping[str, Any]], ctx: CallContext, purpose: str,
                       deadline: str, call: DecisionCall) -> DecisionsResponse:
        started = self.now()
        try:
            return await self._decide(state, wire, ctx, finish=call.outcome)
        except ProviderError as e:
            if e.code != "rate_limited" or purpose not in RETRY_429:
                raise
            wait = min(RETRY_MAX_S, max(RETRY_MIN_S, float(e.retry_after or 0)))
            spent = (self.now() - started).total_seconds()
            if spent + wait >= self.timeout_for(deadline) or call.cancelled:
                raise
            log.info("decision %s rate-limited; retrying once in %.1fs", purpose, wait)
            await self.sleep(wait)
            return await self._decide(state, wire, ctx, finish=call.outcome)

    def _start_task(self, name: str, coro: Coroutine[Any, Any, DecisionsResponse]) -> asyncio.Task[DecisionsResponse]:
        if self._spawn is not None:
            task = self._spawn(name, coro)
        else:
            task = asyncio.get_running_loop().create_task(coro, name=name)
            vclock.track(task, name)  # a late answer's ledger row still lands before an advance returns
        self._late.add(task)

        def done(t: asyncio.Task[Any]) -> None:
            self._late.discard(t)
            if not t.cancelled() and t.exception() is not None:
                log.info("decision request failed: %s", getattr(t.exception(), "code", type(t.exception()).__name__))

        task.add_done_callback(done)
        return task

    async def idle(self) -> None:
        """Wait for requests still in flight (tests)."""
        while self._late:
            await asyncio.gather(*list(self._late), return_exceptions=True)

    async def stop(self) -> None:
        """Shutdown and factory reset: cancel requests in flight (the pipeline records each at its estimate)."""
        tasks = list(self._late)
        for t in tasks:
            t.cancel()
        for t in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t

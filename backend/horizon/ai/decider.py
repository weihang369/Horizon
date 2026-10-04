"""The Decider (doc backend/05 §3, D-66, decider spec): the ONLY way the backend asks a bounded question.

    ask(state, questions, ctx, *, purpose, timeout_ms=None, fallback=None) -> DecisionResult

- **Fixtures first.** A scripted answer for (purpose, key) is returned with source "fixture", with no request and no
  ledger row (tests, and the scripted AI profile from M3).
- **One call per state.** All remaining questions go to Jev (`typesafe/jev-1.13`, pinned) in a single paid call,
  after a 32K budget check (state + the longest question); over budget counts as a failure and nothing is sent.
- **Per-purpose timeout** (route 400 ms, gate 500, rerank 600, emotion 300, otherwise 3 s; config, overridable per
  call). On timeout the caller gets the fallback at once, while the request keeps running in the background so its
  cost is still recorded (late answers are discarded).
- **Validation per answer.** Each answer is checked against its type and option set; the fallback runs only for the
  invalid ones. With no fallback, any failure raises `DecisionUnavailable` and the caller takes its hold path (R-13).
- Every call is `category: decision` with the caller's purpose, and never drains energy (the pipeline sees to that).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable, Coroutine, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Literal

from horizon.domain.pricing import count_tokens
from horizon.gateway.context import CallContext
from horizon.gateway.decisions import DecisionsResponse
from horizon.gateway.types import Timeouts

log = logging.getLogger("horizon.decider")

JEV_BUDGET_TOKENS = 32_000
Source = Literal["jev", "fallback", "fixture"]


# ── questions ──
@dataclass(frozen=True)
class Choice:
    instructions: str
    options: Mapping[str, str]          # option → description (include an explicit "none" option)


@dataclass(frozen=True)
class Noul:
    instructions: str
    true: str
    false: str


@dataclass(frozen=True)
class Score:
    instructions: str
    levels: Sequence[str]               # 2..10 concrete levels


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
    score: float
    confidence: float | None = None
    probabilities: Mapping[str, float] | None = None
    source: Source = "jev"


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


Decide = Callable[[Any, Mapping[str, Mapping[str, Any]], CallContext], Coroutine[Any, Any, DecisionsResponse]]


def budget_tokens(state: Any, questions: Mapping[str, Mapping[str, Any]]) -> int:
    """Jev's 32K counts the state plus the longest question (questions are answered in parallel)."""
    longest = max((count_tokens(json.dumps(q, ensure_ascii=False)) for q in questions.values()), default=0)
    return count_tokens(json.dumps(state, ensure_ascii=False)) + longest


class Decider:
    def __init__(self, decide: Decide, timeouts: Timeouts, fixtures: DeciderFixtures | None = None, *,
                 budget: int = JEV_BUDGET_TOKENS) -> None:
        self._decide = decide
        self.timeouts = timeouts
        self.fixtures = fixtures or DeciderFixtures()
        self.budget = budget
        self._late: set[asyncio.Task[Any]] = set()

    async def ask(self, state: Any, questions: Mapping[str, Question], ctx: CallContext, *, purpose: str,
                  timeout_ms: int | None = None, fallback: Fallback | None = None) -> DecisionResult:
        if ctx.purpose != purpose or ctx.category != "decision":
            raise ValueError("the call context must be a decision context for this purpose")
        answers: dict[str, Answer] = {}
        pending: dict[str, Question] = {}
        for key, q in questions.items():
            fx = self.fixtures.get(purpose, key)
            if fx is not None:
                answers[key] = fx
            else:
                pending[key] = q
        if not pending:
            return DecisionResult(answers=answers)

        wire = {k: wire_question(q) for k, q in pending.items()}
        if budget_tokens(state, wire) > self.budget:
            return await self._fail(answers, pending, fallback, "over the 32K decision budget")

        timeout = timeout_ms / 1000 if timeout_ms is not None else self.timeouts.for_decision(purpose)
        task: asyncio.Task[DecisionsResponse] = asyncio.get_running_loop().create_task(
            self._decide(state, wire, ctx), name=f"decide:{purpose}")
        done, _ = await asyncio.wait({task}, timeout=timeout)
        if not done:
            self._keep(task)  # still recorded in the ledger when it lands; the answer is discarded
            return await self._fail(answers, pending, fallback, "timeout")
        try:
            resp = task.result()
        except Exception as e:  # ProviderError, DecisionsResponse parsing, cap refusals…
            code = getattr(e, "code", type(e).__name__)
            return await self._fail(answers, pending, fallback, str(code))

        invalid: list[str] = []
        for key, q in pending.items():
            a = validate(q, resp.answers.get(key))
            if a is None:
                invalid.append(key)
            else:
                answers[key] = a
        if invalid:
            if fallback is None:
                raise DecisionUnavailable(f"invalid answers for {', '.join(sorted(invalid))} and no fallback")
            fb = await fallback()
            for key in invalid:
                if key not in fb:
                    raise DecisionUnavailable(f"the fallback has no answer for {key}")
                answers[key] = replace(fb[key], source="fallback")
        return DecisionResult(answers=answers, generation_id=resp.generation_id)

    async def _fail(self, answers: dict[str, Answer], pending: Mapping[str, Question], fallback: Fallback | None,
                    why: str) -> DecisionResult:
        if fallback is None:
            raise DecisionUnavailable(why)
        fb = await fallback()
        for key in pending:
            if key not in fb:
                raise DecisionUnavailable(f"{why}; the fallback has no answer for {key}")
            answers[key] = replace(fb[key], source="fallback")
        return DecisionResult(answers=answers, failure=why)

    def _keep(self, task: asyncio.Task[Any]) -> None:
        self._late.add(task)

        def done(t: asyncio.Task[Any]) -> None:
            self._late.discard(t)
            if not t.cancelled() and t.exception() is not None:
                log.info("late decision failed: %s", getattr(t.exception(), "code", type(t.exception()).__name__))

        task.add_done_callback(done)

    async def idle(self) -> None:
        """Wait for late requests still in flight (tests)."""
        while self._late:
            await asyncio.gather(*list(self._late), return_exceptions=True)

    async def stop(self) -> None:
        """Shutdown: cancel late requests (the pipeline records each at its estimate)."""
        tasks = list(self._late)
        for t in tasks:
            t.cancel()
        for t in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t

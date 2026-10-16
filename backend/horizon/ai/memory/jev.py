"""Jev's two questions in a pause run (docs/ai/09 M4, M5; memory design D14, D15).

- **Importance** (purpose `importance`, bank entry `importance`): one request per character per piece, one score
  question per added or rewritten line (`importance:l{n}`, ≤ 5). importance = the answer's `unit` (W11). The fallback,
  when Jev fails or is late (a background purpose: the Decider retries one 429 after ≥ 1 s, then the 30 s deadline),
  is the rewrite's weight hint, (weight − 1) / 4, or 0.5 without one. M14's seam: `importance_request(...,
  extra_questions=...)` adds its own question ids beside these, so `importance` is never re-versioned (D38).
- **The guard** (purpose `memory_guard`, bank entry `memory_guard`): one request per rewrite, asking whether the new
  line keeps every still-true part of the old one. p ≥ `t_keep` → Supersede; below it, or failed or late → the new
  line is inserted beside the old one (the fallback answers 0.0).
- **Same fact?** (purpose `memory_guard`, bank entry `same_fact`; phase 10, the user's choice): one request per add
  whose nearest current memory is at or above `memory.dupCosine`. p ≥ `t_same` → that memory is reinforced; below it,
  or failed or late → the add is written (the fallback answers 0.0: a dropped detail can't be recovered, a duplicate
  line can be forgotten).

Every request waits for a place in the run's semaphore (at most 10 Jev requests in flight per run, doc 09 M13).
Cancelling the run cancels the reads; a request already sent still settles and is recorded at its cost.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from horizon.ai.decider import Answers, NoulAnswer, Question, ScoreAnswer
from horizon.ai.questions import bank
from horizon.services.memory.stretch import Present

IMPORTANCE = "importance"
GUARD = "memory_guard"
SAME = "same_fact"
LEVELS = 5
NO_HINT = 0.5
LABEL_MAX = 40


@dataclass(frozen=True)
class Scored:
    value: float
    source: str                 # jev | fallback | fixture


def hint(weight: int | None) -> float:
    """The rewrite's weight as an importance: (weight − 1) / 4, or 0.5 without one."""
    return (weight - 1) / 4 if weight is not None and 1 <= weight <= 5 else NO_HINT


def first_sentence(text: str) -> str:
    s = " ".join(str(text or "").split())
    for i, ch in enumerate(s):
        if ch in ".!?" and (i + 1 == len(s) or s[i + 1] == " "):
            return s[:i + 1]
    return s


def _label(text: str) -> str:
    s = " ".join(text.split())
    return s if len(s) <= LABEL_MAX else s[:LABEL_MAX - 1].rstrip() + "…"


def importance_request(p: Present, user_name: str, lines: Sequence[str],
                       extra_questions: Mapping[str, Question] | None = None) -> tuple[dict[str, Any], dict[str, Question]]:
    """The state and questions of one character's importance request. `extra_questions` is M14's seam (D38)."""
    state: dict[str, Any] = {"quoted_name": p.name, "role": _label(p.role or "character"),
                             "quoted_about": first_sentence(p.about), "quoted_user": user_name,
                             "quoted_lines": {f"l{i}": text for i, text in enumerate(lines, 1)}}
    b = bank()
    name = _label(p.name)
    questions: dict[str, Question] = {f"{IMPORTANCE}:l{i}": b.question(IMPORTANCE, name=name, n=i)
                                      for i in range(1, len(lines) + 1)}
    questions.update(extra_questions or {})
    return state, questions


def t_keep() -> float:
    return float(bank().get(GUARD).thresholds.get("t_keep", 0.7))


def t_same() -> float:
    return float(bank().get(SAME).thresholds.get("t_same", 0.5))


async def _ask(deps: Any, sem: asyncio.Semaphore, state: Mapping[str, Any], questions: Mapping[str, Question],
               ctx: Any, purpose: str, fallback: Answers) -> tuple[Answers, str | None]:
    decider = deps.decider()

    async def fb() -> Answers:
        return fallback

    async with sem:
        call = decider.start(state, questions, ctx, purpose=purpose, fallback=fb)
        try:
            res = await call.by(decider.now() + timedelta(seconds=decider.timeout_for(purpose)))
        except asyncio.CancelledError:
            call.cancel()
            raise
    return res.answers, res.failure


async def importance(deps: Any, sem: asyncio.Semaphore, run_ctx: Any, p: Present, user_name: str,
                     lines: Sequence[tuple[str, int | None]]) -> list[Scored]:
    """One request for this character: `lines` are (text, weight hint), ≤ 5. Returns one score per line, in order."""
    if not lines:
        return []
    state, questions = importance_request(p, user_name, [x for x, _ in lines])
    fallback = {f"{IMPORTANCE}:l{i}": ScoreAnswer(score=hint(w) * (LEVELS - 1), source="fallback")
                for i, (_, w) in enumerate(lines, 1)}
    answers, _ = await _ask(deps, sem, state, questions, run_ctx.call(IMPORTANCE, character_id=p.character_id),
                            IMPORTANCE, fallback)
    out: list[Scored] = []
    for i, (_, w) in enumerate(lines, 1):
        a = answers.get(f"{IMPORTANCE}:l{i}")
        if isinstance(a, ScoreAnswer):
            out.append(Scored(round(a.unit(LEVELS), 4), a.source))
        else:
            out.append(Scored(hint(w), "fallback"))
    return out


async def guard(deps: Any, sem: asyncio.Semaphore, run_ctx: Any, character_id: str, old: str, new: str,
                source: str) -> Scored:
    """Does the rewrite keep the old line's still-true parts? p, or 0.0 when Jev failed or was late."""
    state = {"quoted_old": old, "quoted_new": new, "quoted_source": source}
    answers, _ = await _ask(deps, sem, state, {GUARD: bank().question(GUARD)},
                            run_ctx.call(GUARD, character_id=character_id), GUARD,
                            {GUARD: NoulAnswer(p=0.0, source="fallback")})
    a = answers.get(GUARD)
    if isinstance(a, NoulAnswer):
        return Scored(float(a.p), a.source)
    return Scored(0.0, "fallback")


async def same_fact(deps: Any, sem: asyncio.Semaphore, run_ctx: Any, character_id: str, old: str,
                    new: str) -> Scored:
    """Does the add say what the near memory already says, adding nothing? p, or 0.0 when Jev failed or was late."""
    state = {"quoted_old": old, "quoted_new": new}
    answers, _ = await _ask(deps, sem, state, {SAME: bank().question(SAME)},
                            run_ctx.call(GUARD, character_id=character_id), GUARD,
                            {SAME: NoulAnswer(p=0.0, source="fallback")})
    a = answers.get(SAME)
    if isinstance(a, NoulAnswer):
        return Scored(float(a.p), a.source)
    return Scored(0.0, "fallback")

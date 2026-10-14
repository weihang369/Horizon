"""The verdict's scores (doc 08 V7; doc 13 W5, W11; debate design D12; debate-verdict spec): Jev scores each side on each
criterion, and code decides the winner.

- **One Jev request** (purpose `rubric`, deadline `rubric` = 10 s): one 5-level `score` question per side per criterion,
  keyed `rubric_evidence:prop`, …, or `rubric_generic:prop:{n}` for a criterion the config names without a known id
  (its label goes in `quoted_criteria`, never in the instructions: S6). A 429 is retried once after 1 s, inside the
  deadline (W11's background rule).
- **The state:** the motion, the criteria labels (only with a generic question), the sides as an ORDERED LIST of blocks
  (each side's members, its arguments in speaking order with phase and speaker, Ask answers inside their speaker's block,
  and its missed turns), and the moderator's notes and questions apart. A list, because the store key sorts dict keys
  (M9 D38's trap): the evaluation's swapped order must be a different request.
- **The budget:** 24,000 tokens. Over it: every argument of an earlier iteration of a phase, and every Ask answer, is cut
  to its first 60 words; then every argument to 120 words; still over, no scores (summary only).
- **Bars:** `value` = round(unit × 10, 1), unit = index / 4 (W11). **The winner:** each side's mean bar over the
  criteria (equal weights); a difference under `verdict.margin` (0–10 scale) is "too close to call"; else the higher.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from horizon.ai.contexts import DebateLine, VerdictRequest
from horizon.ai.decider import Answers, DecisionCancelled, DecisionResult, Question, ScoreAnswer
from horizon.ai.questions import bank
from horizon.domain.pricing import count_tokens

log = logging.getLogger("horizon.ai.rubric")

PURPOSE = "rubric"
KNOWN = {"evidence": "rubric_evidence", "rebuttal": "rubric_rebuttal", "clarity": "rubric_clarity",
         "persuasion": "rubric_persuasion"}
GENERIC = "rubric_generic"
DEFAULT_RUBRIC = [{"id": "evidence", "label": "Evidence"}, {"id": "rebuttal", "label": "Rebuttal"},
                  {"id": "clarity", "label": "Clarity"}, {"id": "persuasion", "label": "Persuasion"}]
STATE_MAX = 24000
SIDES = ("prop", "opp")
SIDE_NAME = {"prop": "Proposition", "opp": "Opposition"}
RETRY_AFTER_S = 1.0


@dataclass(frozen=True)
class Criterion:
    id: str
    label: str
    qid: str
    n: int | None = None      # a generic criterion's position in `quoted_criteria` (1-based)

    def key(self, side: str) -> str:
        return f"{self.qid}:{side}" if self.n is None else f"{self.qid}:{side}:{self.n}"


@dataclass
class Scores:
    """The rubric's outcome: bars per side and criterion, the means, the stronger case (None: too close), or a failure
    (no scores: the verdict is summary only)."""

    bars: list[dict[str, Any]] = field(default_factory=list)
    means: dict[str, float] = field(default_factory=dict)
    stronger: str | None = None
    failure: str | None = None
    state_tokens: int = 0
    cut: int = 0              # 0 whole, 1 earlier iterations and answers cut to 60 words, 2 everything to 120
    calls: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.failure is None


def criteria(cfg: dict[str, Any]) -> list[Criterion]:
    out: list[Criterion] = []
    n = 0
    for r in cfg.get("rubric") or DEFAULT_RUBRIC:
        cid = str(r["id"])
        label = str(r.get("label") or cid)
        if cid in KNOWN:
            out.append(Criterion(cid, label, KNOWN[cid]))
        else:
            n += 1
            out.append(Criterion(cid, label, GENERIC, n))
    return out


def margin() -> float:
    """`verdict.margin`: the rubric entries' shared `thresholds.margin` (kept equal by the loader)."""
    th = bank().get("rubric_evidence").raw.get("thresholds") or {}
    return float(th.get("margin", 0.5))


def first_words(text: str, n: int) -> str:
    w = text.split()
    return text if len(w) <= n else " ".join(w[:n]) + " …"


def _latest_iterations(lines: list[DebateLine]) -> dict[str, int]:
    out: dict[str, int] = {}
    for x in lines:
        if x.kind == "argument":
            out[x.phase] = max(out.get(x.phase, 1), x.iteration)
    return out


def side_blocks(req: VerdictRequest, cut: int) -> list[dict[str, Any]]:
    """The two side blocks, Proposition first (live) or Opposition first (`swapped`, the evaluation)."""
    s = req.session
    latest = _latest_iterations(req.lines)
    blocks: list[dict[str, Any]] = []
    for side in (SIDES[::-1] if req.swapped else SIDES):
        args: list[dict[str, str]] = []
        for x in req.lines:
            if x.side != side or x.kind not in ("argument", "answer"):
                continue
            text = x.text
            if cut >= 2:
                text = first_words(text, 60 if x.kind == "answer" or x.iteration < latest.get(x.phase, 1) else 120)
            elif cut >= 1 and (x.kind == "answer" or x.iteration < latest.get(x.phase, 1)):
                text = first_words(text, 60)
            args.append({"phase": "answer" if x.kind == "answer" else x.phase, "speaker": x.speaker, "text": text})
        block: dict[str, Any] = {"side": SIDE_NAME[side],
                                 "members": [p.name for p in s.participants if p.side == side], "arguments": args}
        m = req.missed.get(side)
        if m:
            n = int(m.get("missed", 0))
            why = "everyone on that side was asleep" if m.get("reason") == "asleep" else "the debate ended early"
            block["missed"] = f"{n} turn{'s' if n != 1 else ''} missed, {why}"
        blocks.append(block)
    return blocks


def state_for(req: VerdictRequest, crit: list[Criterion], cut: int = 0) -> dict[str, Any]:
    cfg = req.session.config or {}
    state: dict[str, Any] = {"mode": "debate", "quoted_motion": str(cfg.get("motion", ""))}
    generic = [c.label for c in crit if c.n is not None]
    if generic:
        state["quoted_criteria"] = generic
    state["quoted_sides"] = side_blocks(req, cut)
    moderator = [x.text for x in req.lines if x.kind in ("note", "question")]
    if moderator:
        state["quoted_moderator"] = moderator
    return state


def tokens(state: dict[str, Any], questions: dict[str, Question] | None = None) -> int:
    t = count_tokens(json.dumps(state, ensure_ascii=False))
    for q in (questions or {}).values():
        t += count_tokens(getattr(q, "instructions", ""))
    return t


def budgeted(req: VerdictRequest, crit: list[Criterion], limit: int = STATE_MAX) -> tuple[dict[str, Any], int] | None:
    """The state within `limit` tokens, cutting in V7's order; None when even the deepest cut is over."""
    for cut in (0, 1, 2):
        state = state_for(req, crit, cut)
        if tokens(state) <= limit:
            return state, cut
    return None


def questions(req: VerdictRequest, crit: list[Criterion]) -> dict[str, Question]:
    b = bank()
    seed = f"{req.session.seed}:rubric"
    out: dict[str, Question] = {}
    for side in SIDES:
        for c in crit:
            out[c.key(side)] = b.question(c.qid, side=SIDE_NAME[side], n=c.n, seed=f"{seed}:{c.key(side)}")
    return out


def bars(answers: Answers, crit: list[Criterion]) -> list[dict[str, Any]] | None:
    """`value` = round(unit × 10, 1) per side and criterion; None when any answer is missing or a fallback."""
    out: list[dict[str, Any]] = []
    for side in SIDES:
        for c in crit:
            a = answers.get(c.key(side))
            if not isinstance(a, ScoreAnswer) or a.source == "fallback":
                return None
            out.append({"subjectId": side, "criterionId": c.id, "value": round(a.unit(5) * 10, 1)})
    return out


def decide(values: list[dict[str, Any]], margin_: float) -> tuple[dict[str, float], str | None]:
    """Each side's mean bar (equal weights) and the stronger case: None when the difference is under the margin."""
    means = {s: sum(v["value"] for v in values if v["subjectId"] == s) / max(1, sum(1 for v in values
                                                                                if v["subjectId"] == s))
             for s in SIDES}
    diff = means["prop"] - means["opp"]
    return means, (None if abs(diff) < margin_ else "prop" if diff > 0 else "opp")


async def score(deps: Any, req: VerdictRequest) -> Scores:
    """Ask Jev (one request, its 429 retried once after 1 s inside the deadline) and decide the winner in code."""
    from horizon.ai.agent.cast_plan import ledger_call

    crit = criteria(req.session.config or {})
    fitted = budgeted(req, crit)
    if fitted is None:
        return Scores(failure="too_large")
    state, cut = fitted
    qs = questions(req, crit)
    decider = deps.decider()
    clock = deps.clock()
    deadline = clock.now() + timedelta(seconds=decider.timeout_for("rubric"))

    async def fallback() -> Answers:
        return {}

    res: DecisionResult | None = None
    for attempt in (0, 1):
        call = decider.start(state, qs, req.session.call_ctx(PURPOSE), purpose=PURPOSE, fallback=None)
        try:
            res = await call.by(deadline)
        except DecisionCancelled:
            raise asyncio.CancelledError() from None
        except asyncio.CancelledError:
            call.cancel()
            raise
        except Exception as e:   # no fallback: a failure arrives as DecisionUnavailable
            res = DecisionResult(answers={}, failure=str(e).split(";")[0] or "failed")
        if res.failure == "rate_limited" and attempt == 0 and clock.now() + timedelta(seconds=RETRY_AFTER_S) < deadline:
            await clock.sleep(RETRY_AFTER_S)
            continue
        break
    assert res is not None
    tok = tokens(state)
    if res.failure is not None:
        return Scores(failure=res.failure, state_tokens=tok, cut=cut)
    values = bars(res.answers, crit)
    if values is None:
        return Scores(failure="invalid", state_tokens=tok, cut=cut)
    means, stronger = decide(values, margin())
    row = await ledger_call(deps, res.generation_id, PURPOSE)
    return Scores(bars=values, means=means, stronger=stronger, state_tokens=tok, cut=cut,
                  calls=[row] if row else [])

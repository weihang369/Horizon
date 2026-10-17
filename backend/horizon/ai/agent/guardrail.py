"""The `agent` guardrail: the live Jev output check (doc 11 S5; safety design D9–D11, D19; content-safety "The output
check reads every reply", "The output check blocks, flags or passes").

One `guardrail` request per checked text, question `output_rules` ("reply breaks the rules?"), deadline
`timeoutsMs.decision.guardrail` (700 ms):
- **the state:** the speaker's name and role (labels), `care` (the reply's care cue), `quoted_message` (what the
  reply answers: the user's line; a debate argument's motion and the line before it; a scene's last line) and
  `quoted_reply` (the text as stored). At most 1,500 tokens with the question: `quoted_message` is cut from its start,
  the reply never (D9).
- **outcomes:** p ≥ `safety.tBlock` blocks; p ≥ `safety.tFlag` flags; below passes. Late or failed (a 429 included:
  `guardrail` is a hot-path purpose, W11) passes with a flag and no `p` (S5: Jev down never blocks).

`start()` returns a handle whose `by(deadline)` the runtime waits on at the stream's end; a Stop during the wait hands
the same handle to the after-the-fact check, which reads it with `final()` (W11), so nothing is paid twice (D10).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from horizon.ai.contexts import SessionContext, TurnContext
from horizon.ai.decider import Answers, DecisionCall, DecisionCancelled, DecisionResult, NoulAnswer, wire_question
from horizon.ai.ports import GuardrailResult
from horizon.ai.questions import bank
from horizon.domain.pricing import count_tokens

PURPOSE = "guardrail"
QID = "output_rules"
CAP = 1500                  # D9: state + question
LABEL_MAX = 40


def thresholds() -> dict[str, float]:
    t = bank().get(QID).thresholds
    return {"tFlag": float(t.get("tFlag", 0.5)), "tBlock": float(t.get("tBlock", 0.9))}


def _label(text: str) -> str:
    one = " ".join(str(text).split())
    return one if len(one) <= LABEL_MAX else one[:LABEL_MAX - 1].rstrip() + "…"


def _name(ctx: TurnContext) -> str:
    full = ctx.speaker.name
    return _label(full if len(full) <= LABEL_MAX else ctx.speaker.first_name)


def _role(ctx: TurnContext) -> str:
    part = next((p for p in ctx.session.participants if p.character_id == ctx.speaker.id), None)
    return _label(part.character_role if part is not None and part.character_role else "character")


def answered(ctx: TurnContext) -> str:
    """What the reply answers (D9): the user's line in 1:1 and group; a debate argument's motion and the line before
    it (as K4's query reads it); an Ask's question; a scene's last line."""
    recent = [m for m in ctx.session.recent if m.content and m.author_type != "system"]
    if ctx.line.kind == "answer":
        return ctx.prompt
    if ctx.line.kind == "debate":
        motion = ctx.debate.motion if ctx.debate is not None else ""
        before = next((m for m in reversed(recent) if m.character_id != ctx.speaker.id and m.author_type == "character"),
                      None)
        return "\n".join(x for x in (f"Motion: {motion}" if motion else "",
                                     f"{before.name}: {before.content}" if before is not None else "") if x)
    if ctx.session.mode in ("one_on_one", "group"):
        user = next((m for m in reversed(recent) if m.author_type == "user"), None)
        if user is not None:
            return user.content
    last = recent[-1] if recent else None
    return f"{last.name}: {last.content}" if last is not None else ""


def _tail_tokens(text: str, limit: int) -> str:
    """The last `limit` tokens of `text` (by UTF-8 bytes / 3, as `count_tokens`), cut at a character."""
    if limit <= 0:
        return ""
    if count_tokens(text) <= limit:
        return text
    budget, used, out = limit * 3 - 3, 0, []
    for ch in reversed(text):
        used += len(ch.encode("utf-8"))
        if used > budget:
            break
        out.append(ch)
    return "…" + "".join(reversed(out)).lstrip()


def build(ctx: TurnContext, text: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """(state, questions) within the 1,500-token cap: the answered line is cut from its start, the reply never."""
    care = bool(ctx.plan is not None and ctx.plan.safety is not None and ctx.plan.safety.care)
    return build_text(text, name=_name(ctx), role=_role(ctx), message=answered(ctx), care=care)


def build_text(text: str, *, name: str, role: str, message: str, care: bool = False) -> tuple[dict[str, Any],
                                                                                              dict[str, Any]]:
    """The same check for any shown text (a debate host line, verdict prose: D10), by whoever wrote it."""
    q = bank().question(QID, name=_label(name))
    state: dict[str, Any] = {"name": _label(name), "role": _label(role), "care": care,
                             "quoted_message": message, "quoted_reply": text}
    qtokens = count_tokens(json.dumps(wire_question(q), ensure_ascii=False))
    over = count_tokens(json.dumps(state, ensure_ascii=False)) + qtokens - CAP
    if over > 0:
        keep = max(0, count_tokens(state["quoted_message"]) - over - 2)
        state["quoted_message"] = _tail_tokens(state["quoted_message"], keep)
    return state, {QID: q}


def size(state: dict[str, Any], qs: dict[str, Any]) -> int:
    return count_tokens(json.dumps(state, ensure_ascii=False)) + sum(
        count_tokens(json.dumps(wire_question(q), ensure_ascii=False)) for q in qs.values())


def verdict_for(p: float) -> str:
    th = thresholds()
    return "block" if p >= th["tBlock"] else "flag" if p >= th["tFlag"] else "pass"


def result_from(res: DecisionResult | None, *, cancelled: bool = False) -> GuardrailResult:
    """The check's outcome, its `output` check (merged by name into the trace) and its System 1 row (D19)."""
    a = res.answers.get(QID) if res is not None else None
    p = a.p if isinstance(a, NoulAnswer) and a.source != "fallback" else None
    e = bank().get(QID)
    th = thresholds()
    row: dict[str, Any] = {"purpose": PURPOSE, "id": QID, "version": e.version, "label": e.label}
    if p is None:
        why = "late" if res is not None and res.failure == "timeout" else "failed"
        row.update(answer="no", compared=[], result="fallback", action=f"flagged: Jev {why}")
        return GuardrailResult("pass", [{"name": "output", "verdict": "flag"}], rows=[row], fallback=True)
    verdict = verdict_for(p)
    pr = round(p, 4)
    row.update(answer="yes" if verdict != "pass" else "no", p=pr,
               compared=[{"name": "tFlag", "value": pr, "threshold": th["tFlag"]},
                         {"name": "tBlock", "value": pr, "threshold": th["tBlock"]}],
               result="used", action=verdict)
    return GuardrailResult("block" if verdict == "block" else "pass",
                           [{"name": "output", "verdict": verdict, "p": pr}], rows=[row], p=p)


class GuardCall:
    """One output check in flight: `by(deadline)` at the stream's end, `final()` after the fact (D10)."""

    def __init__(self, decider: Any, call: DecisionCall) -> None:
        self.decider = decider
        self.call = call
        self.started_at: datetime = decider.now()

    @property
    def landed(self) -> bool:
        return self.call.landed

    async def by(self, at: datetime) -> GuardrailResult:
        try:
            return result_from(await self.call.by(at))
        except DecisionCancelled:
            return result_from(None)

    async def final(self) -> GuardrailResult:
        try:
            return result_from(await self.call.final())
        except DecisionCancelled:
            return result_from(None)

    def cancel(self) -> None:
        self.call.cancel()

    def timeout(self) -> timedelta:
        return timedelta(seconds=self.decider.timeout_for(PURPOSE))

    def deadline(self) -> datetime:
        """`timeoutsMs.decision.guardrail` from the moment the check was sent."""
        return self.started_at + self.timeout()


IMAGE_NOULS = ("image_likeness", "image_nudity", "image_gore", "image_young")   # doc 12 I3: four in one request
SONG_NOUL = "song_copy"                                                         # doc 12 I4
PROMPT_THRESHOLD = {"image_likeness": "tImageLikeness", "image_nudity": "tImageNudity", "image_gore": "tImageGore",
                    "image_young": "tImageYoung", "song_copy": "tSong"}
CACHE_MAX = 512


class PromptCache:
    """D17: Jev's answers to a prompt check, kept in memory by SHA-256 of (the entries' versions, the kind, the text);
    a bounded LRU. A fail-open pass is never kept; a restart forgets everything."""

    def __init__(self, size: int = CACHE_MAX) -> None:
        from collections import OrderedDict

        self.size = size
        self._d: OrderedDict[str, GuardrailResult] = OrderedDict()

    @staticmethod
    def key(kind: str, text: str) -> str:
        import hashlib

        ids = IMAGE_NOULS if kind == "image" else (SONG_NOUL,)
        versions = ",".join(f"{i}@{bank().get(i).version}" for i in ids)
        return hashlib.sha256(f"{versions}|{kind}|{text}".encode()).hexdigest()

    def get(self, k: str) -> GuardrailResult | None:
        got = self._d.get(k)
        if got is not None:
            self._d.move_to_end(k)
        return got

    def put(self, k: str, v: GuardrailResult) -> None:
        self._d[k] = v
        self._d.move_to_end(k)
        while len(self._d) > self.size:
            self._d.popitem(last=False)


MOTION = "motion_rules"
MOTION_DEADLINE = "guardrail_prompt"
MOTION_REFUSED = "The motion (or premise) was declined by the safety check. Try different wording."
MOTION_KIND = {"debate": "debate motion", "watch": "watch premise"}


def t_motion() -> float:
    return float(bank().get(MOTION).thresholds.get("tMotion", 0.7))


class AgentGuardrail:
    """The `agent` guardrail (D9), the motion check (D14) and, from phase 6, `check_prompt` (doc 12 I3, I4)."""

    def __init__(self, deps: Any) -> None:
        self.deps = deps
        self.prompts = PromptCache()

    async def check_prompt(self, cctx: Any, kind: str, text: str) -> GuardrailResult:
        """D17 (doc 12 I3, I4): the text an image job or a song task will send: four image nouls in one request, or
        `song_copy`, with deadline `guardrail_prompt`. Any noul at or above its threshold blocks; late or failed passes
        (`fallback`, nothing cached). Only Jev's answers are cached."""
        k = PromptCache.key(kind, text)
        hit = self.prompts.get(k)
        if hit is not None:
            return hit
        ids = IMAGE_NOULS if kind == "image" else (SONG_NOUL,)
        qs = {i: bank().question(i) for i in ids}

        async def fallback() -> Answers:
            return {i: NoulAnswer(0.0) for i in ids}

        decider = self.deps.decider()
        call = decider.start({"quoted_text": text}, qs, cctx, purpose=PURPOSE, fallback=fallback)
        try:
            res = await call.by(decider.now() + timedelta(seconds=decider.timeout_for(MOTION_DEADLINE)))
        except DecisionCancelled:
            return GuardrailResult("pass", [], fallback=True)
        checks: list[dict[str, Any]] = []
        block = False
        for i in ids:
            a = res.answers.get(i)
            if not isinstance(a, NoulAnswer) or a.source == "fallback":
                return GuardrailResult("pass", [], fallback=True)
            th = float(bank().get(i).thresholds.get(PROMPT_THRESHOLD[i], 0.5))
            hit_ = a.p >= th
            block = block or hit_
            checks.append({"name": i, "verdict": "block" if hit_ else "pass", "p": round(a.p, 4)})
        out = GuardrailResult("block" if block else "pass", checks, p=max(c["p"] for c in checks))
        self.prompts.put(k, out)
        return out

    def start(self, ctx: TurnContext, text: str) -> GuardCall:
        state, qs = build(ctx, text)
        return self._send(state, qs, ctx.call_ctx(PURPOSE))

    def _send(self, state: dict[str, Any], qs: dict[str, Any], cctx: Any) -> GuardCall:
        async def fallback() -> Answers:
            return {QID: NoulAnswer(0.0)}

        decider = self.deps.decider()
        call = decider.start(state, qs, cctx, purpose=PURPOSE, fallback=fallback)
        return GuardCall(decider, call)

    async def check(self, ctx: TurnContext, text: str) -> GuardrailResult:
        call = self.start(ctx, text)
        return await call.by(call.deadline())

    async def check_motion(self, world_id: str, mode: str, text: str) -> GuardrailResult:
        """D14: a debate's motion or a watch's premise, once when the session is created (deadline
        `guardrail_prompt`). p ≥ `safety.tMotion` blocks; late or failed passes with no p (the session starts)."""
        from horizon.gateway.context import call_ctx

        q = bank().question(MOTION)
        state = {"kind": MOTION_KIND.get(mode, "debate motion"), "quoted_premise": text}

        async def fallback() -> Answers:
            return {MOTION: NoulAnswer(0.0)}

        decider = self.deps.decider()
        call = decider.start(state, {MOTION: q}, call_ctx(PURPOSE, world_id=world_id), purpose=PURPOSE,
                             fallback=fallback)
        try:
            res = await call.by(decider.now() + timedelta(seconds=decider.timeout_for(MOTION_DEADLINE)))
        except DecisionCancelled:
            res = None
        a = res.answers.get(MOTION) if res is not None else None
        p = a.p if isinstance(a, NoulAnswer) and a.source != "fallback" else None
        if p is None:
            return GuardrailResult("pass", [], fallback=True)
        return GuardrailResult("block" if p >= t_motion() else "pass", [], p=p)

    async def check_text(self, session: SessionContext, text: str, *, name: str, role: str,
                         message: str) -> GuardrailResult:
        """D10: a debate host line inside its `host_line` task, verdict prose inside the `verdict` work."""
        state, qs = build_text(text, name=name, role=role, message=message)
        call = self._send(state, qs, session.call_ctx(PURPOSE))
        return await call.by(call.deadline())

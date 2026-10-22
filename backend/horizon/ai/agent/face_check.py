"""The live face-and-words check (doc 13 W2; docs/ai/06 E7; turn-plan-emotion design D23, D24; face-check spec).

After `turn.end`, Jev reads only the reply's words (its last 600 tokens, quoted) and picks which of the 7 emotions they
show. The System 1 row says whether that agrees with the face shown: `yes`, `clash` (happy against sad or angry,
either way), or `no (words read: {pick})`, with `p` = Jev's probability for the face shown and result `shown_only`.
D-112 (the user's choice, U-54, reversing the display-only rule of turn-plan-emotion D24 for clashes only): on a clash
the runtime switches the face to the words' emotion and the row says so; any other answer never changes the face. A
late, failed or refused call returns None, and the runtime adds a `skipped` row saying so (U-49), as it does for a
face it doesn't check.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import select

from horizon.ai.contexts import SessionContext
from horizon.ai.decider import ChoiceAnswer, DecisionResult
from horizon.ai.ports import FaceCheckOut
from horizon.ai.questions import bank
from horizon.db import tables as t
from horizon.domain.pricing import count_tokens

log = logging.getLogger("horizon.ai.face_check")

PURPOSE = "face_check"
QUESTION = "face_check"
TAIL_TOKENS = 600
CLASH = {frozenset({"happy", "sad"}), frozenset({"happy", "angry"})}


def tail(text: str, limit: int = TAIL_TOKENS) -> str:
    """The reply's last `limit` tokens (W2), cut at a character (bytes / 3, as `count_tokens`)."""
    if count_tokens(text) <= limit:
        return text
    return text.encode("utf-8")[-limit * 3:].decode("utf-8", errors="ignore").lstrip()


def verdict(face: str, pick: str) -> str:
    if pick == face:
        return "yes"
    if frozenset({face, pick}) in CLASH:
        return "clash"
    return f"no (words read: {pick})"


def row(*, version: int, label: str, face: str, pick: str, p: float | None) -> dict[str, Any]:
    out: dict[str, Any] = {"purpose": PURPOSE, "id": QUESTION, "version": version, "label": label,
                           "answer": verdict(face, pick)}
    if p is not None:
        out["p"] = round(float(p), 4)
    out.update(compared=[], result="shown_only")
    return out


def skipped_row(reason: str) -> dict[str, Any]:
    """U-49: the row a reply gets when its face isn't checked (a neutral face, MANUAL, no answer in time)."""
    meta = bank().get(QUESTION)
    return {"purpose": PURPOSE, "id": QUESTION, "version": meta.version, "label": meta.label, "answer": "\u2014",
            "compared": [], "result": "skipped", "action": reason}


def switched(r: dict[str, Any], words: str) -> dict[str, Any]:
    """D-112: the clash row once the face was switched to the words' emotion."""
    return {**r, "result": "used", "action": f"face switched to {words}"}


class JevFaceCheck:
    reports_skips = True   # U-49: a reply it doesn't check still gets a row saying why

    def __init__(self, deps: Any) -> None:
        self.deps = deps

    async def check(self, ctx: SessionContext, message_id: str, speaker_id: str, face: str,
                    text: str) -> FaceCheckOut | None:
        q = bank().question(QUESTION, seed=f"{ctx.seed}:{message_id}:face")
        decider = self.deps.decider()
        call_ctx = ctx.call_ctx(PURPOSE, character_id=speaker_id, message_id=message_id)
        call = None
        try:   # no fallback: a late or failed call adds no row (W2)
            call = decider.start({"quoted_reply": tail(text)}, {QUESTION: q}, call_ctx, purpose=PURPOSE)
            res: DecisionResult = await call.by(decider.now() + timedelta(seconds=decider.timeout_for(PURPOSE)))
        except asyncio.CancelledError:
            if call is not None:
                call.cancel()   # clear(): readers detach; a request already sent settles and is recorded
            raise
        except Exception as e:   # DecisionUnavailable, a budget refusal, a provider error: never touches the session
            log.info("face check for %s skipped: %s", message_id, getattr(e, "code", type(e).__name__))
            return None
        a = res.answers.get(QUESTION)
        if not isinstance(a, ChoiceAnswer) or a.source == "fallback":
            return None
        probs = dict(a.probabilities or {})
        meta = q.meta
        r = row(version=meta.version if meta else 0, label=meta.label if meta else "face and words agree?", face=face,
                pick=a.choice, p=probs.get(face, 1.0 if a.choice == face else 0.0))
        return FaceCheckOut(r, await self._call(res.generation_id), a.choice)

    async def _call(self, generation_id: str | None) -> dict[str, Any] | None:
        """The check's ledger row as a `TurnTrace.calls` entry (its latency shows in Insight, W1)."""
        if not generation_id:
            return None
        db = self.deps.gateway().ledger.db
        U = t.usage_records.c
        async with db.read() as conn:
            r = (await conn.execute(select(U.model, U.cost_usd, U.latency_ms).where(U.generation_id == generation_id)
                                    .order_by(U.at.desc()).limit(1))).first()
        if r is None:
            return None
        return {"purpose": PURPOSE, "model": r[0] or "", "costUsd": round(float(r[1]), 6), "latencyMs": int(r[2] or 0)}

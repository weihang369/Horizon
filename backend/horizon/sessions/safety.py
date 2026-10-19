"""The safety questions through the runtime (doc 11 S3, S4; safety design D4, D5, D7, U3, U4).

Every plan that sees a user-written line asks about it until Jev's answer is stored. Here the runtime reads what a plan
needs about the line (`SafetyLine`): which line a plan kind answers, its stored answers, the care stay over the
session's last 3 user lines, and whether another plan of this session is asking about it right now (the per-actor
in-flight set, so two parallel plans ask once). After the plan returns, Jev's answers are written in their own small
write (never in the event path), and the line is released. Nothing here runs unless the planner asks safety questions
(`agent` with a key): `naive` and `scripted` never ask.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from horizon.ai.agent import safety as sf
from horizon.ai.contexts import CastRequest, SafetyCue, SafetyLine, SafetyWording
from horizon.services.ai_meta import StoredSafety, store_safety, stored_safety_many

if TYPE_CHECKING:
    from horizon.sessions.actor import SessionActor

log = logging.getLogger("horizon.sessions")

Wire = dict[str, Any]
CHAT_KINDS = frozenset({"group_first", "group_mentioned", "everyone", "step_in"})   # a chat line, with care (U1)
NOTE_KINDS = frozenset({"scene", "opening", "debate_opening", "debate_line"})     # a note colours the turn (U4)


def asks_safety(actor: SessionActor) -> bool:
    """The resolved planner asks the safety questions (its capability, never its name)."""
    rt = actor.rt
    return bool(getattr(rt.ai.planner(rt.keys.status() == "set"), "asks_safety", False))


def _ordered(actor: SessionActor) -> list[Wire]:
    from horizon.services.runtime.reducer import ordered_messages

    out: list[Wire] = ordered_messages(actor.state)
    return out


def is_chat_line(m: Wire) -> bool:
    """A user line the care stay counts: a 1:1 or group message, or a Step in line (kind `chat`)."""
    return m["author"]["type"] == "user" and (m.get("kind") or "chat") == "chat" and bool(m.get("content"))


async def line(actor: SessionActor, message: Wire | None, *, care: bool, wording: SafetyWording = "chat",
               note: bool = False, may_ask: bool = True, mark: bool = True) -> SafetyLine | None:
    """What a plan needs about `message`: its stored answers, the stay (care only), and whether this plan asks. A
    line this plan asks about is marked in flight (`mark`); `settle` (or `release`) clears it. The debate plan, held
    from one `turn.end` to the next turn and dropped by a fingerprint change, doesn't mark: a dropped plan must never
    leave its line looking asked."""
    if message is None:
        return None
    mid = str(message["id"])
    ids = [mid]
    before: list[str] = []
    if care:   # D7: the 2 user lines before it, for the stay
        chat = [m for m in _ordered(actor) if is_chat_line(m) and int(m["seq"]) < int(message["seq"])]
        before = [str(m["id"]) for m in chat[-2:]]
        ids += before
    stored = await stored_safety_many(actor.rt, ids)
    mine = stored.get(mid)
    asking: set[str] = actor.safety_asking
    ask = mine is None and may_ask and mid not in asking
    if mine is None and not ask and not may_ask:
        return None   # nothing stored and this plan can't read the line itself (a Next speaker after the replies)
    if ask and mark:
        asking.add(mid)
    prev: list[StoredSafety | None] = [stored.get(i) for i in before]
    return SafetyLine(message_id=mid, note=note, text=str(message.get("content") or "") if note else "", care=care,
                      stored=mine.to_json() if mine is not None else None, ask=ask,
                      stay=care and sf.stay_on(prev), wording=wording)


def release(actor: SessionActor, ln: SafetyLine | None) -> None:
    if ln is not None and ln.ask:
        actor.safety_asking.discard(ln.message_id)


def one_voice(plan: Any) -> str | None:
    """D7: the trace's `routing.reason` when a line's steer or care cue is on, so exactly one character answers it."""
    cue = getattr(plan, "safety", None)
    return sf.one_voice_reason(cue) if cue is not None and cue.on else None


async def settle(actor: SessionActor, ln: SafetyLine | None, cue: SafetyCue | None) -> None:
    """Right after the plan returns (D5): Jev's answers are stored for the line, then it is released. A fallback, a
    late or refused answer writes nothing, so the next plan asks again. Losing the write costs a question later."""
    try:
        flags = sf.to_store(cue)
        if flags is not None and cue is not None:
            try:
                await store_safety(actor.rt, cue.message_id, flags)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("storing the safety answers for %s failed", cue.message_id)
    finally:
        release(actor, ln)


# ── which line each plan answers ──
def last_chat_line(actor: SessionActor) -> Wire | None:
    return next((m for m in reversed(_ordered(actor)) if is_chat_line(m)), None)


def last_said(actor: SessionActor) -> Wire | None:
    return next((m for m in reversed(_ordered(actor)) if m["author"]["type"] in ("character", "user")
                 and m.get("content")), None)


def active_note(actor: SessionActor) -> Wire | None:
    """Watch: the director's note colouring this turn (its 2 turns not yet spent)."""
    d = actor.mode.direction
    if d is None or d[1] <= 0:
        return None
    return next((m for m in reversed(_ordered(actor)) if m["author"]["type"] == "user" and m.get("kind") == "direction"),
                None)


def unchecked_interject(actor: SessionActor) -> Wire | None:
    """Debate: the newest Interject newer than the last argument (V4: it reaches the next argument only)."""
    from horizon.sessions.debate_slots import is_argument

    msgs = _ordered(actor)
    last_arg = max((int(m["seq"]) for m in msgs if is_argument(m)), default=0)
    return next((m for m in reversed(msgs) if m["author"]["type"] == "user" and m.get("kind") == "interject"
                 and int(m["seq"]) > last_arg), None)


def last_ask(actor: SessionActor) -> Wire | None:
    return next((m for m in reversed(_ordered(actor)) if m["author"]["type"] == "user" and m.get("kind") == "steer"),
                None)


async def line_for_cast(actor: SessionActor, req: CastRequest) -> SafetyLine | None:
    """D4's table for the cast plan's kinds."""
    kind = req.kind
    if kind in CHAT_KINDS:
        return await line(actor, last_chat_line(actor), care=True)
    if kind == "next":   # Next speaker: reads the stored answers; asks only while the user's line is still the latest
        m = last_chat_line(actor)
        latest = last_said(actor)
        return await line(actor, m, care=True, may_ask=m is not None and latest is not None and latest["id"] == m["id"])
    if kind == "debate_ask":   # U3: the Ask's own face plan, with the Ask as `quoted_latest`
        return await line(actor, last_ask(actor), care=False, wording="debate")
    if kind in ("scene", "opening"):
        return await line(actor, active_note(actor), care=False, wording="scene", note=True)
    if kind in ("debate_opening", "debate_line"):
        return await line(actor, unchecked_interject(actor), care=False, wording="debate", note=True)
    return None

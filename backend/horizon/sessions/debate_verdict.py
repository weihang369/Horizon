"""When the verdict work runs, the pick, and the resume (M11; doc 08 V8, V9; debate design D14; debate-verdict spec).

- **The work** (`DebateHost.assess`: `agent`'s Jev scores then the prose, `naive`'s one call, `scripted`'s mock verdict)
  runs as the named background task `verdict` from the last closing's `turn.end`, unless Extend is set, in parallel with
  the turn gap, the pause, the VERDICT banner, the lead-in and the 1.8 s delay. It is stored with the transcript's
  fingerprint (the seq of the last character message, and the phase and iteration).
- **Discarded** by Extend and Skip, and by `clear()` (Stop, End without verdict, a cap pause, leave, delete).
- **End → "Go to verdict now"** takes the stored work out before `clear(keep_current=True)`, waits for a streaming
  argument's `turn.end`, then reuses the work if its fingerprint still matches, else starts anew: never paid twice.
- **You decide:** `debate.pick` only records the side; the delivery is an actor job queued when the work finishes (at
  once if it has, by the work's completion if it is running, or by starting it if there is none). The pick never waits
  in the inbox.
- **The resume rule** (the cap-refusal hang): a debate in the `verdict` phase with no verdict runs the work again on
  `debate.resume`, on the cap's resume path, and on the actor's first command after a load.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from horizon.ai.contexts import Assessment, DebateLine, VerdictRequest
from horizon.domain import vclock
from horizon.sessions.context import session_context
from horizon.sessions.debate_slots import is_argument, missed_turns

if TYPE_CHECKING:
    from horizon.sessions.actor import SessionActor

Wire = dict[str, Any]
NAME = "verdict"


@dataclass
class Work:
    fp: tuple[Any, ...]
    task: asyncio.Task[Assessment]


def _host(actor: SessionActor) -> Any:
    return actor.rt.ai.host(actor.rt.keys.status() == "set")


def _messages(actor: SessionActor) -> list[Wire]:
    from horizon.services.runtime.reducer import ordered_messages

    out: list[Wire] = ordered_messages(actor.state)
    return out


def cfg_of(actor: SessionActor) -> Wire:
    c: Wire = actor.session.get("config") or {}
    return c


def fingerprint(actor: SessionActor) -> tuple[Any, ...]:
    """D14: the seq of the last character message, plus its phase and iteration (the transcript the work read; a
    VERDICT banner or a host line doesn't change it)."""
    msgs = [m for m in _messages(actor) if m["author"]["type"] == "character"]
    if not msgs:
        return (0, None, None)
    d = msgs[-1].get("debate") or {}
    return (int(msgs[-1]["seq"]), d.get("phase"), d.get("iteration"))


def lines(actor: SessionActor, names: dict[str, str]) -> list[DebateLine]:
    """The transcript for the verdict, from the log: arguments and Ask answers with their phase, side and speaker; the
    moderator's Interjects and Asks."""
    side_of = {p["characterId"]: p.get("side") for p in actor.session["participants"]}
    out: list[DebateLine] = []
    for m in _messages(actor):
        d = m.get("debate") or {}
        phase, it = str(d.get("phase") or ""), int(d.get("iteration") or 1)
        if m["author"]["type"] == "character" and m.get("kind") == "chat" and m.get("content"):
            cid = str(m["author"].get("characterId"))
            out.append(DebateLine(kind="argument" if is_argument(m) else "answer", phase=phase, iteration=it,
                                  side=side_of.get(cid), speaker=names.get(cid, cid), character_id=cid,
                                  text=str(m["content"])))
        elif m["author"]["type"] == "user" and m.get("kind") in ("interject", "steer") and m.get("content"):
            out.append(DebateLine(kind="note" if m.get("kind") == "interject" else "question", phase=phase,
                                  iteration=it, text=str(m["content"])))
    return out


async def request(actor: SessionActor) -> VerdictRequest:
    sctx = await session_context(actor.rt, actor, recent=1000)
    names = {p.character_id: p.name for p in sctx.participants}
    cast = [p["characterId"] for p in actor.session["participants"]]
    return VerdictRequest(session=sctx, by=str(cfg_of(actor).get("verdictBy") or "arbiter"),
                          lines=lines(actor, names), missed=missed_turns(_messages(actor), cfg_of(actor), cast))


def start(actor: SessionActor) -> Work:
    """Start the work now (or keep a running one whose fingerprint matches) and store it."""
    fp = fingerprint(actor)
    cur: Work | None = actor.mode.verdict_work
    if cur is not None and cur.fp == fp and not cur.task.cancelled() and not refused(cur):
        return cur
    discard(actor)

    async def run() -> Assessment:
        req = await request(actor)
        a: Assessment = await checked(actor, req, await _host(actor).assess(req))
        if actor.mode.picked is not None and not a.refused:
            actor.enqueue(lambda: deliver(actor))   # You decide: the click came first
        return a

    work = Work(fp=fp, task=actor.background(NAME, run()))
    actor.mode.verdict_work = work
    return work


async def checked(actor: SessionActor, req: VerdictRequest, a: Assessment) -> Assessment:
    """M14 (safety D10): the prose is checked inside the work, after it is written (≤ 0.7 s on a screen that already
    waits). A block takes the existing "failed prose" fallback: the scores and the winner stay, each side's first
    sentences are quoted, and the note says so. Late or failed: the prose stands."""
    from horizon.ai.naive.verdict import NOTE_PROSE, quoted_summary

    if a.refused or a.simulated is not None or NOTE_PROSE in a.notes:
        return a
    texts = [p for s in a.summary for p in (s.get("points") or [])] + [x for x in (a.key_disagreement, a.rationale) if x]
    if not texts:
        return a
    rt = actor.rt
    check = getattr(rt.ai.guardrail(rt.keys.status() == "set"), "check_text", None)
    if check is None:
        return a
    motion = str((actor.session.get("config") or {}).get("motion", ""))
    res = await check(req.session, "\n".join(str(t) for t in texts), name="The arbiter", role="debate arbiter",
                      message=f"Motion: {motion}" if motion else "")
    if res.verdict != "block":
        return a
    out: Assessment = a.model_copy(update={"summary": quoted_summary(req), "key_disagreement": None, "rationale": None,
                                           "notes": [*a.notes, NOTE_PROSE]})
    return out


def refused(work: Work) -> bool:
    """A cap refused the work: it is run again (D14's resume rule)."""
    return work.task.done() and not work.task.cancelled() and work.task.exception() is None and work.task.result().refused


def discard(actor: SessionActor) -> None:
    """Extend, Skip: the work made for this transcript is cancelled (at most ≈ $0.002 spent, V9)."""
    cur: Work | None = actor.mode.verdict_work
    actor.mode.verdict_work = None
    if cur is not None and not cur.task.done():
        cur.task.cancel()


def take(actor: SessionActor) -> Work | None:
    """End with verdict: the stored work is taken out of the actor's named tasks, so `clear()` can't cancel it."""
    cur: Work | None = actor.mode.verdict_work
    actor.mode.verdict_work = None
    if cur is not None:
        actor._named.get(NAME, set()).discard(cur.task)
    return cur


def put_back(actor: SessionActor, work: Work | None) -> None:
    """After the clear: a taken work is the session's again when it still matches the transcript; else cancelled."""
    if work is None:
        return
    if work.fp == fingerprint(actor) and not work.task.cancelled():
        if not work.task.done():
            actor._named.setdefault(NAME, set()).add(work.task)
        actor.mode.verdict_work = work
    elif not work.task.done():
        work.task.cancel()


async def outcome(actor: SessionActor) -> Assessment | None:
    """The work's result, starting it if needed (None when the work itself was cancelled)."""
    work = start(actor)
    try:
        return await vclock.join(work.task)
    except asyncio.CancelledError:
        me = asyncio.current_task()
        if work.task.cancelled() and (me is None or not me.cancelling()):
            return None
        raise


async def deliver(actor: SessionActor, picked: str | None = None) -> None:
    """Post the failure notes and finish with the verdict. Nothing when it is already delivered, or a cap refused it
    (the session paused; resume runs the work again)."""
    from horizon.sessions.modes.common import message_event, note
    from horizon.sessions.modes.debate import finish

    st = actor.session.get("state") or {}
    if st.get("phase") != "verdict" or st.get("verdict") or actor.session.get("status") == "ended":
        return
    by = str(cfg_of(actor).get("verdictBy") or "arbiter")
    pick = picked if picked is not None else actor.mode.picked
    if by == "user" and pick is None:
        return
    a = await outcome(actor)
    if a is None or a.refused:
        return
    for text in a.notes:
        await actor.emit(message_event(note(actor, text)))
    await finish(actor, _host(actor).deliver(a, pick if by == "user" else None))
    actor.mode.verdict_work = None
    actor.mode.picked = None


def pick(actor: SessionActor, side: str) -> None:
    """D14: the click only records the side; the delivery is a job (queued now if the work is done, else by its
    completion, or by starting it)."""
    actor.mode.picked = side
    work: Work | None = actor.mode.verdict_work
    if work is None:
        start(actor)
    elif work.task.done():
        actor.enqueue(lambda: deliver(actor))


def needs_rerun(actor: SessionActor) -> bool:
    """In the verdict phase with no verdict, and no work running or usable."""
    st = actor.session.get("state") or {}
    work: Work | None = actor.mode.verdict_work
    idle = work is None or work.task.cancelled() or refused(work)
    return st.get("phase") == "verdict" and not st.get("verdict") and actor.session.get("status") != "ended" and idle


def resume(actor: SessionActor) -> None:
    """The resume rule: in the verdict phase with no verdict, run the work again; an Arbiter debate (or a recorded pick)
    then delivers."""
    if not needs_rerun(actor):
        return
    start(actor)
    by = str(cfg_of(actor).get("verdictBy") or "arbiter")
    if by != "user" or actor.mode.picked is not None:
        actor.enqueue(lambda: deliver(actor))

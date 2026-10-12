"""The rolling summary's one task per session (docs/ai/05 X2, X3; conversation-context "The window is cut after the
reply", "One summary writer per session", "Summary failures are bounded", "Forks start their summary at creation";
persona-context design D9, D11, D12).

- **When:** `check()` after every turn that didn't end in error, and when a fork is created. Never in turn
  preparation, so a summary call never delays a first word.
- **Single-flight:** while the task runs, `check()` does nothing; the next `turn.end` checks again.
- **Off the hot path:** an actor background task (`rt.spawn`): it takes no LLM slot and doesn't hold the turn queue.
  Actor stop (idle release, delete, reset, shutdown) cancels it, and it writes nothing. Stop, `clear()` and Forget
  don't touch it: it folds older, finished messages, which Forget never changes (D11).
- **One writer:** every `rolling` row, real or fallback, is written here under the session's write lock, after
  re-reading the latest row; a result whose boundary isn't newer is discarded.
- **Bounded failures:** per summary boundary, a second attempt waits until the window has grown by 1,000 more tokens;
  after 2 failures the free fallback is written (the old notes minus their oldest lines, then the last 12 dropped
  lines, within 600 tokens). The counts live on the actor: a restart allows at most 2 more paid attempts.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from horizon.ai.naive.window import plan_window, summary_lines
from horizon.db import tables as t
from horizon.domain.pricing import count_tokens

if TYPE_CHECKING:
    from horizon.sessions.actor import SessionActor

log = logging.getLogger("horizon.sessions")

RETRY_GROWTH = 1000
MAX_ATTEMPTS = 2
FALLBACK_LINES = 12
SUMMARY_MAX = 600


@dataclass
class Attempts:
    failures: int = 0
    tokens_at_failure: int = 0


def fallback_summary(previous: str | None, lines: list[str], limit: int = SUMMARY_MAX) -> str:
    """X2's cheap fallback: the newest content is never the part that is cut."""
    old = [x for x in (previous or "").split("\n") if x.strip()]
    tail = lines[-FALLBACK_LINES:]
    while old and count_tokens("\n".join(old + tail)) > limit:
        old.pop(0)
    while len(tail) > 1 and count_tokens("\n".join(old + tail)) > limit:
        tail.pop(0)
    return "\n".join(old + tail)


class SummaryTask:
    def __init__(self, actor: SessionActor) -> None:
        self.actor = actor
        self.task: asyncio.Task[None] | None = None
        self.attempts: dict[int, Attempts] = {}   # keyed by the summary boundary the dropped part starts after

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    def check(self) -> None:
        if self.running or self.actor.stopped:
            return
        self.task = self.actor.background("summary", self._run())

    async def _run(self) -> None:
        from horizon.services.runtime.reducer import ordered_messages
        from horizon.sessions.context import _latest_summary, _views, characters, session_context

        actor, rt = self.actor, self.actor.rt
        upto, previous = await _latest_summary(rt, actor.sid)
        msgs = [m for m in ordered_messages(actor.state) if m["status"] != "streaming"]
        ids = sorted({m["author"].get("characterId") for m in msgs if m["author"].get("characterId")})
        names = {cid: r["profile"].get("name", cid) for cid, r in (await characters(rt, ids)).items()}
        views = _views(msgs, names)
        size = rt.runtime_cfg.runtime.window_tokens.for_mode(actor.session["mode"])
        plan = plan_window(views, upto, size)
        if plan.upto_seq is None:
            return
        grown = sum(count_tokens(m.content) for m in views if m.seq > upto)
        st = self.attempts.get(upto)
        if st is not None and st.failures and grown < st.tokens_at_failure + RETRY_GROWTH:
            return   # the last attempt for this boundary failed: wait for 1,000 more tokens
        sctx = await session_context(rt, actor)
        you = str((sctx.world.you or {}).get("displayName") or "User")
        lines = summary_lines(plan.dropped, you)
        summariser = rt.ai.summariser(rt.keys.status() == "set")
        try:
            text = await summariser.rolling(sctx, previous, lines)
        except asyncio.CancelledError:
            raise
        except Exception as e:   # provider error, timeout, the cap, a refusal, an empty result
            st = self.attempts.setdefault(upto, Attempts())
            st.failures += 1
            st.tokens_at_failure = grown
            log.warning("rolling summary failed for session %s after seq %s (attempt %s): %s", actor.sid, upto,
                        st.failures, getattr(e, "code", type(e).__name__))
            if st.failures < MAX_ATTEMPTS:
                return
            text = fallback_summary(previous, lines)
        await self._write(plan.upto_seq, text)
        self.attempts.pop(upto, None)

    async def _write(self, upto_seq: int, text: str) -> None:
        from horizon.sessions.context import _latest_summary

        actor, rt = self.actor, self.actor.rt
        async with actor.write_lock:
            latest, _ = await _latest_summary(rt, actor.sid)
            if latest >= upto_seq:
                return   # another row already covers this boundary (it shouldn't): never two summaries racing
            async with rt.db.write() as tx:
                await tx.conn.execute(t.session_summaries.insert().values(
                    session_id=actor.sid, upto_seq=upto_seq, kind="rolling", character_id=None, text=text,
                    created_at=rt.now_iso()))


def summary_task(actor: SessionActor) -> SummaryTask:
    if actor.summary is None:
        actor.summary = SummaryTask(actor)
    task: SummaryTask = actor.summary
    return task


def check_summary(actor: Any) -> None:
    summary_task(actor).check()

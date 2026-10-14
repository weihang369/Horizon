"""The Auto host's lines through the runtime (M11; doc 08 V6; debate design D11; debate-host spec).

Only with `moderator: auto_host`. Each line is requested ahead, by the `HostKey` it introduces, as the named background
task `host_line`, and shown after its banner when ready, or replaced by the fixed line at its deadline (the late answer
is dropped and its ledger row records `late`). The wait is on the turn job, so a late host delays the round's first
argument by at most `hostBannerWaitMs`, never more.

| line | requested | shown, waiting until |
|---|---|---|
| welcome | at Start | after ROUND 1's banner, Start + `hostWelcomeWaitMs` |
| bridge | at the round's last `turn.end` | after the next banner, banner + `hostBannerWaitMs` |
| extended / skip | when that `begin_phase` runs | after its banner, banner + `hostBannerWaitMs` |
| lead-in | at the last closing's `turn.end` | after the VERDICT banner, banner + `hostBannerWaitMs` |

A key that no longer matches what comes next is cancelled (Extend, Skip); `clear()` cancels `host_line`.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from horizon.ai.contexts import HostKey
from horizon.domain import vclock
from horizon.sessions.context import session_context

if TYPE_CHECKING:
    from horizon.sessions.actor import SessionActor

NAME = "host_line"


@dataclass
class Pending:
    key: HostKey
    task: asyncio.Task[str | None]
    late: bool = False
    dropped: bool = False

    def finish(self) -> str | None:
        """The call's ledger outcome when the runtime stopped waiting for it (read inside the call's own task, so a
        cancel of that task, by `clear()` or a newer key, shows as `cancelling`)."""
        task = asyncio.current_task()
        if self.dropped or (task is not None and task.cancelling()):
            return "cancelled"
        return "late" if self.late else None


def auto_host(actor: SessionActor) -> bool:
    return bool((actor.session.get("config") or {}).get("moderator") == "auto_host")


def _host(actor: SessionActor) -> Any:
    return actor.rt.ai.host(actor.rt.keys.status() == "set")


def request(actor: SessionActor, key: HostKey) -> None:
    """Start writing the line for `key` now (a different pending key is dropped). Nothing without Auto host."""
    if not auto_host(actor):
        return
    cur: Pending | None = actor.mode.host_line
    if cur is not None and cur.key == key:
        return
    drop(actor)

    async def write() -> str | None:
        sctx = await session_context(actor.rt, actor, recent=1000)
        out: str | None = await _host(actor).narration(sctx, key, finish=pending.finish)
        return out

    pending = Pending(key=key, task=None)  # type: ignore[arg-type]
    pending.task = actor.background(NAME, write())
    actor.mode.host_line = pending


def drop(actor: SessionActor) -> None:
    """Forget the pending line: its request is cancelled and recorded `cancelled`."""
    cur: Pending | None = actor.mode.host_line
    actor.mode.host_line = None
    if cur is not None and not cur.task.done():
        cur.dropped = True
        cur.task.cancel()


async def show(actor: SessionActor, key: HostKey, until: datetime) -> None:
    """After its banner: the line for `key` once written, by `until` at the latest; else the fixed line. A line asked
    for another key is dropped and this one asked now."""
    from horizon.sessions.modes.common import message_event, note

    if not auto_host(actor):
        return
    request(actor, key)
    cur: Pending | None = actor.mode.host_line
    actor.mode.host_line = None
    text: str | None = None
    if cur is not None:
        wait = max(0.0, (until - actor.rt.clock.now()).total_seconds())
        if await vclock.wait_at_most(actor.rt.clock, cur.task, wait):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                text = cur.task.result()
        else:
            cur.late = True   # dropped: it still lands, its row records `late`
    if not text:
        cfg = actor.session.get("config") or {}
        text = str(_host(actor).fixed_line(key, str(cfg.get("verdictBy") or "arbiter"), str(cfg.get("motion", ""))))
    await actor.emit(message_event(note(actor, text, "narration", {"type": "host"})))

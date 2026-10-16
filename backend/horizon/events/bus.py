"""The EventBus (doc 01 §4.1): in-process pub/sub with two channel kinds, `global` and `session:{id}`.

Each subscriber has a bounded queue (1,000). A subscriber whose queue overflows is dropped: its stream closes and
the browser reconnects (`Last-Event-ID` for sessions; a re-query for global). Publishing never blocks.

M13 (memory design D7; event-streams "A session stream left empty is noticed"): `watch(prefix, on_first, on_drained)`
calls `on_drained(channel)` when a matching channel's last subscriber leaves, and `on_first(channel)` when a channel
with none gains one. The memory runs use it for the session stream's 30-second grace. Neither fires during
`close_all` (a shutdown is not the user leaving).
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

log = logging.getLogger("horizon.events")

GLOBAL = "global"
QUEUE_SIZE = 1000
_CLOSE = object()


def session_channel(session_id: str) -> str:
    return f"session:{session_id}"


class Subscriber:
    def __init__(self, channel: str, maxsize: int = QUEUE_SIZE) -> None:
        self.channel = channel
        self.queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=maxsize)
        self.closed = False
        self.dropped = False

    def _close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.queue.put_nowait(_CLOSE)
        except asyncio.QueueFull:
            # Make room for the close marker: the stream is ending anyway.
            while not self.queue.empty():
                self.queue.get_nowait()
            self.queue.put_nowait(_CLOSE)

    async def get(self) -> dict[str, Any] | None:
        """The next event, or None once the subscription is closed or dropped."""
        if self.closed and self.queue.empty():
            return None
        item = await self.queue.get()
        return None if item is _CLOSE else item


class EventBus:
    def __init__(self, maxsize: int = QUEUE_SIZE) -> None:
        self._subs: dict[str, set[Subscriber]] = defaultdict(set)
        self._maxsize = maxsize
        self._watchers: list[tuple[str, Callable[[str], None], Callable[[str], None]]] = []
        self._closing = False

    def watch(self, prefix: str, on_first: Callable[[str], None], on_drained: Callable[[str], None]) -> None:
        """M13: be told when a channel starting with `prefix` gains its first subscriber or loses its last one."""
        self._watchers.append((prefix, on_first, on_drained))

    def _tell(self, channel: str, first: bool) -> None:
        if self._closing:
            return
        for prefix, on_first, on_drained in list(self._watchers):
            if channel.startswith(prefix):
                try:
                    (on_first if first else on_drained)(channel)
                except Exception:   # a watcher's bug never breaks a stream
                    log.exception("channel watcher failed for %s", channel)

    def subscribe(self, channel: str) -> Subscriber:
        sub = Subscriber(channel, self._maxsize)
        subs = self._subs[channel]
        subs.add(sub)
        if len(subs) == 1:
            self._tell(channel, first=True)
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        subs = self._subs.get(sub.channel, set())
        was_in = sub in subs
        subs.discard(sub)
        sub._close()
        if was_in and not subs:
            self._tell(sub.channel, first=False)

    def publish(self, channel: str, event: dict[str, Any]) -> None:
        for sub in list(self._subs.get(channel, ())):
            if sub.closed:
                continue
            try:
                sub.queue.put_nowait(event)
            except asyncio.QueueFull:
                log.warning("dropping a slow %s subscriber", channel)
                sub.dropped = True
                self.unsubscribe(sub)

    def subscriber_count(self, channel: str) -> int:
        return len(self._subs.get(channel, ()))

    def close_all(self) -> None:
        self._closing = True
        try:
            for subs in list(self._subs.values()):
                for sub in list(subs):
                    self.unsubscribe(sub)
            self._subs.clear()
        finally:
            self._closing = False

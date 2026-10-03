"""The EventBus (doc 01 §4.1): in-process pub/sub with two channel kinds, `global` and `session:{id}`.

Each subscriber has a bounded queue (1,000). A subscriber whose queue overflows is dropped: its stream closes and
the browser reconnects (`Last-Event-ID` for sessions; a re-query for global). Publishing never blocks.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
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

    def subscribe(self, channel: str) -> Subscriber:
        sub = Subscriber(channel, self._maxsize)
        self._subs[channel].add(sub)
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        self._subs.get(sub.channel, set()).discard(sub)
        sub._close()

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
        for subs in list(self._subs.values()):
            for sub in list(subs):
                self.unsubscribe(sub)
        self._subs.clear()

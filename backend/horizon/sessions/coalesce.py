"""Token coalescing (session-runtime design D6, OQ-5).

Deltas are buffered and flushed as one `token` event when the buffer reaches 48 characters, when 50 ms of clock time
have passed since its first delta, when the engine yields a non-token event, or when the turn ends. The runner also
arms a trailing timer, so an idle stream still flushes within 50 ms. A flushed event is stored and then published as the
same object, so what is stored equals what was streamed.
"""

from __future__ import annotations

from collections.abc import Callable


class Coalescer:
    def __init__(self, max_chars: int, max_ms: float, now_ms: Callable[[], float]) -> None:
        self.max_chars = max_chars
        self.max_ms = max_ms
        self.now_ms = now_ms
        self.buf = ""
        self.first_at: float | None = None

    @property
    def pending(self) -> bool:
        return bool(self.buf)

    def due_in_ms(self) -> float:
        """Clock time until the time rule flushes the buffer (0 when it is due)."""
        if self.first_at is None:
            return self.max_ms
        return max(0.0, self.max_ms - (self.now_ms() - self.first_at))

    def add(self, delta: str) -> str | None:
        """Buffer a delta; returns the text to flush when a size or time rule says so."""
        if not delta:
            return None
        if not self.buf:
            self.first_at = self.now_ms()
        self.buf += delta
        if len(self.buf) >= self.max_chars or self.due_in_ms() <= 0:
            return self.take()
        return None

    def take(self) -> str:
        out = self.buf
        self.buf = ""
        self.first_at = None
        return out

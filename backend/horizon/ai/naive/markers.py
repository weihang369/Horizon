"""Unlisted citation markers leave the reply stream (D-102; v1 test stage, 2026-10-21).

A reply may write `[n]` only for a passage it was given (the docs block says "never use a number that isn't listed
here"). Recording the seed debate showed the model breaking that rule on 5 of 12 turns: without a docs block it copies
the `[n]` it sees in earlier turns, and a single passage holding numbered paragraphs came back as `[2] [3] [4]`. Those
markers render as plain text and point at nothing, so they are dropped from the stream, together with the spaces
before them, before any token is shown or stored. A listed marker, and `[n](...)` (a link), pass unchanged.
"""

from __future__ import annotations

import re
from collections.abc import Collection

_HELD = re.compile(r"[ \t]*(?:\[\d{0,2}(?:\])?)?$")   # what may still turn into a dropped marker: spaces, `[`, `[1`, `[12]`
_MARKER = re.compile(r"([ \t]*)\[(\d{1,2})\](?!\()")


class MarkerFilter:
    """Feed streamed text, get back the text that is safe to show; `close()` returns whatever was held at the end."""

    def __init__(self, listed: Collection[int]) -> None:
        self.listed = {int(n) for n in listed}
        self._held = ""

    def _clean(self, text: str) -> str:
        return _MARKER.sub(lambda m: m.group(0) if int(m.group(2)) in self.listed else "", text)

    def feed(self, text: str) -> str:
        buf = self._held + text
        held = _HELD.search(buf)
        cut = held.start() if held is not None else len(buf)
        self._held = buf[cut:]
        return self._clean(buf[:cut])

    def close(self) -> str:
        out, self._held = self._clean(self._held), ""
        return out

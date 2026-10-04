"""AiStateHooks (doc 05 §4): what the AI layer is told about the session runtime's life. M3 ships the no-op default;
memory and retrieval (M5) replace it. `on_delete` is delivered at least once through the purge outbox
(`services/purge.py`), so an implementation must be idempotent.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class AiStateHooks(Protocol):
    async def on_delete(self, scope: str, ids: Sequence[str]) -> None: ...


class NoOpHooks:
    async def on_delete(self, scope: str, ids: Sequence[str]) -> None:
        return None

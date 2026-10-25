"""AiStateHooks (doc 05 §4): what the AI layer is told about the session runtime's life. M3 ships the no-op default;
memory and retrieval (M5) replace it. `on_delete` and `on_forget` (M5: a memory Forget, design D16) are delivered at
least once through the purge outbox (`services/purge.py`), so an implementation must be idempotent.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class AiStateHooks(Protocol):
    async def on_delete(self, scope: str, ids: Sequence[str]) -> None: ...
    async def on_forget(self, memory_item_ids: Sequence[str], character_id: str, message_ids: Sequence[str]) -> None: ...


class NoOpHooks:
    async def on_delete(self, scope: str, ids: Sequence[str]) -> None:
        return None

    async def on_forget(self, memory_item_ids: Sequence[str], character_id: str, message_ids: Sequence[str]) -> None:
        return None


class CompositeHooks:
    """Delivers each hook to every member in order (ai-foundation D29: capture now; M9+ adds the graph store).
    Members are idempotent, so a redelivery after a partial failure is safe."""

    def __init__(self, members: Sequence[AiStateHooks]) -> None:
        self.members = list(members)

    async def on_delete(self, scope: str, ids: Sequence[str]) -> None:
        for m in self.members:
            await m.on_delete(scope, ids)

    async def on_forget(self, memory_item_ids: Sequence[str], character_id: str, message_ids: Sequence[str]) -> None:
        for m in self.members:
            await m.on_forget(memory_item_ids, character_id, message_ids)

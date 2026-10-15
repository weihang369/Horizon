"""What the `agent` deep work reads from the runtime (rag design D15; ai-ports "The planner runs a speaker's deep work").

The planner never builds an index or picks a space itself: the runtime gives it the speaker's read-only `ScopedIndex`
(bound to the world, the character and the space active when it was made, D12), that space's spec, whether the
speaker has vectors in it (the embedding's condition, D11), and the embedder.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from horizon.db import spaces
from horizon.db import tables as t
from horizon.db.spaces import SpaceSpec
from horizon.services.knowledge.index import ScopedIndex, has_vectors

if TYPE_CHECKING:
    from horizon.runtime import Runtime


class RuntimeDeepIO:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt

    def index(self, world_id: str, character_id: str) -> ScopedIndex:
        return ScopedIndex(self.rt, world_id, character_id, self.rt.space_id or "")

    async def space(self, space_id: str) -> SpaceSpec | None:
        async with self.rt.db.read() as conn:
            row = (await conn.execute(select(t.embedding_spaces).where(t.embedding_spaces.c.id == space_id))
                   ).mappings().first()
        return spaces.spec_of(row) if row is not None else None

    async def has_vectors(self, character_id: str, space_id: str) -> bool:
        if space_id != self.rt.space_id:
            return False
        return await has_vectors(self.rt, [character_id])

    def embedder(self) -> Any:
        return self.rt.ai.embedder(self.rt.keys.status() == "set")

    def key_set(self) -> bool:
        return self.rt.keys.status() == "set"

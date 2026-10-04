"""CallContext (doc backend/04 §1): who a paid call is for, what it is for, and which ledger bucket it lands in.

Contexts are built only by factories that take the purpose: `call_ctx` for system calls here, and the turn and job
factories that M3/M4 add on their actors. There is no flag to ask for an energy drain: `drains` is derived from
`purpose == "reply"` (D-42), so AI code can't mislabel a call into draining (or not draining) a character.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Category = Literal["chat", "decision", "image", "music", "profile", "summary", "memory", "embedding"]

# The ledger category a purpose lands in when the caller doesn't name one.
PURPOSE_CATEGORY: dict[str, Category] = {
    "reply": "chat", "host": "chat", "verdict": "chat",
    "route": "decision", "gate": "decision", "rerank": "decision", "guardrail": "decision", "reaction": "decision",
    "emotion": "decision", "importance": "decision", "rubric": "decision", "watch_end": "decision",
    "query_embed": "embedding", "embed_doc": "embedding",
    "summary": "summary", "memory": "memory", "profile": "profile", "song": "music",
}


@dataclass(frozen=True)
class CallContext:
    category: Category
    purpose: str
    world_id: str | None = None          # None only for system calls (testModel probes)
    character_id: str | None = None
    session_id: str | None = None
    job_id: str | None = None
    message_id: str | None = None
    creation: bool = False               # counts toward the character's creation cap (unapproved characters only)

    @property
    def drains(self) -> bool:
        return self.purpose == "reply"


def call_ctx(purpose: str, *, category: Category | None = None, world_id: str | None = None,
             character_id: str | None = None, session_id: str | None = None, job_id: str | None = None,
             message_id: str | None = None, creation: bool = False) -> CallContext:
    cat = category or PURPOSE_CATEGORY.get(purpose) or ("image" if purpose.startswith("image_") else None)
    if cat is None:
        raise ValueError(f"purpose {purpose!r} needs an explicit ledger category")
    return CallContext(category=cat, purpose=purpose, world_id=world_id, character_id=character_id,
                       session_id=session_id, job_id=job_id, message_id=message_id, creation=creation)

"""Frozen, scoped contexts for the AI ports (doc 05 §2, §4; ai-ports "Ports see frozen, scoped context").

A port receives an immutable, JSON-serialisable snapshot: the session, its participants with their energy, recent
messages (active variants only), the latest rolling summary, mode config and state, and the world and character scope.
It reaches the provider only through the gateway, with calls built by `call_ctx(purpose)`, which binds the session,
world, speaker and message, so a port can't mislabel spend (D-42: only `reply` drains). Ports never touch rows.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from horizon.gateway.context import CallContext, call_ctx

LineKind = Literal["greeting", "chat", "debate", "scene", "answer", "direction"]


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class WorldView(Frozen):
    id: str
    name: str
    you: dict[str, Any] | None = None


class CharacterView(Frozen):
    id: str
    name: str
    profile: dict[str, Any]

    @property
    def first_name(self) -> str:
        words = [w for w in self.name.split(" ") if w.rstrip(".").lower() not in ("dr", "prof", "mr", "ms", "mrs")]
        return words[0] if words else self.name


class ParticipantView(Frozen):
    character_id: str
    name: str
    role: str
    side: str | None = None
    muted: bool = False
    emotion: str = "neutral"        # the face shown now (the naive engine's default when no tag arrives)
    energy: dict[str, Any]


class MessageView(Frozen):
    id: str
    seq: int
    author_type: str
    character_id: str | None = None
    name: str
    kind: str
    content: str
    emotion: str | None = None


class SessionContext(Frozen):
    session_id: str
    seed: str = ""                  # stable randomness seed (creation instant, mode, cast): same state, same output
    world: WorldView
    mode: str
    title: str
    config: dict[str, Any] | None = None
    state: dict[str, Any] | None = None
    participants: list[ParticipantView]
    recent: list[MessageView]
    summary: str | None = None
    emotion_mode: str = "llm"
    content_rating: str = "sfw"
    period: Literal["peak", "off_peak"] = "off_peak"
    history_tokens: int = 0

    def call_ctx(self, purpose: str, *, character_id: str | None = None, message_id: str | None = None) -> CallContext:
        return call_ctx(purpose, world_id=self.world.id, session_id=self.session_id, character_id=character_id,
                        message_id=message_id)

    def name_of(self, character_id: str) -> str:
        for p in self.participants:
            if p.character_id == character_id:
                return p.name
        return character_id


class LineHint(Frozen):
    """What the mode asks for: the kind of line, and an explicit text when the mode already knows it (a greeting)."""

    kind: LineKind = "chat"
    text: str | None = None
    emotion: str | None = None


class DebateMeta(Frozen):
    phase: str
    round: int
    iteration: int
    side: str | None = None
    motion: str = ""


class TurnContext(Frozen):
    session: SessionContext
    speaker: CharacterView
    message_id: str | None          # None while prefetched (the ledger row is linked when the turn is released)
    variant_id: str | None = None
    prompt: str = ""
    line: LineHint = LineHint()
    turn_index: int = 0
    max_tokens: int = 350
    direction_note: str | None = None
    debate: DebateMeta | None = None

    def call_ctx(self, purpose: str) -> CallContext:
        return self.session.call_ctx(purpose, character_id=self.speaker.id, message_id=self.message_id)


class RouteContext(Frozen):
    session: SessionContext
    text: str
    mentions: list[str]
    eligible: list[str]
    policy: str
    turn_index: int = 0
    last_spoke: dict[str, int] = {}

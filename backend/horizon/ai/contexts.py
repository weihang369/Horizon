"""Frozen, scoped contexts for the AI ports (doc 05 §2, §4; ai-ports "Ports see frozen, scoped context").

A port receives an immutable, JSON-serialisable snapshot: the session, its participants with their energy, recent
messages (active variants only), the latest rolling summary, mode config and state, the world and character scope, and
(M5) the knowledge passages and memories the runtime already retrieved for the speaker.
It reaches the provider only through the gateway, with calls built by `call_ctx(purpose)`, which binds the session,
world, speaker and message, so a port can't mislabel spend (D-42: only `reply` drains). Ports never touch rows.
"""

from __future__ import annotations

from datetime import datetime
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
    appearance_summary: str = ""    # M8 (doc 04 P3): the "Looks" line, so self-descriptions match the portrait
    advisory: bool = False          # M8 (doc 11 S2): advisory characters get the advisory line

    @property
    def first_name(self) -> str:
        words = [w for w in self.name.split(" ") if w.rstrip(".").lower() not in ("dr", "prof", "mr", "ms", "mrs")]
        return words[0] if words else self.name


class ParticipantView(Frozen):
    character_id: str
    name: str
    role: str                       # the participant role: speaker | debater
    character_role: str = ""        # M8 (doc 04 P5): the profile's role, e.g. "barista"
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
        return call_ctx(purpose, world_id=self.world.id, session_id=self.session_id or None, character_id=character_id,
                        message_id=message_id)   # "" (an eval's stand-alone context) records no session

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
    verbatim: bool = False          # M8 (docs/ai/04 P9): say `text` word for word, with no model call


class DebateMeta(Frozen):
    phase: str
    round: int
    iteration: int
    side: str | None = None
    motion: str = ""


class KnowledgeHit(Frozen):
    """A retrieved passage (a child chunk) with what an engine needs to use and cite it (M5 design D10)."""

    chunk_id: str
    source_id: str
    title: str
    type: str                       # text | file | url (Citation.type)
    locator: str | None = None
    text: str                       # the child: what is cited and quoted
    section_text: str               # its parent section: what an LLM reads
    score: float                    # 0..1


class MemoryHit(Frozen):
    id: str
    kind: str
    text: str
    source_session_id: str | None = None
    score: float | None = None


# ── The turn plan (M9, turn-plan-emotion design D4; turn-plan spec) ──
PlanKind = Literal["reply", "greeting"]
FaceOutcome = Literal["jev", "none", "below_floor", "fallback", "late"]


class PlannedFace(Frozen):
    """What the plan decided for the speaker's face (doc 06 E1–E3; design D12, D13)."""

    face: str                                       # the face sent
    source: Literal["classifier", "default"]
    base: str                                       # the face kept on "none", unsure or a fallback
    outcome: FaceOutcome
    pick: str | None = None                         # Jev's pick, after the neutral + none merge
    p: float | None = None                          # Jev's probability for the face sent (None on a fallback)
    confidence: float | None = None
    compared: list[dict[str, Any]] = []             # [{name, value, threshold}] as in the System 1 row
    candidates: list[dict[str, Any]] = []           # TurnTrace.emotion.candidates: the top 3 [{label, p}]
    faded: bool = False
    manual: bool = False


class TurnPlan(Frozen):
    """The frozen result of the turn plan (A9: a turn replays from JSON with no Jev call)."""

    seed: str                                       # "{session seed}:{turn index}" (TurnTrace.system1.seed)
    kind: PlanKind = "reply"
    branch: Literal["quick", "deep"] | None = None  # None: this planner doesn't decide retrieval (the scripted one)
    emotion: PlannedFace | None = None              # None: the reply picks its own face (the scripted planner)
    rows: list[dict[str, Any]] = []                 # System 1 rows, `not_used` ones included
    calls: list[dict[str, Any]] = []                # the turn_plan call as a TurnTrace.calls entry
    graph_path: list[str] = []
    state_tokens: int = 0
    dropped_gates: list[str] = []

    @property
    def deep(self) -> bool:
        """The reply cap reads this (`reply_cap`): M12's deep turns get the deep cap."""
        return self.branch == "deep"


class PlanRequest(Frozen):
    """What the runtime gives the planner (design D4, D6)."""

    session: SessionContext
    speaker_id: str
    cast: list[CharacterView] = []                 # the candidates' profiles (the X9 `about` line)
    message_id: str | None = None                   # the reply's message: the turn_plan ledger row links to it
    kind: PlanKind = "reply"
    latest: str = ""                                # the user's text, without regenerate's " (again)"
    turn_index: int = 0
    base_face: str = "neutral"                      # AUTO: the face now; MANUAL: the last AI-chosen face (E2)
    manual: bool = False
    started_at: datetime                            # the deadline counts from here (the plan starts before turn.next)


class ListenerView(Frozen):
    """A listener as the reactions task reads it from the actor's state when it runs (design D18)."""

    id: str
    name: str
    about_source: str = ""                         # personality summary; cut to 60 tokens in the state (X9 helpers)
    face: str = "neutral"                           # the listener's face now
    side_label: str | None = None                   # debate: "same side as the speaker" | "the other side"
    eligible: bool = True                           # unmuted with energy for a reply: asked of Jev; else fade only (E3)


class ReactionRequest(Frozen):
    """What the reactions task gives `ReactionPredictor.predict` (design D18)."""

    session: SessionContext
    message_id: str
    speaker_id: str
    speaker_name: str = ""
    line: str                                       # the reply text
    before: str = ""                               # the line before it, as "Name: text"
    listeners: list[ListenerView] = []
    seed: str                                       # "{session seed}:{turn index}"


class TurnContext(Frozen):
    session: SessionContext
    speaker: CharacterView
    message_id: str | None          # None while prefetched (the ledger row is linked when the turn is released)
    variant_id: str | None = None
    prompt: str = ""
    line: LineHint = LineHint()
    turn_index: int = 0
    max_tokens: int                 # chosen by the runtime after the plan (docs/ai/03 C4; design D14)
    direction_note: str | None = None
    debate: DebateMeta | None = None
    knowledge: list[KnowledgeHit] = []   # M5: retrieved by the runtime in the speaker's scope (design D10)
    memory: list[MemoryHit] = []
    query: str | None = None             # the text retrieval used
    plan: TurnPlan | None = None          # M9: the frozen turn plan (design D4); None when the turn wasn't planned

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

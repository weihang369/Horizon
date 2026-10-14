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


class DebateLine(Frozen):
    """One line of a debate's transcript for the verdict (M11, debate D12, D13), read by the runtime from the log:
    an argument or an Ask answer with its phase, iteration, side and speaker, or a moderator's note or question."""

    kind: Literal["argument", "answer", "note", "question"]
    phase: str = ""
    iteration: int = 1
    side: str | None = None
    speaker: str = ""
    character_id: str | None = None
    text: str


class VerdictRequest(Frozen):
    """What `DebateHost.assess` reads (D12–D15): the session, the verdict mode, the transcript and the missed turns.
    `swapped` asks with the Opposition block first (the evaluation's order check, V11)."""

    session: SessionContext
    by: str                                         # arbiter | user | none
    lines: list[DebateLine] = []
    missed: dict[str, dict[str, Any]] = {}          # per side {missed, reason} (debate_slots.missed_turns)
    swapped: bool = False


class Assessment(Frozen):
    """The verdict work's result before a pick (D14): the bars and the arbiter's stronger case when scored, the prose or
    its quoted fallback, the failure notes to post, and whether a cap refused it (nothing to deliver: the session
    pauses, and the work runs again on resume)."""

    by: str
    two_sided: bool
    scored: bool = False
    scores: list[dict[str, Any]] = []
    stronger: str | None = None                     # the arbiter's stronger case; None: too close, or no scores
    summary: list[dict[str, Any]] = []
    key_disagreement: str | None = None
    rationale: str | None = None
    notes: list[str] = []
    refused: bool = False
    simulated: dict[str, Any] | None = None         # `scripted`: the mock's verdict, delivered as it is


HostKind = Literal["welcome", "bridge", "extended", "skip", "lead_in"]


class HostKey(Frozen):
    """What a host line introduces (doc 08 V6; debate D11): its kind and the (phase, iteration) it opens (the lead-in:
    `verdict`). A line requested for one key is dropped when a different one comes next (Extend, Skip)."""

    kind: HostKind
    phase: str
    iteration: int = 1


class DebateMeta(Frozen):
    phase: str
    round: int
    iteration: int
    side: str | None = None
    motion: str = ""
    # M11 (debate D10): the cue's facts, computed by the runtime from the log when it builds the spec (A9: a stored
    # context replays the same request); the engine only renders them
    teammates_heard: list[str] = []      # character IDs of teammates already heard in this phase-iteration
    after_interject: bool = False        # an Interject is newer than the last argument
    panel: bool = False


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


CueKind = Literal["second", "next", "steer"]


class GateAnswer(Frozen):
    """One candidate's "needs documents?" (M12: docs/ai/01 A4; rag design D7, D8): Jev's p, or None and why."""

    p: float | None = None
    outcome: Literal["jev", "late", "fallback", "dropped"] = "jev"


class MessageNouls(Frozen):
    """"standalone?" and "English?" about the message being answered (M12: doc 10 K4; rag D8), asked once per message
    in 1:1 and group. None: that answer fell back (no rewrite)."""

    standalone: float | None = None
    english: float | None = None
    outcome: Literal["jev", "late", "fallback"] = "jev"
    message_id: str | None = None                   # the message they were asked about (the follow plan reuses them)


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
    cue: CueKind | None = None                      # M10 (doc 07 G3; group-watch D10): the cue's one sentence
    answered: str | None = None                     # the first replier's name, for cue "second"
    gate: GateAnswer | None = None                  # M12: the speaker's "needs documents?" (None: not asked)
    abstain_ok: bool = False                        # M12 (rag D8): a not-found outcome may say so
    nouls: MessageNouls | None = None               # M12: "standalone?" / "English?" for the rewrite (1:1, group)

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
    documents: dict[str, list[str]] = {}            # M12 (rag D6): searchable sources' titles, by character


# ── The cast plan and the follow plan (M10: doc 07 G1–G8; group-watch design D3, D8, D22) ──
CastKind = Literal["group_first", "group_mentioned", "everyone", "next", "step_in", "scene", "opening",
                   "debate_opening", "debate_ask", "debate_line"]   # M11 (debate D5, D8): forced, the face only
WhoSource = Literal["jev", "below_floor", "fallback", "late", "forced", "single"]
SteerBlock = Literal["recent", "note"]


class WhoPick(Frozen):
    """Who speaks, and why (G1, G4, G6)."""

    pick: str                                       # the character who speaks (Everyone: the top of the order)
    source: WhoSource
    question: str | None = None                     # the bank id asked; None when nothing was asked
    label: str = ""
    p: float | None = None
    confidence: float | None = None
    candidates: list[dict[str, Any]] = []           # routing.candidates: [{characterId, p}], highest first
    forced_by: Literal["mention", "nudge", "round_order", "user_ask"] | None = None
    reason: str | None = None                       # routing.reason ("fallback", or the guard's sentence)


class TalkFinished(Frozen):
    """Watch's "is the talk finished?" and what code did with it (G7; D14)."""

    p: float | None                                 # None on a fallback
    steer: bool
    action: str


class DebateFacts(Frozen):
    """What a debate state holds besides the cast (docs/ai/05 X9's debate row; debate design D6): the motion, the
    phase and side set by code, the last argument by the other side (by anyone else in a panel), and each candidate's
    latest argument."""

    motion: str
    phase: str
    side: str | None = None
    last_opposing: str = ""
    latest_by_candidate: dict[str, str] = {}


class CastRequest(Frozen):
    """What the runtime gives `plan_cast` (D3): the candidates, who is forced, and what is being answered."""

    session: SessionContext
    kind: CastKind
    candidates: list[str]                           # who may be picked or asked about, in cast order
    forced: list[str] = []                          # speak without a who question (mentions, a nudge, the guard)
    forced_by: Literal["mention", "nudge", "round_order", "user_ask"] | None = None
    reason: str | None = None                       # the guard's routing.reason
    cast: list[CharacterView] = []                  # the candidates' profiles (X9's `about`)
    latest: str = ""                                # the line being answered: the user's text, or "Name: line"
    turn_index: int = 0
    base_faces: dict[str, str] = {}                 # E2's base per candidate (AUTO: the face now; MANUAL: last chosen)
    manual: bool = False
    turns_since: dict[str, int | None] = {}         # character lines since each last spoke (None: not yet)
    steer_block: SteerBlock | None = None           # watch: why a steer can't happen this turn (D14)
    started_at: datetime
    deadline_at: datetime | None = None             # None: started_at + the turn_plan deadline; plan-ahead sets it (D15)
    debate: DebateFacts | None = None               # M11: a debate turn's motion, phase and side (debate D7)
    documents: dict[str, list[str]] = {}            # M12 (rag D6): searchable sources' titles, by character
    message_id: str | None = None                   # M12: the user message being answered (the nouls are about it)


class CastPlan(Frozen):
    """The frozen cast plan (D3). `for_speaker` gives each reply its own `TurnPlan` for `TurnContext.plan`."""

    seed: str
    kind: CastKind
    order: list[str]                                # who speaks, in order (one, except Everyone)
    who: WhoPick | None = None                      # None: nobody to pick (e.g. all forced)
    faces: dict[str, PlannedFace] = {}
    face_rows: dict[str, dict[str, Any]] = {}       # each candidate's emotion row, as if used
    shared_rows: list[dict[str, Any]] = []          # the who row and the talk-finished row
    talk: TalkFinished | None = None
    calls: list[dict[str, Any]] = []
    graph_path: list[str] = []
    state_tokens: int = 0
    gates: dict[str, GateAnswer] = {}               # M12 (rag D8): "needs documents?" per candidate asked
    nouls: MessageNouls | None = None               # M12: "standalone?" / "English?" when a group message is answered

    @property
    def steer(self) -> bool:
        return self.talk is not None and self.talk.steer

    def for_speaker(self, cid: str, *, cue: CueKind | None = None, answered: str | None = None) -> TurnPlan:
        """The reply's frozen plan: its face, the shared rows plus its own row `used`, and the other candidates' rows
        `not_used` (W1), except on an Everyone reply, which carries only its own (D22). M12: the speaker's own gate
        decides the branch; the other candidates' gate rows are `not_used`."""
        from horizon.ai.agent import gates as g

        rows = list(self.shared_rows)
        for other, row in self.face_rows.items():
            if other == cid:
                rows.append(row)
            elif self.kind != "everyone":
                rows.append({**row, "result": "not_used"})
        gate = self.gates.get(cid)
        rows += g.speaker_rows(cid, self.gates, self.nouls, purpose="turn_plan", kind=self.kind,
                               everyone=self.kind == "everyone")
        return TurnPlan(seed=self.seed, kind="reply", branch="deep" if g.deep(gate) else "quick",
                        emotion=self.faces.get(cid), rows=rows, calls=list(self.calls),
                        graph_path=list(self.graph_path), state_tokens=self.state_tokens,
                        cue="steer" if self.steer and cue is None else cue, answered=answered, gate=gate,
                        abstain_ok=g.abstain_allowed(gate, self.kind), nouls=self.nouls)


class FollowRequest(Frozen):
    """What the runtime gives `start_follow` (D8): the first reply, the message it answered, and who may speak up."""

    session: SessionContext
    first_id: str
    first_name: str
    first_message_id: str
    first_text: str
    message: str                                    # the user's message both replies answer
    candidates: list[str]
    cast: list[CharacterView] = []
    turn_index: int = 0
    base_faces: dict[str, str] = {}
    manual: bool = False
    turns_since: dict[str, int | None] = {}
    started_at: datetime                            # the first reply's stream end (doc 11 S5)
    documents: dict[str, list[str]] = {}            # M12 (rag D6): searchable sources' titles, by character
    message_id: str | None = None                   # M12: the user message both replies answer
    nouls: MessageNouls | None = None               # M12 (rag D8): the cast plan's answers for that message, reused


FollowOutcome = Literal["jev", "none", "below_floor", "late", "fallback", "cancelled"]


class FollowPlan(Frozen):
    """The follow plan's answer (G2): a second speaker or none, and the rows either way."""

    seed: str
    second: str | None
    outcome: FollowOutcome
    who: WhoPick | None = None
    faces: dict[str, PlannedFace] = {}
    face_rows: dict[str, dict[str, Any]] = {}
    shared_rows: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    graph_path: list[str] = []
    state_tokens: int = 0
    gates: dict[str, GateAnswer] = {}               # M12 (rag D8): "needs documents?" per follow candidate asked
    nouls: MessageNouls | None = None               # M12: the cast plan's, or this plan's own when it had to ask
    asked_nouls: bool = False                       # M12: this request asked them (the cast plan hadn't)

    def rows_for_first(self) -> list[dict[str, Any]]:
        """No second reply: the rows go on the first reply's trace (W1), every emotion row `not_used`, and every gate
        row this plan asked `not_used` too."""
        from horizon.ai.agent import gates as g

        rows = [*self.shared_rows, *({**r, "result": "not_used"} for r in self.face_rows.values())]
        rows += [g.gate_row(c, a, purpose="follow_plan", abstain_kind=True, result="not_used")
                 for c, a in self.gates.items() if a.outcome != "dropped"]
        return rows

    def for_speaker(self, cid: str, *, answered: str) -> TurnPlan:
        from horizon.ai.agent import gates as g

        rows = list(self.shared_rows)
        for other, row in self.face_rows.items():
            rows.append(row if other == cid else {**row, "result": "not_used"})
        gate = self.gates.get(cid)
        rows += g.speaker_rows(cid, self.gates, self.nouls if self.asked_nouls else None, purpose="follow_plan",
                               kind="second")
        return TurnPlan(seed=self.seed, kind="reply", branch="deep" if g.deep(gate) else "quick",
                        emotion=self.faces.get(cid), rows=rows, calls=list(self.calls),
                        graph_path=list(self.graph_path), state_tokens=self.state_tokens, cue="second",
                        answered=answered, gate=gate, abstain_ok=g.abstain_allowed(gate, "second"), nouls=self.nouls)


# ── The debate plan (M11: doc 08 V2, V3; doc 13 W5 row 11, W11; debate design D5, D6, D8, D27) ──
class DebateRequest(Frozen):
    """What the runtime gives `start_debate`: the slot, its eligible members in fixed order, and what they answer."""

    session: SessionContext
    phase: str
    iteration: int
    side: str | None                                # None: a panel
    candidates: list[str]                           # eligible (awake, not yet heard), fixed order
    cast: list[CharacterView] = []
    facts: DebateFacts
    latest: str = ""                                # the argument just made, "Name: text" (emotion_line's quoted_latest)
    turn_index: int = 0
    base_faces: dict[str, str] = {}
    manual: bool = False
    started_at: datetime                            # the `turn.end` it starts at
    documents: dict[str, list[str]] = {}            # M12 (rag D6): searchable sources' titles, by character


DebateOutcome = Literal["jev", "below_floor", "late", "fallback", "single", "cancelled"]


class DebatePlan(Frozen):
    """The debate plan's answer: the member (fixed at the deadline), and each candidate's face when Jev's answer
    landed in time (else the fallback faces). `for_speaker` gives the argument its frozen `TurnPlan`."""

    seed: str
    member: str
    outcome: DebateOutcome
    who: WhoPick | None = None
    faces: dict[str, PlannedFace] = {}
    face_rows: dict[str, dict[str, Any]] = {}
    shared_rows: list[dict[str, Any]] = []          # the member row (none for a single candidate)
    calls: list[dict[str, Any]] = []
    graph_path: list[str] = []
    state_tokens: int = 0
    gates: dict[str, GateAnswer] = {}               # M12 (rag D8): used if back by the turn's start, else fallback

    def for_speaker(self, cid: str) -> TurnPlan:
        from horizon.ai.agent import gates as g

        rows = list(self.shared_rows)
        for other, row in self.face_rows.items():
            rows.append(row if other == cid else {**row, "result": "not_used"})
        gate = self.gates.get(cid)
        rows += g.speaker_rows(cid, self.gates, None, purpose="debate_plan", kind="debate")
        return TurnPlan(seed=self.seed, kind="reply", branch="deep" if g.deep(gate) else "quick",
                        emotion=self.faces.get(cid), rows=rows, calls=list(self.calls),
                        graph_path=list(self.graph_path), state_tokens=self.state_tokens, gate=gate)


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

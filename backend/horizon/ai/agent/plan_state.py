"""What Jev call 1 sees: the `turn_plan` state (docs/ai/05 X9 with doc 11 S6's `quoted_*` names; doc 07 G9; persona-
context design D22; conversation-context "The turn-plan state").

A pure builder with no runtime caller until M9's `TurnPlanner`, which imports it from here.
- Only what the plan's questions need (doc 01 A3 rule 6). Every top-level field holding text written by the user, a
  character or a document is `quoted_*`, and everything nested in it is quoted text (S6).
- Numbers become labels in code (A3 rule 7): "not yet", "just now", "1 turn ago", "n turns ago".
- **No energy** (G9): code applies energy; `eligible_candidates` drops exhausted and muted characters first.
- **At most 2,000 tokens** (`count_tokens`), cut in X9's order: document titles past 5, `about` to 30, the oldest
  recent lines (keeping 3), the latest message to 300; M13 (memory D28, the user's U2): a debate then cuts each
  candidate's latest argument to 30 words and the last opposing argument to 120 tokens; only then the candidates last
  in speaking order lose their per-candidate gate questions (reported in `dropped_gates`, never removed from the
  cast).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from horizon.ai.contexts import SessionContext
from horizon.domain.pricing import count_tokens

LIMIT = 2000
ABOUT_MAX = 60
ABOUT_CUT = 30
TITLE_MAX = 20
TITLES_MAX = 10
TITLES_CUT = 5
LATEST_MAX = 600            # first 450 + last 150
LATEST_CUT = 300
LINE_MAX = 300
RECENT = 6
RECENT_WATCH = 12
RECENT_KEEP = 3
ARGUMENT_WORDS = 60
ARGUMENT_WORDS_CUT = 30      # M13 (memory D28, the user's U2): a long debate cuts its arguments before its gates
OPPOSING_CUT = 120           # tokens
_FIRST_SENTENCE = re.compile(r"(?<=[.!?。！？])\s")


class Candidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    role: str = ""
    about_source: str = ""          # the profile's personality summary; its first sentence becomes `about`
    face: str = "neutral"
    turns_since: int | None = None  # None: hasn't spoken in this session


class DebateInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    motion: str
    phase: str
    side: str | None = None
    last_opposing: str = ""
    latest_by_candidate: dict[str, str] = Field(default_factory=dict)


class PlanStateInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: str
    user_name: str = ""
    candidates: list[Candidate]
    documents: dict[str, list[str]] = Field(default_factory=dict)
    latest: str = ""
    recent: list[dict[str, str]] = Field(default_factory=list)   # [{speaker, text}], oldest first
    premise: str = ""
    summary: str = ""
    debate: DebateInput | None = None
    # M11 (debate design D6, D17): False leaves `last_spoke` out of every cast entry. Jev read the label as a fairness
    # cue (M10: `who_scene` picked the silent-longest on 75 of 100 items); the guard keeps fairness in code. The
    # default keeps every earlier state byte-identical.
    last_spoke: bool = True


class PlanState(BaseModel):
    model_config = ConfigDict(frozen=True)

    state: dict[str, Any]
    tokens: int
    dropped_gates: list[str] = Field(default_factory=list)


def last_spoke_label(turns_since: int | None) -> str:
    if turns_since is None:
        return "not yet"
    if turns_since <= 0:
        return "just now"
    return "1 turn ago" if turns_since == 1 else f"{turns_since} turns ago"


def cut_tokens(text: str, limit: int) -> str:
    """At most `limit` tokens, cut at a character (by UTF-8 bytes / 3, as `count_tokens`)."""
    if count_tokens(text) <= limit:
        return text
    budget, used, out = limit * 3 - 3, 0, []
    for ch in text:
        used += len(ch.encode("utf-8"))
        if used > budget:
            break
        out.append(ch)
    return "".join(out).rstrip() + "…"


def head_tail(text: str, limit: int, head: int, tail: int) -> str:
    """X9's latest message: over `limit`, the first `head` and the last `tail` tokens."""
    if count_tokens(text) <= limit:
        return text
    data = text.encode("utf-8")
    return (data[:head * 3].decode("utf-8", errors="ignore") + " … "
            + data[-tail * 3:].decode("utf-8", errors="ignore"))


def first_sentence(text: str) -> str:
    return _FIRST_SENTENCE.split(text.strip(), maxsplit=1)[0] if text.strip() else ""


def words(text: str, n: int) -> str:
    w = text.split()
    return text if len(w) <= n else " ".join(w[:n]) + " …"


def eligible_candidates(ctx: SessionContext, est_points: float, ids: Sequence[str] | None = None) -> list[str]:
    """G9: muted and exhausted characters are never candidates; energy itself never reaches Jev."""
    return [p.character_id for p in ctx.participants
            if (ids is None or p.character_id in ids) and not p.muted
            and float(p.energy.get("current", 0)) >= est_points]


def _state(inp: PlanStateInput, *, titles: int, about: int, recent_n: int, latest: int,
           arg_words: int = ARGUMENT_WORDS, opposing: int | None = None) -> dict[str, Any]:
    cast = [{"name": c.name, "role": c.role, "about": cut_tokens(first_sentence(c.about_source), about), "face": c.face,
             **({"last_spoke": last_spoke_label(c.turns_since)} if inp.last_spoke else {})} for c in inp.candidates]
    state: dict[str, Any] = {"mode": inp.mode, "quoted_user": inp.user_name or "the user", "quoted_cast": cast}
    docs = {c.name: [cut_tokens(t, TITLE_MAX) for t in inp.documents.get(c.id, [])[:titles]]
            for c in inp.candidates if inp.documents.get(c.id)}
    if docs:
        state["quoted_documents"] = docs
    if inp.latest:
        state["quoted_latest"] = (head_tail(inp.latest, LATEST_MAX, 450, 150) if latest >= LATEST_MAX
                                  else cut_tokens(inp.latest, latest))
    lines = inp.recent[-recent_n:] if recent_n else []
    state["quoted_recent"] = [{"speaker": r.get("speaker", ""), "text": cut_tokens(r.get("text", ""), LINE_MAX)}
                              for r in lines]
    if inp.mode == "watch":
        if inp.premise:
            state["quoted_premise"] = inp.premise
        if inp.summary:
            state["quoted_summary"] = inp.summary
    if inp.debate is not None:
        d = inp.debate
        state["phase"] = d.phase
        if d.side:
            state["side"] = d.side
        state["quoted_motion"] = d.motion
        state["quoted_arguments"] = {
            "last_opposing": cut_tokens(d.last_opposing, opposing) if opposing is not None else d.last_opposing,
            "latest_by_candidate": {c.name: words(d.latest_by_candidate[c.id], arg_words)
                                    for c in inp.candidates if d.latest_by_candidate.get(c.id)}}
    return state


def _tokens(state: Mapping[str, Any]) -> int:
    return count_tokens(json.dumps(state, ensure_ascii=False))


def build_turn_plan_state(inp: PlanStateInput, *, cut_arguments: bool = True, reserve: int = 0) -> PlanState:
    """The state, cut in X9's order until it fits 2,000 tokens. `cut_arguments=False` is M12's order (the measurement
    of D28 only). M14 (safety D4, U4): `reserve` tokens are kept for a moderator's or director's note the caller adds
    as `quoted_note`, which is never cut (arguments go first)."""
    limit = LIMIT - max(0, reserve)
    recent_n = RECENT_WATCH if inp.mode == "watch" else RECENT
    knobs: dict[str, Any] = {"titles": TITLES_MAX, "about": ABOUT_MAX, "recent_n": recent_n, "latest": LATEST_MAX}
    state = _state(inp, **knobs)
    steps: list[dict[str, Any]] = [{"titles": TITLES_CUT}, {"about": ABOUT_CUT}]
    steps += [{"recent_n": n} for n in range(min(recent_n, len(inp.recent)) - 1, RECENT_KEEP - 1, -1)]
    steps.append({"latest": LATEST_CUT})
    if inp.debate is not None and cut_arguments:   # M13 (memory D28, U2): arguments cut before any gate drops
        steps += [{"arg_words": ARGUMENT_WORDS_CUT}, {"opposing": OPPOSING_CUT}]
    for step in steps:
        if _tokens(state) <= limit:
            break
        knobs.update(step)
        state = _state(inp, **knobs)
    dropped: list[str] = []
    # least recently spoken first (never spoken, then longest ago): the end of this list spoke most recently
    order = sorted(inp.candidates, key=lambda c: (c.turns_since is not None, -(c.turns_since or 0)))
    # still over: the candidates furthest down the last-spoke order lose their gates (and their document titles)
    reduced = inp
    while _tokens(state) > limit and len(dropped) < len(order):
        victim = order[-(len(dropped) + 1)]
        dropped.append(victim.id)
        reduced = reduced.model_copy(update={"documents": {k: v for k, v in reduced.documents.items() if k != victim.id}})
        state = _state(reduced, **knobs)
    return PlanState(state=state, tokens=_tokens(state), dropped_gates=dropped)

"""What a pause run reads: the stretch (docs/ai/09 M2; memory design D9, D12; long-term-memory "A run reads only settled
lines once", "Below the minimum nothing moves").

`build_stretch` is pure over a read snapshot:
- **The settled bound:** messages with `seq` in (`memory_seq`, `upto`], where `upto` is the first still-streaming
  message's `seq` − 1 (a user line sent while a character streams never lets the checkpoint pass that reply).
- **The lines kept:** user and character messages, complete, the active variant (`content`). Never interrupted,
  failed or blocked replies (a later Continue makes them complete; doc 09 M7 then reads them again), never notes,
  narration, recaps, verdict prose, host lines or watch `direction` notes (not heard in the scene).
- **Labels:** the user as the You card's name; debate `steer` / `interject` as "Moderator (the user)"; a character by
  name, with the argument's phase in a debate.
- **The header:** a debate's motion, sides and verdict; watch's premise.
- **Context:** the 6 kept lines before each piece, "already processed, context only".
- **Re-reads:** each `memory_reread` message still complete, with the two lines before it, riding the first piece.
- **Pieces:** past `pieceTokens` (8,000) the lines are cut at message boundaries; each piece commits its own checkpoint.
- **The minimum:** at least one line the user said in the scene, or at least 4 character lines; else no piece (an
  ended session still advances: the caller does that).
- **Flagged talk** (M14, safety D16; doc 11 S7): `flagged` user lines (their steer or care cue was on, the care stay
  included) are dropped before anything else, with the replies to them: in 1:1 and group, the character lines up to
  the next user line; in debate and watch, the one reply that answered it. They are no numbered line, no context line
  and no re-read; the minimum counts what is left (the caller still moves the checkpoint past them).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from horizon.ai.ports import MemoryOp
from horizon.domain.pricing import count_tokens
from horizon.services.memory.block import ListedMemory

CONTEXT_LINES = 6
REREAD_CONTEXT = 2
MIN_CHARACTER_LINES = 4
MODERATOR = "Moderator (the user)"
USER_KINDS = frozenset({"chat", "steer", "interject"})   # what the user says in the scene (never `direction`)
MODERATOR_KINDS = frozenset({"steer", "interject"})


@dataclass(frozen=True)
class StretchLine:
    """One numbered line. `n` is what the model writes as `source`; code maps it back."""

    n: int
    message_id: str
    variant_id: str | None
    seq: int
    speaker: str
    text: str
    author: str                    # user | character
    character_id: str | None = None
    reread: bool = False


@dataclass(frozen=True)
class Present:
    """A character present. `n` is the number the model uses for `for` and `about`."""

    n: int
    character_id: str
    name: str
    role: str
    memories: list[ListedMemory] = field(default_factory=list)   # m1…: the same lines as its prompt block
    about: str = ""                # the profile's personality summary (importance's quoted_about, D14)


@dataclass(frozen=True)
class Stretch:
    session_id: str
    world_id: str
    world_name: str
    user_name: str
    mode: str                      # one_on_one | group | debate | watch: every draft's `source_mode`
    header: str
    context: list[str]             # "Name: text", context only
    lines: list[StretchLine]
    present: list[Present]
    from_seq: int
    upto_seq: int
    reread_ids: list[str]
    reread_context: dict[str, list[str]] = field(default_factory=dict)   # message id → its two earlier lines


@dataclass(frozen=True)
class WriterResult:
    ops: dict[str, list[MemoryOp]] = field(default_factory=dict)            # by character id
    vectors: dict[str, dict[str, list[float]]] = field(default_factory=dict)   # draft text → {space id: vector}
    touched: list[str] = field(default_factory=list)                        # recall-used memories to Touch (D35)
    log: list[dict[str, Any]] = field(default_factory=list)                  # what was dropped, and why
    failed: bool = False           # the call failed after its retry: no ops, a try is counted


@dataclass(frozen=True)
class Msg:
    """A message row as the builder needs it."""

    id: str
    seq: int
    author_type: str               # user | character | host | system
    character_id: str | None
    kind: str
    content: str
    status: str
    variant_id: str | None
    phase: str | None = None       # a debate argument's phase


def settled_upto(msgs: list[Msg]) -> int:
    """The last `seq` before the first still-streaming message (or the last `seq`)."""
    ordered = sorted(msgs, key=lambda m: m.seq)
    for m in ordered:
        if m.status == "streaming":
            return m.seq - 1
    return ordered[-1].seq if ordered else 0


def heard(m: Msg) -> bool:
    if m.status != "complete" or not m.content.strip():
        return False
    if m.author_type == "user":
        return m.kind in USER_KINDS
    return m.author_type == "character" and m.kind == "chat"


def label(m: Msg, names: dict[str, str], user_name: str, mode: str) -> str:
    if m.author_type == "user":
        return MODERATOR if m.kind in MODERATOR_KINDS else user_name
    name = names.get(m.character_id or "", m.character_id or "someone")
    return f"{name} ({m.phase})" if mode == "debate" and m.phase else name


def _line_text(speaker: str, text: str) -> str:
    return f"{speaker}: {' '.join(text.split())}"


def unflagged(kept: list[Msg], flagged: frozenset[str], mode: str) -> list[Msg]:
    """M14 (D16): `kept` without the flagged user lines and the replies to them."""
    if not flagged:
        return kept
    out: list[Msg] = []
    dropping = 0   # character lines still to drop after a flagged user line (-1: up to the next user line)
    for m in kept:
        if m.author_type == "user":
            dropping = 0
            if m.id in flagged:
                dropping = -1 if mode in ("one_on_one", "group") else 1
                continue
        elif dropping:
            dropping = dropping - 1 if dropping > 0 else -1
            continue
        out.append(m)
    return out


def build_stretch(*, session_id: str, world_id: str, world_name: str, user_name: str, mode: str, header: str,
                  msgs: list[Msg], from_seq: int, reread_ids: list[str], present: list[Present],
                  names: dict[str, str], piece_tokens: int,
                  flagged: frozenset[str] = frozenset()) -> tuple[list[Stretch], int]:
    """The pieces to run, and the settled bound. No pieces: below the minimum (or nothing new)."""
    upto = settled_upto(msgs)
    if upto <= from_seq and not reread_ids:
        return [], max(upto, from_seq)
    kept = unflagged(sorted([m for m in msgs if heard(m)], key=lambda m: m.seq), flagged, mode)
    new = [m for m in kept if from_seq < m.seq <= upto]
    by_id = {m.id: m for m in kept}
    rereads = [by_id[i] for i in reread_ids if i in by_id and by_id[i].seq <= upto]
    said = [m for m in [*new, *rereads] if m.author_type == "user"]
    spoken = [m for m in [*new, *rereads] if m.author_type == "character"]
    if not said and len(spoken) < MIN_CHARACTER_LINES:
        return [], upto
    # pieces of new lines, cut at message boundaries
    groups: list[list[Msg]] = []
    cur: list[Msg] = []
    used = 0
    for m in new:
        cost = count_tokens(_line_text(label(m, names, user_name, mode), m.content)) + 2
        if cur and used + cost > piece_tokens:
            groups.append(cur)
            cur, used = [], 0
        cur.append(m)
        used += cost
    if cur or not groups:
        groups.append(cur)
    pieces: list[Stretch] = []
    start = from_seq
    for i, group in enumerate(groups):
        lines: list[StretchLine] = []
        n = 0
        first_seq = group[0].seq if group else upto + 1
        context = [_line_text(label(m, names, user_name, mode), m.content)
                   for m in [k for k in kept if k.seq < first_seq][-CONTEXT_LINES:]]
        if i == 0:
            for r in rereads:
                n += 1
                lines.append(StretchLine(n=n, message_id=r.id, variant_id=r.variant_id, seq=r.seq,
                                         speaker=label(r, names, user_name, mode), text=r.content.strip(),
                                         author=r.author_type, character_id=r.character_id, reread=True))
        for m in group:
            n += 1
            lines.append(StretchLine(n=n, message_id=m.id, variant_id=m.variant_id, seq=m.seq,
                                     speaker=label(m, names, user_name, mode), text=m.content.strip(),
                                     author=m.author_type, character_id=m.character_id))
        end = group[-1].seq if i < len(groups) - 1 else max(upto, from_seq)
        pieces.append(Stretch(session_id=session_id, world_id=world_id, world_name=world_name, user_name=user_name,
                              mode=mode, header=header, context=context, lines=lines, present=present,
                              from_seq=start, upto_seq=end,
                              reread_ids=[r.id for r in rereads] if i == 0 else [],
                              reread_context={r.id: reread_context(msgs, r, names, user_name, mode) for r in rereads}
                              if i == 0 else {}))
        start = end
    return pieces, upto


def flagged_lines(user_lines: list[tuple[str, str]], stored: dict[str, Any]) -> frozenset[str]:
    """M14 (D16, D7): the user lines whose cue was on, from their stored answers: steered, or answered with care (its
    own yes, or one of the 2 chat lines before it). `user_lines` are (id, kind) in order; a line with no stored answer
    counts as no."""
    out: set[str] = set()
    chat: list[str] = []
    for mid, kind in user_lines:
        s = stored.get(mid)
        if kind == "chat":
            chat.append(mid)
            care = any(stored.get(x) is not None and stored[x].care for x in chat[-3:])
            if care or (s is not None and s.steer):
                out.add(mid)
        elif s is not None and s.steer:
            out.add(mid)
    return frozenset(out)


def reread_context(msgs: list[Msg], target: Msg, names: dict[str, str], user_name: str, mode: str) -> list[str]:
    """The two kept lines before a re-read message (doc 09 M2)."""
    kept = sorted([m for m in msgs if heard(m) and m.seq < target.seq], key=lambda m: m.seq)
    return [_line_text(label(m, names, user_name, mode), m.content) for m in kept[-REREAD_CONTEXT:]]


def debate_header(config: dict[str, Any], sides: dict[str, list[str]], verdict: dict[str, Any] | None) -> str:
    lines = [f"Debate motion: {config.get('motion', '')}"]
    for side, label_ in (("prop", "For"), ("opp", "Against")):
        if sides.get(side):
            lines.append(f"{label_}: {', '.join(sides[side])}")
    if verdict:
        stronger = verdict.get("strongerCase")
        if stronger in ("prop", "opp"):
            lines.append(f"Verdict: the {'For' if stronger == 'prop' else 'Against'} side made the stronger case.")
        elif verdict.get("decidedBy") == "none" or stronger is None:
            lines.append("Verdict: no winner was named.")
    return "\n".join(lines)


def watch_header(config: dict[str, Any]) -> str:
    premise = str(config.get("premise") or "").strip()
    return f"Scene premise: {premise}" if premise else ""

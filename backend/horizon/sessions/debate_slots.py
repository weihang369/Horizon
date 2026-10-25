"""A debate phase as slots (M11; doc 08 V1, V3, V5; debate design D3, D4; session-modes "Debate phases", "A side with
nobody awake pauses the debate").

A phase is a list of slots: two-sided debates alternate sides by today's interleaving (one slot per member, 2 v 1 runs
P, O, P); a panel has one slot per panellist (side `None`). Each slot is filled when it comes up, by a member of its
side who is awake and not yet heard in this phase-iteration. Debate ignores mute, as it always has.

Everything here is pure and read from the stored log, so an idle release, a fork or a restart rebuilds the same cursor:
the phase starts at its `ROUND n · …` banner; since then each argument (a character `chat` message that isn't an Ask
answer) and each skip note uses one slot, and "heard" is the set of argument authors.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

Wire = dict[str, Any]
SKIP_SUFFIX = " is asleep, skipping."
SIDE_NAME = {"prop": "Proposition", "opp": "Opposition"}


def two_sided(cfg: Mapping[str, Any]) -> bool:
    return cfg.get("format") == "two_sided" and bool(cfg.get("sides"))


def phase_slots(cfg: Mapping[str, Any], cast: Sequence[str]) -> list[str | None]:
    """The side of each slot in a phase (`None` for a panel's)."""
    if not two_sided(cfg):
        return [None] * len(cast)
    sides = cfg["sides"]
    prop, opp = list(sides.get("prop") or []), list(sides.get("opp") or [])
    out: list[str | None] = []
    for i in range(max(len(prop), len(opp))):
        if i < len(prop):
            out.append("prop")
        if i < len(opp):
            out.append("opp")
    return out


def members(cfg: Mapping[str, Any], cast: Sequence[str], side: str | None) -> list[str]:
    """A side's members in fixed order (a panel: the cast order)."""
    if side is None or not two_sided(cfg):
        return list(cast)
    return list(cfg["sides"].get(side) or [])


def is_banner(m: Mapping[str, Any]) -> bool:
    return (m["author"]["type"] == "system" and m.get("kind") == "system_note"
            and str(m.get("content", "")).startswith("ROUND "))


def is_argument(m: Mapping[str, Any]) -> bool:
    return m["author"]["type"] == "character" and m.get("kind") == "chat" and not m.get("forcedSpeaker")


def is_skip(m: Mapping[str, Any]) -> bool:
    return (m["author"]["type"] == "system" and bool(m.get("targetCharacterId"))
            and str(m.get("content", "")).endswith(SKIP_SUFFIX))


@dataclass(frozen=True)
class Cursor:
    """Where a phase stands: the next slot's index, who has been heard, and the arguments since the banner."""

    used: int
    heard: tuple[str, ...]
    start_seq: int


def cursor(messages: Sequence[Mapping[str, Any]]) -> Cursor:
    """The current phase's cursor, from the log (messages in seq order)."""
    start = 0
    for m in messages:
        if is_banner(m):
            start = int(m["seq"])
    used, heard = 0, []
    for m in messages:
        if int(m["seq"]) <= start:
            continue
        if is_argument(m):
            used += 1
            cid = str(m["author"].get("characterId"))
            if cid not in heard:
                heard.append(cid)
        elif is_skip(m):
            used += 1
    return Cursor(used=used, heard=tuple(heard), start_seq=start)


Action = Literal["speak", "skip", "pause"]


@dataclass(frozen=True)
class Fill:
    """What a slot does: `speak` (who, and the members still eligible, fixed order), `skip` (whose note), or `pause`
    (every asleep member of the side)."""

    action: Action
    who: str | None = None
    eligible: tuple[str, ...] = ()
    asleep: tuple[str, ...] = ()


def fill(side_members: Sequence[str], heard: Sequence[str], awake: Mapping[str, bool]) -> Fill:
    """V3 and V5: the eligible are awake and not yet heard. With some, the first in fixed order speaks (the debate plan
    may pick another). With none but someone awake, the slot is skipped with the first asleep unheard member's note
    (the side has been heard). With nobody awake, the debate pauses on this slot."""
    eligible = tuple(c for c in side_members if c not in heard and awake.get(c, False))
    if eligible:
        return Fill("speak", who=eligible[0], eligible=eligible)
    asleep = tuple(c for c in side_members if not awake.get(c, False))
    if len(asleep) < len(side_members):
        unheard = [c for c in asleep if c not in heard]
        return Fill("skip", who=(unheard or list(asleep))[0] if asleep else None, asleep=asleep)
    return Fill("pause", asleep=asleep)


def missed_turns(messages: Sequence[Mapping[str, Any]], cfg: Mapping[str, Any], cast: Sequence[str]) -> dict[str, Wire]:
    """V5 / V8: per side, the slots of every reached phase-iteration minus its arguments, with why ("asleep" when the
    side had a skip or an asleep note there, else "the debate ended early"). Two-sided debates only."""
    if not two_sided(cfg):
        return {}
    slots = phase_slots(cfg, cast)
    per_side = {s: slots.count(s) for s in ("prop", "opp")}
    side_of = {c: s for s in ("prop", "opp") for c in (cfg["sides"].get(s) or [])}
    out: dict[str, Wire] = {s: {"missed": 0, "asleep": False} for s in ("prop", "opp")}
    segments: list[list[Mapping[str, Any]]] = []
    for m in messages:
        if is_banner(m):
            if "VERDICT" in str(m.get("content", "")):
                break
            segments.append([])
        elif segments:
            segments[-1].append(m)
    for seg in segments:
        spoke = {"prop": 0, "opp": 0}
        for m in seg:
            if is_argument(m):
                s = side_of.get(str(m["author"].get("characterId")))
                if s:
                    spoke[s] += 1
            elif m["author"]["type"] == "system" and m.get("targetCharacterId") and "is asleep" in str(m.get("content")):
                s = side_of.get(str(m["targetCharacterId"]))
                if s:
                    out[s]["asleep"] = True
        for s in ("prop", "opp"):
            out[s]["missed"] += max(0, per_side[s] - spoke[s])
    return {s: {"missed": v["missed"], "reason": "asleep" if v["asleep"] else "the debate ended early"}
            for s, v in out.items() if v["missed"]}


def missed_sentence(missed: Mapping[str, Wire]) -> str:
    """"Opposition: 2 turns missed, everyone on that side was asleep" (V5), one clause per side."""
    parts = []
    for s in ("prop", "opp"):
        if s in missed:
            n = int(missed[s]["missed"])
            why = "everyone on that side was asleep" if missed[s]["reason"] == "asleep" else "the debate ended early"
            parts.append(f"{SIDE_NAME[s]}: {n} turn{'s' if n != 1 else ''} missed, {why}")
    return "; ".join(parts)

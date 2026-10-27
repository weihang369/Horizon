"""The keep rule: which checked passages a reply gets, and what it is told (doc 10 K7; rag design D14; deep-turn "Code
keeps the passages by rule", "What each outcome does", "Jev call 2 failures fall back to the search order").

From each returned check: usable when `p_answers + p_partly ≥ t_keep`, found when `p_answers ≥ t_found`, ordered by
the weighted score `unit` (ties by the fused order).

| Outcome | When | Kept |
|---|---|---|
| found | a found passage, or a set check that said yes | the usable and the found ones, best first, at most k |
| partly | none found, some usable | up to k |
| not found | no usable passage, every check back (or the search found nothing) | none |
| fallback | Jev call 2 failed, or some checks missing and none found | the top k in search order, no scores |

What the reply gets (D8's abstain rule): found → the passages; partly → the passages, plus the partly line when
abstaining is allowed; not found → the not-found line at the quick length when abstaining is allowed, else a quick
reply; fallback → the passages, with no scores. Debate, watch, Next speaker and Step in never abstain.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

Outcome = Literal["found", "partly", "not_found", "fallback"]


@dataclass(frozen=True)
class Checked:
    """One candidate after Jev call 2. `p_answers` / `p_partly` are None when its check is missing (late, 429,
    failed)."""

    rid: int
    order: int                      # the search's (MMR) order
    p_answers: float | None = None
    p_partly: float | None = None
    unit: float | None = None       # Σ k·p_k / 2, W11's scale

    @property
    def back(self) -> bool:
        return self.p_answers is not None and self.p_partly is not None


@dataclass(frozen=True)
class Kept:
    outcome: Outcome
    kept: list[int]                 # rids, best first, at most k
    usable: list[int]               # every usable rid, best first (the set check reads these)
    abstain: bool                   # the reply says the documents don't cover it (not found, abstain allowed)
    partly_line: bool               # the partly line rides after the passages


def usable(c: Checked, t_keep: float) -> bool:
    return c.back and (c.p_answers or 0.0) + (c.p_partly or 0.0) >= t_keep


def found(c: Checked, t_found: float) -> bool:
    return c.back and (c.p_answers or 0.0) >= t_found


def best_first(cs: Sequence[Checked]) -> list[Checked]:
    return sorted(cs, key=lambda c: (-(c.unit or 0.0), c.order))


def needs_set_check(checked: Sequence[Checked], *, t_keep: float, t_found: float) -> bool:
    """K6: one more request when no passage is found and two or more are usable."""
    return not any(found(c, t_found) for c in checked) and sum(usable(c, t_keep) for c in checked) >= 2


def keep(checked: Sequence[Checked], *, k: int, t_keep: float, t_found: float, set_yes: bool | None = None,
         abstain_ok: bool = False, failed: bool = False) -> Kept:
    """The outcome and the kept passages. `set_yes`: the set check's answer (None: not asked or missing); `failed`:
    Jev call 2 failed as a whole."""
    by_search = sorted(checked, key=lambda c: c.order)
    if failed:
        return Kept("fallback", [c.rid for c in by_search[:k]], [], False, False)
    if not checked:   # the search matched nothing in the speaker's documents: they don't cover it
        return Kept("not_found", [], [], abstain_ok, False)
    use = best_first([c for c in checked if usable(c, t_keep)])
    any_found = any(found(c, t_found) for c in checked)
    all_back = all(c.back for c in checked)
    if any_found or set_yes:
        # a found passage is kept even when it isn't usable (p_answers 0.6, p_partly 0.2): it answers the question
        keepers = best_first([c for c in checked if usable(c, t_keep) or found(c, t_found)])
        return Kept("found", [c.rid for c in keepers[:k]], [c.rid for c in use], False, False)
    if not all_back:
        # some missing and none found: never decide "not found" (or "partly") on partial evidence (K6)
        return Kept("fallback", [c.rid for c in by_search[:k]], [c.rid for c in use], False, False)
    if use:
        return Kept("partly", [c.rid for c in use[:k]], [c.rid for c in use], False, abstain_ok)
    return Kept("not_found", [], [], abstain_ok, False)

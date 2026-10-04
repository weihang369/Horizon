"""Cap predicates (doc backend/04 §3, NFR-07, budget-caps spec): pure, so the reservation book and tests share them.

A call is refused when spent + reserved + estimate would pass the cap. The warning fires once, as spend crosses
`cap × warnAtPct / 100` (`before < warn_at ≤ after`): no flag is stored, so it can never fire twice for one crossing.
"""

from __future__ import annotations

EPS = 1e-9  # float noise: a call landing exactly on the cap is allowed


def exceeds_daily(spent_today: float, reserved: float, estimate: float, cap: float) -> bool:
    return spent_today + reserved + estimate > cap + EPS


def exceeds_creation(creation_spent: float, reserved_for_character: float, estimate: float, cap: float) -> bool:
    return creation_spent + reserved_for_character + estimate > cap + EPS


def warn_at(cap: float, warn_at_pct: float) -> float:
    return cap * warn_at_pct / 100


def crossed(before: float, after: float, line: float) -> bool:
    """True exactly when this step moved spend across `line` (before < line ≤ after)."""
    return before < line - EPS and after >= line - EPS

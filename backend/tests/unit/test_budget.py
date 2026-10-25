"""Cap predicates (task 3.3, budget-caps "Daily cap", "Creation cap", "Warning on crossing")."""

from __future__ import annotations

import pytest

from horizon.domain import budget as b


def test_daily_cap() -> None:
    assert b.exceeds_daily(0.999, 0.0, 0.002, 1.0)
    assert not b.exceeds_daily(0.30, 0.30, 0.30, 1.0)
    assert b.exceeds_daily(0.30, 0.60, 0.30, 1.0)
    assert not b.exceeds_daily(0.7, 0.1, 0.2, 1.0)  # landing exactly on the cap (float noise included) is allowed


def test_creation_cap() -> None:
    assert b.exceeds_creation(0.59, 0.0, 0.018, 0.6)
    assert not b.exceeds_creation(0.5, 0.05, 0.018, 0.6)


@pytest.mark.parametrize(("before", "after", "fires"), [
    (0.79, 0.81, True),
    (0.81, 0.83, False),
    (0.79, 0.80, True),     # landing exactly on the line counts
    (0.80, 0.81, False),    # starting on the line already crossed it
    (0.10, 0.20, False),
])
def test_warning_on_crossing(before: float, after: float, fires: bool) -> None:
    assert b.crossed(before, after, b.warn_at(1.0, 80)) is fires


def test_creation_scope_line() -> None:
    line = b.warn_at(0.6, 80)
    assert line == pytest.approx(0.48)
    assert b.crossed(0.47, 0.488, line) and not b.crossed(0.49, 0.5, line)

"""Shared energy fixtures (energy spec): `domain/energy.py` must match `energy.ts` case for case."""

import json
import re
from pathlib import Path
from typing import Any

import pytest

from horizon.domain import energy as en
from horizon.domain.timeutil import ms_from_iso

FIXTURE = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "energy" / "cases.json").read_text("utf-8"))
TOL: float = FIXTURE["tolerance"]
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T")


def run(c: dict[str, Any]) -> Any:
    a = c["args"]
    e = a.get("energy")
    kw = {"est_reply_points": a.get("estReplyPoints"), "frozen": bool(a.get("frozen"))}
    fn = c["fn"]
    if fn == "pointsForCost":
        return en.points_for_cost(a["costUsd"], a["usdPerPoint"])
    if fn == "regenAt":
        return en.regen_at(e, ms_from_iso(a["now"]))
    if fn == "energyState":
        return en.energy_state(a["current"], a["max"], a["estReplyPoints"])
    if fn == "drain":
        return en.drain(e, a["points"], ms_from_iso(a["now"]), **kw)
    if fn == "topUp":
        return en.top_up(e, a["points"], ms_from_iso(a["now"]), **kw)
    if fn == "settle":
        return en.settle(e, ms_from_iso(a["now"]), **kw)
    if fn == "dayRoll":
        return en.day_roll(e, ms_from_iso(a["now"]), FIXTURE["dayUtcOffsetMin"])
    if fn == "canTopUp":
        return en.can_top_up(a)
    if fn == "withMax":
        return en.with_max(e, a["max"], ms_from_iso(a["now"]), **kw)
    if fn == "toWireEnergy":
        return en.to_wire_energy(e)
    raise AssertionError(f"unknown fn {fn}")


def match(actual: Any, expected: Any, at: str) -> None:
    if isinstance(expected, bool) or expected is None:
        assert actual == expected, at
    elif isinstance(expected, (int, float)):
        assert abs(actual - expected) <= TOL, f"{at}: {actual} vs {expected}"
    elif isinstance(expected, str) and ISO.match(expected):
        assert ms_from_iso(actual) == ms_from_iso(expected), at
    elif isinstance(expected, dict):
        for k, v in expected.items():
            match(actual.get(k), v, f"{at}.{k}")
    else:
        assert actual == expected, at


def test_every_function_has_cases() -> None:
    fns = {c["fn"] for c in FIXTURE["cases"]}
    for f in ("pointsForCost", "regenAt", "energyState", "drain", "topUp", "settle", "dayRoll", "canTopUp", "toWireEnergy", "withMax"):
        assert f in fns


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=[c["name"] for c in FIXTURE["cases"]])
def test_energy_case(case: dict[str, Any]) -> None:
    match(run(case), case["expected"], case["fn"])


def test_broken_threshold_fails_a_case(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(current: float, max_: float, est: float = 4) -> str:
        return "exhausted" if current <= est + 10 else ("tired" if current < max_ * 0.2 else "active")

    monkeypatch.setattr(en, "energy_state", broken)
    failures = 0
    for c in FIXTURE["cases"]:
        try:
            match(run(c), c["expected"], c["fn"])
        except AssertionError:
            failures += 1
    assert failures >= 1


def test_frozen_read_keeps_fullat_from_asof_and_floors() -> None:
    stored = {"max": 1000, "current": 920.7, "asOf": "2026-10-01T12:00:00.000Z", "regenPerHour": 1000 / 24, "spentToday": 80.4}
    later = ms_from_iso("2026-10-03T03:00:00.000Z")
    w = en.read_energy(stored, later, frozen=True, est_reply_points=8)
    assert w["current"] == 920 and w["spentToday"] == 80 and w["state"] == "active"
    assert w["fullAt"] == "2026-10-01T13:54:11.520Z"
    six = {**stored, "current": 6.0}
    assert en.read_energy(six, later, frozen=True, est_reply_points=8)["state"] == "exhausted"
    assert en.read_energy(six, later, frozen=True, est_reply_points=4)["state"] == "tired"


def test_with_max_drops_fullat_when_full() -> None:
    e = {"max": 1000, "current": 800, "asOf": "2026-10-01T04:00:00.000Z", "regenPerHour": 1000 / 24, "spentToday": 0,
         "fullAt": "2026-10-01T08:48:00.000Z"}
    out = en.with_max(e, 500, ms_from_iso("2026-10-01T04:00:00.000Z"), est_reply_points=4)
    assert "fullAt" not in out and out["current"] == 800

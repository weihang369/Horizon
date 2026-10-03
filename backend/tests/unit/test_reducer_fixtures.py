"""Shared reducer fixtures (D-79): the Python port must produce exactly what the TS reducer produces."""

import json
from pathlib import Path

import pytest

from horizon.services.runtime.reducer import apply_event, initial_runtime, ordered_messages, reduce_all

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "reducer"
CASES = sorted(FIXTURES.glob("*.json"))


def test_found_the_cases() -> None:
    assert len(CASES) >= 6


@pytest.mark.parametrize("path", CASES, ids=[p.stem for p in CASES])
def test_reducer_case(path: Path) -> None:
    case = json.loads(path.read_text(encoding="utf-8"))
    s = reduce_all(initial_runtime(case["session"]), case["events"])
    assert s["session"] == case["expected"]["session"]
    assert ordered_messages(s) == case["expected"]["messages"]


def test_apply_event_is_pure_and_ignores_stale() -> None:
    case = json.loads((FIXTURES / "insight-replacement.json").read_text(encoding="utf-8"))
    events = case["events"]
    before = json.dumps(events, sort_keys=True)
    s0 = initial_runtime(case["session"])
    s1 = apply_event(s0, events[0])
    assert s0["lastSeq"] == 0 and s1["lastSeq"] == events[0]["seq"]
    assert apply_event(s1, events[0]) is s1
    reduce_all(s0, events)
    assert json.dumps(events, sort_keys=True) == before

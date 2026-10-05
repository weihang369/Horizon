"""Fork and export against the shared fixtures generated from the TS code (session-event-sourcing "Fork is identical in
both languages"; session-lifecycle "Markdown export"; tasks 11.2, 11.5). Regenerate with `npm run fixtures:build`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from horizon.sessions.fork import fork_result

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SEED = Path(__file__).resolve().parents[3] / "seed" / "sessions"
FORKS = sorted((FIXTURES / "fork").glob("*.json"))


def _data(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))["data"]


def test_found_the_cases() -> None:
    assert len(FORKS) >= 4 and any("mid_stream" in p.stem for p in FORKS)


@pytest.mark.parametrize("path", FORKS, ids=lambda p: p.stem)
def test_fork_fixture(path: Path) -> None:
    case = json.loads(path.read_text(encoding="utf-8"))
    source = _data(SEED / case["source"] / "session.json")
    events = _data(SEED / case["source"] / "events.json")
    got = fork_result(events, source, case["atSeq"], case["newSessionId"], case["now"])
    assert got == case["expected"]
    if "mid_stream" in case["name"]:
        assert len(got["events"]) > len([e for e in events if e["seq"] <= case["atSeq"]])  # the cut was extended
        assert all(m["status"] != "streaming" for m in got["messages"])

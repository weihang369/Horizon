"""Demo replays play in recorded time (U-72): no shipped session may hold an hours-long gap between two events. The
U-62 re-record paused three scenes with POST /leave a story-day later, so Long Day's replay read 0:01 / 899:45 and the
seek bar sat at the start for the whole recording."""

from __future__ import annotations

import json
from datetime import datetime
from itertools import pairwise

from tests.conftest import SEED_DIR

MAX_GAP_S = 300   # the longest real pause in a recording is a reply or an image wait, well under a minute


def at(e: dict[str, object]) -> datetime:
    return datetime.fromisoformat(str(e["at"]).replace("Z", "+00:00"))


def test_no_seed_session_has_a_long_gap_between_events() -> None:
    files = sorted([*(SEED_DIR / "sessions").glob("*/events.json"), *(SEED_DIR / "_mock" / "sessions").glob("*/events.json")])
    assert len(files) >= 9
    for path in files:
        events = json.loads(path.read_text(encoding="utf-8"))["data"]
        for a, b in pairwise(events):
            gap = (at(b) - at(a)).total_seconds()
            assert gap <= MAX_GAP_S, f"{path.parent.name}: {gap:.0f} s before seq {b['seq']} ({b['type']})"

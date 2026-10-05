"""Static rules for the session runtime (session-runtime design D2 risks)."""

from __future__ import annotations

import re
from pathlib import Path

HORIZON = Path(__file__).resolve().parents[2] / "horizon"


def test_sessions_and_ai_spawn_only_through_the_runtime() -> None:
    """Background work in `sessions/` and `ai/` must hold an activity token, so it goes through `rt.spawn`."""
    offenders = []
    for pkg in ("sessions", "ai"):
        for p in (HORIZON / pkg).rglob("*.py"):
            text = p.read_text(encoding="utf-8")
            if re.search(r"\bcreate_task\s*\(|\bensure_future\s*\(", text):
                offenders.append(p.relative_to(HORIZON).as_posix())
    allowed = {"ai/decider.py"}  # M2's Decider tracks its request task with vclock.track
    assert sorted(set(offenders) - allowed) == []

"""The context budget (docs/ai/05 X1; persona-context design D16): each section's cap, and the planned input per mode
that `TurnTrace.context.budget` reports for both reply engines.

| section | cap (count_tokens) |
|---|---|
| the card (doc 04 P4) | 1,500 |
| the other fixed blocks: world, session, rules, S2 lines, and doc 09's memory list (≤ 1,000) | 1,720 |
| the rolling summary (X3) | 600 |
| the history window (X2) | per mode: 6,000 1:1, 9,000 otherwise |
| the tail: retrieval ≤ 1,400, recall ≤ 400, mood, hint, reminder and cue ≈ 60 | 1,860 |
"""

from __future__ import annotations

from collections.abc import Mapping

CARD = 1500
FIXED = 1720
SUMMARY = 600
TAIL = 1860
NOT_WINDOW = CARD + FIXED + SUMMARY + TAIL          # 5,680
WINDOWS: Mapping[str, int] = {"one_on_one": 6000, "group": 9000, "watch": 9000, "debate": 9000}   # X2's defaults


def planned_input(mode: str, windows: Mapping[str, int] | None = None) -> int:
    """X1: the sum of the caps, so 11,680 for 1:1 and 14,680 for group, watch and debate with X2's windows."""
    w = windows or WINDOWS
    return NOT_WINDOW + int(w.get(mode, w.get("group", WINDOWS["group"])))

"""The procedural theme song (generation-jobs design D9, D-83): a port of `themeSpecFromBrief` (`frontend/src/audio/synth/
spec.ts`), pinned by the shared fixtures in `tests/fixtures/theme_spec/`.

While OpenRouter lists no music model, a `song` job writes this `.proc.json` spec; the app renders it with WebAudio
(R-05, D-52). It costs nothing and has no audio `format`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

LICENSE_NOTE = "Procedural theme rendered in the app from the brief (D-83): no music model is available yet, so it costs nothing."
MODEL = "procedural"


def theme_spec_from_brief(seed: str, brief: Mapping[str, Any], title: str | None = None) -> dict[str, Any]:
    spec: dict[str, Any] = {"kind": "horizon.theme", "version": 1, "seed": seed}
    if title is not None:
        spec["title"] = title
    spec["brief"] = dict(brief)
    return spec


def theme_title(profile_name: str) -> str:
    """The mock's title: the first word of the name, then "'s Theme"."""
    return f"{profile_name.split(' ')[0]}'s Theme"


def duration_sec(bpm: float) -> float:
    """The mock's figure for 8 bars of 4 beats: `Math.round(((8 * 4 * 60) / bpm) * 10) / 10`."""
    n = math.floor((8 * 4 * 60) / bpm * 10 + 0.5) / 10
    return int(n) if float(n).is_integer() else n

"""The procedural theme song (generation-jobs design D9, D-83): a port of `themeSpecFromBrief` (`frontend/src/audio/synth/
spec.ts`), pinned by the shared fixtures in `tests/fixtures/theme_spec/`.

The scripted song generator writes this `.proc.json` spec, and so does a naive song job whose Lyria call failed
(creation-followups design D7, D-87); the app renders it with WebAudio (R-05, D-52). It costs nothing and has no audio
`format`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

LICENSE_NOTE = "Procedural theme rendered in the app from the brief (D-83): it costs nothing."
FALLBACK_NOTE = ("The music model was unavailable, so this is the procedural theme rendered in the app from the brief. "
                 "Regenerate to try again.")
MODEL = "procedural"
CLIP_SECONDS = 30.0   # a Lyria 3 Clip's length, used when the MP3's frames can't be read


def lyria_note(model: str) -> str:
    return f"Composed by {model} through OpenRouter (D-87)."


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

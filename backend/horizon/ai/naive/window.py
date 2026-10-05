"""The cache-friendly history window (doc 05 §5; ai-ports "Naive reply engine"; design D11).

The window holds the messages after the latest rolling summary. It grows until it passes `windowTokens`, then drops
its oldest half in one step, and the summary is refreshed at that boundary. Between drops the rendered history only
grows at the end, so the request prefix stays stable and the provider's prompt cache keeps hitting.

Pure functions: the session runtime applies the plan and stores the summary (ports never write rows).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from horizon.ai.contexts import MessageView
from horizon.domain.pricing import count_tokens


@dataclass(frozen=True)
class WindowPlan:
    window: list[MessageView]
    dropped: list[MessageView]
    upto_seq: int | None          # the new summary boundary, when the window dropped its oldest half


def plan_window(messages: Sequence[MessageView], upto_seq: int, window_tokens: int) -> WindowPlan:
    current = [m for m in messages if m.seq > upto_seq]
    if sum(count_tokens(m.content) for m in current) <= window_tokens or len(current) < 2:
        return WindowPlan(current, [], None)
    half = len(current) // 2
    dropped = current[:half]
    return WindowPlan(current[half:], dropped, dropped[-1].seq)


def summary_lines(dropped: Sequence[MessageView]) -> list[str]:
    return [f"{m.name}: {m.content}" for m in dropped if m.content]


def render_history(window: Sequence[MessageView], speaker_id: str, you: str = "User") -> list[dict[str, Any]]:
    """The speaker's own lines as `assistant`; everyone else's as `user`, prefixed with their name."""
    out: list[dict[str, Any]] = []
    for m in window:
        if not m.content:
            continue
        if m.author_type == "character" and m.character_id == speaker_id:
            out.append({"role": "assistant", "content": m.content})
        elif m.author_type == "user":
            out.append({"role": "user", "content": f"{you}: {m.content}"})
        elif m.author_type == "character":
            out.append({"role": "user", "content": f"{m.name}: {m.content}"})
        else:
            out.append({"role": "user", "content": f"[{m.kind.replace('_', ' ')}] {m.content}"})
    return out

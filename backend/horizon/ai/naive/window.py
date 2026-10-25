"""The cache-friendly history window (docs/ai/05 X2; ai-ports "Naive reply engine"; conversation-context "History
windows per mode"; design D11, persona-context D8).

The window holds the messages after the latest rolling summary. It grows until it passes its mode's `windowTokens`;
then the newest messages totalling at most HALF the size are kept (at least the newest two) and everything older is
folded into the summary, in one step, by the session's summary task after `turn.end`. Between drops the rendered
history only grows at the end, so the request prefix stays stable and the provider's prompt cache keeps hitting.

Pure functions: the session runtime runs the plan and stores the summary (ports never write rows).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from horizon.ai.contexts import MessageView
from horizon.domain.pricing import count_tokens

KEEP_AT_LEAST = 2


@dataclass(frozen=True)
class WindowPlan:
    window: list[MessageView]
    dropped: list[MessageView]
    upto_seq: int | None          # the new summary boundary, when the window drops


def plan_window(messages: Sequence[MessageView], upto_seq: int, window_tokens: int) -> WindowPlan:
    """X2: over `window_tokens`, keep the newest messages within half of it (at least two) and drop the rest."""
    current = [m for m in messages if m.seq > upto_seq]
    if sum(count_tokens(m.content) for m in current) <= window_tokens or len(current) <= KEEP_AT_LEAST:
        return WindowPlan(current, [], None)
    keep, used = 0, 0
    for m in reversed(current):
        cost = count_tokens(m.content)
        if keep >= KEEP_AT_LEAST and used + cost > window_tokens // 2:
            break
        keep += 1
        used += cost
    dropped = current[:len(current) - keep]
    if not dropped:
        return WindowPlan(current, [], None)
    return WindowPlan(current[len(current) - keep:], dropped, dropped[-1].seq)


def ceiling(messages: Sequence[MessageView], limit: int) -> list[MessageView]:
    """X2's hard ceiling (persona-context D10): the newest messages within `limit` tokens, at least the newest two."""
    out: list[MessageView] = []
    used = 0
    for m in reversed(messages):
        cost = count_tokens(m.content)
        if len(out) >= KEEP_AT_LEAST and used + cost > limit:
            break
        out.append(m)
        used += cost
    return out[::-1]


def summary_lines(dropped: Sequence[MessageView], you: str = "User") -> list[str]:
    """X3's summariser input: one `Name: line` per line of each message (a reply shown as bubbles becomes several),
    the user by their You-card name, notes and narration as `[kind] line`."""
    from horizon.ai.agent.turn import clip  # X8: the same per-message limit as the prompt

    out: list[str] = []
    for m in dropped:
        if not m.content:
            continue
        prefix = (f"{you}: " if m.author_type == "user" else f"{m.name}: " if m.author_type == "character"
                  else f"[{m.kind.replace('_', ' ')}] ")
        out += [prefix + line for line in clip(m.content).split("\n") if line.strip()]
    return out


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

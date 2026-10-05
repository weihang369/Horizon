"""Rejections before 202 (session-runtime design D4; http-api "Session command routes"): a port of the MockClient's
`live()` / `liveSession()` / `command()` wrappers.

- **Generating commands** (`live()` in the mock) need a usable key (400 `missing_key` / 401 `invalid_key`) and the
  daily cap not reached (402 `daily_budget_exceeded`).
- **Every command** is refused for a seed session (409) or an ended one (409), and a debate (watch) command in a session
  of another mode (409). Empty text is 422.
- **`liveSession()`** (send, regenerate, everyone-answer, next-speaker, debate resume/next/ask, watch play/step/step-in)
  also refuses while another session is generating (409 + `details.activeSessionId`), and resumes a paused 1:1 or group
  session first (`session.resumed`), unless it is paused by the daily cap and the cap is still reached (402).

Energy exhaustion is never a rejection: it arrives later as a skip, or a "{name} is asleep" note + `energy_exhausted`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from horizon.api.errors import HorizonHTTPError, conflict, validation

if TYPE_CHECKING:
    from horizon.sessions.actor import SessionActor
    from horizon.sessions.manager import LiveSessionManager


@dataclass(frozen=True)
class Rule:
    generating: bool = False       # key + cap (the mock's `live`)
    live_session: bool = False     # another-live-session check + auto-resume (the mock's `liveSession`)
    mode: str | None = None        # "debate" / "watch" commands only
    text: bool = False             # the body's text must not be empty


# Command name → its rule. Names follow the route path after /sessions/{id}/.
COMMANDS: dict[str, Rule] = {
    # chat
    "send": Rule(generating=True, live_session=True, text=True),
    "stop": Rule(),
    "regenerate": Rule(generating=True, live_session=True),
    "set-emotion": Rule(),
    "set-emotion-mode": Rule(),
    "set-responder-policy": Rule(),
    "set-music-policy": Rule(),
    "set-readable-mode": Rule(),
    "everyone-answer": Rule(generating=True, live_session=True),
    "next-speaker": Rule(generating=True, live_session=True),
    "mute": Rule(),
    # debate
    "debate/pause": Rule(mode="debate"),
    "debate/resume": Rule(generating=True, live_session=True, mode="debate"),
    "debate/next": Rule(generating=True, live_session=True, mode="debate"),
    "debate/auto-advance": Rule(mode="debate"),
    "debate/ask": Rule(generating=True, live_session=True, mode="debate", text=True),
    "debate/interject": Rule(mode="debate", text=True),
    "debate/extend-round": Rule(generating=True, mode="debate"),
    "debate/skip-to-closing": Rule(mode="debate"),
    "debate/end": Rule(mode="debate"),            # generating only with `withVerdict: true` (see `rule_for`)
    "debate/pick": Rule(mode="debate"),
    # watch
    "watch/play": Rule(generating=True, live_session=True, mode="watch"),
    "watch/pause": Rule(mode="watch"),
    "watch/step": Rule(generating=True, live_session=True, mode="watch"),
    "watch/pace": Rule(mode="watch"),
    "watch/direct": Rule(mode="watch", text=True),
    "watch/step-in": Rule(generating=True, live_session=True, mode="watch", text=True),
    "watch/extend": Rule(generating=True, mode="watch"),
    "watch/summarise": Rule(generating=True, mode="watch"),
}


def rule_for(command: str, *, with_verdict: bool = False) -> Rule:
    r = COMMANDS[command]
    if command == "debate/end" and with_verdict:
        return Rule(generating=True, mode="debate")
    return r


def check_text(text: str | None) -> None:
    if text is None or not text.strip():
        raise validation("Text can't be empty.", {"field": "text"})


def key_problem(status: str) -> HorizonHTTPError | None:
    if status == "missing":
        return HorizonHTTPError("missing_key", "Add your OpenRouter key in Settings to go live.")
    if status == "invalid":
        return HorizonHTTPError("invalid_key", "Your OpenRouter key was rejected. Check it in Settings.")
    return None


def cap_problem() -> HorizonHTTPError:
    return HorizonHTTPError("daily_budget_exceeded", "Today's spending cap is reached. Raise it in Settings or wait until tomorrow.")


async def check_generating(manager: LiveSessionManager, key_status: str) -> None:
    """The mock's `live()`: a usable key, and the daily cap not reached."""
    problem = key_problem(key_status)
    if problem is not None:
        raise problem
    if await manager.cap_blocked():
        raise cap_problem()


def check_session(actor: SessionActor, rule: Rule) -> None:
    s = actor.session
    if s["isSeed"]:
        raise conflict("Seed sessions are replay-only. Use Continue live.")
    if s["status"] == "ended":
        raise conflict("This session has ended.")
    if rule.mode is not None and s["mode"] != rule.mode:
        raise conflict(f"This is not a {rule.mode} session.", {"mode": s["mode"]})


def check_no_other_live(manager: LiveSessionManager, sid: str | None) -> None:
    other = manager.active_other(sid)
    if other is not None:
        raise conflict("Another session is live. Leave it first.", {"activeSessionId": other})


Resume = Callable[[], Awaitable[None]]


async def live_session(actor: SessionActor, manager: LiveSessionManager) -> bool:
    """The mock's `liveSession()` after the seed/ended checks. Returns True when the session must auto-resume
    (a paused 1:1 or group session); the caller emits `session.resumed` before its own events."""
    check_no_other_live(manager, actor.sid)
    s = actor.session
    if s["status"] == "paused" and s.get("pausedReason") != "turn_cap":
        if s.get("pausedReason") == "daily_budget" and await manager.cap_blocked():
            raise cap_problem()
        if s["mode"] in ("one_on_one", "group"):
            return True
    return False

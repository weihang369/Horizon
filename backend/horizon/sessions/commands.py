"""Session commands (http-api "Session command routes"; doc 03 §3): each runs inside the session's actor, after the
pre-202 checks (`preconditions.py`), and only queues or emits; its results arrive on the session stream."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from horizon.api.errors import HorizonHTTPError, not_found
from horizon.sessions.modes import debate, group, one_on_one, watch
from horizon.sessions.modes.common import patch_settings
from horizon.sessions.preconditions import (
    check_generating,
    check_session,
    check_text,
    key_problem,
    live_session,
    rule_for,
)

if TYPE_CHECKING:
    from horizon.runtime import Runtime
    from horizon.sessions.actor import SessionActor

Wire = dict[str, Any]
Handler = Callable[["SessionActor", Wire], Awaitable[None]]


# ── chat ──
async def _send(a: SessionActor, b: Wire) -> None:
    mode = a.mode_name
    text = str(b["text"])
    if mode == "one_on_one":
        await one_on_one.send(a, text)
    elif mode == "group":
        await group.send(a, text, list(b.get("mentions") or []))
    elif mode == "watch":
        await watch.step_in(a, text)
    else:
        await debate.interject(a, text)


async def _stop(a: SessionActor, _b: Wire) -> None:
    info = a.current
    await a.clear()
    if info is not None:
        await a.manager.runner.close_interrupted(a, info, by="user")


async def _regenerate(a: SessionActor, b: Wire) -> None:
    mid = str(b["messageId"])
    m = a.state["messages"].get(mid)
    if m is None or m["author"]["type"] != "character" or m["status"] == "streaming":
        raise not_found("Message")
    one_on_one.regenerate(a, mid)


async def _set_emotion(a: SessionActor, b: Wire) -> None:
    await a.emit({"type": "emotion", "payload": {"characterId": b["characterId"], "emotion": b["emotion"], "source": "user"}})


async def _settings(patch: Wire, a: SessionActor) -> None:
    await a.emit(patch_settings(patch))


async def _emotion_mode(a: SessionActor, b: Wire) -> None:
    await _settings({"emotionMode": b["mode"]}, a)


async def _responder_policy(a: SessionActor, b: Wire) -> None:
    await _settings({"config": {**(a.session.get("config") or {}), "responderPolicy": b["policy"]}}, a)


async def _music_policy(a: SessionActor, b: Wire) -> None:
    await _settings({"musicPolicy": b["policy"]}, a)


async def _readable(a: SessionActor, b: Wire) -> None:
    await _settings({"readableMode": bool(b["on"])}, a)


async def _everyone(a: SessionActor, _b: Wire) -> None:
    group.everyone_answer(a)


async def _next_speaker(a: SessionActor, b: Wire) -> None:
    cid = b.get("characterId")
    if cid is not None and cid not in {p["characterId"] for p in a.session["participants"]}:
        raise not_found("Participant")
    if a.mode_name == "watch":
        a.mode.nudge = cid
        if a.held:
            watch.step_once(a)
        return
    await group.next_speaker(a, cid)


async def _mute(a: SessionActor, b: Wire) -> None:
    cid = b["characterId"]
    if cid not in {p["characterId"] for p in a.session["participants"]}:
        raise not_found("Participant")
    parts = [{**p, "mutedByUser": bool(b["muted"])} if p["characterId"] == cid else p for p in a.session["participants"]]
    await a.emit({"type": "session.state", "payload": {"participants": parts}})


# ── debate ──
async def _d_pause(a: SessionActor, _b: Wire) -> None:
    await debate.pause(a)


async def _d_resume(a: SessionActor, _b: Wire) -> None:
    await debate.resume(a)


async def _d_next(a: SessionActor, _b: Wire) -> None:
    debate.step(a)


async def _d_auto(a: SessionActor, b: Wire) -> None:
    await debate.set_auto_advance(a, bool(b["on"]))


async def _d_ask(a: SessionActor, b: Wire) -> None:
    cid = str(b["characterId"])
    if cid not in {p["characterId"] for p in a.session["participants"]}:
        raise not_found("Participant")
    await debate.ask(a, cid, str(b["text"]))


async def _d_interject(a: SessionActor, b: Wire) -> None:
    await debate.interject(a, str(b["text"]))


async def _d_extend(a: SessionActor, _b: Wire) -> None:
    debate.extend_round(a)


async def _d_skip(a: SessionActor, _b: Wire) -> None:
    debate.skip_to_closing(a)


async def _d_end(a: SessionActor, b: Wire) -> None:
    await debate.end_debate(a, bool(b["withVerdict"]))


async def _d_pick(a: SessionActor, b: Wire) -> None:
    await debate.pick(a, str(b["side"]))


# ── watch ──
async def _w_play(a: SessionActor, _b: Wire) -> None:
    await watch.play(a)


async def _w_pause(a: SessionActor, _b: Wire) -> None:
    await watch.pause(a)


async def _w_step(a: SessionActor, _b: Wire) -> None:
    watch.step_once(a)


async def _w_pace(a: SessionActor, b: Wire) -> None:
    await watch.set_pace(a, float(b["paceMs"]))


async def _w_direct(a: SessionActor, b: Wire) -> None:
    await watch.direct(a, str(b["text"]))


async def _w_step_in(a: SessionActor, b: Wire) -> None:
    await watch.step_in(a, str(b["text"]))


async def _w_extend(a: SessionActor, b: Wire) -> None:
    await watch.extend(a, int(b.get("turns") or 10))


async def _w_summarise(a: SessionActor, _b: Wire) -> None:
    await watch.summarise(a)


HANDLERS: dict[str, Handler] = {
    "send": _send, "stop": _stop, "regenerate": _regenerate, "set-emotion": _set_emotion,
    "set-emotion-mode": _emotion_mode, "set-responder-policy": _responder_policy, "set-music-policy": _music_policy,
    "set-readable-mode": _readable, "everyone-answer": _everyone, "next-speaker": _next_speaker, "mute": _mute,
    "debate/pause": _d_pause, "debate/resume": _d_resume, "debate/next": _d_next, "debate/auto-advance": _d_auto,
    "debate/ask": _d_ask, "debate/interject": _d_interject, "debate/extend-round": _d_extend,
    "debate/skip-to-closing": _d_skip, "debate/end": _d_end, "debate/pick": _d_pick,
    "watch/play": _w_play, "watch/pause": _w_pause, "watch/step": _w_step, "watch/pace": _w_pace,
    "watch/direct": _w_direct, "watch/step-in": _w_step_in, "watch/extend": _w_extend, "watch/summarise": _w_summarise,
}


async def run_command(rt: Runtime, sid: str, name: str, body: Wire) -> None:
    """The pre-202 checks in the mock's order (key and cap, then the session, then the text), then the handler,
    all inside the actor so they can't race another command."""
    rule = rule_for(name, with_verdict=bool(body.get("withVerdict")))
    manager = rt.sessions
    if rule.generating:
        problem = key_problem(rt.keys.status())
        if problem is not None:
            raise problem
    actor = await manager.get(sid)
    handler = HANDLERS[name]

    async def inside() -> None:
        check_session(actor, rule)
        if rule.generating:
            await check_generating(manager, rt.keys.status())
        if rule.text:
            check_text(body.get("text"))
        if rule.live_session and await live_session(actor, manager):
            actor.held = False
            await actor.emit({"type": "session.resumed", "payload": {"reason": "user"}})
        actor.touch()
        await handler(actor, body)

    try:
        await actor.submit(inside)
    except HorizonHTTPError:
        raise

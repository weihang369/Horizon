"""Debate (session-modes "Debate phases", "Debate moderation", "Debate verdict"; a port of `mock/engines/debate.ts`).

The configured phases run in order; each opens with a `phase` event, a `ROUND n · LABEL` note and, with `auto_host`,
host narration. Speakers alternate prop/opp (two-sided) or follow cast order (panel), marked `forcedBy: "round_order"`
and tagged with phase, round and iteration. With `autoAdvance`, the next step starts `pauseMs` after a turn ends.
Steering (Ask, Interject, extend, skip) lands at the next turn boundary.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from horizon.ai.contexts import DebateMeta, LineHint
from horizon.gateway.errors import ProviderError
from horizon.sessions.context import session_context
from horizon.sessions.modes.common import (
    asleep_note,
    is_asleep,
    message_event,
    note,
    patch_settings,
    runner,
    speak_then,
    user_message,
)
from horizon.sessions.prefetch import Prefetch
from horizon.sessions.turn import TurnSpec

if TYPE_CHECKING:
    from horizon.sessions.actor import SessionActor

Wire = dict[str, Any]
VERDICT_DELAY_MS = 1800


def cfg_of(actor: SessionActor) -> Wire:
    c: Wire = actor.session.get("config") or {}
    return c


def state_of(actor: SessionActor) -> Wire:
    st: Wire = actor.session.get("state") or {"phase": "setup", "round": 0, "iteration": 1}
    return st


def side_of(actor: SessionActor, cid: str) -> str | None:
    for p in actor.session["participants"]:
        if p["characterId"] == cid:
            side = p.get("side")
            return str(side) if side else None
    return None


def phase_order(cfg: Wire, cast: list[str]) -> list[str]:
    sides = cfg.get("sides")
    if cfg.get("format") != "two_sided" or not sides:
        return list(cast)
    prop, opp = list(sides.get("prop") or []), list(sides.get("opp") or [])
    out: list[str] = []
    for i in range(max(len(prop), len(opp))):
        if i < len(prop):
            out.append(prop[i])
        if i < len(opp):
            out.append(opp[i])
    return out


def _host(actor: SessionActor) -> Any:
    return actor.rt.ai.host(runner(actor).key_set())


async def begin_phase(actor: SessionActor, phase: str, iteration: int = 1) -> None:
    for pf in actor.mode.debate_prefetch.values():
        await pf.discard()
    actor.mode.debate_prefetch = {}
    cfg = cfg_of(actor)
    phases = list(cfg.get("phases") or [])
    round_ = phases.index(phase) + 1 if phase in phases else len(phases)
    cast = [p["characterId"] for p in actor.session["participants"]]
    actor.mode.debate_order = phase_order(cfg, cast)
    actor.mode.debate_idx = 0
    actor.mode.extend = False
    host = _host(actor)
    events: list[Wire] = [{"type": "phase", "payload": {"phase": phase, "round": round_, "iteration": iteration}},
                          message_event(note(actor, host.round_note(phase, round_, iteration)))]
    await actor.emit(*events)
    if cfg.get("moderator") == "auto_host":
        await actor.emit(message_event(note(actor, host.narration(phase, str(cfg.get("motion", ""))), "narration",
                                            {"type": "host"})))


def start(actor: SessionActor) -> None:
    async def job() -> None:
        await actor.rt.clock.sleep(actor.rt.runtime_cfg.timing.debate_start_ms / 1000)
        phases = cfg_of(actor).get("phases") or ["opening"]
        await begin_phase(actor, str(phases[0]))
        step(actor)

    actor.enqueue(job)


def ensure_cursor(actor: SessionActor) -> None:
    """Rebuild the cursor for a resumed or forked debate from the messages already in the current phase."""
    if actor.mode.debate_order is not None:
        return
    st = state_of(actor)
    cast = [p["characterId"] for p in actor.session["participants"]]
    spoken = sum(1 for m in actor.state["messages"].values()
                 if m["author"]["type"] == "character" and m["kind"] == "chat" and not m.get("forcedSpeaker")
                 and (m.get("debate") or {}).get("phase") == st.get("phase")
                 and (m.get("debate") or {}).get("iteration") == st.get("iteration"))
    actor.mode.debate_order = phase_order(cfg_of(actor), cast)
    actor.mode.debate_idx = spoken


def step(actor: SessionActor) -> None:
    """One normal debate turn (or a phase boundary), queued behind any steering."""
    async def job() -> None:
        st = state_of(actor)
        if st.get("phase") in ("verdict", "ended") or actor.session["status"] == "ended":
            return
        cfg = cfg_of(actor)
        phases = [str(p) for p in cfg.get("phases") or []]
        if st.get("phase") == "setup":
            await begin_phase(actor, phases[0] if phases else "opening")
        ensure_cursor(actor)
        m = actor.mode
        if m.skip_to_closing and state_of(actor).get("phase") != "closing":
            await begin_phase(actor, "closing")
            m.skip_to_closing = False
            schedule_next(actor)
            return
        order = m.debate_order or []
        if m.debate_idx >= len(order):
            phase = str(state_of(actor).get("phase"))
            nxt = phases[phases.index(phase) + 1] if phase in phases and phases.index(phase) + 1 < len(phases) else None
            if m.extend:
                await begin_phase(actor, phase, int(state_of(actor).get("iteration", 1)) + 1)
            elif nxt:
                await begin_phase(actor, nxt)
            else:
                await go_verdict(actor)
                return
            schedule_next(actor)
            return
        idx = m.debate_idx
        cid = order[idx]
        m.debate_idx += 1
        pf = m.debate_prefetch.pop(idx, None)
        if pf is None and await is_asleep(actor, cid):
            await asleep_note(actor, cid, skipping=True)
            schedule_next(actor, 200)
            return
        now = state_of(actor)
        if now.get("phase") == "opening" and int(now.get("iteration", 1)) == 1:
            # The opening round is known in advance: generate up to 2 later openings now (design D5).
            for j in range(idx + 1, min(len(order), idx + 1 + actor.rt.runtime_cfg.runtime.prefetch_max)):
                if j not in m.debate_prefetch and not await is_asleep(actor, order[j]):
                    p = await Prefetch.start(actor, turn_spec(actor, order[j], now))
                    if p is not None:
                        m.debate_prefetch[j] = p
        await speak_then(actor, turn_spec(actor, cid, now), prefetch=pf)
        order = m.debate_order or []
        upcoming = order[m.debate_idx] if m.debate_idx < len(order) else None
        if upcoming:
            await actor.emit({"type": "turn.next", "payload": {"nextSpeakerId": upcoming}})
        schedule_next(actor)

    actor.enqueue(job)


def turn_spec(actor: SessionActor, cid: str, now: Wire) -> TurnSpec:
    side = side_of(actor, cid)
    meta: Wire = {"phase": now["phase"], "round": now["round"], "iteration": now["iteration"]}
    if side:
        meta["side"] = side
    return TurnSpec(speaker=cid, line=LineHint(kind="debate"), forced_by="round_order", message={"debate": meta},
                    debate=DebateMeta(phase=str(now["phase"]), round=int(now["round"]), iteration=int(now["iteration"]),
                                      side=side, motion=str(cfg_of(actor).get("motion", ""))))


def schedule_next(actor: SessionActor, ms: float | None = None) -> None:
    if not cfg_of(actor).get("autoAdvance") or actor.held:
        return

    def go() -> None:
        if not actor.held and cfg_of(actor).get("autoAdvance"):
            step(actor)

    actor.after(ms if ms is not None else float(cfg_of(actor).get("pauseMs", 1500)), go)


# ── verdict ──
async def finish(actor: SessionActor, verdict: Wire | None = None) -> None:
    st = state_of(actor)
    events: list[Wire] = []
    if verdict is not None:
        if verdict.get("strongerCase"):
            text = f"STRONGER CASE: {'PROPOSITION' if verdict['strongerCase'] == 'prop' else 'OPPOSITION'}"
        else:
            text = "SUMMARY" if verdict.get("decidedBy") == "none" else "TOO CLOSE TO CALL"
        events.append(message_event(note(actor, text, "verdict")))
        events.append({"type": "session.state", "payload": {"state": {**st, "verdict": verdict}}})
    events.append({"type": "phase", "payload": {"phase": "ended", "round": st.get("round", 0),
                                                "iteration": st.get("iteration", 1)}})
    final = {**st, **({"verdict": verdict} if verdict is not None else {}), "phase": "ended"}
    final.pop("nextSpeakerId", None)
    events.append({"type": "session.state", "payload": {"status": "ended", "state": final}})
    await actor.emit(*events)


async def go_verdict(actor: SessionActor) -> None:
    cfg = cfg_of(actor)
    n = len(cfg.get("phases") or []) + 1
    await actor.emit({"type": "phase", "payload": {"phase": "verdict", "round": n, "iteration": 1}},
                     message_event(note(actor, f"ROUND {n} · VERDICT")))
    if cfg.get("verdictBy") == "user":
        return  # waits for debate.pick

    async def job() -> None:
        await actor.rt.clock.sleep(VERDICT_DELAY_MS / 1000)
        sctx = await session_context(actor.rt, actor, recent=1000)
        try:
            verdict = await _host(actor).verdict(sctx, str(cfg.get("verdictBy", "arbiter")), None)
        except ProviderError:
            return  # a cap refusal pauses the session; resume or end later
        await finish(actor, verdict)

    actor.enqueue(job)


# ── steering ──
def meta(actor: SessionActor) -> Wire:
    st = state_of(actor)
    return {"phase": st.get("phase", "setup"), "round": st.get("round", 0), "iteration": st.get("iteration", 1)}


async def ask(actor: SessionActor, cid: str, text: str) -> None:
    await actor.emit(message_event(user_message(actor, text, "steer", targetCharacterId=cid, debate=meta(actor))))

    async def job() -> None:
        if await is_asleep(actor, cid):
            await asleep_note(actor, cid, skipping=False)
            return
        side = side_of(actor, cid)
        mm = {**meta(actor), **({"side": side} if side else {})}
        await speak_then(actor, TurnSpec(
            speaker=cid, line=LineHint(kind="answer"), prompt=text, forced_by="user_ask",
            message={"forcedSpeaker": True, "debate": mm},
            routing={"question": text, "selected": cid, "forcedBy": "user_ask"}))

    actor.enqueue(job, front=True)


async def interject(actor: SessionActor, text: str) -> None:
    await actor.emit(message_event(user_message(actor, text, "interject", debate=meta(actor))))


def extend_round(actor: SessionActor) -> None:
    ensure_cursor(actor)
    actor.mode.extend = True


def skip_to_closing(actor: SessionActor) -> None:
    ensure_cursor(actor)
    actor.mode.skip_to_closing = True


async def pause(actor: SessionActor) -> None:
    actor.held = True
    await actor.emit({"type": "session.paused", "payload": {"reason": "user"}})


async def resume(actor: SessionActor) -> None:
    actor.held = False
    await actor.emit({"type": "session.resumed", "payload": {"reason": "user"}})
    if not actor.busy and len(actor.turns) == 0:
        step(actor)


async def end_debate(actor: SessionActor, with_verdict: bool) -> None:
    await actor.clear(keep_current=True)
    actor.held = False
    if with_verdict:
        await go_verdict(actor)
    else:
        await finish(actor)


async def pick(actor: SessionActor, side: str) -> None:
    sctx = await session_context(actor.rt, actor, recent=1000)
    await finish(actor, await _host(actor).verdict(sctx, "user", side))


async def set_auto_advance(actor: SessionActor, on: bool) -> None:
    await actor.emit(patch_settings({"config": {**cfg_of(actor), "autoAdvance": on}}))
    if on and not actor.held and not actor.busy:
        step(actor)

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
from horizon.sessions.debate_slots import SIDE_NAME, Fill, cursor, fill, members, phase_slots
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
    """Today's fixed order for a phase (prop[i] / opp[i] interleaved, or cast order): who fills each slot while everyone
    is awake (M11, debate design D3)."""
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
    actor.mode.debate_announced = None
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


def _messages(actor: SessionActor) -> list[Wire]:
    from horizon.services.runtime.reducer import ordered_messages

    out: list[Wire] = ordered_messages(actor.state)
    return out


def _cast(actor: SessionActor) -> list[str]:
    return [p["characterId"] for p in actor.session["participants"]]


async def next_slot(actor: SessionActor) -> tuple[int, str | None, Fill] | None:
    """The next slot of this phase and how it is filled (D3), or None when the phase is done. A slot with a prefetched
    opening is that member's; otherwise the slot rule decides from who is awake now."""
    cfg, cast = cfg_of(actor), _cast(actor)
    slots = phase_slots(cfg, cast)
    cur = cursor(_messages(actor))
    if cur.used >= len(slots):
        return None
    side = slots[cur.used]
    pf = actor.mode.debate_prefetch.get(cur.used)
    if pf is not None:
        return cur.used, side, Fill("speak", who=pf.spec.speaker, eligible=(pf.spec.speaker,))
    side_members = members(cfg, cast, side)
    awake = {c: not await is_asleep(actor, c) for c in side_members}
    return cur.used, side, fill(side_members, cur.heard, awake)


async def upcoming(actor: SessionActor, after_idx: int, heard: list[str], n: int) -> list[tuple[int, str]]:
    """The members the next `n` slots after `after_idx` would get in fixed order, given `heard` (the opening prefetch,
    D3): skipped slots are passed over, and a slot that would pause ends the look-ahead."""
    cfg, cast = cfg_of(actor), _cast(actor)
    slots = phase_slots(cfg, cast)
    out: list[tuple[int, str]] = []
    heard = list(heard)
    for j in range(after_idx + 1, min(len(slots), after_idx + 1 + n)):
        pf = actor.mode.debate_prefetch.get(j)
        if pf is not None:
            heard.append(pf.spec.speaker)
            continue
        side_members = members(cfg, cast, slots[j])
        f = fill(side_members, heard, {c: not await is_asleep(actor, c) for c in side_members})
        if f.action == "pause":
            break
        if f.action == "speak" and f.who is not None:
            out.append((j, f.who))
            heard.append(f.who)
    return out


async def pause_side(actor: SessionActor, side: str | None, asleep: tuple[str, ...]) -> None:
    """V5 (D4): every asleep member of the side gets its note with `energy_exhausted`, a system note names the side,
    and the debate pauses with reason `user`. The slot is kept: play runs it again."""
    for cid in asleep:
        await asleep_note(actor, cid, skipping=False, debate=meta(actor))
    text = ("Everyone on the panel is asleep. Top someone up to continue the debate." if side is None else
            f"The {SIDE_NAME[side]} is asleep. Top someone up to continue the debate.")
    actor.held = True
    await actor.emit(message_event(note(actor, text)), {"type": "session.paused", "payload": {"reason": "user"}})


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
        m = actor.mode
        if m.skip_to_closing and state_of(actor).get("phase") != "closing":
            await begin_phase(actor, "closing")
            m.skip_to_closing = False
            schedule_next(actor)
            return
        slot = await next_slot(actor)
        if slot is None:
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
        idx, side, f = slot
        if f.action == "pause":
            await pause_side(actor, side, f.asleep)
            return
        if f.action == "skip":
            assert f.who is not None
            await asleep_note(actor, f.who, skipping=True, debate=meta(actor))
            schedule_next(actor, 200)
            return
        cid = str(f.who)
        pf = m.debate_prefetch.pop(idx, None)
        if pf is not None and pf.spec.speaker != cid:
            await pf.discard()
            pf = None
        announced, m.debate_announced = m.debate_announced, None
        skipped: list[Wire] | None = None
        if announced is not None and announced[0] == idx and announced[1] != cid and await is_asleep(actor, announced[1]):
            # V3 (D3): the announced member fell asleep before their turn; the next eligible one speaks, and the turn's
            # own `turn.next` names them with the asleep member under `skipped`
            skipped = [{"characterId": announced[1], "reason": "exhausted"}]
        now = state_of(actor)
        if now.get("phase") == "opening" and int(now.get("iteration", 1)) == 1:
            # The opening round is known in advance: generate up to 2 later openings now (design D5).
            heard = [*cursor(_messages(actor)).heard, cid]
            for j, who in await upcoming(actor, idx, heard, actor.rt.runtime_cfg.runtime.prefetch_max):
                if j not in m.debate_prefetch:
                    p = await Prefetch.start(actor, turn_spec(actor, who, now))
                    if p is not None:
                        m.debate_prefetch[j] = p
        spec = turn_spec(actor, cid, now)
        spec.skipped = skipped
        await speak_then(actor, spec, prefetch=pf)
        nxt_slot = await next_slot(actor)
        if nxt_slot is not None and nxt_slot[2].action == "speak" and nxt_slot[2].who is not None:
            await actor.emit({"type": "turn.next", "payload": {"nextSpeakerId": nxt_slot[2].who}})
            m.debate_announced = (nxt_slot[0], nxt_slot[2].who)
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
    actor.mode.extend = True


def skip_to_closing(actor: SessionActor) -> None:
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

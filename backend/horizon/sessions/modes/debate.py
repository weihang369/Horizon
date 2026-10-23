"""Debate (session-modes "Debate phases", "Debate moderation", "Debate verdict"; a port of `mock/engines/debate.ts`).

The configured phases run in order; each opens with a `phase` event, a `ROUND n · LABEL` note and, with `auto_host`,
the host's line (M11: written by DeepSeek ahead of its banner, else the fixed sentence; sessions/debate_host).
Speakers alternate prop/opp (two-sided) or follow cast order (panel), marked `forcedBy: "round_order"` and tagged with
phase, round and iteration. With `autoAdvance`, the next step starts `pauseMs` after a turn ends.
Steering (Ask, Interject, extend, skip) lands at the next turn boundary.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from horizon.ai.contexts import DebateMeta, HostKey, LineHint
from horizon.domain import vclock
from horizon.sessions import debate_host, debate_plan, debate_verdict
from horizon.sessions.context import session_context
from horizon.sessions.debate_slots import SIDE_NAME, Fill, cursor, fill, is_argument, members, phase_slots, two_sided
from horizon.sessions.modes.common import (
    asleep_note,
    checked_s,
    gap,
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


def host_key(actor: SessionActor, phase: str, iteration: int, via: str | None = None) -> HostKey:
    """D11: what a phase's host line introduces: the welcome (the first phase), an extended round, Skip's closing, or a
    bridge."""
    phases = [str(p) for p in cfg_of(actor).get("phases") or ["opening"]]
    if iteration > 1:
        return HostKey(kind="extended", phase=phase, iteration=iteration)
    if via == "skip":
        return HostKey(kind="skip", phase=phase)
    if phases and phase == phases[0]:
        return HostKey(kind="welcome", phase=phase)
    return HostKey(kind="bridge", phase=phase)


def banner_wait(actor: SessionActor) -> timedelta:
    return timedelta(milliseconds=actor.rt.runtime_cfg.runtime.host_banner_wait_ms)


async def begin_phase(actor: SessionActor, phase: str, iteration: int = 1, *, via: str | None = None,
                      host_until: datetime | None = None) -> None:
    """The phase event and its banner; then, with Auto host, its line (V6): shown when written, by `host_until` (the
    welcome's Start + `hostWelcomeWaitMs`) or the banner + `hostBannerWaitMs`, else the fixed sentence."""
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
    if debate_host.auto_host(actor):
        await debate_host.show(actor, host_key(actor, phase, iteration, via),
                               host_until or actor.rt.clock.now() + banner_wait(actor))


def start(actor: SessionActor) -> None:
    actor.mode.debate_armed = True

    async def job() -> None:
        wait = actor.rt.runtime_cfg.timing.debate_start_ms / 1000
        t0 = actor.rt.clock.now()
        phases = cfg_of(actor).get("phases") or ["opening"]
        debate_host.request(actor, host_key(actor, str(phases[0]), 1))   # V6: the welcome is written during the splash
        first = await first_opening(actor)
        if first is not None:   # D8: the first opening's face is planned inside the start delay
            await debate_plan.start_opening(actor, ("opening", 1), first,
                                            actor.rt.clock.now() + timedelta(seconds=wait))
        await actor.rt.clock.sleep(wait)
        await begin_phase(actor, str(phases[0]), host_until=t0 + timedelta(
            milliseconds=actor.rt.runtime_cfg.runtime.host_welcome_wait_ms))
        step(actor)

    actor.enqueue(job)


def _messages(actor: SessionActor) -> list[Wire]:
    from horizon.services.runtime.reducer import ordered_messages

    out: list[Wire] = ordered_messages(actor.state)
    return out


def _cast(actor: SessionActor) -> list[str]:
    return [p["characterId"] for p in actor.session["participants"]]


async def first_opening(actor: SessionActor) -> str | None:
    """Who the first opening's slot will get in fixed order now (the first phase must be the opening)."""
    cfg, cast = cfg_of(actor), _cast(actor)
    phases = [str(p) for p in cfg.get("phases") or ["opening"]]
    slots = phase_slots(cfg, cast)
    if not phases or phases[0] != "opening" or not slots:
        return None
    side_members = members(cfg, cast, slots[0])
    f = fill(side_members, [], {c: not await is_asleep(actor, c) for c in side_members})
    return f.who if f.action == "speak" else None


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
    actor.mode.debate_armed = True

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
            await begin_phase(actor, "closing", via="skip")
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
        announced, m.debate_announced = m.debate_announced, None
        if announced is not None and announced[0] == idx and announced[1] in f.eligible:
            cid = announced[1]   # `turn.next` named them (Jev's pick, D8): they speak if still eligible
        pf = m.debate_prefetch.pop(idx, None)
        if pf is not None and pf.spec.speaker != cid:
            await pf.discard()
            pf = None
        skipped: list[Wire] | None = None
        if announced is not None and announced[0] == idx and announced[1] != cid and await is_asleep(actor, announced[1]):
            # V3 (D3): the announced member fell asleep before their turn; the next eligible one speaks, and the turn's
            # own `turn.next` names them with the asleep member under `skipped`
            skipped = [{"characterId": announced[1], "reason": "exhausted"}]
        now = state_of(actor)
        if now.get("phase") == "opening" and int(now.get("iteration", 1)) == 1:
            # The opening round is known in advance: generate up to 2 later openings now (design D5).
            heard = [*cursor(_messages(actor)).heard, cid]
            ups = await upcoming(actor, idx, heard, actor.rt.runtime_cfg.runtime.prefetch_max)
            for k, (j, who) in enumerate(ups):
                if j not in m.debate_prefetch:
                    before = [*heard, *(w for _, w in ups[:k])]   # who will have argued by this opening (D10)
                    p = await Prefetch.start(actor, turn_spec(actor, who, now, heard=before),
                                             plan_with=opening_planner(actor, who))
                    if p is not None:
                        m.debate_prefetch[j] = p
        target = (str(now.get("phase")), int(now.get("iteration", 1)))
        if pf is not None:   # a prefetched opening carries its own plan (D8)
            plan, routing, stored = None, None, None
        else:
            cid, plan, routing, stored = await plan_slot(actor, idx, side, target, cid, f, announced is not None)
        spec = turn_spec(actor, cid, now)
        spec.skipped = skipped
        if plan is not None:
            spec.plan = plan
        if routing is not None:
            spec.routing = {**routing, **({"skipped": skipped} if skipped else {})}
        late = stored is not None and not stored.call.landed
        out = await runner(actor).run(actor, spec, prefetch=pf)
        if late and stored is not None and out.message_id is not None:
            actor.background(debate_plan.LATE, debate_plan.append_late(actor, stored, out.message_id, cid))
        hidden = 0.0
        if out.status in ("complete", "interrupted", "error"):
            hidden = await after_argument(actor, out)
        # M14 (safety D10): `pauseMs` counts from the stream's end too, so a check shorter than the waits adds nothing;
        # the debate plan still starts at `turn.end`, and the member's deadline still counts from it
        pause = float(cfg_of(actor).get("pauseMs", 1500))
        schedule_next(actor, max(0.0, pause - (checked_s(out) - hidden) * 1000))

    actor.enqueue(job)


async def plan_slot(actor: SessionActor, idx: int, side: str | None, target: tuple[str, int], cid: str, f: Fill,
                    was_announced: bool) -> tuple[str, Any, Wire | None, Any]:
    """At the turn's start (D8): (who speaks, their frozen plan, the routing to show, the stored plan used).

    - A stored plan whose fingerprint holds gives its faces (a phase's first-slot plan fixes its member now).
    - A changed one keeps the announced member and asks the face again (`turn_plan` deadline); a changed first-slot
      plan is dropped, and the slot plans now.
    - With none, a slot with two or more eligible members and no announcement plans its member and faces now, under
      the `turn_plan` deadline (late or unsure: fixed order); otherwise the forced speaker's face is planned now.
    `naive` and `scripted` plan nothing. Openings keep the fixed order (their faces are planned with their turn)."""
    stored, fresh = await debate_plan.take(actor, idx, target)
    if stored is not None and stored.face_task is not None:   # the first opening's face, planned at Start
        if fresh and stored.speaker == cid:
            debate_plan.finish_with(actor, stored)
            return cid, await vclock.join(stored.face_task), None, None
        debate_plan.drop(actor)
        stored = None
    if stored is not None and stored.member is None and not fresh:
        debate_plan.drop(actor)
        stored = None
    if stored is None:
        if target[0] == "opening":   # an opening with no prefetch (D8): its face is planned now
            return cid, await plan_face(actor, cid, target, kind="debate_opening"), None, None
        if len(f.eligible) >= 2 and not was_announced:
            now = actor.rt.clock.now()
            stored = await debate_plan.start(actor, idx, target, side, list(f.eligible), now)
            if stored is not None:
                deadline = now + timedelta(seconds=actor.rt.decider.timeout_for("turn_plan"))
                stored.member = await stored.call.member(deadline)
                if stored.member.member in f.eligible:
                    cid = stored.member.member
                dp = await stored.call.faces(deadline)
                debate_plan.finish_with(actor, stored)
                await settle(actor, None, dp.safety)   # M14 (safety D5): Jev's answer about the Interject is stored
                return cid, dp.for_speaker(cid), member_routing(stored.member, cid), stored
        return cid, await plan_face(actor, cid, target), None, None
    if stored.member is None:   # the phase's first slot, planned at the last phase's end: the member is fixed now
        stored.member = await stored.call.member(actor.rt.clock.now())
        if stored.asked and not was_announced and stored.member.member in f.eligible:
            cid = stored.member.member
    member = stored.member
    routing = member_routing(member, cid)
    if fresh:
        dp = await stored.call.faces(actor.rt.clock.now())
        debate_plan.finish_with(actor, stored)
        await settle(actor, None, dp.safety)   # M14 (safety D5): Jev's answer about the Interject is stored
        return cid, dp.for_speaker(cid), routing, stored
    debate_plan.drop(actor)   # the stored faces are stale (V2): the member stays, the face is asked again
    again = await plan_face(actor, cid, target)
    plan = None
    if again is not None:
        plan = again.model_copy(update={"rows": [*member.shared_rows, *again.rows],
                                        "calls": [*member.calls, *again.calls]})
    return cid, plan, routing, None


async def settle(actor: SessionActor, line: Any, cue: Any) -> None:
    from horizon.sessions import safety as ss

    await ss.settle(actor, line, cue)


def member_routing(member: Any, cid: str) -> Wire | None:
    """D27 / the debate-plan spec: the member question's label, Jev's probabilities, who speaks, and why."""
    if member is None or member.who is None:
        return None
    return {"question": member.who.label, "candidates": member.who.candidates, "selected": cid,
            "forcedBy": "round_order", "reason": member.who.reason}


async def plan_face(actor: SessionActor, cid: str, target: tuple[str, int], kind: str = "debate_line", *,
                    latest: str | None = None, deadline_at: datetime | None = None,
                    forced_by: str = "round_order") -> Any:
    """One forced speaker's face, planned now (`turn_plan`, or by `deadline_at`): `emotion_line` about the argument
    just made, an opening's `emotion_debate_opening`, or an Ask answer's `emotion_reply` about the moderator's question
    (`latest`) (D7, D8). None without a planner."""
    from horizon.sessions.plans import cast_request, plan_cast, plans_cast

    if not plans_cast(actor):
        return None
    sctx = await session_context(actor.rt, actor)
    side = side_of(actor, cid)
    facts, last_line = debate_plan.facts(actor, sctx, target[0], side, [cid])
    req = await cast_request(actor, kind, [], forced=[cid], forced_by=forced_by,  # type: ignore[arg-type]
                             latest=last_line if latest is None else latest, sctx=sctx, debate=facts,
                             deadline_at=deadline_at)
    cp = await plan_cast(actor, req)
    return cp.for_speaker(cid) if cp is not None else None


def opening_planner(actor: SessionActor, cid: str) -> Any:
    """A prefetched opening's own face plan (D8), run by its prefetch when it starts; None without a planner."""
    from horizon.sessions.plans import plans_cast

    if not plans_cast(actor):
        return None

    async def plan() -> Any:
        return await debate_plan.opening_face(actor, cid, ("opening", 1))
    return plan


async def after_argument(actor: SessionActor, out: Any) -> float:
    """After an argument's `turn.end` (D8): the next slot's plan starts at once. With a member question, `turn.next`
    names the member as soon as Jev answers, by `turn.end` + the `debate_plan` deadline, with no turn gap; otherwise
    the turn gap, then `turn.next`, as before. At a phase's end no `turn.next` is sent; the next phase's first slot is
    planned now and decided when it starts."""
    m = actor.mode
    # M14 (safety D10): the turn gap counts from the stream's end; returns the seconds of the check it hid, so the
    # pause hides the rest (a member question's wait still counts from `turn.end`, so it hides nothing)
    check_s = checked_s(out)
    gap_s = actor.rt.runtime_cfg.timing.turn_gap_ms / 1000
    hidden = min(check_s, gap_s)
    st = state_of(actor)
    phase, iteration = str(st.get("phase")), int(st.get("iteration", 1))
    ended = out.ended_at or actor.rt.clock.now()
    nxt = await next_slot(actor)
    if nxt is None:
        target = next_target(actor, phase, iteration)
        if target is None:
            debate_host.request(actor, HostKey(kind="lead_in", phase="verdict"))
            debate_verdict.start(actor)   # D14: in parallel with the gap, the pause, the banner and the delay
        elif not m.extend and not m.skip_to_closing:   # Extend's and Skip's lines are asked when their phase begins
            debate_host.request(actor, HostKey(kind="bridge", phase=target[0]))
        if target is not None and target[0] != "opening":
            cfg, cast = cfg_of(actor), _cast(actor)
            side = phase_slots(cfg, cast)[0] if phase_slots(cfg, cast) else None
            side_members = members(cfg, cast, side)
            first = fill(side_members, [], {c: not await is_asleep(actor, c) for c in side_members})
            if first.action == "speak":
                await debate_plan.start(actor, 0, target, side, list(first.eligible), ended)
        await gap(actor, None, gap_s - hidden)
        return hidden
    idx, side, f = nxt
    if f.action != "speak" or f.who is None:
        await gap(actor, None, gap_s - hidden)
        return hidden
    member = f.who
    stored = None
    if phase != "opening":
        stored = await debate_plan.start(actor, idx, (phase, iteration), side, list(f.eligible), ended)
    if stored is not None and stored.asked:
        deadline = ended + timedelta(seconds=actor.rt.decider.timeout_for(debate_plan.NAME))
        stored.member = await stored.call.member(deadline)
        member = stored.member.member
    else:
        if stored is not None:
            stored.member = await stored.call.member(ended)   # one candidate: fixed at once, nothing waits
        await gap(actor, None, gap_s - hidden)
    await actor.emit({"type": "turn.next", "payload": {"nextSpeakerId": member}})
    m.debate_announced = (idx, member)
    return hidden if not (stored is not None and stored.asked) else 0.0


def next_target(actor: SessionActor, phase: str, iteration: int) -> tuple[str, int] | None:
    """The (phase, iteration) the next step opens, as the boundary will decide it now; None for the verdict."""
    m = actor.mode
    phases = [str(p) for p in cfg_of(actor).get("phases") or []]
    if m.skip_to_closing and phase != "closing":
        return ("closing", 1)
    if m.extend:
        return (phase, iteration + 1)
    if phase in phases and phases.index(phase) + 1 < len(phases):
        return (phases[phases.index(phase) + 1], 1)
    return None


def turn_spec(actor: SessionActor, cid: str, now: Wire, heard: list[str] | None = None) -> TurnSpec:
    """`heard`: who will have argued in this phase-iteration before this turn (a prefetched opening's look-ahead);
    by default, from the log."""
    side = side_of(actor, cid)
    meta: Wire = {"phase": now["phase"], "round": now["round"], "iteration": now["iteration"]}
    if side:
        meta["side"] = side
    msgs = _messages(actor)
    heard = list(cursor(msgs).heard) if heard is None else heard
    teammates = [c for c in heard if c != cid and side is not None and side_of(actor, c) == side]
    return TurnSpec(speaker=cid, line=LineHint(kind="debate"), forced_by="round_order", message={"debate": meta},
                    debate=DebateMeta(phase=str(now["phase"]), round=int(now["round"]), iteration=int(now["iteration"]),
                                      side=side, motion=str(cfg_of(actor).get("motion", "")),
                                      teammates_heard=teammates, after_interject=after_interject(msgs),
                                      panel=not two_sided(cfg_of(actor))))


def after_interject(msgs: list[Wire]) -> bool:
    """V4 (D10): an Interject newer than the last argument reaches the next argument only."""
    last_arg = max((int(m["seq"]) for m in msgs if is_argument(m)), default=0)
    return any(m["author"]["type"] == "user" and m.get("kind") == "interject" and int(m["seq"]) > last_arg
               for m in msgs)


def schedule_next(actor: SessionActor, ms: float | None = None) -> None:
    if not cfg_of(actor).get("autoAdvance") or actor.held:
        return

    def go() -> None:
        if not actor.held and cfg_of(actor).get("autoAdvance"):
            step(actor)

    actor.after(ms if ms is not None else float(cfg_of(actor).get("pauseMs", 1500)), go)


def rearm(actor: SessionActor) -> None:
    """U-43: the auto-advance chain lives in the actor's timer, so an actor loaded from storage mid-round (a restart, an
    idle release) has none. On its first command, after that command's own work, an active, un-held auto-advance
    debate that this actor never started or stepped schedules its next step."""
    async def job() -> None:
        st = state_of(actor)
        if (not actor.mode.debate_armed and not actor.held and actor.session["status"] == "active"
                and st.get("phase") not in ("verdict", "ended")):
            schedule_next(actor)

    actor.enqueue(job)


# ── verdict ──
async def finish(actor: SessionActor, verdict: Wire | None = None) -> None:
    st = state_of(actor)
    events: list[Wire] = []
    if verdict is not None:
        if verdict.get("strongerCase"):
            text = f"STRONGER CASE: {'PROPOSITION' if verdict['strongerCase'] == 'prop' else 'OPPOSITION'}"
        else:
            # U-91: a panel's arbiter summary names no side by design; it isn't a tie
            panel = cfg_of(actor).get("format") == "panel"
            text = "SUMMARY" if verdict.get("decidedBy") == "none" or panel else "TOO CLOSE TO CALL"
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
    banner_at = actor.rt.clock.now()

    async def lead_in() -> None:   # V6: with Auto host, the lead-in after the VERDICT banner (a job: never the inbox)
        await debate_host.show(actor, HostKey(kind="lead_in", phase="verdict"), banner_at + banner_wait(actor))

    if cfg.get("verdictBy") == "user":
        if debate_host.auto_host(actor):
            actor.enqueue(lead_in)
        debate_verdict.start(actor)   # D14: ready before the click, usually
        return  # waits for debate.pick

    async def job() -> None:
        await lead_in()
        spent = (actor.rt.clock.now() - banner_at).total_seconds()
        await actor.rt.clock.sleep(max(0.0, VERDICT_DELAY_MS / 1000 - spent))
        # D14: the work started at the last closing's turn.end (or now); a cap refusal delivers nothing: the session
        # paused, and resume runs the work again
        await debate_verdict.deliver(actor)

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
        st = state_of(actor)
        you = str(((await session_context(actor.rt, actor)).world.you or {}).get("displayName") or "User")
        plan = await plan_face(actor, cid, (str(st.get("phase")), int(st.get("iteration", 1))), kind="debate_ask",
                               latest=f"{you}: {text}", forced_by="user_ask")
        await speak_then(actor, TurnSpec(
            speaker=cid, line=LineHint(kind="answer"), prompt=text, forced_by="user_ask",
            message={"forcedSpeaker": True, "debate": mm}, plan=plan,
            routing={"question": text, "selected": cid, "forcedBy": "user_ask"}))

    actor.enqueue(job, front=True)


async def interject(actor: SessionActor, text: str) -> None:
    await actor.emit(message_event(user_message(actor, text, "interject", debate=meta(actor))))


def extend_round(actor: SessionActor) -> None:
    actor.mode.extend = True
    debate_verdict.discard(actor)   # D14: the verdict work made for this transcript is dropped


def skip_to_closing(actor: SessionActor) -> None:
    actor.mode.skip_to_closing = True
    debate_verdict.discard(actor)


async def pause(actor: SessionActor) -> None:
    actor.held = True
    debate_plan.stale(actor)   # D8: Play plans the faces afresh; an announced member stays
    await actor.emit({"type": "session.paused", "payload": {"reason": "user"}})


async def resume(actor: SessionActor) -> None:
    actor.held = False
    await actor.emit({"type": "session.resumed", "payload": {"reason": "user"}})
    if debate_verdict.needs_rerun(actor):   # D14's resume rule: the cap-refusal hang is gone
        debate_verdict.resume(actor)
    elif not actor.busy and len(actor.turns) == 0:
        step(actor)


async def end_debate(actor: SessionActor, with_verdict: bool) -> None:
    """D14: "Go to verdict now" takes the stored verdict work out before the clear and puts it back, so work made for
    this transcript is reused (End right after the last closing never pays twice); a streaming argument finishes first
    (the verdict job runs after its turn job)."""
    work = debate_verdict.take(actor) if with_verdict else None
    await actor.clear(keep_current=True)
    actor.held = False
    if with_verdict:
        debate_verdict.put_back(actor, work)
        await go_verdict(actor)
    else:
        await finish(actor)


async def pick(actor: SessionActor, side: str) -> None:
    """D14: the click only records the side; the verdict is delivered by a job when the work is done."""
    debate_verdict.pick(actor, side)


async def set_auto_advance(actor: SessionActor, on: bool) -> None:
    await actor.emit(patch_settings({"config": {**cfg_of(actor), "autoAdvance": on}}))
    if on and not actor.held and not actor.busy:
        step(actor)

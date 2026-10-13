"""Group (session-modes "Group responders", "Group routing is traced", "Group steering commands"; a port of
`mock/engines/group.ts`).

`send` posts the user's message, then one queued job asks the router (mentions first, then the policy: `auto` up to 2
responders in all, `everyone`, `mentioned`), and runs the speakers in order. Muted participants are skipped as `muted`,
exhausted unmentioned ones as `exhausted`; every reply of the send carries the routing trace and the route call.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

from horizon.ai.contexts import CastPlan, CueKind, RouteContext
from horizon.ai.ports import RoutingDecision
from horizon.gateway.errors import ProviderError
from horizon.sessions.context import session_context
from horizon.sessions.follow import answer_then_follow, second_reply
from horizon.sessions.modes.common import (
    asleep_note,
    is_asleep,
    last_user_text,
    message_event,
    runner,
    speak_then,
    user_message,
)
from horizon.sessions.plans import cast_request, plan_cast, plans_cast
from horizon.sessions.prefetch import Prefetch
from horizon.sessions.retrieve import start_query
from horizon.sessions.turn import TurnSpec

if TYPE_CHECKING:
    from horizon.sessions.actor import SessionActor

Wire = dict[str, Any]


def policy_of(actor: SessionActor) -> str:
    cfg = actor.session.get("config") or {}
    return str(cfg.get("responderPolicy", "auto"))


async def run_speakers(actor: SessionActor, speakers: list[str], prompt: str, *, forced: set[str] | None = None,
                       forced_by: str | None = None, decision: RoutingDecision | None = None,
                       skipped: list[Wire] | None = None, prefetch: bool = False,
                       cast_plan: CastPlan | None = None) -> None:
    """Speakers one after another inside the current job; a `clear()` (stop, leave, cap pause) ends the run at the
    next boundary. With `prefetch` (everyone-answer, design D5), up to 2 later speakers are generated ahead."""
    epoch = actor.epoch
    forced = forced or set()
    ahead: dict[int, Prefetch] = {}
    limit = actor.rt.runtime_cfg.runtime.prefetch_max
    try:
        for i, cid in enumerate(speakers):
            if actor.epoch != epoch:
                return
            pf = ahead.pop(i, None)
            if pf is None and await is_asleep(actor, cid):
                await asleep_note(actor, cid, skipping=cid not in forced)
                continue
            if prefetch:
                for j in range(i + 1, min(len(speakers), i + 1 + limit)):
                    if j not in ahead and actor.epoch == epoch and not await is_asleep(actor, speakers[j]):
                        p = await Prefetch.start(actor, _spec(speakers[j], j, prompt, forced, forced_by, decision, skipped,
                                                              cast_plan))
                        if p is not None:
                            ahead[j] = p
            await speak_then(actor, _spec(cid, i, prompt, forced, forced_by, decision, skipped, cast_plan), prefetch=pf)
    finally:
        for p in ahead.values():
            await p.discard()


def _spec(cid: str, i: int, prompt: str, forced: set[str], forced_by: str | None, decision: RoutingDecision | None,
          skipped: list[Wire] | None, cast_plan: CastPlan | None = None) -> TurnSpec:
    is_forced = cid in forced
    if cast_plan is not None:
        return _planned_spec(cid, i, prompt, is_forced, forced_by, skipped, cast_plan)
    routing: Wire | None = None
    if decision is not None and (decision.candidates or decision.fallback):
        routing = {"question": decision.question, "selected": cid}
        if decision.candidates:
            routing["candidates"] = decision.candidates
        if is_forced:
            routing["forcedBy"] = forced_by or "mention"
        if skipped:
            routing["skipped"] = skipped
        if decision.fallback:
            routing["reason"] = "fallback"
    return TurnSpec(
        speaker=cid, prompt=prompt, forced_by=(forced_by or "mention") if is_forced else None,
        message={"forcedSpeaker": True} if is_forced else None, skipped=skipped if i == 0 else None,
        routing=routing, calls=[decision.call] if decision is not None and decision.call else [],
        system1=decision.system1 if decision is not None else None)


def _planned_spec(cid: str, i: int, prompt: str, is_forced: bool, forced_by: str | None, skipped: list[Wire] | None,
                  plan: CastPlan, cue: CueKind | None = None) -> TurnSpec:
    """A reply started by a cast plan (M10, group-watch D5, D22): the plan's routing and its per-turn plan. The plan's
    call and rows travel in that per-turn plan (`TurnRunner` lists them), so the spec carries neither."""
    who = plan.who
    routing: Wire | None = None
    if who is not None and who.question:
        routing = {"question": who.label, "selected": cid}
        fell = who.source in ("fallback", "late")
        if who.candidates and not fell:
            routing["candidates"] = who.candidates
        if is_forced:
            routing["forcedBy"] = forced_by or "mention"
        if skipped:
            routing["skipped"] = skipped
        if fell:
            routing["reason"] = "fallback"
    return TurnSpec(
        speaker=cid, prompt=prompt, forced_by=(forced_by or "mention") if is_forced else None,
        message={"forcedSpeaker": True} if is_forced else None, skipped=skipped if i == 0 else None,
        routing=routing, plan=plan.for_speaker(cid, cue=cue))


async def _eligibility(actor: SessionActor, mentions: list[str]) -> tuple[list[str], list[Wire], list[str]]:
    """(eligible, skipped, live mentions): deleted characters are `archived` and never routed, even if mentioned;
    muted ones are `muted`; exhausted unmentioned ones `exhausted`."""
    skipped: list[Wire] = []
    eligible: list[str] = []
    gone: set[str] = set()
    for p in actor.session["participants"]:
        cid = p["characterId"]
        if await runner(actor).energy_now(cid) is None:  # deleted (a tombstone, M4): never routed, even if mentioned
            gone.add(cid)
            skipped.append({"characterId": cid, "reason": "archived"})
        elif p.get("mutedByUser"):
            skipped.append({"characterId": cid, "reason": "muted"})
        elif cid not in mentions and await is_asleep(actor, cid):
            skipped.append({"characterId": cid, "reason": "exhausted"})
        else:
            eligible.append(cid)
    return eligible, skipped, [m for m in mentions if m not in gone]


async def _route(actor: SessionActor, text: str, mentions: list[str]) -> tuple[RoutingDecision, list[Wire]]:
    eligible, skipped, mentions = await _eligibility(actor, mentions)
    sctx = await session_context(actor.rt, actor)
    last: dict[str, int] = {}
    for m in sctx.recent:
        if m.character_id:
            last[m.character_id] = m.seq
    rctx = RouteContext(session=sctx, text=text, mentions=mentions, eligible=eligible, policy=policy_of(actor),
                        turn_index=actor.mode.turn, last_spoke=last)
    router = actor.rt.ai.router(runner(actor).key_set())
    return await router.route(rctx), skipped


async def send(actor: SessionActor, text: str, mentions: list[str]) -> None:
    msg = user_message(actor, text)
    await actor.emit(message_event(msg))
    members = {p["characterId"] for p in actor.session["participants"]}
    start_query(actor, text, str(msg["id"]), sorted(members))  # M5 design D12: in parallel with routing
    mentions = [m for m in mentions if m in members]

    async def job() -> None:
        if await _all_mentions_asleep(actor, mentions):
            return   # G1 (every profile): the user addressed someone asleep; nobody else answers
        if plans_cast(actor) and await _planned(actor, text, mentions):
            return
        try:
            decision, skipped = await _route(actor, text, mentions)
        except ProviderError:
            return  # a cap refusal pauses the session (design D7); nothing else runs for this send
        if not decision.speakers and policy_of(actor) == "mentioned":
            return  # the UI shows "Mention someone with @…"
        await run_speakers(actor, decision.speakers, text, forced=set(mentions), decision=decision, skipped=skipped)

    actor.enqueue(job)


async def _all_mentions_asleep(actor: SessionActor, mentions: list[str]) -> bool:
    """Doc 07 G1 (group-watch D5, D6): when every mentioned character is asleep, each gets the asleep note with Top up
    and nobody else answers. Deleted characters don't count as mentioned."""
    live = [m for m in mentions if await runner(actor).energy_now(m) is not None]
    if not live or not all([await is_asleep(actor, m) for m in live]):
        return False
    for m in live:
        await asleep_note(actor, m, skipping=False)
    return True


async def _planned(actor: SessionActor, text: str, mentions: list[str]) -> bool:
    """Group under a planner that plans the cast (`agent`; group-watch D5, D11). False: the planner gave no plan, and
    the router answers instead."""
    eligible, skipped, mentions = await _eligibility(actor, mentions)
    policy = policy_of(actor)
    awake = [m for m in mentions if not await is_asleep(actor, m)]
    rest = [c for c in eligible if c not in mentions]
    if policy == "everyone":
        pool = [*awake, *rest]
        if not pool:
            return True
        plan = await plan_cast(actor, await cast_request(actor, "everyone", pool, latest=text))
        if plan is None:
            return False
        order = [*mentions, *(c for c in plan.order if c not in mentions)]
        await run_speakers(actor, order, text, forced=set(mentions), skipped=skipped, cast_plan=plan)
        return True
    if mentions or policy == "mentioned":
        if not mentions:
            return True   # the UI shows the hint to mention someone
        plan = await plan_cast(actor, await cast_request(actor, "group_mentioned", awake, latest=text, forced=awake,
                                                         forced_by="mention"))
        if plan is None:
            return False
        if policy == "auto" and len(mentions) == 1:   # G1: one mention may get a second voice from the follow plan
            await _with_follow(actor, _planned_spec(mentions[0], 0, text, True, "mention", skipped, plan), text)
            return True
        await run_speakers(actor, mentions, text, forced=set(mentions), skipped=skipped, cast_plan=plan)
        return True
    if not rest:
        return True
    plan = await plan_cast(actor, await cast_request(actor, "group_first", rest, latest=text))
    if plan is None:
        return False
    await _with_follow(actor, _planned_spec(plan.order[0], 0, text, False, None, skipped, plan), text)
    return True


async def _with_follow(actor: SessionActor, first: TurnSpec, text: str) -> None:
    """The first reply, then the follow plan's optional second (doc 07 G2; group-watch D8)."""
    await answer_then_follow(actor, first, text, lambda fp, cid, name: second_reply(fp, cid, name, prompt=text))


def everyone_answer(actor: SessionActor) -> None:
    speakers = [p["characterId"] for p in actor.session["participants"] if not p.get("mutedByUser")]
    prompt = last_user_text(actor)

    async def job() -> None:
        await run_speakers(actor, speakers, prompt, prefetch=True)

    actor.enqueue(job)


async def next_speaker(actor: SessionActor, character_id: str | None) -> None:
    pick = character_id
    if not pick:
        from horizon.services.runtime.reducer import ordered_messages

        last = next((m["author"].get("characterId") for m in reversed(ordered_messages(actor.state))
                     if m["author"]["type"] == "character"), None)
        pool = [p["characterId"] for p in actor.session["participants"]
                if not p.get("mutedByUser") and p["characterId"] != last and not await is_asleep(actor, p["characterId"])]
        pick = random.Random(f"{actor.seed}:next:{actor.mode.turn}").choice(pool) if pool else None
    if not pick:
        return
    chosen = pick

    async def job() -> None:
        await run_speakers(actor, [chosen], "", forced={character_id} if character_id else None, forced_by="nudge")

    actor.enqueue(job)

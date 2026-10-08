"""Group (session-modes "Group responders", "Group routing is traced", "Group steering commands"; a port of
`mock/engines/group.ts`).

`send` posts the user's message, then one queued job asks the router (mentions first, then the policy: `auto` up to 2
responders in all, `everyone`, `mentioned`), and runs the speakers in order. Muted participants are skipped as `muted`,
exhausted unmentioned ones as `exhausted`; every reply of the send carries the routing trace and the route call.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

from horizon.ai.contexts import RouteContext
from horizon.ai.ports import RoutingDecision
from horizon.gateway.errors import ProviderError
from horizon.sessions.context import session_context
from horizon.sessions.modes.common import (
    asleep_note,
    is_asleep,
    last_user_text,
    message_event,
    runner,
    speak_then,
    user_message,
)
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
                       skipped: list[Wire] | None = None, prefetch: bool = False) -> None:
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
                        p = await Prefetch.start(actor, _spec(speakers[j], j, prompt, forced, forced_by, decision, skipped))
                        if p is not None:
                            ahead[j] = p
            await speak_then(actor, _spec(cid, i, prompt, forced, forced_by, decision, skipped), prefetch=pf)
    finally:
        for p in ahead.values():
            await p.discard()


def _spec(cid: str, i: int, prompt: str, forced: set[str], forced_by: str | None, decision: RoutingDecision | None,
          skipped: list[Wire] | None) -> TurnSpec:
    is_forced = cid in forced
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
        routing=routing, calls=[decision.call] if decision is not None and decision.call else [])


async def _route(actor: SessionActor, text: str, mentions: list[str]) -> tuple[RoutingDecision, list[Wire]]:
    s = actor.session
    skipped: list[Wire] = []
    eligible: list[str] = []
    gone: set[str] = set()
    for p in s["participants"]:
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
    sctx = await session_context(actor.rt, actor)
    last: dict[str, int] = {}
    for m in sctx.recent:
        if m.character_id:
            last[m.character_id] = m.seq
    mentions = [m for m in mentions if m not in gone]
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
        try:
            decision, skipped = await _route(actor, text, mentions)
        except ProviderError:
            return  # a cap refusal pauses the session (design D7); nothing else runs for this send
        if not decision.speakers and policy_of(actor) == "mentioned":
            return  # the UI shows "Mention someone with @…"
        await run_speakers(actor, decision.speakers, text, forced=set(mentions), decision=decision, skipped=skipped)

    actor.enqueue(job)


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

"""The follow plan through the runtime (M10; doc 07 G2, doc 11 S5; doc 13 W1; group-watch design D8, D9;
follow-plan spec).

`answer_then_follow` runs a group's (or Step in's) first reply with a follow hook: at the stream's end the planner
starts the follow plan; at `turn.end` the mode waits for it until `turn.end` + `timeoutsMs.decision.follow_plan`,
which **replaces** the turn gap for this step. A pick starts the second reply at once, with the follow plan's face
and the cue naming the first replier. No pick (`none`, unsure, late, failed) sends nothing: the rows and the call go on
the first reply's trace through `append_system1` (W1), and the job sleeps what is left of the turn gap.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from horizon.ai.contexts import FollowPlan, FollowRequest, MessageNouls
from horizon.domain import vclock
from horizon.sessions.context import character_view, characters, document_titles, session_context
from horizon.sessions.modes.common import gap, is_asleep, runner, speak_then
from horizon.sessions.plans import base_faces, manual, turns_since
from horizon.sessions.turn import TurnOutcome, TurnSpec

if TYPE_CHECKING:
    from horizon.sessions.actor import SessionActor, TurnInfo

Wire = dict[str, Any]
PURPOSE = "follow_plan"


def follow_hook(actor: SessionActor, message: str, nouls: MessageNouls | None = None) -> Callable[[TurnInfo], Any]:
    """The hook `TurnRunner` calls at the first reply's stream end (S5): candidates are the cast that can speak now,
    minus whoever answered this message. M12 (rag D8): the cast plan's "standalone?" / "English?" ride along."""
    async def start(info: TurnInfo) -> Any:
        rt = actor.rt
        sctx = await session_context(rt, actor)
        cands: list[str] = []
        for p in sctx.participants:
            cid = p.character_id
            if cid == info.character_id or p.muted:
                continue
            if await runner(actor).energy_now(cid) is None or await is_asleep(actor, cid):
                continue
            cands.append(cid)
        if not cands:
            return None
        rows = await characters(rt, cands)
        planner = rt.ai.planner(rt.keys.status() == "set")
        docs = await document_titles(rt, sctx.world.id, cands) if getattr(planner, "decides_retrieval", False) else {}
        req = FollowRequest(session=sctx, first_id=info.character_id, first_name=sctx.name_of(info.character_id),
                            first_message_id=info.message_id, first_text=info.content, message=message,
                            candidates=cands, cast=[character_view(rows[c]) for c in cands if c in rows],
                            turn_index=actor.mode.turn, base_faces=base_faces(actor, sctx, cands), manual=manual(actor),
                            turns_since=turns_since(actor, cands), started_at=rt.clock.now(), documents=docs,
                            nouls=nouls)
        return planner.start_follow(req)

    return start


async def answer_then_follow(actor: SessionActor, first: TurnSpec, message: str,
                             second_spec: Callable[[FollowPlan, str, str], TurnSpec]) -> TurnOutcome:
    """The first reply, then at most one second reply chosen by the follow plan (MULTI-03's cap of 2). A user message
    that supersedes the job (G5) ends the wait at once and cancels the follow plan (its ledger row: `cancelled`)."""
    rt = actor.rt
    epoch = first.epoch
    first.follow = follow_hook(actor, message, first.plan.nouls if first.plan is not None else None)
    out = await runner(actor).run(actor, first)
    turn_gap = rt.runtime_cfg.timing.turn_gap_ms / 1000
    if out.status not in ("complete", "interrupted", "error"):
        return out
    if out.follow is None or out.ended_at is None:
        await gap(actor, epoch)
        return out
    deadline = out.ended_at + timedelta(seconds=rt.decider.timeout_for(PURPOSE))
    plan = await _wait_follow(actor, out.follow, deadline, epoch)
    if plan is None:
        return out   # superseded: the new message is answered instead
    if plan.second is None:
        if out.message_id is not None:
            await actor.append_system1(out.message_id, None, plan.rows_for_first(), plan.calls)
        left = (out.ended_at + timedelta(seconds=turn_gap) - rt.clock.now()).total_seconds()
        if left > 0:
            await gap(actor, epoch, left)
        return out
    first_name = (await characters(rt, [first.speaker])).get(first.speaker)
    name = character_view(first_name).first_name if first_name is not None else first.speaker
    second = second_spec(plan, plan.second, name)
    second.epoch = epoch
    return await speak_then(actor, second)


async def _wait_follow(actor: SessionActor, handle: Any, deadline: Any, epoch: int | None) -> FollowPlan | None:
    """`handle.by(deadline)`, unless a user message supersedes `epoch` first (then None, and the handle is cancelled)."""
    if epoch is None:
        plan: FollowPlan = await handle.by(deadline)
        return plan
    task = actor.rt.spawn(f"follow:{actor.sid}", handle.by(deadline))
    try:
        if await vclock.wait_unless(task, actor.superseded(epoch)):
            done: FollowPlan = task.result()
            return done
    except asyncio.CancelledError:
        task.cancel()
        raise
    task.cancel()   # `by` cancels the request: it settles and is recorded `cancelled`
    return None


def second_reply(plan: FollowPlan, cid: str, answered: str, *, prompt: str) -> TurnSpec:
    """The second reply's spec: the follow plan's routing (its question, candidates and pick) and its per-turn plan."""
    who = plan.who
    routing: Wire = {"question": who.label if who is not None else "who speaks up now?", "selected": cid}
    if who is not None and who.candidates:
        routing["candidates"] = who.candidates
    return TurnSpec(speaker=cid, prompt=prompt, routing=routing, plan=plan.for_speaker(cid, answered=answered))

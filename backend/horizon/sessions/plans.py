"""The runtime side of the cast plan (M10; doc 07 G1, G4, G6; group-watch design D3, D5, D11, D13).

Modes ask `plan_cast` here and get `None` back when the profile has no planner for group and watch (`naive`,
`scripted`): they then keep their own routing, so `sessions/` never inspects which implementation runs (ai-ports).
What the runtime reads for the request comes from the actor's state, never from memory that an idle release resets:
- each candidate's base face (docs/ai/06 E2: the face now in AUTO, the last AI-chosen face under MANUAL);
- the character lines since each candidate last spoke (G1's "least recently spoken", G6's guard).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any

from horizon.ai.contexts import CastKind, CastPlan, CastRequest, SessionContext, SteerBlock
from horizon.sessions.context import character_view, characters, session_context

if TYPE_CHECKING:
    from horizon.sessions.actor import SessionActor

Wire = dict[str, Any]


def character_lines(actor: SessionActor, after_seq: int = 0) -> list[Wire]:
    """Character messages after `after_seq`, oldest first."""
    from horizon.services.runtime.reducer import ordered_messages

    return [m for m in ordered_messages(actor.state)
            if m["author"]["type"] == "character" and m["seq"] > after_seq]


def turns_since(actor: SessionActor, ids: Sequence[str], after_seq: int = 0) -> dict[str, int | None]:
    """Character lines since each of `ids` last spoke (0: the last line was theirs); None: not since `after_seq`."""
    lines = character_lines(actor, after_seq)
    out: dict[str, int | None] = {}
    for cid in ids:
        last = next((i for i in range(len(lines) - 1, -1, -1) if lines[i]["author"].get("characterId") == cid), None)
        out[cid] = None if last is None else len(lines) - 1 - last
    return out


def manual(actor: SessionActor) -> bool:
    return bool(actor.session.get("emotionMode") == "user")


def base_faces(actor: SessionActor, sctx: SessionContext, ids: Sequence[str]) -> dict[str, str]:
    """E2: AUTO, the face shown now; MANUAL, each character's last AI-chosen face in this session (else neutral)."""
    if not manual(actor):
        now = {p.character_id: p.emotion for p in sctx.participants}
        return {cid: now.get(cid, "neutral") for cid in ids}
    out: dict[str, str] = {}
    msgs = sorted(actor.state["messages"].values(), key=lambda m: m["seq"])
    for cid in ids:
        mine = [m for m in msgs if m["author"].get("characterId") == cid and m.get("emotion")]
        out[cid] = str(mine[-1]["emotion"]) if mine else "neutral"
    return out


async def cast_request(actor: SessionActor, kind: CastKind, candidates: Sequence[str], *, latest: str = "",
                       forced: Sequence[str] = (), forced_by: Any = None, reason: str | None = None,
                       steer_block: SteerBlock | None = None, scene_start: int = 0,
                       deadline_at: datetime | None = None, sctx: SessionContext | None = None) -> CastRequest:
    rt = actor.rt
    started = rt.clock.now()
    sctx = sctx or await session_context(rt, actor)
    ids = list(dict.fromkeys([*forced, *candidates]))
    rows = await characters(rt, ids)
    return CastRequest(session=sctx, kind=kind, candidates=list(candidates), forced=list(forced), forced_by=forced_by,
                       reason=reason, cast=[character_view(rows[c]) for c in ids if c in rows], latest=latest,
                       turn_index=actor.mode.turn, base_faces=base_faces(actor, sctx, ids), manual=manual(actor),
                       turns_since=turns_since(actor, ids, scene_start), steer_block=steer_block,
                       started_at=started, deadline_at=deadline_at)


async def plan_cast(actor: SessionActor, req: CastRequest) -> CastPlan | None:
    planner = actor.rt.ai.planner(actor.rt.keys.status() == "set")
    plan: CastPlan | None = await planner.plan_cast(req)
    return plan


def plans_cast(actor: SessionActor) -> bool:
    """Whether the resolved planner plans group and watch turns, read from its capability (D18), never its name."""
    return bool(getattr(actor.rt.ai.planner(actor.rt.keys.status() == "set"), "decides_retrieval", False))

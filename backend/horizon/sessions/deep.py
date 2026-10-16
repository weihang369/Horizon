"""The runtime side of the deep work in group, watch and debate (rag design D15; deep-turn "The deep work starts as
early as each mode allows").

A planned reply whose plan went deep needs its speaker's deep work before its request is built. `attach` builds the
frozen `DeepRequest` from the actor's state and starts it through the planner's `start_deep` as an actor background
task (named `deep`, so `clear()` cancels it); `TurnRunner` awaits it before the reply and merges it into the plan.
Modes call `attach` as early as their plan allows (the cast plan landing, the follow plan landing, the plan made ahead,
the member fixed); `TurnRunner` attaches anything still missing at the turn's start.

What is searched (D8, D10):
- **a user message answered** (`group_first`, `group_mentioned`, `everyone`, the second reply): the user's message,
  its two earlier lines, the user message before it (a failed rewrite's extra words), and the plan's nouls;
- **Next speaker, Step in** (`next`, `step_in`) and **watch** (`scene`, `opening`): the last line, and the two earlier
  lines with it; never a rewrite;
- **debate**: the motion plus the last opposing argument (an opening: the motion; an Ask answer: the moderator's
  question plus the motion); never a rewrite, never an abstain.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from horizon.ai.agent.planner import answered_message
from horizon.ai.agent.query import debate_text, earlier_lines
from horizon.ai.contexts import DeepRequest, SessionContext, TurnPlan
from horizon.sessions.context import characters, session_context, speaker_view

if TYPE_CHECKING:
    from horizon.sessions.actor import SessionActor
    from horizon.sessions.turn import TurnSpec

NAME = "deep"
USER_KINDS = frozenset({"reply", "group_first", "group_mentioned", "everyone", "second"})
LINE_KINDS = frozenset({"next", "step_in", "scene", "opening"})
K_MODE = {"one_on_one": "one_on_one", "group": "group", "watch": "watch", "debate": "debate"}


def _last_line(session: SessionContext) -> tuple[str | None, str, list[str]]:
    """(id, "Name: text", the two lines before it) of the last user or character line in the window."""
    you = str((session.world.you or {}).get("displayName") or "") or "the user"
    lines = [m for m in session.recent if m.content and m.author_type in ("user", "character")]
    if not lines:
        return None, "", []
    last = lines[-1]
    name = you if last.author_type == "user" else last.name
    return last.id, f"{name}: {last.content}", earlier_lines(session.recent, last.id, you)


async def deep_request(actor: SessionActor, spec: TurnSpec, plan: TurnPlan,
                       sctx: SessionContext | None = None) -> DeepRequest | None:
    rt = actor.rt
    sctx = sctx or await session_context(rt, actor)
    row = (await characters(rt, [spec.speaker])).get(spec.speaker)
    if row is None:
        return None
    knobs = rt.runtime_cfg.runtime.retrieval.agent
    kind = plan.source_kind or "reply"
    k = knobs.k_for(K_MODE.get(sctx.mode, "group")) if knobs is not None else 2
    from horizon.ai.agent import gates
    from horizon.sessions.context import recall_scope

    common: dict[str, Any] = {"session": sctx, "speaker": await speaker_view(rt, actor, row), "kind": kind, "gate": plan.gate,
                              "abstain_ok": plan.abstain_ok, "k": k, "started_at": rt.clock.now(),
                              # M13 (memory D34): which branches run, and recall's scope
                              "docs": gates.deep(plan.gate), "recall": gates.recalls(plan.recall_gate),
                              "recall_gate": plan.recall_gate, **await recall_scope(rt, actor, spec.speaker)}
    if sctx.mode == "debate":
        cfg = sctx.config or {}
        motion = str(cfg.get("motion") or "")
        if kind == "debate_ask":
            return DeepRequest(**common, message=debate_text(motion, question=spec.prompt), motion=motion,
                               argument=spec.prompt)
        if kind == "debate_opening" or (spec.debate is not None and spec.debate.phase == "opening"):
            return DeepRequest(**common, message=debate_text(motion), motion=motion)
        argument = _last_opposing(actor, spec)
        return DeepRequest(**common, message=debate_text(motion, argument=argument), motion=motion, argument=argument)
    if kind in LINE_KINDS or sctx.mode == "watch":
        mid, line, earlier = _last_line(sctx)
        return DeepRequest(**common, message=line, message_id=mid, earlier=earlier)
    mid, earlier, previous = answered_message(sctx)
    stored = None
    if kind in USER_KINDS and mid is not None:
        from horizon.services.ai_meta import stored_rewrite

        stored = await stored_rewrite(rt, mid, spec.speaker)
    return DeepRequest(**common, message=spec.prompt or (sctx.recent[-1].content if sctx.recent else ""),
                       message_id=mid, earlier=earlier, previous_user=previous, nouls=plan.nouls,
                       stored_rewrite=stored)


def _last_opposing(actor: SessionActor, spec: TurnSpec) -> str:
    """The last argument by the other side (by anyone else in a panel), "Name: text" (doc 01 A6, V2)."""
    from horizon.services.runtime.reducer import ordered_messages
    from horizon.sessions.modes.debate import side_of

    mine = side_of(actor, spec.speaker)
    for m in reversed(ordered_messages(actor.state)):
        if m["author"]["type"] != "character" or not m.get("content") or not (m.get("debate") or {}).get("phase"):
            continue
        cid = m["author"].get("characterId")
        if cid == spec.speaker:
            continue
        if mine is None or side_of(actor, cid) != mine:
            name = next((p.get("name") for p in actor.session["participants"] if p["characterId"] == cid), None)
            return f"{name or cid}: {m['content']}"
    return ""


async def attach(actor: SessionActor, spec: TurnSpec, sctx: SessionContext | None = None) -> None:
    """Start the speaker's deep work for a planned reply that went deep (no-op otherwise, or when already started)."""
    plan = spec.plan
    if plan is None or plan.branch != "deep" or spec.deep is not None:
        return
    rt = actor.rt
    start = getattr(rt.ai.planner(rt.keys.status() == "set"), "start_deep", None)
    if start is None:
        return
    req = await deep_request(actor, spec, plan, sctx)
    if req is None:
        return
    spec.deep = start(req, spawn=lambda name, coro: actor.background(NAME, coro))

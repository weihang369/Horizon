"""The `agent` turn planner: Jev call 1 on the plan graph (docs/ai/01 A4, A5; docs/ai/06 E1–E3; turn-plan-emotion design
D3, D4, D6, D7, D10, D12, D13; turn-plan spec).

In M9 it plans `agent` 1:1 turns and asks one question per candidate: the emotion (`emotion_reply`, or
`emotion_greeting` for a generated greeting). No gate is asked, so `route` is always quick (W4: every 1:1 turn is
quick until M12).

- **state:** M8's `build_turn_plan_state`, imported unchanged, with no document titles (no gate reads them yet).
- **ask:** one `turn_plan` request through the `Decider`, waited for until `started_at` + the `turn_plan` deadline. A
  late, failed, refused or oversized call is a fallback at once; a late answer is still billed and then discarded
  (W11). Cancelling the plan (Stop) detaches the readers and lets the request settle (D8).
- **decide:** `decide_face` per candidate, and one System 1 row each.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from horizon.ai.agent.emotion import decide_face, emotion_row
from horizon.ai.agent.persona import first_name
from horizon.ai.agent.plan_graph import Branch, build_plan_graph, run_plan
from horizon.ai.agent.plan_state import Candidate, PlanState, PlanStateInput, build_turn_plan_state
from horizon.ai.contexts import CastPlan, CastRequest, FollowRequest, PlanRequest, TurnPlan
from horizon.ai.decider import Answers, ChoiceAnswer, DecisionResult
from horizon.ai.questions import bank

log = logging.getLogger("horizon.ai.planner")

PURPOSE = "turn_plan"
QUESTION = {"reply": "emotion_reply", "greeting": "emotion_greeting"}
NAME_MAX = 40


def _name(full: str) -> str:
    """The name the question uses: the cast's name, or the first name when the full one is over the label limit."""
    return full if len(full) <= NAME_MAX else first_name(full)[:NAME_MAX]


def _turns_since(req: PlanRequest, character_id: str) -> int | None:
    """Character lines since this character last spoke in the window (0: the last line was theirs)."""
    n = 0
    for m in reversed(req.session.recent):
        if m.author_type != "character":
            continue
        if m.character_id == character_id:
            return n
        n += 1
    return None


def plan_state_input(req: PlanRequest) -> PlanStateInput:
    """X9's input for this turn. The latest user line is `latest`, so it isn't repeated in `recent`."""
    s = req.session
    profiles = {c.id: c for c in req.cast}
    cands = []
    for cid in [req.speaker_id]:
        view = profiles.get(cid)
        part = next((p for p in s.participants if p.character_id == cid), None)
        name = part.name if part is not None else (view.name if view is not None else cid)
        profile: dict[str, Any] = view.profile if view is not None else {}
        about = str((profile.get("personality") or {}).get("summary") or "")
        cands.append(Candidate(id=cid, name=name, role=part.character_role if part is not None else "",
                               about_source=about, face=req.base_face, turns_since=_turns_since(req, cid)))
    recent = [m for m in s.recent if m.content]
    if req.latest and recent and recent[-1].author_type == "user":
        recent = recent[:-1]
    you = str((s.world.you or {}).get("displayName") or "")
    lines = [{"speaker": (you or "the user") if m.author_type == "user" else m.name, "text": m.content} for m in recent]
    return PlanStateInput(mode=s.mode, user_name=you, candidates=cands, latest=req.latest, recent=lines)


class JevTurnPlanner:
    decides_retrieval = True   # M10 (group-watch D18): a planned turn's retrieval follows the plan's branch

    def __init__(self, deps: Any) -> None:
        self.deps = deps
        self.graph = build_plan_graph(self)
        from horizon.ai.agent.cast_plan import CastSteps

        self.cast_graph = build_plan_graph(CastSteps(deps))   # M10: group and watch (D3, D4)

    async def plan_cast(self, req: CastRequest) -> CastPlan | None:
        """M10 (group-watch D3–D7, D11, D13, D14): who speaks and every candidate's face, in one `turn_plan` request.
        Never raises except CancelledError: a bug costs the faces and Jev's pick, never the reply."""
        from horizon.ai.agent.cast_plan import fallback_plan

        try:
            plan, path = await run_plan(self.cast_graph, req)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("the cast plan failed for %s; falling back", req.session.session_id)
            return fallback_plan(req, self.deps)
        out: CastPlan = plan.model_copy(update={"graph_path": path})
        return out

    def start_follow(self, req: FollowRequest) -> Any:
        return None   # phase 4 (group-watch D8)

    # ── the port ──
    async def plan(self, req: PlanRequest) -> TurnPlan | None:
        try:
            plan, path = await run_plan(self.graph, req)
        except asyncio.CancelledError:
            raise
        except Exception:   # the port never raises (ai/ports.py): a bug here costs the face, never the reply
            log.exception("the turn plan failed for %s; keeping the face", req.speaker_id)
            face = decide_face(None, base=req.base_face, floor=0.6, fade=self.deps.emotion_fade(), manual=req.manual)
            qid = QUESTION[req.kind]
            entry = bank().get(qid)
            row = emotion_row(face, qid=qid, version=entry.version, label=entry.label, about=req.speaker_id)
            return TurnPlan(seed=self.seed(req), kind=req.kind, branch="quick", emotion=face, rows=[row])
        out: TurnPlan = plan.model_copy(update={"graph_path": path, "branch": self.route(req, plan)})
        return out

    # ── the graph's steps (plan_graph.PlanSteps) ──
    async def state(self, req: PlanRequest) -> PlanState:
        return build_turn_plan_state(plan_state_input(req))

    async def ask(self, req: PlanRequest, state: PlanState) -> tuple[DecisionResult, dict[str, Any]]:
        qid = QUESTION[req.kind]
        cid = req.speaker_id
        name = next((p.name for p in req.session.participants if p.character_id == cid), cid)
        key = f"{qid}:{cid}"
        q = bank().question(qid, seed=f"{self.seed(req)}:{cid}", name=_name(name), about=cid)

        async def fallback() -> Answers:
            return {key: ChoiceAnswer("none")}

        decider = self.deps.decider()
        ctx = req.session.call_ctx(PURPOSE, character_id=cid, message_id=req.message_id)
        call = decider.start(state.state, {key: q}, ctx, purpose=PURPOSE, fallback=fallback)
        try:
            res: DecisionResult = await call.by(req.started_at + timedelta(seconds=decider.timeout_for(PURPOSE)))
        except asyncio.CancelledError:
            call.cancel()   # D8: readers detach; the request already sent settles and is recorded `cancelled`
            raise
        return res, {"key": key, "qid": qid, "version": q.meta.version if q.meta else 0,
                     "label": q.meta.label if q.meta else "emotion", "timeout_s": decider.timeout_for(PURPOSE)}

    def decide(self, req: PlanRequest, state: PlanState, result: tuple[DecisionResult, dict[str, Any]]) -> TurnPlan:
        res, meta = result
        entry = bank().get(meta["qid"])
        answer = res.answers.get(meta["key"])
        face = decide_face(answer if isinstance(answer, ChoiceAnswer) else None, base=req.base_face,
                           floor=entry.floor if entry.floor is not None else 0.6, fade=self.deps.emotion_fade(),
                           manual=req.manual, failure=res.failure)
        row = emotion_row(face, qid=meta["qid"], version=meta["version"], label=meta["label"], about=req.speaker_id)
        calls: list[dict[str, Any]] = []
        if face.outcome in ("fallback", "late"):   # a fallback has no ledger row of its own by turn.end (the router's rule)
            calls.append({"purpose": PURPOSE, "model": self.deps.prices.decision.model, "costUsd": 0.0,
                          "latencyMs": float(meta["timeout_s"] * 1000), "fallback": True})
        return TurnPlan(seed=self.seed(req), kind=req.kind, emotion=face, rows=[row], calls=calls,
                        state_tokens=state.tokens, dropped_gates=list(state.dropped_gates))

    def route(self, req: PlanRequest, plan: TurnPlan) -> Branch:
        return "quick"   # M12 adds "deep" when a gate says documents are needed

    @staticmethod
    def seed(req: PlanRequest) -> str:
        return f"{req.session.seed}:{req.turn_index}"

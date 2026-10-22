"""The `agent` turn planner: Jev call 1 on the plan graph (docs/ai/01 A4, A5; docs/ai/06 E1–E3; turn-plan-emotion design
D3, D4, D6, D7, D10, D12, D13; turn-plan spec).

It plans `agent` 1:1 turns and asks one question per candidate: the emotion (`emotion_reply`, or `emotion_greeting`
for a generated greeting). M12 (rag D6–D8): a reply to a speaker with searchable documents also asks "needs
documents?" about them, and "standalone?" and "English?" about the message, in the same request; `route` answers
deep when the speaker's gate is at or above `t_gate`. A generated greeting asks no gate.

- **state:** M8's `build_turn_plan_state`, with the speaker's document titles when the gate is asked.
- **ask:** one `turn_plan` request through the `Decider`, waited for until `started_at` + the `turn_plan` deadline. A
  late, failed, refused or oversized call is a fallback at once; a late answer is still billed and then discarded
  (W11). Cancelling the plan (Stop) detaches the readers and lets the request settle (D8).
- **decide:** `decide_face` per candidate, and one System 1 row each; the gate rows (D20).
- M14 (safety D4–D6): a reply to a user line with no stored safety answer also asks "unsafe request?" and "at risk?"
  in the same request; the frozen plan carries the cue (`TurnPlan.safety`), stored answers included.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from horizon.ai.agent import gates
from horizon.ai.agent import safety as sf
from horizon.ai.agent.emotion import decide_face, emotion_row
from horizon.ai.agent.persona import first_name
from horizon.ai.agent.plan_graph import Branch, build_plan_graph, run_plan
from horizon.ai.agent.plan_state import Candidate, PlanState, PlanStateInput, build_turn_plan_state
from horizon.ai.agent.query import earlier_lines
from horizon.ai.contexts import (
    CastPlan,
    CastRequest,
    DebateRequest,
    DeepRequest,
    FollowRequest,
    PlanRequest,
    SessionContext,
    TurnContext,
    TurnPlan,
)
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
    docs = {req.speaker_id: list(req.documents[req.speaker_id])} \
        if req.kind == "reply" and req.documents.get(req.speaker_id) else {}
    return PlanStateInput(mode=s.mode, user_name=you, candidates=cands, latest=req.latest, recent=lines,
                          documents=docs)


def answered_message(session: SessionContext) -> tuple[str | None, list[str], str]:
    """The user message a 1:1 or group reply answers: (its id, the two lines before it, the user message before
    that), read from the window (M12, rag D10)."""
    you = str((session.world.you or {}).get("displayName") or "") or "the user"
    users = [m for m in session.recent if m.author_type == "user" and m.content]
    if not users:
        return None, [], ""
    last = users[-1]
    return last.id, earlier_lines(session.recent, last.id, you), users[-2].content if len(users) > 1 else ""


class JevTurnPlanner:
    decides_retrieval = True   # M10 (group-watch D18): a planned turn's retrieval follows the plan's branch
    asks_safety = True         # M14 (safety D4): every plan asks the safety questions about a new user line

    def __init__(self, deps: Any) -> None:
        self.deps = deps
        from horizon.ai.agent.deep import DeepSteps, build_deep_graph

        self.deep_graph = build_deep_graph(DeepSteps(deps))   # M12 (rag D15): one graph for every mode
        self.graph = build_plan_graph(self)
        from horizon.ai.agent.cast_plan import CastSteps

        self.cast_graph = build_plan_graph(CastSteps(deps))   # M10: group and watch (D3, D4)
        from horizon.ai.agent.follow_plan import FollowSteps

        self._follow = FollowSteps(deps)
        self.follow_graph = build_plan_graph(self._follow)   # M10: the follow plan (D4, D8)
        from horizon.ai.agent.debate_plan import DebateSteps

        self._debate = DebateSteps(deps)
        self.debate_graph = build_plan_graph(self._debate)   # M11: the debate plan (debate D5, D8)

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
        """M10 (doc 07 G2; group-watch D8): start the follow plan at the first reply's stream end. None when nobody is
        left to ask; a bug here costs the second reply, never the session."""
        if not req.candidates:
            return None
        try:
            return self._follow.start(self, req)
        except Exception:
            log.exception("the follow plan could not start after %s", req.first_id)
            return None

    def start_debate(self, req: DebateRequest) -> Any:
        """M11 (doc 08 V2; debate D5, D8): start the debate plan at `turn.end` for the next slot. None when nobody is
        eligible; a bug here costs Jev's pick and faces (fixed order, kept faces), never the debate."""
        if not req.candidates:
            return None
        try:
            return self._debate.start(self, req)
        except Exception:
            log.exception("the debate plan could not start in %s", req.session.session_id)
            return None

    def start_deep(self, req: DeepRequest, *, spawn: Any = None) -> Any:
        """M12 (rag D15): one speaker's deep work, started as soon as the speaker is known and their gate said yes
        (group, watch, debate). Returns a `DeepCall` the turn awaits; a bug inside gives a quick turn. `spawn`: the
        runtime's owner for the task (the actor's background, so `clear()` cancels it)."""
        from horizon.ai.agent.deep import DeepCall

        try:
            return DeepCall(self.deps, self.deep_graph, req, spawn)
        except Exception:
            log.exception("the deep work could not start for %s", req.speaker.id)
            return None

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
            cue = sf.decide(req.safety, None)   # M14: a bug is a failed answer: no cue, flagged, nothing stored
            return TurnPlan(seed=self.seed(req), kind=req.kind, branch="quick", emotion=face,
                            rows=[row, *sf.rows(cue, purpose=PURPOSE)], safety=cue)
        branch = plan.branch if plan.branch is not None else self.route(req, plan)
        out: TurnPlan = plan.model_copy(update={"graph_path": [*path, *plan.graph_path], "branch": branch})
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
        gated = gates.gated([cid], req.documents, state.dropped_gates) if req.kind == "reply" else []
        # M13 (memory D26): "needs something from earlier?" only with something to search, and not dropped by X9
        recalling = gates.recall_asked([cid], req.recallable, state.dropped_gates) if req.kind == "reply" else []
        qs = {key: q, **gates.questions({cid: name}, gated, nouls=True, recall=recalling),
              **sf.questions(req.safety)}   # M14 (safety D4): about the user line, when no answer is stored
        if gated or recalling:   # rag 11.5 (M13 D32: widened): the query embedding starts with Jev call 1
            from horizon.ai.agent import rewrite as rw
            from horizon.ai.agent.deep import start_early_embedding

            mid = answered_message(req.session)[0]
            start_early_embedding(self.deps, req.session, gated or recalling, req.latest, mid,
                                  any_space=bool(recalling))
            if gated and req.cast and not req.stored_rewrite:   # 11.9: so does a short message's rewrite
                rw.start_early(self.deps, TurnContext(session=req.session, speaker=req.cast[0],
                                                      message_id=req.message_id, max_tokens=1), req.latest, mid)

        async def fallback() -> Answers:
            return {key: ChoiceAnswer("none"), **gates.fallbacks(qs), **sf.fallbacks(qs)}

        decider = self.deps.decider()
        ctx = req.session.call_ctx(PURPOSE, character_id=cid, message_id=req.message_id)
        call = decider.start({**state.state, **sf.state_extra(req.safety)}, qs, ctx, purpose=PURPOSE, fallback=fallback)
        try:
            wait = gates.plan_wait(self.deps, decider.timeout_for(PURPOSE), bool(gated))   # U-46
            res: DecisionResult = await call.by(req.started_at + timedelta(seconds=wait))
        except asyncio.CancelledError:
            call.cancel()   # D8: readers detach; the request already sent settles and is recorded `cancelled`
            raise
        return res, {"key": key, "qid": qid, "version": q.meta.version if q.meta else 0,
                     "label": q.meta.label if q.meta else "emotion", "timeout_s": decider.timeout_for(PURPOSE),
                     "gated": gated, "recalling": recalling}

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
        found, nouls = gates.read(res, meta["gated"], nouls=True)
        recall = gates.read_recall(res, meta.get("recalling", []))
        recall.update(gates.dropped([c for c in [req.speaker_id] if c in req.recallable and c in state.dropped_gates]))
        gate, rgate = found.get(req.speaker_id), recall.get(req.speaker_id)
        rows = [row, *gates.speaker_rows(req.speaker_id, found, nouls, purpose=PURPOSE, kind=req.kind,
                                         recall_gates=recall, skips=req.kind == "reply")]
        cue = sf.decide(req.safety, res)   # M14 (safety D4, D19): its rows are shared by the reply
        rows += sf.rows(cue, purpose=PURPOSE)
        return TurnPlan(seed=self.seed(req), kind=req.kind, emotion=face, rows=rows, calls=calls,
                        state_tokens=state.tokens, dropped_gates=list(state.dropped_gates), gate=gate,
                        abstain_ok=gates.abstain_allowed(gate, req.kind), nouls=nouls, recall_gate=rgate, safety=cue)

    def route(self, req: PlanRequest, plan: TurnPlan) -> Branch:
        """M12 (rag D8): deep when the speaker's own gate is at or above `t_gate`. M13 (D26): or its "needs something
        from earlier?" at or above its own."""
        return gates.branch(plan.gate, plan.recall_gate)

    async def deep(self, req: PlanRequest, plan: TurnPlan) -> TurnPlan:
        """M12 (rag D15): the plan graph's deep node in 1:1, so the plan returns with its passages. A bug inside is a
        quick turn with a `fallback` row and call (the port never raises)."""
        from horizon.ai.agent.deep import fallback_result, run_safely

        mid, earlier, previous = answered_message(req.session)
        view = req.cast[0] if req.cast else None
        if view is None:
            return plan.model_copy(update={"branch": "quick"})
        knobs = self.deps.retrieval().agent
        dreq = DeepRequest(session=req.session, speaker=view, kind=req.kind, message=req.latest, message_id=mid,
                           earlier=earlier, previous_user=previous, gate=plan.gate, abstain_ok=plan.abstain_ok,
                           nouls=plan.nouls, stored_rewrite=req.stored_rewrite, k=knobs.k_for("one_on_one"),
                           reply_message_id=req.message_id, started_at=req.started_at,
                           docs=gates.deep(plan.gate), recall=gates.recalls(plan.recall_gate),
                           recall_gate=plan.recall_gate, upto_seq=req.upto_seq, block_ids=list(req.block_ids),
                           has_overflow=req.has_overflow)
        res = await run_safely(self.deep_graph, dreq, self.deps)
        if res is None:
            failed = fallback_result(dreq, self.deps)
            return plan.model_copy(update={"branch": "quick", "rows": [*plan.rows, *failed.rows],
                                           "calls": [*plan.calls, *failed.calls]})
        out: TurnPlan = plan.with_deep(res).model_copy(update={"branch": "deep"})
        return out

    @staticmethod
    def seed(req: PlanRequest) -> str:
        return f"{req.session.seed}:{req.turn_index}"

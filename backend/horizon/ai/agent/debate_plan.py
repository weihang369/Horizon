"""The debate plan: which member of a side fills a rebuttal, closing or panel slot, and each candidate's face (doc 08
V2, V3; doc 13 W5 row 11, W11; debate design D5–D9, D27; debate-plan spec).

- **When:** `start_debate` runs at the previous argument's `turn.end`. It builds the state and sends one
  `debate_plan` request at once.
- **What it asks:** the phase's member question (`member_rebuttal`, `member_closing` or `member_panel`, no `none`)
  when two or more members are eligible, and `emotion_line` per candidate about the argument just made.
- **Two waits on one request** (W11's `by` / `final`): `member(deadline)` fixes who speaks by `turn.end` + the
  `debate_plan` deadline (`turn.next` names them); `faces(until)` reads the same answer when the turn starts, so a
  member that fell back can still get Jev's face. `late_rows()` waits for an answer that missed both, for the trace.
- **The state** (D6): X9's debate fields from M8's builder, with no `last_spoke` (every candidate is "not yet heard";
  the label only pushes Jev towards the fixed order), and only the fields its questions declare (A3 rule 6).
- **The gate** (M12, rag D8): "needs documents?" about each eligible member with a searchable source rides the same
  request (no "standalone?" or "English?": debate never rewrites), with their titles in `quoted_documents`. The member's
  deadline is unchanged; the gate is read with the faces at the turn's start, and one still missing then is quick.
- M13 (memory D26, D27): "needs something from earlier?" (`earlier`) about each eligible member with something to
  search. M14 (safety D4, U4): "unsafe note?" about an Interject not yet checked, in the same request.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from horizon.ai.agent import gates
from horizon.ai.agent import safety as sf
from horizon.ai.agent.cast_plan import candidate_views, ledger_call, recent_lines
from horizon.ai.agent.emotion import decide_face, emotion_row, merges
from horizon.ai.agent.plan_graph import Branch, build_plan_graph, run_plan
from horizon.ai.agent.plan_state import DebateInput, PlanState, PlanStateInput, _tokens, build_turn_plan_state
from horizon.ai.agent.planner import _name
from horizon.ai.contexts import DebatePlan, DebateRequest, PlannedFace, WhoPick
from horizon.ai.decider import Answers, ChoiceAnswer, DecisionCall, DecisionCancelled, DecisionResult, Question
from horizon.ai.questions import bank

log = logging.getLogger("horizon.ai.planner")

PURPOSE = "debate_plan"
FACE = "emotion_line"
MEMBER = {"rebuttal": "member_rebuttal", "closing": "member_closing"}
PANEL = "member_panel"
SIDE_LABEL = {"prop": "Proposition", "opp": "Opposition"}
REASON = "Side by the debate order; speaker chosen by Jev"
REASON_TAIL = {"late": ", next in order: Jev was late", "fallback": ", next in order: Jev was late",
               "below_floor": ", next in order: Jev was unsure"}
ACTION = {"jev": "speaks", "below_floor": "next in order (unsure)", "late": "next in order (late)",
          "fallback": "next in order (failed)"}


def member_question(req: DebateRequest) -> str | None:
    """The phase's member question, or None (one candidate; openings keep the fixed order)."""
    if len(req.candidates) < 2:
        return None
    if req.side is None:
        return PANEL
    return MEMBER.get(req.phase)


def only_declared(state: dict[str, Any], questions: dict[str, Question]) -> dict[str, Any]:
    """Doc 01 A3 rule 6: only what the request's questions need, so a faces-only request carries no member fields."""
    declared: set[str] = set()
    for q in questions.values():
        if q.meta is not None:
            declared.update(q.meta.state)
    return {k: v for k, v in state.items() if k in declared}


def routing_reason(outcome: str) -> str:
    return REASON + REASON_TAIL.get(outcome, "")


def decide_member(answer: ChoiceAnswer | None, cands: list[str], *, floor: float,
                  failure: str | None) -> tuple[str, str, float | None]:
    """(member, outcome, confidence), V2's table: Jev's pick at or above `floor.member`, else the first eligible in
    fixed order."""
    if answer is None or answer.source == "fallback":
        return cands[0], "late" if failure == "timeout" else "fallback", None
    conf = float(answer.confidence) if answer.confidence is not None else None
    if answer.choice in cands and (conf or 0.0) >= floor:
        return answer.choice, "jev", conf
    if answer.choice in cands:
        return cands[0], "below_floor", conf
    return cands[0], "fallback", None


class DebateSteps:
    """The graph's steps (plan_graph.PlanSteps); the graph's input is {handle, deadline}."""

    def __init__(self, deps: Any) -> None:
        self.deps = deps

    @staticmethod
    def seed(req: DebateRequest) -> str:
        return f"{req.session.seed}:{req.turn_index}:debate"

    @classmethod
    def questions(cls, req: DebateRequest) -> tuple[dict[str, Question], dict[str, str], str | None]:
        """The request's questions, the face keys by candidate, and the member question's id (None for one
        candidate). Shared with the timing check (D9), so it asks exactly what live asks."""
        b = bank()
        names = {p.character_id: p for p in req.session.participants}
        seed = cls.seed(req)
        qs: dict[str, Question] = {}
        qid = member_question(req)
        if qid is not None:
            values = [{"key": c, "name": names[c].name if c in names else c,
                       "role": names[c].character_role if c in names else ""} for c in req.candidates]
            qs[qid] = b.question(qid, values=values, seed=seed, side=SIDE_LABEL.get(req.side or ""))
        keys: dict[str, str] = {}
        for cid in req.candidates:
            key = f"{FACE}:{cid}"
            qs[key] = b.question(FACE, seed=f"{seed}:{cid}", name=_name(names[cid].name if cid in names else cid),
                                 about=cid)
            keys[cid] = key
        who = gates.gated(req.candidates, req.documents)
        recalling = gates.recall_asked(req.candidates, req.recallable)   # M13 (memory D26, D27): each member
        qs.update(gates.questions({c: names[c].name if c in names else c for c in [*who, *recalling]}, who,
                                  nouls=False, recall=recalling))
        qs.update(sf.questions(req.safety))   # M14 (safety D4, U4): "unsafe note?" about an unchecked Interject
        return qs, keys, qid

    @staticmethod
    def state_for(req: DebateRequest, questions: dict[str, Question]) -> PlanState:
        """D6: the builder's debate state without `last_spoke`, then only the declared fields."""
        s = req.session
        you = str((s.world.you or {}).get("displayName") or "")
        f = req.facts
        inp = PlanStateInput(mode="debate", user_name=you,
                             candidates=candidate_views(s, req.candidates, req.cast, req.base_faces, {}),
                             documents={c: list(req.documents[c]) for c in gates.gated(req.candidates, req.documents)},
                             latest=req.latest, recent=recent_lines(s, skip_last=bool(req.latest)),
                             debate=DebateInput(motion=f.motion, phase=f.phase, side=f.side,
                                                last_opposing=f.last_opposing,
                                                latest_by_candidate=dict(f.latest_by_candidate)),
                             last_spoke=False)
        extra = sf.state_extra(req.safety)   # M14 (U4): the Interject as `quoted_note`, never cut (arguments go first)
        built = build_turn_plan_state(inp, reserve=_tokens(extra) if extra else 0)
        # M12: the titles a gate reads are added to what the member and face questions declare, and nothing else
        state = only_declared(dict(built.state), {k: q for k, q in questions.items()
                                                  if not k.startswith(("docs:", "earlier:"))})
        if "quoted_documents" in built.state:
            state["quoted_documents"] = built.state["quoted_documents"]
        state.update(extra)
        return PlanState(state=state, tokens=_tokens(state), dropped_gates=list(built.dropped_gates))

    def start(self, planner: Any, req: DebateRequest) -> JevDebateCall:
        qs, keys, qid = self.questions(req)
        state = self.state_for(req, qs)
        for cid in state.dropped_gates:   # X9's cap dropped their titles: no gate, a quick turn
            qs.pop(gates.gate_key(cid), None)
            qs.pop(gates.earlier_key(cid), None)   # M13 (D26): X9's dropped gates drop `earlier` too
        nouls = {**gates.fallbacks(qs), **sf.fallbacks(qs)}

        async def fallback() -> Answers:
            return {k: nouls.get(k, ChoiceAnswer(req.candidates[0] if k == qid else "none")) for k in qs}

        call = self.deps.decider().start(state.state, qs, req.session.call_ctx(PURPOSE), purpose=PURPOSE,
                                         fallback=fallback)
        return JevDebateCall(planner, self, req, state, call, keys, qid,
                             [c for c in req.candidates if gates.gate_key(c) in qs],
                             [c for c in req.candidates if gates.earlier_key(c) in qs])

    # ── the graph (run by `member`) ──
    async def state(self, run: dict[str, Any]) -> PlanState:
        st: PlanState = run["handle"].state
        return st

    async def ask(self, run: dict[str, Any], state: PlanState) -> tuple[DecisionResult, dict[str, Any]]:
        h: JevDebateCall = run["handle"]
        return await h.read(run["deadline"])

    def decide(self, run: dict[str, Any], state: PlanState, result: tuple[DecisionResult, dict[str, Any]]) -> DebatePlan:
        h: JevDebateCall = run["handle"]
        return h.plan_from(result[0], result[1], member=None)

    def route(self, run: dict[str, Any], plan: DebatePlan) -> Branch:
        return "quick"   # each argument's branch comes from its own gate (`DebatePlan.for_speaker`)


class JevDebateCall:
    """The handle `start_debate` returns: the request is in flight from `turn.end`."""

    def __init__(self, planner: Any, steps: DebateSteps, req: DebateRequest, state: PlanState, call: DecisionCall,
                 keys: dict[str, str], qid: str | None, gated: list[str] | None = None,
                 recalling: list[str] | None = None) -> None:
        self.planner, self.steps, self.req, self.state, self.call = planner, steps, req, state, call
        self.keys, self.qid = keys, qid
        self.gated = list(gated or [])   # M12: who was asked "needs documents?"
        self.recalling = list(recalling or [])   # M13: who was asked "needs something from earlier?"
        self.fixed: DebatePlan | None = None   # the plan as `member` fixed it

    async def read(self, at: datetime) -> tuple[DecisionResult, dict[str, Any]]:
        res: DecisionResult = await self.call.by(at)
        ms = max(0.0, (at - self.req.started_at).total_seconds() * 1000)
        meta = {"call": await ledger_call(self.steps.deps, res.generation_id, PURPOSE) if not res.failure else None,
                "deadline_ms": ms}
        return res, meta

    async def member(self, deadline: datetime) -> DebatePlan:
        if self.qid is None:   # one candidate: no member question, nothing to wait for
            self.fixed = DebatePlan(seed=self.steps.seed(self.req), member=self.req.candidates[0], outcome="single")
            return self.fixed
        try:
            plan, path = await run_plan(self.planner.debate_graph, {"handle": self, "deadline": deadline})
        except asyncio.CancelledError:
            self.call.cancel()   # the request already sent settles and is recorded `cancelled` (M9 D8)
            raise
        except DecisionCancelled:   # the plan was dropped under us (a clear, a newer plan): fixed order, quietly
            plan, path = self.plan_from(DecisionResult(answers={}, failure="cancelled"),
                                        {"call": None, "deadline_ms": 0.0}, member=None), []
        except Exception:   # the port never raises: a bug costs Jev's pick, never the debate
            log.exception("the debate plan failed for %s; fixed order", self.req.session.session_id)
            plan, path = DebatePlan(seed=self.steps.seed(self.req), member=self.req.candidates[0],
                                    outcome="fallback"), []
        self.fixed = plan.model_copy(update={"graph_path": path})
        return self.fixed

    async def faces(self, until: datetime) -> DebatePlan:
        """At the turn's start: the member as fixed, and the faces if Jev's answer has landed (else fallbacks)."""
        fixed = self.fixed or await self.member(until)
        waited = gates.plan_wait(self.steps.deps, 0.0, bool(self.gated))   # U-46: the gate is waited for, not dropped
        if waited:
            until = max(until, self.req.started_at + timedelta(seconds=waited))
        try:
            res, meta = await self.read(until)
        except asyncio.CancelledError:
            self.call.cancel()
            raise
        except DecisionCancelled:   # dropped under us: the member stands, the faces fall back
            res, meta = DecisionResult(answers={}, failure="cancelled"), {"call": None, "deadline_ms": 0.0}
        return self.plan_from(res, meta, member=fixed)

    async def late_rows(self) -> DebatePlan | None:
        """An answer that missed its deadline (the member) or the turn's start (the faces), once it lands: the rows
        for the trace, every one `fallback` (the turn didn't use it), with Jev's answer (D27). None if cancelled or
        failed."""
        try:
            res = await self.call.final()
        except Exception:
            return None
        if res.failure is not None or self.fixed is None:
            return None
        # the call itself goes on the trace too (W1: a call that lands after `turn.end` shows its latency and cost)
        call = await ledger_call(self.steps.deps, res.generation_id, PURPOSE)
        plan = self.plan_from(res, {"call": call, "deadline_ms": 0.0}, member=self.fixed, late=True)
        return plan

    def cancel(self) -> None:
        self.call.cancel()

    @property
    def landed(self) -> bool:
        return self.call.landed

    # ── the decision ──
    def plan_from(self, res: DecisionResult, meta: dict[str, Any], *, member: DebatePlan | None,
                  late: bool = False) -> DebatePlan:
        req = self.req
        b = bank()
        shared: list[dict[str, Any]] = []
        who: WhoPick | None = None
        outcome: str
        if member is not None:   # the member was fixed earlier: keep it, and its row
            chosen, outcome, who = member.member, member.outcome, member.who
            shared = [self._late_member_row(res, member) if late or self._answered_after(res, member)
                      else r for r in member.shared_rows]
        elif self.qid is None:
            chosen, outcome = req.candidates[0], "single"
        else:
            me = b.get(self.qid)
            floor = me.floor if me.floor is not None else 0.6
            a = res.answers.get(self.qid)
            ans = a if isinstance(a, ChoiceAnswer) else None
            chosen, outcome, conf = decide_member(ans, req.candidates, floor=floor, failure=res.failure)
            jev = ans is not None and ans.source != "fallback"
            probs = dict(ans.probabilities or {}) if jev and ans is not None else {}
            cands = [{"characterId": c, "p": round(float(probs.get(c, 0.0)), 2)}
                     for c in sorted(req.candidates, key=lambda c: -float(probs.get(c, 0.0)))] if jev else []
            pick = ans.choice if jev and ans is not None else chosen
            who = WhoPick(pick=chosen, source="jev" if outcome == "jev" else "below_floor" if outcome == "below_floor"
                          else "late" if outcome == "late" else "fallback", question=self.qid, label=me.label,
                          p=probs.get(pick) if jev else None, confidence=conf, candidates=cands,
                          forced_by="round_order", reason=routing_reason(outcome))
            shared = [member_row(self.qid, me.version, me.label, who, outcome, floor=floor, answer=pick)]
        fe = b.get(FACE)
        fade = self.steps.deps.emotion_fade()
        faces: dict[str, PlannedFace] = {}
        face_rows: dict[str, dict[str, Any]] = {}
        for cid, key in self.keys.items():
            fa = res.answers.get(key)
            face = decide_face(fa if isinstance(fa, ChoiceAnswer) else None, base=req.base_faces.get(cid, "neutral"),
                               floor=fe.floor if fe.floor is not None else 0.6, fade=fade, manual=req.manual,
                               failure=res.failure, merge=merges(FACE))
            faces[cid] = face
            row = emotion_row(face, qid=FACE, version=fe.version, label=fe.label, about=cid, purpose=PURPOSE)
            if late:
                row = {**row, "result": "fallback", "action": "kept the face (Jev answered late)"}
            face_rows[cid] = row
        calls: list[dict[str, Any]] = []
        if res.failure is not None:
            calls.append({"purpose": PURPOSE, "model": self.steps.deps.prices.decision.model, "costUsd": 0.0,
                          "latencyMs": float(meta["deadline_ms"]), "fallback": True})
        elif meta.get("call"):
            calls.append(meta["call"])
        found, _ = gates.read(res, self.gated, nouls=False)   # M12: used only if back by the turn's start (D8)
        found.update(gates.dropped([c for c in gates.gated(req.candidates, req.documents) if c not in self.gated]))
        recall = gates.read_recall(res, self.recalling)   # M13 (D26): the same "back by the turn's start" rule
        recall.update(gates.dropped([c for c in gates.recall_asked(req.candidates, req.recallable)
                                     if c not in self.recalling]))
        return DebatePlan(seed=self.steps.seed(req), member=chosen, outcome=outcome, who=who,  # type: ignore[arg-type]
                          faces=faces if not late else {}, face_rows=face_rows, shared_rows=shared, calls=calls,
                          state_tokens=self.state.tokens,
                          graph_path=list(member.graph_path) if member is not None else [],
                          gates=found if not late else {}, recall_gates=recall if not late else {},
                          safety=sf.decide(req.safety, res) if not late else None)   # M14 (U4)

    @staticmethod
    def _answered_after(res: DecisionResult, member: DebatePlan) -> bool:
        """The member fell back at its deadline but Jev's answer is here now."""
        return member.outcome in ("late", "fallback") and res.failure is None and bool(res.answers)

    def _late_member_row(self, res: DecisionResult, member: DebatePlan) -> dict[str, Any]:
        rows = [r for r in member.shared_rows]
        base = dict(rows[0]) if rows else {}
        a = res.answers.get(self.qid or "")
        if not base or not isinstance(a, ChoiceAnswer) or a.source == "fallback":
            return base
        probs = dict(a.probabilities or {})
        base.update(answer=a.choice, result="fallback", action="next in order (Jev answered late)")
        if probs.get(a.choice) is not None:
            base["p"] = round(float(probs[a.choice]), 4)
        if a.confidence is not None:
            base["confidence"] = round(float(a.confidence), 4)
        return base


def member_row(qid: str, version: int, label: str, who: WhoPick, outcome: str, *, floor: float,
               answer: str) -> dict[str, Any]:
    """D27's member row: the pick, its `p` and confidence, the floor comparison, and what code did."""
    row: dict[str, Any] = {"purpose": PURPOSE, "id": qid, "version": version, "label": label}
    if outcome in ("late", "fallback"):
        row.update(answer="next in order (late)" if outcome == "late" else "next in order", compared=[],
                   result="fallback", action=ACTION[outcome])
        return row
    row["answer"] = answer
    if who.p is not None:
        row["p"] = round(who.p, 4)
    if who.confidence is not None:
        row["confidence"] = round(who.confidence, 4)
    row["compared"] = [{"name": "confidence", "value": round(float(who.confidence or 0.0), 4), "threshold": floor}]
    row["result"] = "below_threshold" if outcome == "below_floor" else "used"
    row["action"] = ACTION[outcome]
    return row


def build_debate_graph(deps: Any) -> Any:
    return build_plan_graph(DebateSteps(deps))

"""The follow plan: does a second character speak up after a group's first reply? (doc 07 G2; docs/ai/11 S5; doc 13 W1,
W5 row 10, W11; group-watch design D3, D4, D8, D9, D22; follow-plan spec).

- **When:** `start_follow` runs at the first reply's stream end (S5's position). It builds the state and starts the
  `follow_plan` request at once; the deadline is known only at `turn.end`, so `by(deadline)` takes it then
  (`turn.end` + `timeoutsMs.decision.follow_plan`, which replaces the turn gap for this step).
- **What it asks:** `who_second` (the cast minus everyone who already answered, plus `none`), named after the first
  replier, and `emotion_reply` per candidate. Its state is M8's builder (unchanged) with the first reply as the latest
  line, plus `quoted_message`: the user's message both replies answer.
- **Outcomes favour silence:** a pick at or above `floor.second` speaks second; `none`, unsure, failed or late gives no
  second reply. `by` never raises except CancelledError.
- **On the graph** (D4): `by` runs `state → ask → decide → route`; `state` returns the state built at the stream end and
  `ask` waits for the request already sent.
- **The gates** (M12, rag D8): "needs documents?" about each candidate with a searchable source, in the same request.
  "standalone?" and "English?" are the cast plan's answers for the same message (`FollowRequest.nouls`), asked here
  only when it didn't ask them. The second reply's own gate decides its branch.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from horizon.ai.agent import gates
from horizon.ai.agent.cast_plan import candidate_views, ledger_call
from horizon.ai.agent.emotion import decide_face, emotion_row
from horizon.ai.agent.plan_graph import Branch, build_plan_graph, run_plan
from horizon.ai.agent.plan_state import (
    LIMIT,
    PlanState,
    PlanStateInput,
    _tokens,
    build_turn_plan_state,
    cut_tokens,
    head_tail,
)
from horizon.ai.agent.planner import _name
from horizon.ai.contexts import FollowPlan, FollowRequest, PlannedFace, WhoPick
from horizon.ai.decider import Answers, ChoiceAnswer, DecisionCall, DecisionResult
from horizon.ai.questions import bank

log = logging.getLogger("horizon.ai.planner")

PURPOSE = "follow_plan"
WHO = "who_second"
FACE = "emotion_reply"
RECENT_BEFORE = 4
MESSAGE_MAX, MESSAGE_HEAD, MESSAGE_TAIL, MESSAGE_CUT = 300, 225, 75, 150


def lines_before_message(req: FollowRequest) -> list[dict[str, str]]:
    """The lines before the user's message, at most 4 (the message itself is `quoted_message`)."""
    s = req.session
    you = str((s.world.you or {}).get("displayName") or "")
    recent = [m for m in s.recent if m.content and m.author_type != "system"]
    last_user = max((i for i, m in enumerate(recent) if m.author_type == "user"), default=len(recent))
    before = recent[:last_user][-RECENT_BEFORE:]
    return [{"speaker": (you or "the user") if m.author_type == "user" else m.name, "text": m.content} for m in before]


def follow_state(req: FollowRequest) -> PlanState:
    """D8's template: the builder's fields (the first reply as `quoted_latest`), then `quoted_message`, all within the
    2,000-token limit (the builder's cut order first, then the message down to 150)."""
    s = req.session
    you = str((s.world.you or {}).get("displayName") or "")
    inp = PlanStateInput(mode=s.mode, user_name=you,
                         candidates=candidate_views(s, req.candidates, req.cast, req.base_faces, req.turns_since),
                         documents={c: list(req.documents[c]) for c in gates.gated(req.candidates, req.documents)},
                         latest=f"{req.first_name}: {req.first_text}", recent=lines_before_message(req),
                         premise=str((s.config or {}).get("premise") or "") if s.mode == "watch" else "",
                         summary=(s.summary or "") if s.mode == "watch" else "")
    built = build_turn_plan_state(inp)
    state = dict(built.state)
    state["quoted_message"] = head_tail(req.message, MESSAGE_MAX, MESSAGE_HEAD, MESSAGE_TAIL)
    if _tokens(state) > LIMIT:
        state["quoted_message"] = cut_tokens(req.message, MESSAGE_CUT)
    return PlanState(state=state, tokens=_tokens(state), dropped_gates=list(built.dropped_gates))


def decide_second(answer: ChoiceAnswer | None, cands: list[str], *, floor: float,
                  failure: str | None) -> tuple[str | None, str, float | None]:
    """(second, outcome, confidence), G2's table: silence unless Jev picks someone at or above `floor.second`."""
    if answer is None or answer.source == "fallback":
        return None, "late" if failure == "timeout" else "fallback", None
    conf = float(answer.confidence) if answer.confidence is not None else None
    if answer.choice == "none":
        return None, "none", conf
    if answer.choice in cands and (conf or 0.0) >= floor:
        return answer.choice, "jev", conf
    if answer.choice not in cands:
        return None, "fallback", None
    return None, "below_floor", conf


def second_row(who: WhoPick, outcome: str, *, version: int, floor: float) -> dict[str, Any]:
    row: dict[str, Any] = {"purpose": PURPOSE, "id": WHO, "version": version, "label": who.label}
    if outcome in ("late", "fallback", "cancelled"):
        row.update(answer="no second reply (late)" if outcome == "late" else "no second reply", compared=[],
                   result="fallback", action="no second reply")
        return row
    row["answer"] = who.pick
    if who.p is not None:
        row["p"] = round(who.p, 4)
    if who.confidence is not None:
        row["confidence"] = round(who.confidence, 4)
    row["compared"] = [{"name": "confidence", "value": round(float(who.confidence or 0.0), 4), "threshold": floor}]
    row["result"] = "below_threshold" if outcome == "below_floor" else "used"
    row["action"] = "speaks second" if outcome == "jev" else "no second reply"
    return row


class JevFollowCall:
    """The handle `start_follow` returns: the request is already in flight; `by(deadline)` runs the graph."""

    def __init__(self, planner: Any, req: FollowRequest, state: PlanState, call: DecisionCall,
                 keys: dict[str, str], asked: frozenset[str] = frozenset()) -> None:
        self.planner, self.req, self.state, self.call, self.keys = planner, req, state, call, keys
        self.asked = asked   # the request's question keys (M12: which gates rode it)

    async def by(self, deadline: datetime) -> FollowPlan:
        try:
            plan, path = await run_plan(self.planner.follow_graph, {"handle": self, "deadline": deadline})
        except asyncio.CancelledError:
            self.call.cancel()   # the request already sent settles and is recorded `cancelled` (M9 D8)
            raise
        except Exception:   # the port never raises: a bug here costs the second reply, never the session
            log.exception("the follow plan failed after %s; no second reply", self.req.first_id)
            return FollowPlan(seed=FollowSteps.seed(self.req), second=None, outcome="fallback")
        out: FollowPlan = plan.model_copy(update={"graph_path": path})
        return out

    def cancel(self) -> None:
        self.call.cancel()


class FollowSteps:
    """The graph's steps for the follow plan (plan_graph.PlanSteps); the graph's input is {handle, deadline}."""

    def __init__(self, deps: Any) -> None:
        self.deps = deps

    @staticmethod
    def seed(req: FollowRequest) -> str:
        return f"{req.session.seed}:{req.turn_index}:follow"

    @classmethod
    def questions(cls, req: FollowRequest, *, dropped: list[str] | None = None) -> tuple[dict[str, Any], dict[str, str]]:
        """The request's questions (`who_second`, each candidate's face and, M12, the gates) and the face keys by
        candidate. Shared with the follow timing check (D9), so it asks exactly what live asks."""
        b = bank()
        names = {p.character_id: p for p in req.session.participants}
        values = [{"key": c, "name": names[c].name if c in names else c,
                   "role": names[c].character_role if c in names else ""} for c in req.candidates]
        seed = cls.seed(req)
        qs: dict[str, Any] = {WHO: b.question(WHO, values=values, seed=seed, name=_name(req.first_name))}
        keys: dict[str, str] = {}
        for cid in req.candidates:
            key = f"{FACE}:{cid}"
            qs[key] = b.question(FACE, seed=f"{seed}:{cid}", name=_name(names[cid].name if cid in names else cid),
                                 about=cid)
            keys[cid] = key
        who = gates.gated(req.candidates, req.documents, dropped or ())
        qs.update(gates.questions({c: names[c].name if c in names else c for c in who}, who, nouls=req.nouls is None))
        return qs, keys

    def start(self, planner: Any, req: FollowRequest) -> JevFollowCall:
        state = follow_state(req)
        qs, keys = self.questions(req, dropped=list(state.dropped_gates))
        nouls = gates.fallbacks(qs)

        async def fallback() -> Answers:
            return {k: nouls.get(k, ChoiceAnswer("none")) for k in qs}

        who = gates.gated(req.candidates, req.documents, state.dropped_gates)
        if who:   # rag 11.5: the user message's embedding starts with the follow plan (shared with the first reply's)
            from horizon.ai.agent.deep import start_early_embedding
            from horizon.ai.agent.planner import answered_message

            start_early_embedding(self.deps, req.session, who, req.message, answered_message(req.session)[0])
        call = self.deps.decider().start(state.state, qs, req.session.call_ctx(PURPOSE), purpose=PURPOSE,
                                         fallback=fallback)
        return JevFollowCall(planner, req, state, call, keys, frozenset(qs))

    async def state(self, run: dict[str, Any]) -> PlanState:
        st: PlanState = run["handle"].state
        return st

    async def ask(self, run: dict[str, Any], state: PlanState) -> tuple[DecisionResult, dict[str, Any]]:
        h: JevFollowCall = run["handle"]
        res: DecisionResult = await h.call.by(run["deadline"])
        ms = max(0.0, (run["deadline"] - h.req.started_at).total_seconds() * 1000)
        meta = {"call": await ledger_call(self.deps, res.generation_id, PURPOSE) if not res.failure else None,
                "deadline_ms": ms}
        return res, meta

    def decide(self, run: dict[str, Any], state: PlanState, result: tuple[DecisionResult, dict[str, Any]]) -> FollowPlan:
        h: JevFollowCall = run["handle"]
        req = h.req
        res, meta = result
        b = bank()
        we = b.get(WHO)
        floor = we.floor if we.floor is not None else 0.6
        a = res.answers.get(WHO)
        ans = a if isinstance(a, ChoiceAnswer) else None
        second, outcome, conf = decide_second(ans, req.candidates, floor=floor, failure=res.failure)
        jev = ans is not None and ans.source != "fallback"
        probs = dict(ans.probabilities or {}) if jev and ans is not None else {}
        cands: list[dict[str, Any]] = [{"characterId": c, "p": round(float(probs.get(c, 0.0)), 2)}
                                       for c in sorted(req.candidates, key=lambda c: -float(probs.get(c, 0.0)))] if jev else []
        pick = ans.choice if jev and ans is not None else "none"
        who = WhoPick(pick=second or pick, source="jev" if outcome == "jev" else "below_floor" if outcome == "below_floor"
                      else "fallback", question=WHO, label=we.label, p=probs.get(pick) if jev else None,
                      confidence=conf, candidates=cands, reason="fallback" if outcome in ("late", "fallback") else None)
        fe = b.get(FACE)
        fade = self.deps.emotion_fade()
        faces: dict[str, PlannedFace] = {}
        face_rows: dict[str, dict[str, Any]] = {}
        for cid, key in h.keys.items():
            fa = res.answers.get(key)
            face = decide_face(fa if isinstance(fa, ChoiceAnswer) else None, base=req.base_faces.get(cid, "neutral"),
                               floor=fe.floor if fe.floor is not None else 0.6, fade=fade, manual=req.manual,
                               failure=res.failure)
            faces[cid] = face
            face_rows[cid] = emotion_row(face, qid=FACE, version=fe.version, label=fe.label, about=cid,
                                         purpose=PURPOSE)
        calls: list[dict[str, Any]] = []
        if res.failure is not None:
            calls.append({"purpose": PURPOSE, "model": self.deps.prices.decision.model, "costUsd": 0.0,
                          "latencyMs": float(meta["deadline_ms"]), "fallback": True})
        elif meta.get("call"):
            calls.append(meta["call"])
        asked = [c for c in req.candidates if gates.gate_key(c) in h.asked]
        own = req.nouls is None and bool(asked)
        found, nouls = gates.read(res, asked, nouls=own, message_id=req.message_id)
        found.update(gates.dropped([c for c in gates.gated(req.candidates, req.documents) if c not in asked]))
        return FollowPlan(seed=self.seed(req), second=second, outcome=outcome, who=who, faces=faces,  # type: ignore[arg-type]
                          face_rows=face_rows, shared_rows=[second_row(who, outcome, version=we.version, floor=floor)],
                          calls=calls, state_tokens=state.tokens, gates=found, nouls=nouls if own else req.nouls,
                          asked_nouls=own)

    def route(self, run: dict[str, Any], plan: FollowPlan) -> Branch:
        return "quick"   # M12 adds "deep"


def build_follow_graph(deps: Any) -> Any:
    return build_plan_graph(FollowSteps(deps))

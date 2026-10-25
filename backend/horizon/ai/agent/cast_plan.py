"""The cast plan: Jev call 1 for group and watch turns (doc 07 G1, G4, G6, G7, G9; docs/ai/01 A3, A4; docs/ai/06 E1;
group-watch design D3–D7, D11, D13, D14, D16, D22; turn-plan "The cast plan for group and watch").

One `turn_plan` request per plan, on the M9 plan graph (`state → ask → decide → route`):
- **who speaks** (`who_first`, `who_next` or `who_scene`, no `none`), unless the speakers are forced (mentions, a
  nudge, the guard) or only one candidate is left;
- **the emotion of every candidate asked** (`emotion_reply`, `emotion_line` or `emotion_opening`), so code keeps the
  answers for whoever speaks (A4's Speculative Fan-Out);
- **"is the talk finished?"** on a watch turn after the opening;
- M12 (rag D6–D8): **"needs documents?"** about each candidate asked who has a searchable source, plus
  **"standalone?" and "English?"** once when a group message is answered (`group_first`, `group_mentioned`,
  `everyone`). `for_speaker` takes the speaker's own gate; the others are `not_used`.
- M14 (safety D4, U1, U3, U4): **"unsafe request?"** (and **"at risk?"** for a group message or Step in) about a user
  line with no stored answer; a debate Ask's own face plan asks it about the Ask; a director's note or an Interject is
  asked **"unsafe note?"** with the note as `quoted_note`. The cue is shared by every reply the plan starts.

Code then applies the floors and G1's fallbacks: unsure → the least recently spoken of Jev's top 2; failed or late →
the least recently spoken. Energy never reaches Jev (G9): the runtime gives only awake, unmuted candidates.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from datetime import timedelta
from typing import Any

from sqlalchemy import select

from horizon.ai.agent import gates
from horizon.ai.agent import safety as sf
from horizon.ai.agent.emotion import decide_face, emotion_row, merges
from horizon.ai.agent.plan_graph import Branch
from horizon.ai.agent.plan_state import (
    Candidate,
    DebateInput,
    PlanState,
    PlanStateInput,
    _tokens,
    build_turn_plan_state,
)
from horizon.ai.agent.planner import _name
from horizon.ai.contexts import CastKind, CastPlan, CastRequest, PlannedFace, SessionContext, TalkFinished, WhoPick
from horizon.ai.decider import Answers, ChoiceAnswer, DecisionResult, NoulAnswer
from horizon.ai.questions import bank
from horizon.db import tables as t

log = logging.getLogger("horizon.ai.planner")

PURPOSE = "turn_plan"
TALK = "talk_finished"
WHO_QUESTION: dict[CastKind, str | None] = {
    "group_first": "who_first", "everyone": "who_first", "step_in": "who_first", "group_mentioned": None,
    "next": "who_next", "scene": "who_scene", "opening": "who_scene",
    "debate_opening": None, "debate_ask": None, "debate_line": None}   # M11: debate turns are forced (debate D8)
FACE_QUESTION: dict[CastKind, str] = {
    "group_first": "emotion_reply", "group_mentioned": "emotion_reply", "everyone": "emotion_reply",
    "step_in": "emotion_reply", "next": "emotion_line", "scene": "emotion_line", "opening": "emotion_opening",
    # M11 (doc 06 E1; debate D7): an opening's side of the motion, an Ask answer, a line re-asked at its turn
    "debate_opening": "emotion_debate_opening", "debate_ask": "emotion_reply", "debate_line": "emotion_line"}
WHO_ACTION: dict[CastKind, str] = {
    "group_first": "answers first", "step_in": "answers first", "everyone": "sets the order",
    "next": "speaks next", "scene": "speaks next", "opening": "speaks next", "group_mentioned": "answers first",
    "debate_opening": "speaks", "debate_ask": "answers", "debate_line": "speaks"}


# ── pure rules, shared with the evaluation ──
def least_recent(cands: Sequence[str], turns_since: Mapping[str, int | None]) -> str:
    """G1's fallback: never spoken first, then the longest ago, then cast order."""
    order = {c: i for i, c in enumerate(cands)}
    return min(cands, key=lambda c: (turns_since.get(c) is not None, -(turns_since.get(c) or 0), order[c]))


def probabilities(answer: ChoiceAnswer, cands: Sequence[str]) -> dict[str, float]:
    probs = dict(answer.probabilities or {answer.choice: float(answer.confidence or 1.0)})
    return {c: float(probs.get(c, 0.0)) for c in cands}


def pick_who(answer: ChoiceAnswer | None, cands: Sequence[str], *, floor: float,
             turns_since: Mapping[str, int | None], failure: str | None = None) -> tuple[str, str, float | None]:
    """(pick, source, confidence) for a who-speaks choice with no `none` (G1, G4, G6): Jev's pick at or above the floor;
    unsure: the least recently spoken of Jev's top 2; failed or late: the least recently spoken."""
    if answer is None or answer.source == "fallback" or answer.choice not in cands:
        return least_recent(cands, turns_since), "late" if failure == "timeout" else "fallback", None
    conf = float(answer.confidence if answer.confidence is not None else 0.0)
    if conf >= floor:
        return answer.choice, "jev", conf
    probs = probabilities(answer, cands)
    order = {c: i for i, c in enumerate(cands)}
    top2 = sorted(cands, key=lambda c: (-probs[c], order[c]))[:2]
    return least_recent(top2, turns_since), "below_floor", conf


def steer_rule(p: float | None, t_end: float, block: str | None) -> TalkFinished:
    """G7 (D14): a yes at or above `t_end` steers, unless a steer was recent or a director's note is active."""
    if p is None:
        return TalkFinished(p=None, steer=False, action="no steer")
    if p < t_end:
        return TalkFinished(p=p, steer=False, action="no steer")
    if block == "recent":
        return TalkFinished(p=p, steer=False, action="no steer (steered recently)")
    if block == "note":
        return TalkFinished(p=p, steer=False, action="no steer (director's note)")
    return TalkFinished(p=p, steer=True, action="steer")


def who_row(who: WhoPick, *, version: int, floor: float, action: str, purpose: str = PURPOSE) -> dict[str, Any]:
    row: dict[str, Any] = {"purpose": purpose, "id": who.question, "version": version, "label": who.label,
                           "answer": who.pick}
    if who.source in ("fallback", "late"):
        row.update(compared=[], result="fallback", action="least recently spoken " + action)
        return row
    row["p"] = round(float(who.p or 0.0), 4)
    if who.confidence is not None:
        row["confidence"] = round(who.confidence, 4)
    row["compared"] = [{"name": "confidence", "value": round(float(who.confidence or 0.0), 4), "threshold": floor}]
    row["result"] = "used" if who.source == "jev" else "below_threshold"
    row["action"] = action if who.source == "jev" else f"least recent of the top 2 {action}"
    return row


def talk_row(talk: TalkFinished, *, version: int, label: str, t_end: float) -> dict[str, Any]:
    row: dict[str, Any] = {"purpose": PURPOSE, "id": TALK, "version": version, "label": label}
    if talk.p is None:
        row.update(answer="no", compared=[], result="fallback", action="no steer")
        return row
    row.update(answer="yes" if talk.p >= t_end else "no", p=round(talk.p, 4),
               compared=[{"name": "t_end", "value": round(talk.p, 4), "threshold": t_end}], result="used",
               action=talk.action)
    return row


async def ledger_call(deps: Any, generation_id: str | None, purpose: str) -> dict[str, Any] | None:
    """The plan's ledger row as a `TurnTrace.calls` entry: it has no message ID (it chose the speaker), so the runtime
    can't find it by message (the router's rule, OQ-13)."""
    if not generation_id:
        return None
    db = deps.gateway().ledger.db
    U = t.usage_records.c
    async with db.read() as conn:
        r = (await conn.execute(select(U.model, U.cost_usd, U.latency_ms).where(U.generation_id == generation_id)
                                .order_by(U.at.desc()).limit(1))).first()
    if r is None:
        return None
    return {"purpose": purpose, "model": r[0] or "", "costUsd": round(float(r[1]), 6), "latencyMs": int(r[2] or 0)}


# ── the state ──
def candidate_views(session: SessionContext, ids: Sequence[str], cast: Sequence[Any], base_faces: Mapping[str, str],
                    turns_since: Mapping[str, int | None]) -> list[Candidate]:
    profiles = {c.id: c for c in cast}
    out = []
    for cid in ids:
        part = next((p for p in session.participants if p.character_id == cid), None)
        view = profiles.get(cid)
        profile: dict[str, Any] = view.profile if view is not None else {}
        out.append(Candidate(id=cid, name=part.name if part is not None else (view.name if view else cid),
                             role=part.character_role if part is not None else "",
                             about_source=str((profile.get("personality") or {}).get("summary") or ""),
                             face=base_faces.get(cid, "neutral"), turns_since=turns_since.get(cid)))
    return out


def recent_lines(session: SessionContext, skip_last: bool) -> list[dict[str, str]]:
    you = str((session.world.you or {}).get("displayName") or "")
    recent = [m for m in session.recent if m.content and m.author_type != "system"]   # the premise is its own field
    if skip_last and recent:
        recent = recent[:-1]
    return [{"speaker": (you or "the user") if m.author_type == "user" else m.name, "text": m.content} for m in recent]


# M11 (debate design D17): the plans whose who-speaks question is judged on fit alone see no `last_spoke` label
NO_LAST_SPOKE: frozenset[str] = frozenset({"scene", "opening", "next", "debate_opening", "debate_ask", "debate_line"})
DEBATE_KINDS: frozenset[str] = frozenset({"debate_opening", "debate_ask", "debate_line"})


def state_input(req: CastRequest) -> PlanStateInput:
    """X9's input. `latest` is the line being answered, so it isn't repeated in `recent` (the last stored line).
    Watch turns and group Next speaker leave `last_spoke` out (`who_scene` / `who_next` v3)."""
    s = req.session
    ids = list(dict.fromkeys([*req.forced, *req.candidates]))   # everyone who may speak, for context
    cands = candidate_views(s, ids, req.cast, req.base_faces, req.turns_since)
    you = str((s.world.you or {}).get("displayName") or "")
    premise = str((s.config or {}).get("premise") or "") if s.mode == "watch" else ""
    docs = {c: list(req.documents[c]) for c in gates.gated(asked_about(req), req.documents)}   # M12: gated only
    return PlanStateInput(mode=s.mode, user_name=you, candidates=cands, latest=req.latest, documents=docs,
                          recent=recent_lines(s, skip_last=bool(req.latest)), premise=premise,
                          summary=s.summary or "" if s.mode == "watch" else "",
                          last_spoke=req.kind not in NO_LAST_SPOKE,
                          debate=DebateInput(motion=req.debate.motion, phase=req.debate.phase, side=req.debate.side,
                                             last_opposing=req.debate.last_opposing,
                                             latest_by_candidate=dict(req.debate.latest_by_candidate))
                          if req.debate is not None else None)


def asked_about(req: CastRequest) -> list[str]:
    """Whose emotion is asked: the forced speakers when there are any, else every candidate."""
    return list(req.forced) if req.forced else list(req.candidates)


def who_asked(req: CastRequest) -> str | None:
    qid = WHO_QUESTION.get(req.kind)
    if qid is None or req.forced or len(req.candidates) < 2:
        return None
    return qid


class CastSteps:
    """The graph's steps for `plan_cast` (plan_graph.PlanSteps)."""

    def __init__(self, deps: Any) -> None:
        self.deps = deps

    @staticmethod
    def seed(req: CastRequest) -> str:
        return f"{req.session.seed}:{req.turn_index}"

    async def state(self, req: CastRequest) -> PlanState:
        extra = sf.state_extra(req.safety)   # M14 (U4): a note rides as `quoted_note`, never cut by X9's cap
        built = build_turn_plan_state(state_input(req), reserve=_tokens(extra) if extra else 0)
        if extra:
            built = PlanState(state={**built.state, **extra}, tokens=_tokens({**built.state, **extra}),
                              dropped_gates=list(built.dropped_gates))
        if req.kind not in DEBATE_KINDS:
            return built
        # M11 (doc 01 A3 rule 6; debate D7): a debate turn's face question sees only the fields it declares; M12 adds
        # the titles a gate reads, and nothing else
        from horizon.ai.agent.debate_plan import only_declared

        qs, _ = self.questions(req, gated=[], recall=[])
        state = only_declared(dict(built.state), qs)
        if "quoted_documents" in built.state:
            state["quoted_documents"] = built.state["quoted_documents"]
        return PlanState(state=state, tokens=_tokens(state), dropped_gates=list(built.dropped_gates))

    def questions(self, req: CastRequest, *, gated: list[str] | None = None,
                  recall: list[str] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        """The request's questions. `gated`: who is asked "needs documents?" (None: everyone asked about who has a
        searchable source)."""
        b = bank()
        seed = self.seed(req)
        names = {p.character_id: p for p in req.session.participants}
        qs: dict[str, Any] = {}
        meta: dict[str, Any] = {"who": None, "faces": {}, "talk": False}
        who = who_asked(req)
        if who is not None:
            values = [{"key": c, "name": names[c].name if c in names else c,
                       "role": names[c].character_role if c in names else ""} for c in req.candidates]
            qs[who] = b.question(who, values=values, seed=seed, none=False)
            meta["who"] = who
        fq = FACE_QUESTION[req.kind]
        for cid in asked_about(req):
            name = names[cid].name if cid in names else cid
            key = f"{fq}:{cid}"
            qs[key] = b.question(fq, seed=f"{seed}:{cid}", name=_name(name), about=cid)
            meta["faces"][cid] = key
        if req.kind == "scene":
            qs[TALK] = b.question(TALK)
            meta["talk"] = True
        who_gated = gates.gated(asked_about(req), req.documents) if gated is None else list(gated)
        meta["gated"] = who_gated
        meta["nouls"] = req.kind in gates.NOUL_KINDS and bool(who_gated)
        # M13 (memory D26, D27): "needs something from earlier?" per candidate with something to search
        # (a debate slot's face-only cast plan asks none: the debate plan asks its members, D27)
        recalling = [] if req.kind.startswith("debate") else (
            gates.recall_asked(asked_about(req), req.recallable) if recall is None else list(recall))
        meta["recalling"] = recalling
        qs.update(gates.questions({c: names[c].name if c in names else c for c in [*who_gated, *recalling]},
                                  who_gated, nouls=meta["nouls"], recall=recalling))
        qs.update(sf.questions(req.safety))   # M14 (safety D4): about the user line, when no answer is stored
        return qs, meta

    async def ask(self, req: CastRequest, state: PlanState) -> tuple[DecisionResult, dict[str, Any]]:
        qs, meta = self.questions(req, gated=gates.gated(asked_about(req), req.documents, state.dropped_gates),
                                  recall=gates.recall_asked(asked_about(req), req.recallable, state.dropped_gates))
        meta["dropped"] = [c for c in gates.gated(asked_about(req), req.documents) if c in state.dropped_gates]
        meta["recall_dropped"] = [c for c in gates.recall_asked(asked_about(req), req.recallable)
                                  if c in state.dropped_gates]
        nouls = {**gates.fallbacks(qs), **sf.fallbacks(qs)}

        async def fallback() -> Answers:
            out: dict[str, Any] = {}
            for key in qs:
                out[key] = nouls[key] if key in nouls else NoulAnswer(0.0) if key == TALK else ChoiceAnswer(
                    least_recent(req.candidates, req.turns_since) if key == meta["who"] else "none")
            return out

        if req.kind in gates.NOUL_KINDS and (meta["gated"] or meta["recalling"]):   # rag 11.5 (M13 D32: widened)
            from horizon.ai.agent.deep import start_early_embedding
            from horizon.ai.agent.planner import answered_message

            start_early_embedding(self.deps, req.session, meta["gated"] or meta["recalling"], req.latest,
                                  req.message_id or answered_message(req.session)[0],
                                  any_space=bool(meta["recalling"]))
        decider = self.deps.decider()
        ctx = req.session.call_ctx(PURPOSE)
        call = decider.start(state.state, qs, ctx, purpose=PURPOSE, fallback=fallback)
        deadline = req.deadline_at or req.started_at + timedelta(seconds=decider.timeout_for(PURPOSE))
        waited = gates.plan_wait(self.deps, 0.0, bool(meta["gated"]))   # U-46: a plan with a documents question
        if waited:
            deadline = max(deadline, req.started_at + timedelta(seconds=waited))
        try:
            res: DecisionResult = await call.by(deadline)
        except asyncio.CancelledError:
            call.cancel()   # the request already sent settles and is recorded `cancelled` (M9 D8)
            raise
        meta["timeout_s"] = decider.timeout_for(PURPOSE)
        meta["call"] = await ledger_call(self.deps, res.generation_id, PURPOSE) if not res.failure else None
        return res, meta

    def decide(self, req: CastRequest, state: PlanState, result: tuple[DecisionResult, dict[str, Any]]) -> CastPlan:
        res, meta = result
        b = bank()
        fade = self.deps.emotion_fade()
        faces: dict[str, PlannedFace] = {}
        face_rows: dict[str, dict[str, Any]] = {}
        fq = FACE_QUESTION[req.kind]
        fe = b.get(fq)
        for cid, key in meta["faces"].items():
            a = res.answers.get(key)
            face = decide_face(a if isinstance(a, ChoiceAnswer) else None, base=req.base_faces.get(cid, "neutral"),
                               floor=fe.floor if fe.floor is not None else 0.6, fade=fade, manual=req.manual,
                               failure=res.failure, merge=merges(fq))
            faces[cid] = face
            face_rows[cid] = emotion_row(face, qid=fq, version=fe.version, label=fe.label, about=cid)
        shared: list[dict[str, Any]] = []
        who: WhoPick | None = None
        order: list[str]
        if meta["who"] is not None:
            qid = meta["who"]
            e = b.get(qid)
            floor = e.floor if e.floor is not None else 0.6
            a = res.answers.get(qid)
            ans = a if isinstance(a, ChoiceAnswer) else None
            pick, source, conf = pick_who(ans, req.candidates, floor=floor, turns_since=req.turns_since,
                                          failure=res.failure)
            jev = ans is not None and ans.source != "fallback" and ans.choice in req.candidates
            probs = probabilities(ans, req.candidates) if jev and ans is not None else {}
            if req.kind == "everyone" and jev:   # G4: the probabilities set the order; no floor applies
                pick, source = max(req.candidates, key=lambda c: probs.get(c, 0.0)), "jev"
            cands: list[dict[str, Any]] = [{"characterId": c, "p": round(p, 2)}
                                           for c, p in sorted(probs.items(), key=lambda kv: -kv[1])]
            who = WhoPick(pick=pick, source=source, question=qid, label=e.label,  # type: ignore[arg-type]
                          p=probs.get(pick) if jev else None, confidence=conf, candidates=cands,
                          reason="fallback" if source in ("fallback", "late") else None)
            shared.append(who_row(who, version=e.version, floor=floor, action=WHO_ACTION[req.kind]))
            if req.kind == "everyone":
                if jev:
                    pos = {c: i for i, c in enumerate(req.candidates)}
                    order = sorted(req.candidates, key=lambda c: (-probs.get(c, 0.0), pos[c]))
                else:
                    order = list(req.candidates)   # Jev failed: cast order (G4)
            else:
                order = [pick]
        elif req.forced:
            order = list(req.forced)
            who = WhoPick(pick=order[0], source="forced", forced_by=req.forced_by or "mention", reason=req.reason)
        else:
            order = list(req.candidates[:1])
            if order:
                who = WhoPick(pick=order[0], source="single")
        talk: TalkFinished | None = None
        if meta["talk"]:
            te = b.get(TALK)
            t_end = float(te.thresholds.get("t_end", 0.8))
            a = res.answers.get(TALK)
            p = a.p if isinstance(a, NoulAnswer) and a.source != "fallback" else None
            talk = steer_rule(p, t_end, req.steer_block)
            shared.append(talk_row(talk, version=te.version, label=te.label, t_end=t_end))
        elif req.kind == "opening":   # U-49: the scene's first line has no talk to finish
            shared.append(gates.skipped_row(TALK, purpose=PURPOSE, reason="skipped: the scene's opening"))
        calls: list[dict[str, Any]] = []
        if res.failure is not None:
            calls.append({"purpose": PURPOSE, "model": self.deps.prices.decision.model, "costUsd": 0.0,
                          "latencyMs": float(meta.get("timeout_s", 0.7) * 1000), "fallback": True})
        elif meta.get("call"):
            calls.append(meta["call"])
        found, nouls = gates.read(res, meta.get("gated", []), nouls=bool(meta.get("nouls")), message_id=req.message_id)
        found.update(gates.dropped(meta.get("dropped", [])))
        recall = gates.read_recall(res, meta.get("recalling", []))
        recall.update(gates.dropped(meta.get("recall_dropped", [])))
        return CastPlan(seed=self.seed(req), kind=req.kind, order=order, who=who, faces=faces, face_rows=face_rows,
                        shared_rows=shared, talk=talk, calls=calls, state_tokens=state.tokens, gates=found,
                        nouls=nouls, recall_gates=recall, safety=sf.decide(req.safety, res))

    def route(self, req: CastRequest, plan: CastPlan) -> Branch:
        return "quick"   # M12 adds "deep"


def fallback_plan(req: CastRequest, deps: Any) -> CastPlan:
    """A bug in the plan costs the faces and Jev's pick, never the reply (the port never raises)."""
    fade = deps.emotion_fade()
    faces = {c: decide_face(None, base=req.base_faces.get(c, "neutral"), floor=0.6, fade=fade, manual=req.manual)
             for c in asked_about(req)}
    order = (list(req.forced) or [least_recent(req.candidates, req.turns_since)]) if req.candidates or req.forced else []
    if req.kind == "everyone":
        order = list(req.candidates)
    who = WhoPick(pick=order[0], source="fallback", reason="fallback") if order else None
    return CastPlan(seed=CastSteps.seed(req), kind=req.kind, order=order, who=who, faces=faces,
                    safety=sf.decide(req.safety, None))   # M14: a bug is a failed answer: no cue, flagged

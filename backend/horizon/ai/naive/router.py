"""The Jev Router (design D12; ai-ports "Jev router"; D-66 maximise Jev for bounded decisions).

One Decider `choice` question over the eligible cast plus `none`, with a compact state (the cast with names, roles and
when each last spoke, and the last 6 lines). @mentioned participants always answer first. For a group in `auto`, the
top choice answers, then the next options above p 0.25, at most 2 responders in all. On a timeout (route: 400 ms) or a
failure, the fallback is deterministic: the mentions, else the least-recently-spoken participant; the trace marks the
fallback and carries no candidates. The paid route call (its ledger row has no message) is returned for `TurnTrace.calls`.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from horizon.ai.contexts import RouteContext
from horizon.ai.decider import Answers, Choice, ChoiceAnswer, DecisionResult
from horizon.ai.ports import RoutingDecision
from horizon.ai.scripted.ports import AiDeps
from horizon.db import tables as t

QUESTION = "speaker"
QUEUE_P = 0.25
MAX_RESPONDERS = 2
RECENT_LINES = 6


class JevRouter:
    def __init__(self, deps: AiDeps) -> None:
        self.deps = deps

    def _state(self, ctx: RouteContext) -> dict[str, Any]:
        s = ctx.session
        cast = [{"id": p.character_id, "name": p.name, "role": p.role, "lastSpoke": ctx.last_spoke.get(p.character_id, 0)}
                for p in s.participants if p.character_id in ctx.eligible]
        lines = [f"{m.name}: {m.content[:200]}" for m in s.recent[-RECENT_LINES:]]
        return {"mode": s.mode, "cast": cast, "recent": lines, "message": ctx.text[:500]}

    def _question(self, ctx: RouteContext) -> Choice:
        names = {p.character_id: p for p in ctx.session.participants}
        options = {cid: f"{names[cid].name}" + (f" ({names[cid].role})" if cid in names else "")
                   for cid in ctx.eligible if cid not in ctx.mentions and cid in names}
        options["none"] = "Nobody else should answer."
        return Choice(instructions="Who in the cast should answer the user's last message next? Choose none if nobody "
                                   "else needs to.", options=options)

    def fallback_pick(self, ctx: RouteContext) -> list[str]:
        """Mentions, else the least-recently-spoken eligible participant (never spoken first, then cast order)."""
        if ctx.mentions:
            return []
        rest = [c for c in ctx.eligible if c not in ctx.mentions]
        if not rest or ctx.policy == "mentioned":
            return []
        order = {cid: i for i, cid in enumerate(ctx.eligible)}
        return [min(rest, key=lambda c: (ctx.last_spoke.get(c, 0), order[c]))]

    async def route(self, ctx: RouteContext) -> RoutingDecision:
        forced = [m for m in ctx.mentions if any(p.character_id == m for p in ctx.session.participants)]
        q = self._question(ctx)
        if len(q.options) <= 1:  # nobody to ask about
            return RoutingDecision(speakers=forced)

        async def fallback() -> Answers:
            pick = self.fallback_pick(ctx)
            return {QUESTION: ChoiceAnswer(choice=pick[0] if pick else "none")}

        decider = self.deps.decider()
        call_ctx = ctx.session.call_ctx("route")
        res: DecisionResult = await decider.ask(self._state(ctx), {QUESTION: q}, call_ctx, purpose="route", fallback=fallback)
        answer = res.answers[QUESTION]
        assert isinstance(answer, ChoiceAnswer)
        if answer.source == "fallback":
            pick = self.fallback_pick(ctx)
            fb: dict[str, Any] = {"purpose": "route", "model": self.deps.prices.decision.model, "costUsd": 0.0,
                                  "latencyMs": float(decider.timeouts.for_decision("route") * 1000), "fallback": True}
            return RoutingDecision(speakers=[*forced, *pick] if ctx.policy != "mentioned" else forced, fallback=True,
                                   call=fb)
        probs = dict(answer.probabilities or {answer.choice: 1.0})
        candidates: list[dict[str, Any]] = sorted(
            ({"characterId": c, "p": round(min(1.0, max(0.0, float(p))), 2)} for c, p in probs.items()
             if c != "none" and c in q.options), key=lambda x: -float(x["p"]))
        if answer.choice != "none" and not any(c["characterId"] == answer.choice for c in candidates):
            candidates.insert(0, {"characterId": answer.choice, "p": 1.0})
        rest: list[str] = []
        if ctx.policy == "everyone":
            rest = [c for c in ctx.eligible if c not in forced]
        elif ctx.policy == "auto":
            room = max(0, MAX_RESPONDERS - len(forced))
            if answer.choice != "none" and room:
                rest.append(answer.choice)
            for c in candidates:
                if len(rest) >= room:
                    break
                if c["characterId"] not in rest and float(c["p"]) > QUEUE_P:
                    rest.append(c["characterId"])
        call = await self._call(res.generation_id) if answer.source == "jev" else None
        return RoutingDecision(speakers=[*forced, *rest], candidates=candidates, call=call)

    async def _call(self, generation_id: str | None) -> dict[str, Any] | None:
        """The route call's ledger row (no message ID; OQ-13), as a `TurnTrace.calls` entry."""
        if not generation_id:
            return None
        gw = self.deps.gateway()
        db = gw.ledger.db  # type: ignore[attr-defined]
        U = t.usage_records.c
        async with db.read() as conn:
            r = (await conn.execute(select(U.model, U.cost_usd, U.latency_ms).where(U.generation_id == generation_id)
                                    .order_by(U.at.desc()).limit(1))).first()
        if r is None:
            return None
        return {"purpose": "route", "model": r[0] or "", "costUsd": round(float(r[1]), 6), "latencyMs": int(r[2] or 0)}

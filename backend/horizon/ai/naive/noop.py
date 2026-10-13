"""`naive`'s own planner and face check: they do nothing (turn-plan-emotion design D5; ai-ports "AI profile selection").

They exist so the port fallback chain never hands `naive` the scripted stand-ins, which record simulated spend: with a
key, that would be a fake `turn_plan` or `face_check` row in a real ledger. `naive` is the yardstick: it plans nothing
and checks nothing (doc 13 W2: "naive has no check").
"""

from __future__ import annotations

from typing import Any

from horizon.ai.contexts import CastPlan, CastRequest, FollowRequest, PlanRequest, SessionContext, TurnPlan


class NoPlanner:
    decides_retrieval = False

    async def plan(self, req: PlanRequest) -> TurnPlan | None:
        return None

    async def plan_cast(self, req: CastRequest) -> CastPlan | None:
        return None   # M10 (group-watch D3): naive keeps its router, round-robin and random picks (G13)

    def start_follow(self, req: FollowRequest) -> None:
        return None


class NoFaceCheck:
    async def check(self, ctx: SessionContext, message_id: str, speaker_id: str, face: str,
                    text: str) -> tuple[dict[str, Any], dict[str, Any] | None] | None:
        return None

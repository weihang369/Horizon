"""`naive`'s own planner and face check: they do nothing (turn-plan-emotion design D5; ai-ports "AI profile selection").

They exist so the port fallback chain never hands `naive` the scripted stand-ins, which record simulated spend: with a
key, that would be a fake `turn_plan` or `face_check` row in a real ledger. `naive` is the yardstick: it plans nothing
and checks nothing (doc 13 W2: "naive has no check").
"""

from __future__ import annotations

from typing import Any

from horizon.ai.contexts import (
    CastPlan,
    CastRequest,
    DebateRequest,
    FollowRequest,
    PlanRequest,
    SessionContext,
    TurnContext,
    TurnPlan,
)
from horizon.ai.ports import GuardrailResult


class NoPlanner:
    decides_retrieval = False

    async def plan(self, req: PlanRequest) -> TurnPlan | None:
        return None

    async def plan_cast(self, req: CastRequest) -> CastPlan | None:
        return None   # M10 (group-watch D3): naive keeps its router, round-robin and random picks (G13)

    def start_follow(self, req: FollowRequest) -> None:
        return None

    def start_debate(self, req: DebateRequest) -> None:
        return None   # M11 (debate D5, V12): naive fills debate slots in fixed order


class NoFaceCheck:
    async def check(self, ctx: SessionContext, message_id: str, speaker_id: str, face: str,
                    text: str) -> tuple[dict[str, Any], dict[str, Any] | None] | None:
        return None


class NoGuardrail:
    """M14 (safety D12; doc 11 S5 "the other profiles"): `naive` checks nothing, so its trace shows no checks that never
    ran (before M14 it fell back to the scripted guardrail's fixed `sfw` and `advice_scope`)."""

    async def check(self, ctx: TurnContext, text: str) -> GuardrailResult:
        return GuardrailResult("pass", [])

    async def check_prompt(self, cctx: Any, kind: str, text: str) -> GuardrailResult:
        return GuardrailResult("pass", [])   # D17: the yardstick checks no prompt

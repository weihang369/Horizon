"""The turn-plan graph (docs/ai/01 A4, A7, A9, A11; turn-plan-emotion design D3; turn-plan spec).

Built to its final shape, although in M9 it is one Jev call:

    state ──▶ ask ──▶ decide ──▶ route ──quick──▶ END
                                      └──deep───▶ (M12: embed → search → Jev call 2 → keep)

- **No checkpointer** (A9): every run starts from frozen inputs and returns a result; nothing is stored between runs.
- **Only `langgraph`** (A8): the nodes call our own `Decider` and code; no LangChain model class is used.
- **Tracing** stays off unless the user opted in (docs/ai/02 B11): a run is wrapped in `no_trace()`.
- **The node path** is collected once per run and returned with the result (A12: one writer per graph).

The nodes come from a `PlanSteps` object, so the planner (M9 phase 3), the checks (phase 1) and tests share one graph.
"""

from __future__ import annotations

import contextlib
import operator
from typing import Annotated, Any, Literal, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph

from horizon.tracing import TRACER, no_trace

Branch = Literal["quick", "deep"]
NODES = ("state", "ask", "decide", "route")


class PlanRun(TypedDict, total=False):
    req: Any                                   # the frozen request
    state: Any                                 # what `state` built (the Jev state and its size)
    result: Any                                # what `ask` got back (answers, or a fallback)
    plan: Any                                  # what `decide` made of it
    branch: Branch
    path: Annotated[list[str], operator.add]   # each node appends its own name


class PlanSteps(Protocol):
    async def state(self, req: Any) -> Any: ...
    async def ask(self, req: Any, state: Any) -> Any: ...
    def decide(self, req: Any, state: Any, result: Any) -> Any: ...
    def route(self, req: Any, plan: Any) -> Branch: ...


def build_plan_graph(steps: PlanSteps) -> Any:
    """Compile the graph over `steps`. In M9 only the quick branch exists, so `route` must answer "quick"."""

    # LangGraph's node protocol names the parameter `state`; here it is the whole run, not the Jev state.
    async def state_node(state: PlanRun) -> PlanRun:
        return {"state": await steps.state(state["req"]), "path": ["state"]}

    async def ask_node(state: PlanRun) -> PlanRun:
        return {"result": await steps.ask(state["req"], state["state"]), "path": ["ask"]}

    async def decide_node(state: PlanRun) -> PlanRun:
        return {"plan": steps.decide(state["req"], state["state"], state["result"]), "path": ["decide"]}

    async def route_node(state: PlanRun) -> PlanRun:
        return {"branch": steps.route(state["req"], state["plan"]), "path": ["route"]}

    g = StateGraph(PlanRun)
    g.add_node("state", state_node)
    g.add_node("ask", ask_node)
    g.add_node("decide", decide_node)
    g.add_node("route", route_node)
    g.add_edge(START, "state")
    g.add_edge("state", "ask")
    g.add_edge("ask", "decide")
    g.add_edge("decide", "route")
    g.add_conditional_edges("route", lambda run: run["branch"], {"quick": END})   # M12 adds "deep"
    return g.compile()


async def run_plan(graph: Any, req: Any) -> tuple[Any, list[str]]:
    """One run: (the plan, the node path). Cancelling the caller cancels the run (A11)."""
    guard = contextlib.nullcontext() if TRACER.enabled else no_trace()
    with guard:
        out: PlanRun = await graph.ainvoke({"req": req, "path": []}, config={"recursion_limit": 10})
    return out["plan"], list(out.get("path") or [])

"""The `agent` request, byte for byte (turn-plan-emotion tasks 4.1, 4.3; design D16; persona-prompt "The mood line never
touches the cached prefix").

`backend/tests/fixtures/agent_request/request_agent1_*.json` were recorded from the `agent-1` engine BEFORE the mood
line existed (task 4.1). `agent-2` must send exactly those requests on a neutral, a MANUAL and an unplanned turn, and
differ only in the tail on a planned non-neutral one.

Recording again (only if `agent-1`'s system message itself changes, which re-versions the prompt):
`HORIZON_RECORD_REQUESTS=1 uv run pytest tests/sessions/test_agent_request_fixtures.py`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from horizon.ai.contexts import LineHint, PlannedFace, TurnContext, TurnPlan
from tests.sessions.test_agent_turn import ctx, engine, mv

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "agent_request"
RECORD = os.environ.get("HORIZON_RECORD_REQUESTS") == "1"


def planned(base: TurnContext, face: str, *, manual: bool = False) -> TurnContext:
    pf = PlannedFace(face=face, source="classifier" if face != "neutral" else "default", base="thinking",
                     outcome="jev", pick=face, p=0.8, confidence=0.8, manual=manual)
    return base.model_copy(update={"plan": TurnPlan(seed="s:1", branch="quick", emotion=pf)})


def cases() -> dict[str, TurnContext]:
    one = ctx([mv(1, "user", "Morning.", name="user"), mv(2, "character", "Morning, Kai.", "chr_a", "Amara Okafor"),
               mv(3, "user", "My dog died this morning.", name="user")], mode="one_on_one", others=False,
              summary="**Kai — facts**\n- Has a dog called Pepper.")
    group = ctx([mv(1, "user", "Morning all", name="user"),
                 mv(2, "character", "Hi!\nLong day ahead.", "chr_h", "Hana Morisaki")], mode="group")
    greet = ctx([], mode="one_on_one", others=False, line=LineHint(kind="greeting"))
    return {"one_on_one": one, "group": group, "greeting": greet}


def dump(c: TurnContext) -> dict[str, Any]:
    req, prefix = engine().request(c)
    return {"messages": req.messages, "stop": req.stop, "max_tokens": req.max_tokens, "prefix_len": len(prefix)}


def fixture(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIX / f"request_agent1_{name}.json").read_text(encoding="utf-8"))
    return data


@pytest.mark.parametrize("name", ["one_on_one", "group", "greeting"])
def test_unplanned_requests_equal_the_agent1_fixture(name: str) -> None:
    got = dump(cases()[name])
    if RECORD:
        (FIX / f"request_agent1_{name}.json").write_text(json.dumps(got, indent=2, ensure_ascii=False) + "\n",
                                                          encoding="utf-8")
    assert got == fixture(name)

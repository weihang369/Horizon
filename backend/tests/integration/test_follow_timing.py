"""`F`, our side's time from a reply's stream end to its `turn.end` (group-watch task 4.7; design D9).

The follow plan's deadline counts from `turn.end`, but the request starts at the stream's end (S5), so Jev's real
budget is `F` + 400 ms. `F` is our own work (the guardrail check, the ledger reads, the append), measured here in real
time over 100 scripted group replies on this machine. The figures are printed (`pytest -s`) and copied into
docs/ai/checks/m10.md.
"""

from __future__ import annotations

import statistics
import time
from typing import Any

from horizon.sessions.actor import SessionActor
from horizon.sessions.turn import TurnRunner
from tests.conftest import Api
from tests.sessions.kit import command, create

TRIO = ["chr_seedAmara", "chr_seedMei", "chr_seedVictor"]
N = 100


async def test_f_stream_end_to_turn_end_is_small(api: Api, monkeypatch: Any) -> None:
    started: dict[str, float] = {}
    f_ms: list[float] = []
    finish, emit = TurnRunner.finish, SessionActor.emit

    async def timed_finish(self: TurnRunner, actor: SessionActor, info: Any, *a: Any, **k: Any) -> str:
        started[info.message_id] = time.perf_counter()   # the stream has ended (settled and flushed)
        return await finish(self, actor, info, *a, **k)

    async def timed_emit(self: SessionActor, *events: Any, **k: Any) -> Any:
        out = await emit(self, *events, **k)
        for e in events:
            if e.get("type") == "turn.end":
                t0 = started.pop(e["payload"]["messageId"], None)
                if t0 is not None:
                    f_ms.append((time.perf_counter() - t0) * 1000)
        return out

    monkeypatch.setattr(TurnRunner, "finish", timed_finish)
    monkeypatch.setattr(SessionActor, "emit", timed_emit)
    await api.set_key()
    sid: str = (await create(api, "group", TRIO))["session"]["id"]
    await api.drive(6000)
    f_ms.clear()   # the greeting's first append warms the writer; count group replies only
    i = 0
    while len(f_ms) < N:
        await command(api, sid, "send", {"text": f"Round {i}: what's everyone up to?"})
        await api.drive(40000)
        i += 1
        assert i < 400, "too few replies (is the cast asleep?)"
    xs = sorted(f_ms[:N])
    p50, p90 = statistics.median(xs), xs[int(0.9 * (N - 1))]
    print(f"\nM10 F (stream end -> turn.end, real time, {N} scripted group replies): p50 {p50:.1f} ms, "
          f"p90 {p90:.1f} ms, max {xs[-1]:.1f} ms")
    assert p90 < 200

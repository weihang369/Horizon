"""The memory writer (docs/ai/09 M3–M5; memory design D12–D19): the `memory-1` rewrite call, Jev's importance and guard
questions, the duplicate check, and the `naive` and `agent` writers built from them."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Any

from horizon.domain import vclock


async def all_of(*aws: Awaitable[Any]) -> list[Any]:
    """Run these together and return their results in order (`vclock.together`: a cancelled run waits for its children,
    so no request outlives the run, and each child keeps its own virtual-time token). One failure cancels the rest; a
    single failure is raised as itself, so a daily-cap refusal still reads as one."""
    try:
        return await vclock.together(*(_as_coro(a) for a in aws))
    except BaseExceptionGroup as eg:
        if len(eg.exceptions) == 1:
            raise eg.exceptions[0] from None
        raise


async def _as_coro(a: Awaitable[Any]) -> Any:
    return await a

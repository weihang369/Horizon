"""Cancel storms on the paths M13 adds (memory design D2; session-runtime "New cancel paths leave the writer free").

Every new cancel path is stormed while it writes (`storm_during_write`) and while it waits on a parked Jev or DeepSeek
call (`storm_during_call`). Afterwards the writer is free, the clock settles and the log reduces.

Task 0.2 lists each path as a strict xfail naming the phase that builds it; that phase replaces the placeholder with
the real storm, so a path can't be forgotten and a placeholder can't pass by accident.
"""

from __future__ import annotations

import pytest

from tests.conftest import Api

PATHS = [
    ("a run cut by a session delete during the rewrite call", 2),
    ("a run cut by a character delete during the Jev requests", 3),
    ("a run cut by a world delete during the embeddings", 3),
    ("a run cut by Reset demo inside apply_run's transaction", 2),
    ("Forget during a run", 4),
    ("a regenerate during a run, and the undo before it streams", 4),
    ("the window-drop indexing mid-write", 6),
    ("recall's search and Jev call 2 on Stop", 7),
    ("the memory block's refresh through the actor inbox", 5),
    ("shutdown with runs pending, then the start-up sweep", 2),
]


@pytest.mark.parametrize(("path", "phase"), PATHS, ids=[p for p, _ in PATHS])
@pytest.mark.xfail(strict=True, reason="placeholder: the phase that builds this cancel path replaces it")
async def test_storm_placeholder(api: Api, path: str, phase: int) -> None:
    pytest.fail(f"not built yet (phase {phase}): {path}")

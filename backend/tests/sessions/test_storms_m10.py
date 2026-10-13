"""Cancel storms on the paths M10 adds (group-watch design D2; session-runtime "New cancel paths leave the writer
free"). Each path is stormed while it writes and while its plan waits on a parked Jev answer; afterwards no
connection is checked out, a fresh write commits within 5 s, and the plan's ledger row says `cancelled`.

Phase 0 checks the helpers on M9's 1:1 plan; later phases add a test per new path."""

from __future__ import annotations

from horizon.sessions.actor import SessionActor
from tests.conftest import Api
from tests.helpers.storm import assert_writer_free, park_next_decision, storm
from tests.sessions.kit import command, ledger
from tests.sessions.test_turn_plan import agent


async def test_a_storm_while_the_one_on_one_plan_waits_leaves_the_writer_free(api: Api) -> None:
    sid = await agent(api)
    release = park_next_decision(api.rt)
    await command(api, sid, "send", {"text": "Are you awake?"})
    await api.drive(300)                                   # turn.next and turn.thinking are out; Jev is parked
    actor: SessionActor = await api.rt.sessions.get(sid)
    worker = actor._worker
    assert worker is not None and not worker.done()
    await storm(worker)
    await assert_writer_free(api.rt.db)
    release.set()
    await api.drive(2000)
    assert [r for r in await ledger(api) if r["purpose"] == "turn_plan"][-1]["finish_reason"] == "cancelled"
    assert not [r for r in await ledger(api) if r["purpose"] == "reply"]

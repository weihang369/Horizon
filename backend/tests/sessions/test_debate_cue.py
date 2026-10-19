"""The debate cue's facts from the log (debate tasks 5.2, 5.3; design D10; session-modes "Interject reaches the next
argument once"; persona-prompt "A rebuttal after a teammate"). The facts ride on `DebateMeta`, so the requests show
them. No network."""

from __future__ import annotations

import json
from typing import Any

from tests.conftest import Api
from tests.sessions.kit import command
from tests.sessions.test_debate_plan import TWO_V_ONE, debate, first_rebuttal_end

MODERATOR = "Take the moderator's last note into account."
EXTENDED = "The round was extended: make a point not yet made."


def cues(api: Api) -> list[str]:
    """Each debate argument's cue line (the tail), in request order."""
    assert api.rt.fake is not None
    out = []
    for r in api.rt.fake.requests:
        if not r.url.path.endswith("/chat/completions"):
            continue
        body: dict[str, Any] = json.loads(r.content)
        msgs = body.get("messages") or []
        tail = str(msgs[-1]["content"]) if msgs and msgs[-1]["role"] == "system" else ""
        if tail.startswith(("Give your opening", "Give your rebuttal", "Give your closing")):
            out.append(tail)
    return out


async def test_a_teammates_opening_and_rebuttal_name_the_teammate_heard(api: Api) -> None:
    """2 v 1 (Amara, Mei v Victor): Mei's opening (prefetched) and her rebuttal follow Amara's in the same round."""
    sid = await debate(api, sides=TWO_V_ONE)
    await api.drive(150000)
    got = cues(api)
    openings = [c for c in got if c.startswith("Give your opening")]
    rebuttals = [c for c in got if c.startswith("Give your rebuttal")]
    assert len(openings) == 3 and len(rebuttals) == 3
    mate = "has already spoken for your side this round: add to it, don't repeat it."
    # the two later openings are prefetched together, so their requests may go in either order
    assert [c for c in openings if mate in c] == [
        "Give your opening statement: your case in two or three reasons.\nAmara " + mate]
    assert [mate in c for c in rebuttals] == [False, False, True] and "Amara " + mate in rebuttals[2]
    assert all(MODERATOR not in c and EXTENDED not in c for c in got)
    assert sid


async def test_an_interject_reaches_the_next_argument_once(api: Api) -> None:
    sid = await debate(api)
    await first_rebuttal_end(api, sid)
    before = len(cues(api))
    await command(api, sid, "debate/interject", {"text": "Please keep to the evidence."})
    await api.drive(150000)
    after = cues(api)[before:]
    assert after and MODERATOR in after[0]
    assert sum(MODERATOR in c for c in cues(api)) == 1


async def test_an_extended_round_says_so_on_every_argument(api: Api) -> None:
    sid = await debate(api, phases=["opening", "rebuttal"])
    await first_rebuttal_end(api, sid)
    await command(api, sid, "debate/extend-round")
    await api.drive(200000)
    rebuttals = [c for c in cues(api) if c.startswith("Give your rebuttal")]
    assert len(rebuttals) == 6
    assert [EXTENDED in c for c in rebuttals] == [False] * 3 + [True] * 3


async def test_label_follows_the_bytes_in_a_live_debate(api: Api) -> None:
    """ai-ports "Steer and debate labels": every `agent` argument is `agent-7`; an Ask answer keeps `agent-1`."""
    import sqlalchemy as sa

    from horizon.db import tables as t
    from tests.sessions.kit import chars, messages

    sid = await debate(api, autoAdvance=False)
    await api.drive(20000)
    await command(api, sid, "debate/ask", {"characterId": "chr_seedAmara", "text": "Amara, why?"})
    await api.drive(20000)
    msgs = chars(await messages(api, sid))
    async with api.rt.db.read() as conn:
        labels = dict((await conn.execute(sa.select(t.turn_traces.c.message_id, t.turn_traces.c.prompt_version)
                                          .where(t.turn_traces.c.message_id.in_([m["id"] for m in msgs])))).all())
    assert [(bool(m.get("forcedSpeaker")), labels[m["id"]]) for m in msgs] == [(False, "agent-15"), (True, "agent-9")]

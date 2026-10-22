"""The waits the user chose after the pilot review (U-62): a plan that asks "needs documents?" is waited for to the end
(U-46), and so is recall's search, its vector and every check (U-56), as deep insight already was (D-111). A plan with
no documents question keeps its measured 700 ms. Each reply says what its search waited for, and where each memory it
was given came from (U-58)."""

from __future__ import annotations

from tests.conftest import Api
from tests.sessions.kit import chars, command, messages
from tests.sessions.test_deep_m12 import measured_deadlines
from tests.sessions.test_gates_m12 import AMARA, RIN, SUNNY, agent, gate
from tests.sessions.test_memory_recall_m13 import indexed_session, recall_yes, rows_of


def row(reply: dict, qid: str) -> dict:
    return next(r for r in reply["trace"]["system1"]["questions"] if r["id"] == qid and r["result"] != "not_used")


async def test_a_plan_that_asks_needs_documents_waits_for_jev(api: Api) -> None:
    sid = await agent(api, "one_on_one", [AMARA])
    gate(api, AMARA, 0.2)                                     # a quick reply: only the plan's wait is under test
    fake = api.rt.fake
    assert fake is not None
    release = fake.park_question("emotion_reply:")   # the turn plan's request
    before = len(chars(await messages(api, sid)))
    await command(api, sid, "send", {"text": "How was the night shift?"})
    await api.drive(3000)                                     # far past the 700 ms deadline
    assert len(chars(await messages(api, sid))) == before     # no fallback reply: still waiting for Jev
    release.set()
    await api.drive(15000)
    reply = chars(await messages(api, sid))[-1]
    assert row(reply, "emotion_reply")["result"] != "fallback" and row(reply, "docs")["result"] == "used"
    # U-58: every memory the reply was given came from the prompt's memory list
    assert {m.get("via") for m in reply["trace"]["memory"]["recalled"]} == {"block"}


async def test_a_plan_with_no_documents_question_keeps_its_deadline(api: Api) -> None:
    sid = await agent(api, "one_on_one", [RIN], world=SUNNY)   # Rin has no documents: no gate, no wait
    fake = api.rt.fake
    assert fake is not None
    release = fake.park_question("emotion_reply:")   # the turn plan's request
    await command(api, sid, "send", {"text": "Raid tonight?"})
    await api.drive(3000)
    reply = chars(await messages(api, sid))[-1]
    assert row(reply, "emotion_reply")["result"] == "fallback"
    release.set()
    await api.drive(1000)


async def test_with_measured_deadlines_the_documents_plan_falls_back(api: Api) -> None:
    measured_deadlines(api)                                   # `docsWaitAll` off: the 700 ms deadline again
    sid = await agent(api, "one_on_one", [AMARA])
    fake = api.rt.fake
    assert fake is not None
    release = fake.park_question("emotion_reply:")   # the turn plan's request
    await command(api, sid, "send", {"text": "How was the night shift?"})
    await api.drive(3000)
    assert row(chars(await messages(api, sid))[-1], "emotion_reply")["result"] == "fallback"
    release.set()
    await api.drive(1000)


async def test_recall_waits_for_every_check(api: Api) -> None:
    sid = await indexed_session(api)
    recall_yes(api)
    fake = api.rt.fake
    assert fake is not None
    held = fake.park_questions("recall:", 6)
    await command(api, sid, "send", {"text": "What did I say about Mia and the walk home?"})
    await api.drive(20_000)                                   # far past recall.checkMs (1.5 s)
    for ev in held:
        ev.set()
    await api.drive(5000)
    reply = chars(await messages(api, sid))[-1]
    recall = rows_of(reply, "recall")
    assert recall and not any(r["result"] == "fallback" for r in recall)
    assert "recallVectorMs" in reply["trace"]["search"]       # U-58: recall's own vector wait is shown

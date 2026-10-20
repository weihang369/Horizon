"""Regenerate asks for a fresh reply to the same user line (v1 test stage, audit 04-01): the reply being replaced is
not in the history the model reads, and the request doesn't end on "continue" after it."""

from __future__ import annotations

from tests.conftest import Api
from tests.sessions.kit import chars, command, messages
from tests.sessions.test_naive import _naive, chat_bodies, sse

OLD = "Caffeine withdrawal fits: taper slowly."


async def test_the_replaced_reply_is_not_in_the_regenerate_request(api: Api) -> None:
    assert api.rt.fake is not None
    api.rt.fake.queued.append(sse(["<e:neutral>Shift just ended. What's going on?"]))
    sid = await _naive(api)
    api.rt.fake.queued.append(sse([f"<e:thinking>{OLD}"]))
    await command(api, sid, "send", {"text": "I've had a headache for three days."})
    await api.drive(6000)
    reply = chars(await messages(api, sid))[-1]
    assert reply["content"] == OLD
    api.rt.fake.queued.append(sse(["<e:neutral>Let's start with where it hurts."]))
    await command(api, sid, "regenerate", {"messageId": reply["id"]})
    await api.drive(6000)
    body = chat_bodies(api)[-1]
    contents = [str(m.get("content")) for m in body["messages"]]
    assert not any(OLD in c for c in contents), "the replaced reply was sent back as history"
    assert body["messages"][-1]["role"] != "assistant"
    assert any("I've had a headache for three days." in c for c in contents)   # the user's line is still answered

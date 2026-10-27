"""Regenerate asks for a fresh reply to the same user line (v1 test stage, audit 04-01): the reply being replaced is
not in the history the model reads, and the request doesn't end on "continue" after it."""

from __future__ import annotations

import pytest

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


async def test_regenerate_searches_the_plain_line(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    """Audit B-02: the regenerate marker is for the scripted line only; retrieval reads the user's own words, so the
    message's query vector matches and "again" is never searched."""
    import horizon.sessions.turn as turn_mod

    seen: list[str] = []
    real = turn_mod.retrieve

    async def spy(rt: object, actor: object, sctx: object, cid: str, prompt: str) -> object:
        seen.append(prompt)
        return await real(rt, actor, sctx, cid, prompt)   # type: ignore[arg-type]

    monkeypatch.setattr(turn_mod, "retrieve", spy)
    assert api.rt.fake is not None
    api.rt.fake.queued.append(sse(["<e:neutral>Shift just ended. What's going on?"]))
    sid = await _naive(api)
    api.rt.fake.queued.append(sse([f"<e:thinking>{OLD}"]))
    await command(api, sid, "send", {"text": "I've had a headache for three days."})
    await api.drive(6000)
    reply = chars(await messages(api, sid))[-1]
    api.rt.fake.queued.append(sse(["<e:neutral>Let's start with where it hurts."]))
    await command(api, sid, "regenerate", {"messageId": reply["id"]})
    await api.drive(6000)
    assert seen[-1] == "I've had a headache for three days."


async def test_regenerating_a_generated_greeting_asks_for_a_greeting(api: Api) -> None:
    """Audit 04-01 item 3: the greeting has no user line before it, so its new take is a greeting again (the greeting
    cue), not a reply to nothing."""
    assert api.rt.fake is not None
    api.rt.fake.queued.append(sse(["<e:neutral>Shift just ended. What's going on?"]))
    sid = await _naive(api)
    greeting = chars(await messages(api, sid))[-1]
    api.rt.fake.queued.append(sse(["<e:happy>Kai! Good to see you."]))
    await command(api, sid, "regenerate", {"messageId": greeting["id"]})
    await api.drive(6000)
    body = chat_bodies(api)[-1]
    assert any("Open the conversation with a short, warm greeting" in str(m.get("content")) for m in body["messages"])
    again = chars(await messages(api, sid))[-1]
    assert again["id"] == greeting["id"] and len(again["variants"]) == 2
    assert again["content"] == "Kai! Good to see you."

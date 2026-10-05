"""Session lifecycle over HTTP (session-lifecycle: fork, forked state, rename/leave/end, delete, export;
session-event-sourcing "Interrupted streams at startup"; tasks 11.2–11.6)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from horizon.db import tables as t
from tests.conftest import Api
from tests.sessions.kit import API, assert_reduces, chars, command, create, events, ledger, messages, snapshot

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "export"


async def test_fork_a_debate_at_a_third_and_resume_it(api: Api) -> None:
    await api.set_key()
    src_events = await events(api, "ses_seedDebate4Day")
    at = src_events[len(src_events) // 3]["seq"]
    r = await api.post(f"{API}/sessions/ses_seedDebate4Day/fork", {"atSeq": at})
    assert r.status_code == 201, r.text
    fork = r.json()
    s = fork["session"]
    assert s["isSeed"] is False and s["continuedFrom"] == "ses_seedDebate4Day" and s["status"] == "paused"
    assert s["pausedReason"] == "user" and s["title"].endswith(" · live")
    assert all(m["status"] != "streaming" for m in fork["messages"])
    full = await messages(api, "ses_seedDebate4Day")
    assert len(fork["messages"]) < len(full)
    n = len(fork["messages"])
    await command(api, s["id"], "debate/resume")
    await api.drive(30000)
    assert len(await messages(api, s["id"])) > n
    assert len(await events(api, "ses_seedDebate4Day")) == len(src_events)  # the source is unchanged
    evs = await events(api, s["id"])
    assert [e["seq"] for e in evs] == list(range(1, len(evs) + 1))


async def test_fork_needs_a_key_and_one_on_one_forks_start_active(api: Api) -> None:
    r = await api.post(f"{API}/sessions/ses_seedAmaraHeadache/fork", {})
    assert r.status_code == 400 and r.json()["error"]["code"] == "missing_key"
    await api.set_key()
    fork = (await api.post(f"{API}/sessions/ses_seedAmaraHeadache/fork", {}, status=201)).json()
    assert fork["session"]["status"] == "active"
    sid = fork["session"]["id"]
    await command(api, sid, "send", {"text": "Following up on the headache."})
    await api.drive(12000)
    assert chars(await messages(api, sid))[-1]["status"] == "complete"
    assert (await api.post(f"{API}/sessions/ses_nope/fork", {})).status_code == 404


async def test_send_after_end_and_rename(api: Api) -> None:
    await api.set_key()
    sid = (await create(api, "one_on_one", ["chr_seedAmara"]))["session"]["id"]
    await api.drive(6000)
    title = "  " + "x" * 100 + "  "
    r = await api.client.patch(f"{API}/sessions/{sid}", json={"title": title})
    assert r.status_code == 200
    s = r.json()
    assert s["title"] == "x" * 80 and s["titleIsCustom"] is True
    ev = (await events(api, sid))[-1]
    assert ev["type"] == "session.state" and ev["payload"]["settings"] == {"title": "x" * 80, "titleIsCustom": True}
    assert (await api.client.post(f"{API}/sessions/{sid}/end")).status_code == 204
    assert (await snapshot(api, sid))["session"]["status"] == "ended"
    r = await api.post(f"{API}/sessions/{sid}/send", {"text": "still there?"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"
    await assert_reduces(api, sid)


async def test_leave_does_nothing_on_a_seed_session(api: Api) -> None:
    before = await events(api, "ses_seedAmaraHeadache")
    assert (await api.client.post(f"{API}/sessions/ses_seedAmaraHeadache/leave")).status_code == 204
    assert await events(api, "ses_seedAmaraHeadache") == before
    assert (await api.client.post(f"{API}/sessions/ses_nope/leave")).status_code == 404


async def test_delete_a_streaming_session(api: Api) -> None:
    await api.set_key()
    sid = (await create(api, "one_on_one", ["chr_seedVictor"]))["session"]["id"]
    await api.drive(6000)
    await command(api, sid, "send", {"text": "Tell me everything about precedent."})
    streaming = None
    for _ in range(40):
        await api.drive(250)
        streaming = next((m for m in await messages(api, sid) if m["status"] == "streaming"), None)
        if streaming:
            break
    assert streaming is not None
    sub = api.rt.bus.subscribe("global")
    assert (await api.client.delete(f"{API}/sessions/{sid}")).status_code == 204
    r = await api.client.get(f"{API}/sessions/{sid}")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    rows = [x for x in await ledger(api) if x["message_id"] == streaming["id"]]
    assert len(rows) == 1 and rows[0]["cost_usd"] > 0  # the spend remains
    async with api.rt.db.read() as conn:
        purge = (await conn.execute(t.ai_purge_queue.select().where(t.ai_purge_queue.c.scope == "session"))).mappings().all()
    assert any(p["ids"] == [sid] for p in purge)
    seen = []
    while not sub.queue.empty():
        seen.append(sub.queue.get_nowait())
    assert any(isinstance(x, dict) and x.get("kind") == "session" and x.get("id") == sid for x in seen)
    await api.drive(10000)  # nothing is left running for the deleted session
    assert api.rt.sessions.peek(sid) is None


async def test_seed_debate_export(api: Api) -> None:
    r = await api.client.get(f"{API}/sessions/ses_seedDebate4Day/export")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/markdown")
    md = r.text
    assert "[^1]" in md and "## Sources" in md
    assert re.search(r'\[\^1\]: Meridian Shift Fatigue Review 2025\.pdf, p\. 4\. "', md)
    assert not re.search(r"[a-z.,]\[\d\]", md)
    assert "sk-or-" not in md


async def test_export_matches_the_mock_byte_for_byte(api: Api) -> None:
    files = sorted(FIXTURES.glob("*.json"))
    assert files
    for f in files:
        case = json.loads(f.read_text(encoding="utf-8"))
        r = await api.client.get(f"{API}/sessions/{case['sessionId']}/export")
        assert r.content.decode("utf-8") == case["markdown"], case["sessionId"]


async def test_interrupted_streams_at_startup(make_api: Any, tmp_path: Path) -> None:
    data = tmp_path / "crash"
    a: Api = await make_api(data_dir=data)
    await a.set_key()
    sid = (await create(a, "one_on_one", ["chr_seedVictor"]))["session"]["id"]
    await a.drive(6000)
    await command(a, sid, "send", {"text": "Tell me everything about precedent."})
    for _ in range(40):
        await a.drive(250)
        if any(m["status"] == "streaming" for m in await messages(a, sid)):
            break
    # The backend "crashes": the actors stop without closing the reply.
    for actor in list(a.rt.sessions.actors.values()):
        actor.stopped = True
        for task in (actor._loop, actor._worker, actor._idle):
            if task is not None:
                task.cancel()
    a.rt.sessions.actors.clear()
    await a.rt.stop()
    b: Api = await make_api(data_dir=data)
    reply = chars(await messages(b, sid))[-1]
    assert reply["status"] == "interrupted" and reply["interruptedBy"] == "error"
    await assert_reduces(b, sid)

"""Events (tasks 7.1–7.3): the bus, the global SSE stream and the session stream's replay/resume rule.

The SSE tests run against a real uvicorn server (`live`), because httpx's ASGI transport buffers whole responses.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from typing import Any

import httpx

from horizon.events.bus import EventBus, session_channel
from tests.conftest import Live

COVER = {"kind": "preset", "presetId": "cover_night_skyline"}


# ── 7.1 the bus ──
async def test_slow_subscriber_is_dropped_others_unaffected() -> None:
    bus = EventBus(maxsize=10)
    slow = bus.subscribe("global")
    fast = bus.subscribe("global")
    got: list[int] = []
    for i in range(25):
        bus.publish("global", {"i": i})
        e = await fast.get()
        assert e is not None
        got.append(e["i"])
    assert got == list(range(25))
    assert slow.dropped and await slow.get() is None
    assert bus.subscriber_count("global") == 1


# ── SSE helpers ──
def frames(resp: httpx.Response) -> Iterator[dict[str, Any]]:
    """Parse SSE frames: comments become {'comment': ...}; data frames become {'id', 'event', 'data'}."""
    cur: dict[str, Any] = {}
    for line in resp.iter_lines():
        if line.startswith(":"):
            yield {"comment": line[1:].strip()}
            continue
        if line == "":
            if cur:
                yield cur
                cur = {}
            continue
        k, _, v = line.partition(":")
        cur[k] = v[1:] if v.startswith(" ") else v


def collect(url: str, *, until: Any, headers: dict[str, str] | None = None, timeout: float = 15) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with httpx.Client(timeout=timeout) as c, c.stream("GET", url, headers=headers or {}) as r:
        assert r.status_code == 200, r.read()
        assert r.headers["cache-control"] == "no-cache" and r.headers["x-accel-buffering"] == "no"
        deadline = time.time() + timeout
        for f in frames(r):
            out.append(f)
            if until(out) or time.time() > deadline:
                break
    return out


# ── 7.2 the global stream ──
def test_global_stream_keepalive_and_entity_changed(live: Live) -> None:
    created: dict[str, Any] = {}

    def create_soon() -> None:
        time.sleep(0.5)
        created.update(httpx.post(f"{live.base}/api/v1/worlds", json={"name": "Streamed", "cover": COVER}).json())

    worker = threading.Thread(target=create_soon)
    worker.start()

    def done(fs: list[dict[str, Any]]) -> bool:
        return any("data" in f for f in fs) and any("comment" in f for f in fs)

    got = collect(f"{live.base}/api/v1/events", until=done)
    worker.join(timeout=10)
    data = [json.loads(f["data"]) for f in got if "data" in f]
    assert data[0] == {"type": "entity.changed", "kind": "world", "id": created["id"], "worldId": created["id"]}
    assert any("comment" in f for f in got)  # the keepalive


# ── 7.3 the session stream ──
def _all_events(live: Live, sid: str) -> list[dict[str, Any]]:
    return httpx.get(f"{live.base}/api/v1/sessions/{sid}/events", params={"limit": 1000}).json()["items"]  # type: ignore[no-any-return]


def test_resume_from_since_seq(live: Live) -> None:
    sid = "ses_seedAmaraHeadache"
    stored = _all_events(live, sid)
    expect = [e["seq"] for e in stored if e["seq"] > 3]
    got = collect(f"{live.base}/api/v1/sessions/{sid}/stream?sinceSeq=3",
                  until=lambda fs: len([f for f in fs if "id" in f]) >= len(expect))
    data = [f for f in got if "id" in f]
    assert [int(f["id"]) for f in data] == expect
    first = next(e for e in stored if e["seq"] == expect[0])
    assert data[0]["event"] == first["type"] and json.loads(data[0]["data"]) == first


def test_last_event_id_wins_when_higher(live: Live) -> None:
    sid = "ses_seedDebate4Day"
    stored = _all_events(live, sid)
    assert len(stored) > 45
    got = collect(f"{live.base}/api/v1/sessions/{sid}/stream?sinceSeq=3", headers={"Last-Event-ID": "40"},
                  until=lambda fs: any("id" in f for f in fs))
    assert int(next(f for f in got if "id" in f)["id"]) == 41


def test_live_event_after_replay_arrives_exactly_once(live: Live) -> None:
    sid = "ses_seedHanaLongDay"
    stored = _all_events(live, sid)
    last = stored[-1]["seq"]
    live_evt = {"id": "evt_live1", "sessionId": sid, "seq": last + 1, "at": "2026-10-03T03:00:00.000Z",
                "type": "session.resumed", "payload": {}}
    stale = {**live_evt, "id": "evt_stale", "seq": last}

    def publish_soon() -> None:
        time.sleep(0.6)
        for e in (stale, live_evt, live_evt):
            live.publish(session_channel(sid), e)

    threading.Thread(target=publish_soon).start()
    got = collect(f"{live.base}/api/v1/sessions/{sid}/stream?sinceSeq={last - 2}",
                  until=lambda fs: sum(1 for f in fs if f.get("id") == str(last + 1)) >= 1 and
                  sum(1 for f in fs if "comment" in f) >= 6)
    ids = [int(f["id"]) for f in got if "id" in f]
    assert ids == [last - 1, last, last + 1]


def test_unknown_session_is_404_before_streaming(live: Live) -> None:
    r = httpx.get(f"{live.base}/api/v1/sessions/ses_nope/stream")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"

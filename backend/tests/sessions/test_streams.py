"""Live delivery on the session stream (event-streams "Session stream replay and resume"; session-runtime "Stored events
equal streamed events"; tasks 5.1, 5.2). A real uvicorn server, because httpx's ASGI transport buffers responses."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from horizon.ai.contexts import TurnContext
from horizon.ai.ports import Emotion, Token, TurnEvent
from horizon.gateway.pipeline import SimulatedReply
from horizon.sessions.coalesce import Coalescer
from tests.conftest import Live
from tests.integration.test_events import frames

API = "/api/v1"


# ── 5.1 the coalescer ──
def test_coalescer_flush_rules() -> None:
    now = [0.0]
    c = Coalescer(48, 50, lambda: now[0])
    assert c.add("a" * 47) is None
    assert c.add("b") == "a" * 47 + "b"  # 48 characters
    assert c.add("x") is None
    now[0] = 30
    assert c.add("y") is None and c.due_in_ms() == 20
    now[0] = 50
    assert c.add("z") == "xyz"  # 50 ms since the first buffered delta
    assert c.add("q") is None and c.pending
    assert c.take() == "q" and not c.pending  # a non-token event or the turn end
    assert c.add("") is None and not c.pending


class OneCharEngine:
    """Naive-style deltas: 1 character every 10 ms of clock time."""

    name = "onechar"
    version = "t1"
    prompt_version = None

    def __init__(self, live: Live, text: str) -> None:
        self.live = live
        self.text = text

    async def run(self, ctx: TurnContext) -> AsyncIterator[TurnEvent]:
        rt = self.live.rt
        spec = SimulatedReply(chunks=list(self.text), first_token_ms=300, step_ms=10, tail_ms=10, total_ms=300 + 10 * len(self.text),
                              model="deepseek/deepseek-v4.1-flash", tokens_in=900, tokens_cached=0, tokens_out=40,
                              cost_usd=0.0001)
        yield Emotion("happy")
        async for ch in rt.gateway.simulated_stream(ctx.call_ctx("reply"), spec, rt.clock.sleep):
            if ch.content:
                yield Token(ch.content)


def _advance(live: Live, ms: float) -> None:
    r = httpx.post(f"{live.base}{API}/_test/clock", json={"advanceMs": ms}, timeout=30)
    assert r.status_code == 200, r.text


def _setup(live: Live, cast: str = "chr_seedAmara") -> str:
    httpx.post(f"{live.base}{API}/_test/clock", json={"freezeAt": "2026-10-03T03:00:00.000Z"})
    assert httpx.put(f"{live.base}{API}/settings/key", json={"key": "sk-or-test-0001"}).status_code == 200
    r = httpx.post(f"{live.base}{API}/sessions", json={"worldId": "wld_seedMeridian", "mode": "one_on_one",
                                                       "characterIds": [cast]}, timeout=30)
    assert r.status_code == 201, r.text
    sid: str = r.json()["session"]["id"]
    _advance(live, 6000)
    return sid


def _stored(live: Live, sid: str) -> list[dict[str, Any]]:
    return httpx.get(f"{live.base}{API}/sessions/{sid}/events", params={"limit": 1000}).json()["items"]  # type: ignore[no-any-return]


def _messages(live: Live, sid: str) -> list[dict[str, Any]]:
    return httpx.get(f"{live.base}{API}/sessions/{sid}/messages", params={"limit": 1000}).json()["items"]  # type: ignore[no-any-return]


class Reader(threading.Thread):
    """Collects the session stream's events until `stop` or the connection ends."""

    def __init__(self, url: str, headers: dict[str, str] | None = None, until: Any = None) -> None:
        super().__init__(daemon=True)
        self.url, self.headers, self.until = url, headers or {}, until
        self.events: list[dict[str, Any]] = []
        self.frames: list[dict[str, Any]] = []
        self.opened = threading.Event()

    def run(self) -> None:
        with httpx.Client(timeout=30) as c, c.stream("GET", self.url, headers=self.headers) as r:
            self.opened.set()
            for f in frames(r):
                if "data" not in f:
                    continue
                self.frames.append(f)
                self.events.append(json.loads(f["data"]))
                if self.until is not None and self.until(self.events):
                    return


def _wait(cond: Any, timeout: float = 15) -> None:
    end = time.time() + timeout
    while not cond():
        assert time.time() < end, "timed out"
        time.sleep(0.02)


def test_replay_equals_live_with_coalesced_one_char_deltas(live: Live) -> None:
    sid = _setup(live)
    text = "Short paragraphs, plain language, and two clarifying questions before any advice. " * 2
    live.rt.ai.override("turn", OneCharEngine(live, text))
    reader = Reader(f"{live.base}{API}/sessions/{sid}/stream?sinceSeq=0")
    reader.start()
    reader.opened.wait(10)
    assert httpx.post(f"{live.base}{API}/sessions/{sid}/send", json={"text": "hello"}).status_code == 202
    for _ in range(40):
        _advance(live, 250)
    stored = _stored(live, sid)
    _wait(lambda: len(reader.events) >= len(stored))
    assert reader.events[:len(stored)] == stored  # field for field
    reply = [m for m in _messages(live, sid) if m["author"]["type"] == "character"][-1]
    assert reply["content"] == text
    deltas = [e for e in stored if e["type"] == "token" and e["payload"]["messageId"] == reply["id"]]
    assert len(deltas) < len(text) / 4  # coalesced (≈ 48 characters a flush)
    assert all(len(e["payload"]["delta"]) <= 48 for e in deltas)


def test_live_events_during_replay_arrive_once_in_order(live: Live) -> None:
    sid = _setup(live)
    assert httpx.post(f"{live.base}{API}/sessions/{sid}/send", json={"text": "Tell me about rotas."}).status_code == 202
    for _ in range(40):
        _advance(live, 250)
        if any(m["status"] == "streaming" for m in _messages(live, sid)):
            break
    reader = Reader(f"{live.base}{API}/sessions/{sid}/stream?sinceSeq=0")
    reader.start()
    stop = threading.Event()

    def drive() -> None:
        while not stop.is_set():
            _advance(live, 50)

    driver = threading.Thread(target=drive, daemon=True)
    driver.start()
    reply = None
    end = time.time() + 30
    while time.time() < end:
        msgs = [m for m in _messages(live, sid) if m["author"]["type"] == "character"]
        if len(msgs) == 2 and msgs[-1]["status"] == "complete":
            reply = msgs[-1]
            break
        time.sleep(0.05)
    stop.set()
    driver.join(10)
    assert reply is not None
    stored = _stored(live, sid)
    _wait(lambda: len(reader.events) >= len(stored))
    seqs = [e["seq"] for e in reader.events]
    assert seqs[:len(stored)] == list(range(1, len(stored) + 1))
    assert reader.events[:len(stored)] == stored


def test_reconnect_mid_reply_continues_at_the_next_seq(live: Live) -> None:
    sid = _setup(live, "chr_seedVictor")
    long_text = ("Precedent binds lower courts, persuades equal ones, and is read narrowly when the facts differ. " * 3).strip()
    live.rt.ai.override("turn", OneCharEngine(live, long_text))
    assert httpx.post(f"{live.base}{API}/sessions/{sid}/send", json={"text": "precedent?"}).status_code == 202
    for _ in range(4):
        _advance(live, 100)
    base_seq = len(_stored(live, sid))
    cut = base_seq + 6
    first = Reader(f"{live.base}{API}/sessions/{sid}/stream?sinceSeq=0", until=lambda evs: evs[-1]["seq"] >= cut)
    first.start()
    first.opened.wait(10)
    while first.is_alive():
        _advance(live, 30)
    assert first.events[-1]["seq"] == cut
    second = Reader(f"{live.base}{API}/sessions/{sid}/stream?sinceSeq=0", headers={"Last-Event-ID": str(cut)},
                    until=lambda evs: any(e["type"] == "insight" for e in evs))
    second.start()
    second.opened.wait(10)
    while second.is_alive():
        _advance(live, 100)
    assert second.events[0]["seq"] == cut + 1
    reply = [m for m in _messages(live, sid) if m["author"]["type"] == "character"][-1]
    text = "".join(e["payload"]["delta"] for e in first.events + second.events
                   if e["type"] == "token" and e["payload"]["messageId"] == reply["id"])
    assert text == reply["content"] == long_text


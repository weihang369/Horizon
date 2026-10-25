"""`horizon demo export` (v1 endgame): real portraits, themes and recordings from a running app into the seed.

A fake app answers through httpx's MockTransport; the seed and recorded folders are temporary copies.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image

from horizon import demo_export as dx

WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 fake"


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "teal").save(buf, "PNG")
    return buf.getvalue()


def _fixture(cid: str, emotions: list[str], *, blink: bool = False, candidates: int = 1, song: bool = False) -> dict[str, Any]:
    return {"id": cid, "isSeed": True, "emotions": {e: ({"url": f"/assets/placeholder/{e}.svg"} if e in emotions else None)
                                                   for e in ("neutral", "happy", "sad")},
            "blink": {"url": "/assets/placeholder/blink.svg"} if blink else None,
            "appearance": {"candidates": [{"id": f"cand_{i}"} for i in range(candidates)]},
            **({"themeSongId": f"song_{cid}"} if song else {})}


@pytest.fixture
def dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    seed, recorded = tmp_path / "seed", tmp_path / "recorded"
    (seed / "characters").mkdir(parents=True)
    fixtures = [_fixture("chr_a", ["neutral", "happy"], blink=True, candidates=2, song=True), _fixture("chr_b", ["neutral"])]
    for f in fixtures:
        (seed / "characters" / f"{f['id']}.json").write_text(json.dumps({"schemaVersion": 1, "data": f}))
    monkeypatch.setattr(dx, "SEED", seed)
    monkeypatch.setattr(dx, "RECORDED", recorded)
    return seed, recorded


def _app() -> httpx.Client:
    live = {
        "chr_a": {"emotions": {"neutral": {"url": "/assets/gen/a/n.webp"}, "happy": {"url": "/assets/gen/a/h.png"},
                               "sad": {"url": "/assets/gen/a/s.webp"}},
                  "blink": {"url": "/assets/gen/a/b.webp"},
                  "appearance": {"attributes": {"hair": "black"}, "appearanceSummary": "A doctor.",
                                 "candidates": [{"id": "c1", "url": "/assets/gen/a/c1.webp", "selected": True, "status": "ready"},
                                                {"id": "c2", "url": "/assets/gen/a/c2.webp", "selected": False, "status": "ready"}]}},
        # A placeholder in the source app: the seed keeps what it has.
        "chr_b": {"emotions": {"neutral": {"url": "/assets/placeholder/portraits/chr_b/neutral.svg"}}, "blink": None,
                  "appearance": {"attributes": {}, "candidates": []}},
    }
    events = [{"id": f"evt_{i}", "seq": i, "type": "token", "payload": {}} for i in range(1, 251)]

    def handle(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path == "/api/v1/health":
            return httpx.Response(200, json={"ok": True})
        if path == "/api/v1/settings":
            return httpx.Response(200, json={"models": {"image": "bytedance-seed/seedream-5-0-flash"}})
        if path.startswith("/api/v1/characters/") and path.endswith("/song"):
            return httpx.Response(200, json={"url": "/assets/gen/a/song_v2.mp3", "durationSec": 30.7, "bytes": 3, "format": "mp3",
                                             "generation": {"model": "google/lyria-3-clip-preview", "prompt": "p", "costUsd": 0.04},
                                             "licenseNote": "Composed by Lyria."})
        if path.startswith("/api/v1/characters/") and path.endswith("/memory"):
            return httpx.Response(200, json=[{"id": "mem_1", "characterId": "chr_a", "createdAt": "x", "sourceSessionId": "ses_rec"},
                                             {"id": "mem_2", "characterId": "chr_a", "createdAt": "y", "sourceSessionId": "ses_other"}])
        if path.startswith("/api/v1/characters/"):
            cid = path.rsplit("/", 1)[-1]
            return httpx.Response(200, json=live[cid]) if cid in live else httpx.Response(404, json={})
        if path == "/api/v1/sessions/ses_rec":
            return httpx.Response(200, json={"session": {"id": "ses_rec"}, "messages": [{"id": "msg_1"}], "lastSeq": 250})
        if path == "/api/v1/sessions/ses_rec/events":
            after = int(req.url.params.get("cursor") or 0)
            page = events[after:after + 200]
            nxt = str(after + 200) if after + 200 < len(events) else None
            return httpx.Response(200, json={"items": page, "nextCursor": nxt})
        if path.endswith(".png"):
            return httpx.Response(200, content=_png())
        if path.startswith("/assets/gen/"):
            return httpx.Response(200, content=WEBP if path.endswith(".webp") else b"ID3")
        return httpx.Response(404, json={})

    return httpx.Client(transport=httpx.MockTransport(handle), base_url="http://app")


def test_assets_copy_the_active_raster_portraits_and_the_theme(dirs: tuple[Path, Path]) -> None:
    seed, recorded = dirs
    src = dx.Source("http://app", _app())
    written = dx.export_assets(src, log=lambda *_: None)
    a = seed / "assets" / "portraits" / "chr_a"
    # The fixture shows neutral, happy, the blink and a second candidate; "sad" isn't in it, so it isn't shipped.
    assert sorted(p.name for p in a.iterdir()) == ["blink.webp", "cand-2.webp", "happy.webp", "neutral.webp"]
    assert (a / "happy.webp").read_bytes()[8:12] == b"WEBP"            # the PNG became a WebP
    assert (a / "cand-2.webp").read_bytes() == WEBP                     # the candidate that wasn't locked
    assert not (seed / "assets" / "portraits" / "chr_b").exists()      # a placeholder in the app is never copied
    assert (seed / "assets" / "themes" / "chr_a.mp3").read_bytes() == b"ID3"
    assert written == 5
    songs = json.loads((recorded / "songs.json").read_text())
    assert songs["chr_a"]["generation"]["model"] == "google/lyria-3-clip-preview" and songs["chr_a"]["durationSec"] == 30.7
    images = json.loads((recorded / "images.json").read_text())
    assert images["chr_a"]["model"] == "bytedance-seed/seedream-5-0-flash"
    assert images["chr_a"]["variants"] == ["blink", "cand-2", "happy", "neutral"]
    # Running it again writes nothing new.
    assert dx.export_assets(src, log=lambda *_: None) == 0


def test_a_session_is_recorded_with_every_event_page_and_only_its_memories(dirs: tuple[Path, Path]) -> None:
    _, recorded = dirs
    src = dx.Source("http://app", _app())
    dx.export_session(src, "ses_rec", "ses_seedX", log=lambda *_: None)
    rec = json.loads((recorded / "sessions" / "ses_seedX.json").read_text())
    assert rec["source"] == "ses_rec" and len(rec["events"]) == 250 and rec["messages"] == [{"id": "msg_1"}]
    dx.export_memory(src, ["chr_a"], ["ses_rec"], log=lambda *_: None)
    assert [m["id"] for m in json.loads((recorded / "memory.json").read_text())] == ["mem_1"]


def test_the_command_refuses_without_a_running_app(dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    down = httpx.Client(transport=httpx.MockTransport(lambda _r: httpx.Response(404, json={})), base_url="http://app")
    real = dx.Source
    monkeypatch.setattr(dx, "Source", lambda base: real(base, down))
    args = type("A", (), {"source": "http://app", "assets": True, "character": None, "session": None,
                          "knowledge": False, "memory": False})()
    with pytest.raises(SystemExit, match="no Horizon backend"):
        dx.run(args)

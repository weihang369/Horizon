"""Leak sweep (task 14.1, local-backend "The API key never leaks"; M2 acceptance: the key is absent from logs, errors,
the ledger, exports and SSE). One fake key goes through every M2 path, then everything the backend wrote is grepped."""

from __future__ import annotations

import asyncio
import io
import json
import logging
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image

from horizon.gateway.chat import ChatRequest
from horizon.gateway.context import call_ctx
from horizon.logs import close_file_logging
from tests.conftest import Api

KEY = "sk-or-test-leakcheck-0001"


async def test_the_key_appears_nowhere(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    rt = api.rt
    assert rt.fake is not None
    sse: list[str] = []
    bodies: list[str] = []
    real_publish = rt.bus.publish

    def spy(channel: str, event: dict[str, Any]) -> None:
        sse.append(json.dumps(event))
        real_publish(channel, event)

    monkeypatch.setattr(rt.bus, "publish", spy)

    async def call(method: str, path: str, **kw: Any) -> httpx.Response:
        r = await api.client.request(method, f"/api/v1{path}", **kw)
        bodies.append(r.text)
        return r

    await call("PUT", "/settings/key", json={"key": KEY})
    assert (await call("POST", "/settings/test-connection")).status_code == 200
    for role in ("chat", "decision", "embedding", "image", "music"):
        assert (await call("POST", "/settings/test-model", json={"role": role})).status_code == 200
    assert (await call("POST", "/characters/chr_seedHana/energy/top-up", json={"points": 500})).status_code == 200

    # M3: a live exchange (session SSE frames go through the bus spy), its traces, events and the Markdown export.
    r = await call("POST", "/sessions", json={"worldId": "wld_seedMeridian", "mode": "one_on_one",
                                              "characterIds": ["chr_seedAmara"]})
    assert r.status_code == 201, r.text
    sid = r.json()["session"]["id"]
    await api.drive(6000)
    assert (await call("POST", f"/sessions/{sid}/send", json={"text": "How do I sleep after nights?"})).status_code == 202
    await api.drive(12000)
    msgs = (await call("GET", f"/sessions/{sid}/messages")).json()["items"]
    assert any(m.get("trace") for m in msgs)
    for m in msgs:
        await call("GET", f"/messages/{m['id']}/trace")
    await call("GET", f"/sessions/{sid}/events")
    assert (await call("GET", f"/sessions/{sid}/export")).status_code == 200
    assert any(sid in e for e in sse)  # session events went through the bus

    # M4: job rows, job input, task errors and the cover upload response.
    for j in (await call("GET", "/jobs", params={"active": "true"})).json():
        await rt.jobs.cancel(j["id"])   # the test-mode overlay job: keep the queued provider answers for this test
    r = await call("POST", "/worlds/wld_seedMeridian/characters", json={"seedPrompt": "Sarah, a doctor", "intent": "expert"})
    assert r.status_code == 201, r.text
    await api.drive(5000)
    r = await call("POST", "/jobs", json={"characterId": "chr_mockSarah", "kind": "portrait_candidates",
                                          "prompt": "a kind, tired smile"})
    assert r.status_code == 201, r.text
    await api.drive(21000)
    await call("GET", f"/jobs/{r.json()['id']}")
    await call("POST", "/_test/ai-profile", json={"profile": "scripted", "overrides": {"image": "naive"}})
    rt.fake.queued.append(httpx.Response(500, json={"error": {"message": f"upstream said: bad token {KEY}"}}))
    r = await call("POST", "/jobs", json={"characterId": "chr_seedAmara", "kind": "portrait_candidates"})
    assert r.status_code == 201, r.text
    for _ in range(100):
        failed = (await call("GET", f"/jobs/{r.json()['id']}")).json()
        if failed["status"] not in ("queued", "running"):
            break
        await asyncio.sleep(0.02)
    assert failed["tasks"][0]["status"] == "failed" and "sk-or-***" in failed["tasks"][0]["error"]["message"]
    await call("POST", "/_test/ai-profile", json={"profile": "scripted"})
    buf = io.BytesIO()
    Image.new("RGB", (32, 18), (10, 20, 30)).save(buf, "PNG")
    assert (await call("POST", "/worlds/wld_seedMeridian/cover", files={"file": ("c.png", buf.getvalue(), "image/png")})
            ).status_code == 200

    # A cancelled stream, then its correction.
    agen = rt.gateway.chat_stream(ChatRequest(model="deepseek/deepseek-v4.1-flash", messages=[{"role": "user", "content": "hi"}],
                                              max_tokens=8), call_ctx("host", world_id="wld_seedSunnyHollow"), estimate=0.0006)
    await agen.__anext__()
    await agen.aclose()
    await rt.gateway.drain_background()
    await rt.corrector.idle()

    # Provider failures that echo the key back: a 500 with the key in its body, then a 401.
    rt.fake.queued += [
        httpx.Response(500, json={"error": {"message": f"upstream said: bad token {KEY}"}}),
        httpx.Response(401, json={"error": {"message": f"No auth credentials found for {KEY}"}}),
    ]
    assert (await call("POST", "/settings/test-model", json={"role": "chat"})).status_code == 502
    assert (await call("POST", "/settings/test-connection")).json()["error"]["code"] == "invalid_key"
    logging.getLogger("horizon.test").warning("someone logged the key %s by mistake", KEY)

    usage = await call("GET", "/usage", params={"sinceDays": 30})
    settings = await call("GET", "/settings")
    assert usage.status_code == settings.status_code == 200

    close_file_logging()
    await rt.stop()  # flush the WAL, close files so every byte can be read
    names, hits, log_text, secrets = await asyncio.to_thread(scan, Path(api.data_dir))
    assert "horizon.log" in names and "horizon.db" in names
    assert hits == [], f"the key leaked into {hits}"
    assert not [b for b in bodies if KEY in b], "an HTTP response carried the key"
    assert not [e for e in sse if KEY in e], "a global event carried the key"
    assert "sk-or-***" in log_text
    assert json.loads(secrets) == {"openRouterKey": KEY}


def scan(data: Path) -> tuple[set[str], list[str], str, str]:
    """Every file under data/ except the secrets file: which ones contain the key."""
    files = [p for p in data.rglob("*") if p.is_file() and p.name != "secrets.local.json"]
    hits = [str(p.relative_to(data)) for p in files if KEY.encode() in p.read_bytes()]
    log_text = (data / "logs" / "horizon.log").read_text(encoding="utf-8")
    return {p.name for p in files}, hits, log_text, (data / "secrets.local.json").read_text(encoding="utf-8")

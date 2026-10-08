"""Manual live generation check (M4 task 9.4, generation-jobs design D13). NEVER part of CI.

Runs only with `HORIZON_LIVE=1` and an OpenRouter key in the environment or the repo's `.env` (put there by you; never
pasted into chat; this test only checks that a key is present and never prints it). On the real clock, in `naive`:

1. `createDraft` (one DeepSeek structured-output call, ~$0.001);
2. one Lean `portrait_candidates` job (one Seedream 5.0 Flash base portrait, $0.018), then lock it;
3. one `emotion_regenerate` for `happy` (one Seedream edit of the locked base, $0.018);
4. a free `model_exists` check for the music model (no paid music call, D-83).

It asserts the image response shape (an image and a provider-reported `usage.cost`), WebP files of at most 250 KB,
`actualCostUsd` equal to the job's ledger rows, and a total of less than $0.05.

    PowerShell:  $env:HORIZON_LIVE=1; uv run pytest -m live -s tests/live/test_live_jobs.py
    bash:        HORIZON_LIVE=1 uv run pytest -m live -s tests/live/test_live_jobs.py
"""

from __future__ import annotations

import asyncio
import io
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager
from PIL import Image
from sqlalchemy import text

from horizon.config import load_config
from horizon.main import create_app
from horizon.runtime import Runtime

pytestmark = pytest.mark.live
BUDGET_USD = 0.05
API = "/api/v1"


async def _finish(client: httpx.AsyncClient, job_id: str, wait_s: float = 180) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    end = loop.time() + wait_s
    while loop.time() < end:
        j: dict[str, Any] = (await client.get(f"{API}/jobs/{job_id}")).json()
        if j["status"] not in ("queued", "running"):
            return j
        await asyncio.sleep(1.0)
    raise AssertionError(f"job {job_id} did not finish within {wait_s}s")


async def _rows(rt: Runtime, job_id: str) -> list[dict[str, Any]]:
    async with rt.db.read() as conn:
        res = await conn.execute(text("SELECT * FROM usage_records WHERE job_id = :j"), {"j": job_id})
        return [dict(r) for r in res.mappings()]


async def _webp_ok(client: httpx.AsyncClient, url: str) -> int:
    r = await client.get(url)
    assert r.status_code == 200, url
    with Image.open(io.BytesIO(r.content)) as img:
        assert img.format == "WEBP" and img.size == (768, 1024)
    assert len(r.content) <= 250 * 1024
    return len(r.content)


async def test_live_naive_creation(tmp_path: Path) -> None:
    cfg = load_config()  # env > .env, normal mode (test mode never reads a key)
    if os.environ.get("HORIZON_LIVE") != "1" or cfg.openrouter_key is None:
        pytest.skip("live run: set HORIZON_LIVE=1 and OPENROUTER_API_KEY (env or .env)")
    cfg = replace(cfg, data_dir=tmp_path / "live-jobs", test_mode=False, ai_env={})
    rt = Runtime(cfg)
    app = create_app(cfg, runtime=rt)
    async with LifespanManager(app, startup_timeout=60, shutdown_timeout=60), httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1", timeout=240) as client:
        assert rt.ai.impl("drafter", key_set=True) == "naive" and rt.ai.impl("image", key_set=True) == "naive"
        jobs: list[dict[str, Any]] = []

        r = await client.post(f"{API}/worlds/wld_seedMeridian/characters",
                              json={"seedPrompt": "Mira, a marine biologist who loves night dives", "intent": "expert"})
        assert r.status_code == 201, r.text
        cid = r.json()["character"]["id"]
        jobs.append(await _finish(client, r.json()["job"]["id"]))
        assert jobs[-1]["status"] == "succeeded", jobs[-1]
        ch = (await client.get(f"{API}/characters/{cid}")).json()
        print(f"\n  draft: {ch['profile']['name']}, {ch['profile']['role']}, age {ch['profile']['age']}")

        r = await client.post(f"{API}/jobs", json={"characterId": cid, "kind": "portrait_candidates"})
        assert r.status_code == 201, r.text
        jobs.append(await _finish(client, r.json()["id"]))
        assert jobs[-1]["status"] == "succeeded", jobs[-1]
        cand = (await client.get(f"{API}/characters/{cid}")).json()["appearance"]["candidates"][0]
        size = await _webp_ok(client, cand["url"])
        print(f"  base portrait: {size // 1024} KB WebP")
        r = await client.post(f"{API}/characters/{cid}/lock-portrait", json={"candidateId": cand["id"]})
        assert r.status_code == 200, r.text

        r = await client.post(f"{API}/jobs", json={"characterId": cid, "kind": "emotion_regenerate", "emotions": ["happy"]})
        assert r.status_code == 201, r.text
        jobs.append(await _finish(client, r.json()["id"]))
        assert jobs[-1]["status"] == "succeeded", jobs[-1]
        happy = (await client.get(f"{API}/characters/{cid}")).json()["emotions"]["happy"]["url"]
        print(f"  happy edit: {await _webp_ok(client, happy) // 1024} KB WebP")

        total = 0.0
        for j in jobs:
            rows = await _rows(rt, j["id"])
            spent = round(sum(float(x["cost_usd"]) for x in rows), 6)
            assert j["actualCostUsd"] == pytest.approx(spent, abs=1e-6), (j["kind"], j["actualCostUsd"], spent)
            if j["kind"] != "profile_draft":
                assert all(x["cost_source"] == "provider" for x in rows), "the image response carried no usage.cost"
            total += spent
            print(f"  {j['kind']}: ${spent:.6f} over {len(rows)} call(s)")
        listed = await rt.gateway.meta.model_exists(str(rt.settings_doc()["models"]["music"]))
        print(f"  music model listed on OpenRouter: {listed} (the song job stays procedural, D-83)")
        print(f"  total: ${total:.6f}")
        assert total < BUDGET_USD


async def test_live_song(tmp_path: Path) -> None:
    """creation-followups task 7.2, design D9: one naive `song` job (one Lyria 3 Clip call, $0.04) for a seed character,
    under a daily cap of today's spend + $0.05. Prints only the shape: chunks, bytes, format, duration, latency, cost.

        PowerShell:  $env:HORIZON_LIVE=1; uv run pytest -m live -s tests/live/test_live_jobs.py -k song
    """
    from horizon.gateway.errors import ProviderError
    from horizon.gateway.music import MusicResult
    from horizon.storage.audio import is_mp3, mp3_duration

    cfg = load_config()
    if os.environ.get("HORIZON_LIVE") != "1" or cfg.openrouter_key is None:
        pytest.skip("live run: set HORIZON_LIVE=1 and OPENROUTER_API_KEY (env or .env)")
    cfg = replace(cfg, data_dir=tmp_path / "live-song", test_mode=False, ai_env={})
    rt = Runtime(cfg)
    app = create_app(cfg, runtime=rt)
    seen: dict[str, Any] = {}
    async with LifespanManager(app, startup_timeout=60, shutdown_timeout=60), httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1", timeout=240) as client:
        assert rt.ai.impl("song", key_set=True) == "naive"
        original = rt.gateway.music.generate

        async def observed(*, model: str, prompt: str) -> MusicResult:
            seen["model"], seen["prompt_chars"] = model, len(prompt)
            try:
                r = await original(model=model, prompt=prompt)
            except ProviderError as e:
                seen["error"] = f"{e.code} (status {e.status}, maybe charged {e.maybe_charged})"
                raise
            seen.update(chunks=r.chunks, bytes=len(r.audio), head=r.audio[:4].hex(), mp3=is_mp3(r.audio),
                        duration=mp3_duration(r.audio), latency_ms=r.latency_ms, provider=r.provider,
                        cost=r.usage.cost_usd if r.usage else None)
            return r

        rt.gateway.music.generate = observed  # type: ignore[method-assign]
        spent = (await client.get(f"{API}/settings")).json()["spentTodayUsd"]
        r = await client.patch(f"{API}/settings", json={"budget": {"dailyCapUsd": round(spent + BUDGET_USD, 6)}})
        assert r.status_code == 200, r.text
        r = await client.post(f"{API}/jobs", json={"characterId": "chr_seedHana", "kind": "song"})
        assert r.status_code == 201, r.text
        assert r.json()["estimatedCostUsd"] == 0.04
        done = await _finish(client, r.json()["id"], wait_s=240)
        song = (await client.get(f"{API}/characters/chr_seedHana/song")).json()
        rows = await _rows(rt, done["id"])
        total = round(sum(float(x["cost_usd"]) for x in rows), 6)
        print(f"\n  music call: {seen}")
        print(f"  job: {done['status']}, song: {song['url'].rsplit('/', 1)[-1]}, format {song.get('format')}, "
              f"duration {song.get('durationSec')}, licenseNote: {song['licenseNote']}")
        print(f"  ledger: {[(x['category'], x['purpose'], x['cost_usd'], x['cost_source']) for x in rows]}  total ${total:.6f}")
        assert done["status"] == "succeeded", done
        if song.get("format") == "mp3":
            assert 5 <= float(song["durationSec"]) <= 40 and len(rows) == 1
        else:
            print("  Lyria unavailable at run time: the song fell back to the procedural theme (design D7)")
        assert total <= BUDGET_USD

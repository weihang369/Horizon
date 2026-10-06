"""Generated assets (generation-jobs tasks 3.6–3.8; generated-assets spec)."""

from __future__ import annotations

import io
import json
from typing import Any

from PIL import Image

from tests.conftest import Api
from tests.jobs.kit import API, cancel_overlay_jobs, character, job, ledger, rows, start


async def setup(api: Api, standard: bool = False) -> None:
    await api.set_key()
    await cancel_overlay_jobs(api)
    if standard:
        r = await api.client.patch(f"{API}/settings", json={"generationMode": "standard"})
        assert r.status_code == 200


async def served(api: Api, url: str) -> tuple[bytes, dict[str, str]]:
    r = await api.get(url)
    assert r.status_code == 200, url
    return r.content, dict(r.headers)


async def test_candidates_appear_immediately_and_tweak_keeps_the_batch(api: Api) -> None:
    await setup(api, standard=True)
    j = await start(api, {"characterId": "chr_mockSarah", "kind": "portrait_candidates"})
    cands = (await character(api, "chr_mockSarah"))["appearance"]["candidates"]
    assert [c["status"] for c in cands] == ["generating", "generating"]
    assert all(c["url"].startswith("data:image/gif") for c in cands)  # a blank placeholder: the contract needs a URL
    await api.drive(21000)
    assert (await job(api, j["id"]))["status"] == "succeeded"
    first = (await character(api, "chr_mockSarah"))["appearance"]["candidates"]
    assert [c["status"] for c in first] == ["ready", "ready"]
    t = await start(api, {"characterId": "chr_mockSarah", "kind": "portrait_tweak", "prompt": "warmer smile"})
    assert t["estimatedCostUsd"] == 0.018
    after = (await character(api, "chr_mockSarah"))["appearance"]["candidates"]
    assert [c["id"] for c in after[:2]] == [c["id"] for c in first] and after[2]["status"] == "generating"
    await api.drive(21000)
    after = (await character(api, "chr_mockSarah"))["appearance"]["candidates"]
    assert len(after) == 3 and all(c["status"] == "ready" for c in after)
    # a new candidates batch shows only the earlier selected one plus the new batch
    await api.post(f"{API}/characters/chr_mockSarah/lock-portrait", {"candidateId": after[2]["id"]}, status=200)
    await start(api, {"characterId": "chr_mockSarah", "kind": "portrait_candidates"})
    shown = (await character(api, "chr_mockSarah"))["appearance"]["candidates"]
    assert shown[0]["id"] == after[2]["id"] and shown[0]["selected"] and len(shown) == 3


async def test_lock_rules(api: Api) -> None:
    await setup(api)
    j = await start(api, {"characterId": "chr_mockSarah", "kind": "portrait_candidates"})
    (cand,) = (await character(api, "chr_mockSarah"))["appearance"]["candidates"]
    r = await api.post(f"{API}/characters/chr_mockSarah/lock-portrait", {"candidateId": cand["id"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"  # still generating
    r = await api.post(f"{API}/characters/chr_mockSarah/lock-portrait", {"candidateId": "cand_nope"})
    assert r.status_code == 404
    await api.drive(21000)
    assert (await job(api, j["id"]))["status"] == "succeeded"
    (cand,) = (await character(api, "chr_mockSarah"))["appearance"]["candidates"]
    ch = (await api.post(f"{API}/characters/chr_mockSarah/lock-portrait", {"candidateId": cand["id"]}, status=200)).json()
    assert ch["emotions"]["neutral"]["url"] == cand["url"] == ch["appearance"]["basePortraitUrl"]
    assert [c["selected"] for c in ch["appearance"]["candidates"]] == [True] and ch["creationStep"] == "emotions"


async def lock(api: Api, cid: str) -> dict[str, Any]:
    j = await start(api, {"characterId": cid, "kind": "portrait_candidates"})
    await api.drive(21000)
    assert (await job(api, j["id"]))["status"] == "succeeded"
    cand = next(c for c in (await character(api, cid))["appearance"]["candidates"] if c["status"] == "ready")
    out: dict[str, Any] = (await api.post(f"{API}/characters/{cid}/lock-portrait", {"candidateId": cand["id"]}, status=200)).json()
    return out


async def test_draft_emotions_go_live_and_files_are_webp(api: Api) -> None:
    await setup(api)
    await lock(api, "chr_mockSarah")
    j = await start(api, {"characterId": "chr_mockSarah", "kind": "emotion_set"})
    await api.drive(31000)
    assert (await job(api, j["id"]))["status"] == "succeeded"
    ch = await character(api, "chr_mockSarah")
    for e in ("happy", "sad", "angry"):
        url = ch["emotions"][e]["url"]
        assert url.startswith("/assets/gen/wld_seedMeridian/chr_mockSarah/portrait_") and url.endswith("_v1.webp")
        data, headers = await served(api, url)
        assert "immutable" in headers["cache-control"] and len(data) <= 250 * 1024
        with Image.open(io.BytesIO(data)) as img:
            assert img.format == "WEBP" and img.size == (768, 1024)
    assert ch["emotions"]["surprised"] is None
    originals = list((api.data_dir / "originals" / "wld_seedMeridian" / "chr_mockSarah").glob("*.png"))
    assert len(originals) >= 4  # the base candidate and three emotions
    tasks = (await job(api, j["id"]))["tasks"]
    assert all(t["resultRef"].startswith("emo_") and t["previewUrl"].startswith("/assets/gen/") for t in tasks)


async def test_approved_character_keeps_its_face_until_accepted(api: Api) -> None:
    await setup(api)
    before = await character(api, "chr_seedHana")
    old_url = before["emotions"]["sad"]["url"]
    j = await start(api, {"characterId": "chr_seedHana", "kind": "emotion_regenerate", "emotions": ["sad"]})
    await api.drive(16000)
    assert (await job(api, j["id"]))["status"] == "succeeded"
    ch = await character(api, "chr_seedHana")
    assert ch["emotions"]["sad"]["url"] == old_url
    versions = [a for a in await api.json(f"{API}/characters/chr_seedHana/assets") if a["emotion"] == "sad"]
    assert [(a["version"], a["isActive"]) for a in versions] == [(1, True), (2, False)]
    new = versions[1]
    assert new["url"] != old_url
    ch = (await api.post(f"{API}/assets/{new['id']}/accept", status=200)).json()
    assert ch["emotions"]["sad"]["url"] == new["url"] and ch["version"] == before["version"] + 1
    versions = [a for a in await api.json(f"{API}/characters/chr_seedHana/assets") if a["emotion"] == "sad"]
    assert [a["isActive"] for a in versions] == [False, True]
    assert (await api.get(old_url)).status_code == 200  # the old URL still serves the old image
    assert (await api.post(f"{API}/assets/emo_nope/accept")).status_code == 404


async def test_sheet_slices_into_emotions(api: Api) -> None:
    await setup(api)
    await lock(api, "chr_mockSarah")
    j = await start(api, {"characterId": "chr_mockSarah", "kind": "emotion_set", "technique": "expression_sheet"})
    assert [t["type"] for t in j["tasks"]] == ["expression_sheet", "emotion_image", "emotion_image", "emotion_image"]
    assert j["estimatedCostUsd"] == 0.018
    await api.drive(31000)
    done = await job(api, j["id"])
    assert done["status"] == "succeeded" and all(t["status"] == "succeeded" for t in done["tasks"])
    ch = await character(api, "chr_mockSarah")
    assert all(ch["emotions"][e] for e in ("happy", "sad", "angry"))
    image_rows = [r for r in await ledger(api, j["id"]) if r["category"] == "image"]
    assert len(image_rows) == 1 and image_rows[0]["purpose"] == "image_sheet"


async def test_procedural_theme(api: Api) -> None:
    await setup(api)
    j = await start(api, {"characterId": "chr_seedHana", "kind": "song"})
    assert j["estimatedCostUsd"] == 0
    await api.drive(41000)
    assert (await job(api, j["id"]))["status"] == "succeeded"
    song = await api.json(f"{API}/characters/chr_seedHana/song")
    assert song["status"] == "ready" and song["url"].endswith(".proc.json") and "format" not in song
    assert song["generation"]["model"] == "procedural" and song["generation"]["costUsd"] == 0
    assert "procedural" in song["licenseNote"].lower()
    data, _ = await served(api, song["url"])
    spec = json.loads(data)
    assert spec["kind"] == "horizon.theme" and spec["version"] == 1 and spec["seed"] == "chr_seedHana" and spec["brief"]
    assert [r for r in await ledger(api, j["id"]) if r["category"] == "music"] == []
    assert (await character(api, "chr_seedHana"))["themeSongId"] == song["id"]
    assert api.rt.fake is not None and api.rt.fake.counts["models"] >= 1  # the free music-model check


async def test_regenerated_emotion_gets_a_new_url(api: Api) -> None:
    await setup(api)
    await lock(api, "chr_mockSarah")
    urls = []
    for _ in range(2):
        j = await start(api, {"characterId": "chr_mockSarah", "kind": "emotion_regenerate", "emotions": ["happy"]})
        await api.drive(16000)
        assert (await job(api, j["id"]))["status"] == "succeeded"
        urls.append((await character(api, "chr_mockSarah"))["emotions"]["happy"]["url"])
    assert urls[0] != urls[1] and urls[1].endswith("_v2.webp")
    assert (await api.get(urls[0])).status_code == 200
    rows_ = await rows(api, "SELECT version, is_active FROM image_assets WHERE character_id='chr_mockSarah' AND emotion='happy'")
    assert sorted((r["version"], r["is_active"]) for r in rows_) == [(1, 0), (2, 1)]

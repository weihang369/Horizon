"""Character lifecycle over HTTP (generation-jobs tasks 3.5, 6.1–6.4; character-lifecycle, http-api specs)."""

from __future__ import annotations

from typing import Any

import pytest

from tests.conftest import Api
from tests.jobs.kit import API, Recorder, cancel_overlay_jobs, character, job, ledger, rows, start


async def draft(api: Api, seed: str = "Sarah, a doctor", intent: str = "expert", world: str = "wld_seedMeridian") -> dict[str, Any]:
    r = await api.post(f"{API}/worlds/{world}/characters", {"seedPrompt": seed, "intent": intent})
    assert r.status_code == 201, r.text
    out: dict[str, Any] = r.json()
    return out


async def test_draft_from_a_seed_prompt(api: Api) -> None:
    await api.set_key()
    out = await draft(api)
    ch, j = out["character"], out["job"]
    assert ch["status"] == "draft" and ch["creationStep"] == "seed" and ch["advisory"] is True
    assert ch["activeJobId"] == j["id"] and j["kind"] == "profile_draft" and j["status"] in ("queued", "running")
    assert [x["type"] for x in j["tasks"]] == ["profile", "appearance_summary", "palette_pick", "song_brief"]
    await api.drive(5000)
    assert (await job(api, j["id"]))["status"] == "succeeded"
    ch = await character(api, ch["id"])
    assert ch["profile"]["name"] == "Sarah" and ch["profile"]["role"] == "Doctor" and ch["creationStep"] == "profile"
    assert ch["profile"]["age"] >= 18 and "activeJobId" not in ch and ch["themeSongId"].startswith("song_")
    song = await api.json(f"{API}/characters/{ch['id']}/song")
    assert song["status"] == "pending" and song["brief"]["vibe"] == "Sarah's everyday theme"
    rows_ = await ledger(api, j["id"])
    assert [r["category"] for r in rows_] == ["profile"] * 4 and all(r["provider"] == "scripted" for r in rows_)
    assert sum(r["cost_usd"] for r in rows_) == pytest.approx(0.002)
    assert all(r["counts_to_creation_cap"] for r in rows_)


async def test_draft_without_a_key(api: Api) -> None:
    before = await rows(api, "SELECT id FROM characters")
    r = await api.post(f"{API}/worlds/wld_seedMeridian/characters", {"seedPrompt": "Noor, a baker", "intent": "companion"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "missing_key"
    assert await rows(api, "SELECT id FROM characters") == before


async def test_draft_in_an_unknown_world(api: Api) -> None:
    await api.set_key()
    r = await api.post(f"{API}/worlds/wld_nope/characters", {"seedPrompt": "Noor, a baker", "intent": "companion"})
    assert r.status_code == 404


async def test_edit_one_profile_field(api: Api) -> None:
    before = await character(api, "chr_seedHana")
    r = await api.client.patch(f"{API}/characters/chr_seedHana", json={"profile": {"tagline": "New"}})
    assert r.status_code == 200, r.text
    after = r.json()
    assert after["profile"]["tagline"] == "New"
    assert {k: v for k, v in after["profile"].items() if k != "tagline"} == \
        {k: v for k, v in before["profile"].items() if k != "tagline"}
    assert after["version"] == before["version"] + 1  # approved: the version bumps


async def test_patch_rejects_unknown_fields_and_invalid_values(api: Api) -> None:
    r = await api.client.patch(f"{API}/characters/chr_seedHana", json={"energy": {"current": 0}})
    assert r.status_code == 422
    r = await api.client.patch(f"{API}/characters/chr_seedHana", json={"profile": {"age": 12}})
    assert r.status_code == 422 and (await character(api, "chr_seedHana"))["profile"]["age"] == 26


async def test_edit_while_a_job_writes(api: Api) -> None:
    """Both the edit and the candidate are present afterwards (one writer serialises them)."""
    await api.set_key()
    await cancel_overlay_jobs(api)
    j = await start(api, {"characterId": "chr_mockSarah", "kind": "portrait_candidates"})
    import asyncio

    drive = asyncio.ensure_future(api.drive(21000))
    patch = asyncio.ensure_future(api.client.patch(f"{API}/characters/chr_mockSarah", json={"profile": {"tagline": "Edited"}}))
    await asyncio.gather(drive, patch)
    assert patch.result().status_code == 200
    assert (await job(api, j["id"]))["status"] == "succeeded"
    ch = await character(api, "chr_mockSarah")
    assert ch["profile"]["tagline"] == "Edited" and ch["appearance"]["candidates"][0]["status"] == "ready"


async def lock_first_candidate(api: Api, cid: str) -> dict[str, Any]:
    j = await start(api, {"characterId": cid, "kind": "portrait_candidates"})
    await api.drive(21000)
    assert (await job(api, j["id"]))["status"] == "succeeded"
    cand = next(c for c in (await character(api, cid))["appearance"]["candidates"] if c["status"] == "ready")
    r = await api.post(f"{API}/characters/{cid}/lock-portrait", {"candidateId": cand["id"]})
    assert r.status_code == 200, r.text
    out: dict[str, Any] = r.json()
    assert out["emotions"]["neutral"]["url"] == cand["url"] == out["appearance"]["basePortraitUrl"]
    return out


async def test_approve_gate(api: Api) -> None:
    await api.set_key()
    out = await draft(api, "Noor, a baker", "companion")
    cid = out["character"]["id"]
    await api.drive(5000)
    r = await api.post(f"{API}/characters/{cid}/approve")
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation"
    assert (await character(api, cid))["status"] == "draft"
    ch = await lock_first_candidate(api, cid)
    assert ch["creationStep"] == "emotions"
    r = await api.post(f"{API}/characters/{cid}/approve", status=200)
    body = r.json()
    assert body["status"] == "approved" and body["approvedAt"] and "creationStep" not in body


async def test_archive_then_restore(api: Api) -> None:
    r = await api.post(f"{API}/characters/chr_seedHana/archive", status=200)
    assert r.json()["status"] == "archived" and r.json()["archivedAt"]
    roster = await api.json(f"{API}/worlds/wld_seedSunnyHollow/characters")
    assert "chr_seedHana" not in [c["id"] for c in roster]
    r = await api.post(f"{API}/characters/chr_seedHana/restore", status=200)
    assert r.json()["status"] == "approved" and "archivedAt" not in r.json()


async def test_tombstone_after_delete(api: Api) -> None:
    rec = Recorder(api.rt)
    before = await character(api, "chr_seedVictor")
    r = await api.client.delete(f"{API}/characters/chr_seedVictor")
    assert r.status_code == 204
    t = await character(api, "chr_seedVictor")
    assert t["deletedAt"] and t["profile"]["name"] == before["profile"]["name"] and t["paletteId"] == before["paletteId"]
    assert t["emotions"]["neutral"]["url"] == before["emotions"]["neutral"]["url"]
    assert all(v is None for k, v in t["emotions"].items() if k != "neutral")
    assert await api.json(f"{API}/characters/chr_seedVictor/memory") == []
    assert await api.json(f"{API}/characters/chr_seedVictor/knowledge") == []
    assert await api.json(f"{API}/characters/chr_seedVictor/song") is None   # a read resolves; the song is gone (M6 G11)
    assert any(e["type"] == "entity.changed" and e["kind"] == "character" and e.get("id") == "chr_seedVictor"
               for e in rec.events)
    purge = await rows(api, "SELECT scope, ids FROM ai_purge_queue WHERE scope = 'character'")
    assert purge and '"chr_seedVictor"' in str(purge[0]["ids"])


async def test_command_on_a_tombstone(api: Api) -> None:
    await api.set_key()
    assert (await api.client.delete(f"{API}/characters/chr_seedVictor")).status_code == 204
    r = await api.client.patch(f"{API}/characters/chr_seedVictor", json={"advisory": True})
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    for path in ("approve", "archive", "restore"):
        assert (await api.post(f"{API}/characters/chr_seedVictor/{path}")).status_code == 404
    assert (await api.client.delete(f"{API}/characters/chr_seedVictor")).status_code == 404
    assert (await api.post(f"{API}/jobs", {"characterId": "chr_seedVictor", "kind": "song"})).status_code == 404


async def test_delete_during_a_generation_job(api: Api) -> None:
    await api.set_key()
    await cancel_overlay_jobs(api)
    out = await draft(api, "Noor, a baker", "companion")
    cid = out["character"]["id"]
    await api.drive(5000)
    await lock_first_candidate(api, cid)
    j = await start(api, {"characterId": cid, "kind": "emotion_set"})
    await api.drive(16000)  # happy and sad done, angry in flight
    fake_images = api.rt.fake.counts["images"] if api.rt.fake else 0
    assert (await api.client.delete(f"{API}/characters/{cid}")).status_code == 204
    await api.drive(30000)
    assert await rows(api, "SELECT id FROM generation_jobs WHERE id = :j", j=j["id"]) == []
    assert (api.rt.fake.counts["images"] if api.rt.fake else 0) == fake_images
    ch = await character(api, cid)
    gen = api.data_dir / "assets" / "gen" / ch["worldId"] / cid
    files = sorted(p.name for p in gen.rglob("*") if p.is_file())
    neutral = ch["emotions"]["neutral"]["url"].rsplit("/", 1)[1]
    assert files == [neutral]
    assert not (api.data_dir / "originals" / ch["worldId"] / cid).exists()


async def test_delete_during_a_live_reply(api: Api) -> None:
    from tests.sessions.kit import command, create, messages

    await api.set_key()
    await cancel_overlay_jobs(api)
    s = await create(api, "one_on_one", ["chr_seedVictor"])
    sid = s["session"]["id"]
    await api.drive(6000)
    await command(api, sid, "send", {"text": "Walk me through the whole case, step by step."})
    for _ in range(40):
        await api.drive(250)
        if any(m["status"] == "streaming" for m in await messages(api, sid)):
            break
    r = await api.client.delete(f"{API}/characters/chr_seedVictor")
    assert r.status_code == 409 and r.json()["error"]["details"]["activeSessionId"] == sid
    assert "deletedAt" not in await character(api, "chr_seedVictor")


async def test_regenerated_seed_emotion_after_reset(api: Api) -> None:
    """demo-data "Regenerated seed emotion after reset"."""
    await api.set_key()
    await cancel_overlay_jobs(api)
    shipped = (await character(api, "chr_seedHana"))["emotions"]["happy"]["url"]
    j = await start(api, {"characterId": "chr_seedHana", "kind": "emotion_regenerate", "emotions": ["happy"]})
    await api.drive(16000)
    new = next(a for a in await api.json(f"{API}/characters/chr_seedHana/assets") if a["emotion"] == "happy" and a["version"] == 2)
    await api.post(f"{API}/assets/{new['id']}/accept", status=200)
    assert (await character(api, "chr_seedHana"))["emotions"]["happy"]["url"] == new["url"]
    other = await start(api, {"characterId": "chr_seedHana", "kind": "song"})   # a user job still running at reset
    await api.post(f"{API}/admin/reset-demo", {"confirm": True}, status=204)
    assert (await job(api, other["id"]))["status"] == "cancelled"
    ch = await character(api, "chr_seedHana")
    assert ch["emotions"]["happy"]["url"] == shipped and "activeJobId" not in ch
    happy = [a for a in await api.json(f"{API}/characters/chr_seedHana/assets") if a["emotion"] == "happy"]
    assert [(a["version"], a["isActive"]) for a in happy] == [(1, True), (2, False)]
    assert (await job(api, j["id"]))["status"] == "succeeded"
    assert (await job(api, "job_mockKenjiEmotions"))["status"] in ("queued", "running")   # re-adopted


async def test_deleted_group_participant_is_skipped_as_archived(api: Api) -> None:
    from tests.sessions.kit import command, create, events, messages

    await api.set_key()
    await cancel_overlay_jobs(api)
    s = await create(api, "group", ["chr_seedHana", "chr_seedTakeshi"], world="wld_seedSunnyHollow")
    sid = s["session"]["id"]
    await api.drive(6000)
    await command(api, sid, "send", {"text": "Anyone hungry?"})
    await api.drive(20000)
    assert await messages(api, sid)
    assert (await api.client.delete(f"{API}/characters/chr_seedTakeshi")).status_code == 204
    await command(api, sid, "send", {"text": "@Takeshi what about you?", "mentions": ["chr_seedTakeshi"]})
    await api.drive(20000)
    msgs = await messages(api, sid)
    last_turns = [m for m in msgs if m["author"]["type"] == "character" and m["seq"] > max(
        x["seq"] for x in msgs if x["author"]["type"] == "user" and x["content"].startswith("@Takeshi"))]
    assert all(m["author"]["characterId"] != "chr_seedTakeshi" for m in last_turns)
    traces = [m.get("trace") or {} for m in last_turns]
    skipped = [x for t in traces for x in ((t.get("routing") or {}).get("skipped") or [])]
    assert {"characterId": "chr_seedTakeshi", "reason": "archived"} in skipped
    # transcripts with the deleted speaker still open, replay and export
    assert (await api.json(f"{API}/sessions/{sid}"))["messages"]
    assert await events(api, sid)
    export = await api.get(f"{API}/sessions/{sid}/export")
    assert export.status_code == 200

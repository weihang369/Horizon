"""Theme songs with Lyria 3 Clip (creation-followups; generated-assets "Theme song", "Procedural fallback for a failed
song"; ai-ports "Song generator"; design D3–D7). The provider is the in-process fake: no network, a silent MP3 stub."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from horizon.db import tables as t
from horizon.services import theme
from horizon.services.jobs import apply as ap
from horizon.storage.audio import silent_mp3
from tests.conftest import Api
from tests.jobs.kit import API, rows

BRIEF = {"genres": ["lo-fi"], "moods": ["warm"], "bpm": 84, "instruments": ["piano"], "vibe": "late-night clinic"}


async def put_audio(api: Api, cid: str, audio: bytes, duration: float | None = 0.2) -> str:
    async with api.rt.db.write() as tx:
        ch = await ap.live_character(tx.conn, cid)
        assert ch is not None
        return await ap.apply_audio_theme(tx.conn, ch, audio=audio, duration_sec=duration, brief=BRIEF,
                                          model="google/lyria-3-clip-preview", prompt="Instrumental theme", cost_usd=0.04,
                                          assets_dir=api.rt.cfg.assets_dir, job_id="job_mockAoiEmotions",
                                          now=api.rt.now_iso())


async def song(api: Api, cid: str) -> dict[str, Any]:
    out: dict[str, Any] = await api.json(f"{API}/characters/{cid}/song")
    return out


# ── task 3.3: the MP3 version ──
async def test_audio_theme_is_a_new_mp3_version(api: Api) -> None:
    clip = silent_mp3(8)
    await put_audio(api, "chr_seedHana", clip)
    s = await song(api, "chr_seedHana")
    assert s["status"] == "ready" and s["url"].endswith(".mp3") and s["format"] == "mp3"
    assert s["bytes"] == len(clip) and s["durationSec"] == 0.2 and s["instrumental"] is True
    assert s["generation"] == {"model": "google/lyria-3-clip-preview", "prompt": "Instrumental theme", "costUsd": 0.04,
                               "jobId": "job_mockAoiEmotions"}
    assert "lyria-3-clip-preview" in s["licenseNote"]
    api.rt.schema.check("ThemeSong", s)
    served = await api.get(s["url"])
    assert served.status_code == 200 and served.content == clip
    assert "immutable" in served.headers.get("cache-control", "")

    first_url = s["url"]
    await put_audio(api, "chr_seedHana", silent_mp3(4), duration=None)
    again = await song(api, "chr_seedHana")
    assert again["url"] != first_url and again["url"].endswith(".mp3")
    assert again["durationSec"] == theme.CLIP_SECONDS   # frames unreadable → the clip length
    assert (await api.get(first_url)).content == clip   # the old name still serves the old bytes


async def test_audio_file_exists_before_the_row_commits(api: Api) -> None:
    async with api.rt.db.write() as tx:
        ch = await ap.live_character(tx.conn, "chr_seedMei")
        assert ch is not None
        await ap.apply_audio_theme(tx.conn, ch, audio=silent_mp3(2), duration_sec=0.05, brief=BRIEF, model="m", prompt="p",
                                   cost_usd=0.04, assets_dir=api.rt.cfg.assets_dir, job_id="job_mockAoiEmotions",
                                   now=api.rt.now_iso())
        rel = (await tx.conn.execute(select(t.theme_songs.c.rel_path).where(
            t.theme_songs.c.character_id == "chr_seedMei"))).scalar()
        assert rel and rel.endswith(".mp3") and (api.rt.cfg.assets_dir / rel).is_file()   # inside the open transaction
    (row,) = await rows(api, "SELECT format, bytes FROM theme_songs WHERE character_id = 'chr_seedMei'")
    assert row == {"format": "mp3", "bytes": len(silent_mp3(2))}


# ── task 4.2: the naive port and its prompt ──
def test_prompt_states_every_brief_value() -> None:
    from horizon.ai.naive.creation import song_prompt

    p = song_prompt({"genres": ["lo-fi", "jazz"], "moods": ["warm"], "bpm": 84, "instruments": ["piano", "brushes"],
                     "vibe": "late-night clinic"}, "Sarah's Theme")
    assert p == ('Instrumental theme music for "Sarah\'s Theme". Genres: lo-fi, jazz. Mood: warm. '
                 "Instruments: piano, brushes. Tempo: about 84 BPM. Feel: late-night clinic. "
                 "No vocals, no lyrics. A 30-second piece that loops cleanly.")
    bare = song_prompt({"genres": [], "moods": [" "], "bpm": 120, "instruments": [], "vibe": ""}, "X's Theme")
    assert bare == 'Instrumental theme music for "X\'s Theme". Tempo: about 120 BPM. No vocals, no lyrics. ' \
                   "A 30-second piece that loops cleanly."


async def test_naive_profile_selects_lyria_and_the_override_keeps_procedural(api: Api) -> None:
    from horizon.ai.naive.creation import NaiveSong
    from horizon.ai.scripted.creation import ProceduralSong

    await api.set_key()
    assert (await api.post(f"{API}/_test/ai-profile", {"profile": "naive"})).status_code == 204
    assert isinstance(api.rt.ai.song(True), NaiveSong) and api.rt.ai.song(True).paid
    r = await api.post(f"{API}/_test/ai-profile", {"profile": "naive", "overrides": {"song": "scripted"}})
    assert r.status_code == 204
    assert isinstance(api.rt.ai.song(True), ProceduralSong) and not api.rt.ai.song(True).paid


# ── tasks 4.3–4.4: the song job in each profile ──
async def naive_profile(api: Api, **overrides: str) -> Any:
    from tests.jobs.kit import cancel_overlay_jobs

    await api.set_key()
    await cancel_overlay_jobs(api)
    r = await api.post(f"{API}/_test/ai-profile", {"profile": "naive", "overrides": overrides})
    assert r.status_code == 204
    fake = api.rt.fake
    assert fake is not None
    return fake


def quick_music_timeout(api: Api, seconds: float = 0.3) -> None:
    from dataclasses import replace

    music = api.rt.gateway.music
    music.cfg = replace(music.cfg, timeouts=replace(music.cfg.timeouts, music=seconds, chat_idle=seconds))


async def settle(api: Api, job_id: str) -> dict[str, Any]:
    from tests.jobs.test_naive import settle_job

    return await settle_job(api, job_id)


async def music_rows(api: Api, job_id: str) -> list[dict[str, Any]]:
    from tests.jobs.kit import ledger

    return [r for r in await ledger(api, job_id) if r["category"] == "music"]


async def test_song_estimate_follows_the_port(api: Api) -> None:
    await naive_profile(api)
    body = {"characterId": "chr_seedHana", "kind": "song"}
    assert (await api.post(f"{API}/jobs/estimate", body)).json()["estimatedCostUsd"] == 0.04
    await naive_profile(api, song="scripted")
    assert (await api.post(f"{API}/jobs/estimate", body)).json()["estimatedCostUsd"] == 0


async def test_lyria_song_reserves_bills_and_releases(api: Api) -> None:
    from tests.jobs.kit import start, until

    fake = await naive_profile(api)
    before = fake.counts["music"]
    await api.rt.music_slots.acquire()   # hold the music slot: the task waits before its preflight
    try:
        j = await start(api, {"characterId": "chr_seedHana", "kind": "song"})
        assert j["estimatedCostUsd"] == 0.04
        await until(lambda: api.rt.book.job_remaining(j["id"]) == 0.04)
    finally:
        api.rt.music_slots.release()
    done = await settle(api, j["id"])
    assert done["status"] == "succeeded" and done["actualCostUsd"] == 0.04
    assert api.rt.book.total() == 0
    s = await song(api, "chr_seedHana")
    assert s["url"].endswith(".mp3") and s["format"] == "mp3" and s["generation"]["costUsd"] == 0.04
    assert s["generation"]["model"] == "google/lyria-3-clip-preview" and s["durationSec"] > 0
    (row,) = await music_rows(api, j["id"])
    assert row["purpose"] == "song" and row["cost_usd"] == 0.04 and row["model"] == "google/lyria-3-clip-preview"
    assert fake.counts["music"] == before + 1
    (task,) = await rows(api, "SELECT provider_called_at, target_path FROM generation_tasks WHERE job_id = :j", j=j["id"])
    assert task["provider_called_at"] and (api.rt.cfg.data_dir / f"{task['target_path']}.mp3").is_file()   # the original
    body = (await api.get(s["url"])).content
    assert body == silent_mp3(8)


async def test_provider_error_falls_back_to_the_procedural_theme(api: Api) -> None:
    from tests.jobs.kit import start

    fake = await naive_profile(api)
    fake.music_mode = "fail"
    j = await start(api, {"characterId": "chr_seedHana", "kind": "song"})
    done = await settle(api, j["id"])
    assert done["status"] == "succeeded" and done["actualCostUsd"] == 0
    s = await song(api, "chr_seedHana")
    assert s["url"].endswith(".proc.json") and "format" not in s
    assert s["licenseNote"] == theme.FALLBACK_NOTE and s["generation"]["costUsd"] == 0
    assert await music_rows(api, j["id"]) == [] and api.rt.book.total() == 0


async def test_charged_timeout_falls_back_and_is_billed(api: Api) -> None:
    from tests.jobs.kit import start

    fake = await naive_profile(api)
    fake.music_mode = "stall"
    quick_music_timeout(api)
    j = await start(api, {"characterId": "chr_seedHana", "kind": "song"})
    done = await settle(api, j["id"])
    assert done["status"] == "succeeded" and done["actualCostUsd"] == 0.04
    s = await song(api, "chr_seedHana")
    assert s["url"].endswith(".proc.json") and s["licenseNote"] == theme.FALLBACK_NOTE
    assert s["generation"]["costUsd"] == 0.04
    (row,) = await music_rows(api, j["id"])
    assert row["cost_usd"] == 0.04 and row["cost_source"] == "estimate"


async def test_unusable_audio_falls_back_and_is_billed(api: Api) -> None:
    from tests.jobs.kit import start

    fake = await naive_profile(api)
    fake.music_mode = "not_mp3"
    j = await start(api, {"characterId": "chr_seedHana", "kind": "song"})
    done = await settle(api, j["id"])
    assert done["status"] == "succeeded"
    s = await song(api, "chr_seedHana")
    assert s["url"].endswith(".proc.json") and s["licenseNote"] == theme.FALLBACK_NOTE
    (row,) = await music_rows(api, j["id"])
    assert row["cost_usd"] == 0.04 and row["cost_source"] == "provider"
    (task,) = await rows(api, "SELECT target_path FROM generation_tasks WHERE job_id = :j", j=j["id"])
    assert not list((api.rt.cfg.data_dir / task["target_path"]).parent.glob("*.mp3"))   # nothing unusable kept


async def test_cap_reached_before_the_call_fails_without_a_request(api: Api) -> None:
    from tests.jobs.kit import start

    fake = await naive_profile(api)
    before_song = await song(api, "chr_seedHana")
    before = fake.counts["music"]
    await api.rt.music_slots.acquire()
    try:
        j = await start(api, {"characterId": "chr_seedHana", "kind": "song"})
        spent = (await api.json(f"{API}/settings"))["spentTodayUsd"]
        r = await api.client.patch(f"{API}/settings", json={"budget": {"dailyCapUsd": round(spent + 0.01, 6)}})
        assert r.status_code == 200
    finally:
        api.rt.music_slots.release()
    done = await settle(api, j["id"])
    assert done["status"] == "failed" and done["tasks"][0]["error"]["code"] == "daily_budget_exceeded"
    assert fake.counts["music"] == before and await music_rows(api, j["id"]) == []
    assert (await song(api, "chr_seedHana"))["url"] == before_song["url"]


async def test_song_fails_scenario_still_fails_under_lyria(api: Api) -> None:
    from tests.jobs.kit import start

    fake = await naive_profile(api)
    assert (await api.post(f"{API}/_test/scenario", {"id": "song_fails"})).status_code == 204
    before = fake.counts["music"]
    j = await start(api, {"characterId": "chr_seedHana", "kind": "song"})
    done = await settle(api, j["id"])
    assert done["status"] == "failed" and done["tasks"][0]["error"]["retryable"] is True
    assert fake.counts["music"] == before


# ── task 4.5: restart recovery of a song task (rows written as a crash leaves them) ──
async def test_recover_song_with_a_stored_clip_derives_only(api: Api) -> None:
    from horizon.services import assets
    from tests.jobs.test_recovery import set_task, stored_job

    fake = await naive_profile(api)
    j = await stored_job(api, kind="song", cid="chr_seedHana")
    tid = j["tasks"][0]["id"]
    ref = assets.original_rel("wld_seedMeridian", "chr_seedHana", tid, 1, "mp3")
    path = api.data_dir / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(silent_mp3(5))
    await set_task(api, tid, status="running", attempt=1, provider_called_at="2026-10-03T02:59:00.000Z", result_ref=ref)
    before = fake.counts["music"]
    await api.rt.jobs.recover()
    done = await settle(api, j["id"])
    assert done["status"] == "succeeded" and fake.counts["music"] == before
    s = await song(api, "chr_seedHana")
    assert s["url"].endswith(".mp3") and (await api.get(s["url"])).content == silent_mp3(5)
    assert await music_rows(api, j["id"]) == []


async def test_recover_song_sent_without_a_result_fails_retryably(api: Api) -> None:
    from horizon.services.jobs.scheduler import INTERRUPTED
    from tests.jobs.test_recovery import set_task, stored_job

    fake = await naive_profile(api)
    j = await stored_job(api, kind="song", cid="chr_seedHana")
    tid = j["tasks"][0]["id"]
    await set_task(api, tid, status="running", attempt=1, provider_called_at="2026-10-03T02:59:00.000Z")
    before = fake.counts["music"]
    await api.rt.jobs.recover()
    done = await settle(api, j["id"])
    assert done["status"] == "failed" and fake.counts["music"] == before
    assert done["tasks"][0]["error"] == {"code": "provider_error", "message": INTERRUPTED, "retryable": True}


async def test_recover_queued_song_runs_once(api: Api) -> None:
    from tests.jobs.test_recovery import stored_job

    fake = await naive_profile(api)
    j = await stored_job(api, kind="song", cid="chr_seedHana")
    before = fake.counts["music"]
    assert await api.rt.jobs.recover() == [j["id"]]
    done = await settle(api, j["id"])
    assert done["status"] == "succeeded" and fake.counts["music"] == before + 1
    assert (await song(api, "chr_seedHana"))["url"].endswith(".mp3")
    assert len(await music_rows(api, j["id"])) == 1


# ── task 4.6: the free music-model check ──
async def test_lyria_job_logs_the_music_model_check(api: Api, caplog: Any) -> None:
    import logging

    from tests.jobs.kit import start, until

    fake = await naive_profile(api)
    before = fake.counts["models"]
    with caplog.at_level(logging.INFO, logger="horizon.jobs"):
        j = await start(api, {"characterId": "chr_seedHana", "kind": "song"})
        await until(lambda: fake.counts["models"] == before + 1)
        await settle(api, j["id"])
        await until(lambda: any("procedural fallback (D-87)" in r.getMessage() for r in caplog.records))
    line = next(r.getMessage() for r in caplog.records if "procedural fallback (D-87)" in r.getMessage())
    assert "google/lyria-3-clip-preview" in line

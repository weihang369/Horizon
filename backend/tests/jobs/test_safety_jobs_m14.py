"""The image and song text checks (safety design D17; tasks 6.1–6.4; doc 12 I3, I4; generation-jobs "Starting a job",
"What the image text check reads"; generated-assets "Procedural fallback for a failed song", "A brief naming an artist
gets the procedural theme"; ai-ports "The guardrail checks prompt text"; http-api "Content refusals"). No network."""

from __future__ import annotations

import json
from typing import Any

from horizon.services import theme
from horizon.services.jobs.scheduler import BASE_REFUSED, TWEAK_REFUSED
from tests.conftest import Api
from tests.jobs.kit import API, cancel_overlay_jobs, ledger, rows, start
from tests.jobs.test_song import music_rows, settle, song

SARAH = "chr_mockSarah"   # a draft character
HANA = "chr_seedHana"
BLOCK = {"type": "noul", "noul": 0.93}


async def agent(api: Api, **overrides: str) -> Any:
    await api.set_key()
    await cancel_overlay_jobs(api)
    r = await api.post(f"{API}/_test/ai-profile", {"profile": "agent", "overrides": overrides})
    assert r.status_code == 204
    fake = api.rt.fake
    assert fake is not None
    return fake


def checks(api: Api, qid: str = "image_likeness") -> list[dict[str, Any]]:
    assert api.rt.fake is not None
    return [json.loads(r.content) for r in api.rt.fake.requests if r.url.path.endswith("/alpha/decisions")
            and qid in json.loads(r.content)["questions"]]


async def jobs_of(api: Api, cid: str) -> list[dict[str, Any]]:
    return await rows(api, "SELECT id FROM generation_jobs WHERE character_id = :c AND is_seed = 0", c=cid)


# ── 6.1: check_prompt and its cache ──
async def test_a_repeat_costs_nothing_and_a_fail_open_pass_is_not_kept(api: Api) -> None:
    from horizon.gateway.context import call_ctx

    fake = await agent(api)
    g = api.rt.ai.guardrail(True)
    ctx = call_ctx("guardrail", world_id="wld_seedMeridian", character_id=SARAH)
    a = await g.check_prompt(ctx, "image", "a 34-year-old doctor with short dark hair")
    b = await g.check_prompt(ctx, "image", "a 34-year-old doctor with short dark hair")
    assert a.verdict == b.verdict == "pass" and len(checks(api)) == 1
    assert [c["name"] for c in a.checks] == ["image_likeness", "image_nudity", "image_gore", "image_young"]
    fake.refuse_question("image_likeness", status=500)
    c = await g.check_prompt(ctx, "image", "a 40-year-old chef")
    assert c.fallback and c.verdict == "pass"
    await g.check_prompt(ctx, "image", "a 40-year-old chef")
    assert len(checks(api)) == 3                                   # the failed one was asked again


async def test_naive_and_scripted_pass_with_no_call(api: Api) -> None:
    from horizon.gateway.context import call_ctx

    await api.set_key()
    ctx = call_ctx("guardrail", world_id="wld_seedMeridian", character_id=SARAH)
    for profile in ("naive", "scripted"):
        assert (await api.post(f"{API}/_test/ai-profile", {"profile": profile})).status_code == 204
        res = await api.rt.ai.guardrail(True).check_prompt(ctx, "image", "make him look like Henry Cavill")
        assert res.verdict == "pass" and res.checks == []
    assert checks(api) == []


# ── 6.2: at job start ──
async def test_a_likeness_tweak_is_refused_with_no_job_or_hold(api: Api) -> None:
    fake = await agent(api, image="scripted")
    fake.answer_question("image_likeness", BLOCK)
    r = await api.post(f"{API}/jobs", {"characterId": SARAH, "kind": "portrait_tweak",
                                      "prompt": "make him look like Henry Cavill"})
    assert r.status_code == 451
    assert r.json() == {"error": {"code": "content_refused", "message": TWEAK_REFUSED, "retryable": True}}
    assert await jobs_of(api, SARAH) == [] and api.rt.book.total() == 0
    [req] = checks(api)
    assert "Henry Cavill" in req["state"]["quoted_text"]
    [row] = await rows(api, "SELECT job_id, character_id, purpose FROM usage_records WHERE purpose = 'guardrail'")
    assert row == {"job_id": None, "character_id": SARAH, "purpose": "guardrail"}


async def test_a_refused_base_and_a_reworded_retry(api: Api) -> None:
    fake = await agent(api, image="scripted")
    fake.answer_question("image_young", BLOCK)
    r = await api.post(f"{API}/jobs", {"characterId": SARAH, "kind": "portrait_candidates", "prompt": "looks about 12"})
    assert r.status_code == 451 and r.json()["error"]["message"] == BASE_REFUSED
    assert "Also: looks about 12" in checks(api)[0]["state"]["quoted_text"]   # the subject block and the API-only note
    fake.answer_question("image_young", None)
    j = await start(api, {"characterId": SARAH, "kind": "portrait_candidates", "prompt": "a square jaw"})
    assert j["status"] in ("queued", "running")


async def test_edits_are_not_checked(api: Api) -> None:
    await agent(api, image="scripted")
    j = await start(api, {"characterId": HANA, "kind": "emotion_regenerate", "emotions": ["happy"]})
    assert j["id"] and checks(api) == []


async def test_jev_down_lets_the_job_start(api: Api, caplog: Any) -> None:
    fake = await agent(api, image="scripted")
    fake.refuse_question("image_likeness", status=500)
    j = await start(api, {"characterId": SARAH, "kind": "portrait_tweak", "prompt": "make him look like Henry Cavill"})
    assert j["id"] and "image text check" in caplog.text


# ── 6.3: the song brief ──
async def song_job(api: Api, brief: dict[str, Any]) -> dict[str, Any]:
    full = {"genres": ["lo-fi"], "moods": ["warm"], "bpm": 84, "instruments": ["guitar"], **brief}
    return await start(api, {"characterId": HANA, "kind": "song", "brief": full})


async def test_a_named_band_gets_the_procedural_theme_with_its_note(api: Api) -> None:
    fake = await agent(api)
    fake.answer_question("song_copy", {"type": "noul", "noul": 0.95})
    music = fake.counts["music"]
    j = await song_job(api, {"genres": ["indie rock"], "vibe": "sounds like Coldplay's Yellow"})
    done = await settle(api, j["id"])
    assert done["status"] == "succeeded" and fake.counts["music"] == music       # no music request
    s = await song(api, HANA)
    assert s["url"].endswith(".proc.json") and s["licenseNote"] == theme.BRIEF_REFUSED_NOTE
    [row] = [x for x in await ledger(api, j["id"]) if x["purpose"] == "guardrail"]
    assert row["category"] == "decision"                                        # its spend carries the job's ID
    [req] = checks(api, "song_copy")
    assert "Coldplay" in req["state"]["quoted_text"]


async def test_a_genre_brief_calls_the_music_model(api: Api) -> None:
    fake = await agent(api)
    fake.answer_question("song_copy", {"type": "noul", "noul": 0.06})
    music = fake.counts["music"]
    j = await song_job(api, {"genres": ["indie rock"], "vibe": "warm British indie rock, chiming guitars"})
    done = await settle(api, j["id"])
    assert done["status"] == "succeeded" and fake.counts["music"] == music + 1
    assert (await song(api, HANA))["url"].endswith(".mp3")


def test_the_notes_by_reason() -> None:
    assert theme.fallback_note("brief_refused") == theme.BRIEF_REFUSED_NOTE
    assert theme.fallback_note("content_refused") == ("The music model declined this brief, so this is the procedural "
                                                      "theme rendered in the app.")
    assert theme.fallback_note("provider_error") == theme.FALLBACK_NOTE == theme.fallback_note("timeout")


async def test_other_faults_keep_the_fallback_note(api: Api) -> None:
    fake = await agent(api)
    fake.music_mode = "fail"
    j = await song_job(api, {"genres": ["lo-fi"], "vibe": "late-night clinic"})
    done = await settle(api, j["id"])
    assert done["status"] == "succeeded" and (await song(api, HANA))["licenseNote"] == theme.FALLBACK_NOTE
    assert await music_rows(api, j["id"]) == []

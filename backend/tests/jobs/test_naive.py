"""Naive creation ports against the in-process fake provider (generation-jobs tasks 9.1–9.3)."""

from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

from horizon.ai.naive.creation import draft_schema
from horizon.ai.scripted.drafts import draft_from_seed
from horizon.contract.validate import default_schema
from horizon.runtime import load_palettes
from tests.conftest import SEED_DIR, Api
from tests.jobs.kit import API, cancel_overlay_jobs, character, job, ledger, rows, start

SEED = Path(__file__).resolve().parents[3] / "seed"
PALETTES = [p["id"] for p in json.loads((SEED / "palettes.json").read_text(encoding="utf-8"))["data"]]


def chat_answer(content: str, cost: float = 0.0004) -> httpx.Response:
    return httpx.Response(200, json={
        "id": "gen-draft-1", "model": "deepseek/deepseek-v4.1-flash", "provider": "DeepSeek", "object": "chat.completion",
        "usage": {"prompt_tokens": 900, "completion_tokens": 700, "total_tokens": 1600, "cost": cost},
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}]})


def valid_draft(seed: str = "Sarah, a doctor") -> dict[str, Any]:
    d = draft_from_seed(seed, "expert", PALETTES)
    d["profile"] = {k: v for k, v in d["profile"].items() if k not in ("exampleLines", "relationshipToUser", "systemPromptPreview")}
    return d


async def settle_job(api: Api, job_id: str) -> dict[str, Any]:
    """Naive calls don't pace on the clock: tick the runner until the job is terminal."""
    for _ in range(400):
        j = await job(api, job_id)
        if j["status"] not in ("queued", "running"):
            return j
        await api.drive(250)
        await asyncio.sleep(0.005)
    raise AssertionError("job did not finish")


async def naive(api: Api, **overrides: str) -> None:
    await api.set_key()
    await cancel_overlay_jobs(api)
    body: dict[str, Any] = {"profile": "scripted", "overrides": overrides}
    assert (await api.post(f"{API}/_test/ai-profile", body)).status_code == 204


async def draft(api: Api) -> dict[str, Any]:
    r = await api.post(f"{API}/worlds/wld_seedMeridian/characters", {"seedPrompt": "Sarah, a doctor", "intent": "expert"})
    assert r.status_code == 201, r.text
    out: dict[str, Any] = r.json()
    return out


# ── 9.1: the naive drafter ──
async def test_naive_draft_is_schema_valid(api: Api) -> None:
    await naive(api, drafter="naive")
    fake = api.rt.fake
    assert fake is not None
    fake.queued.append(chat_answer(json.dumps(valid_draft())))
    out = await draft(api)
    done = await settle_job(api, out["job"]["id"])
    assert done["status"] == "succeeded", done
    ch = await character(api, out["character"]["id"])
    assert ch["profile"]["name"] == "Sarah" and ch["creationStep"] == "profile"
    assert ch["paletteId"] == valid_draft()["paletteId"] and ch["appearance"]["appearanceSummary"]
    rows_ = await ledger(api, out["job"]["id"])
    assert len(rows_) == 1 and rows_[0]["purpose"] == "profile" and rows_[0]["counts_to_creation_cap"]
    assert fake.counts["chat"] == 1   # one call; the other three parts apply the stored answer at $0
    body = json.loads(next(r for r in reversed(fake.requests) if r.url.path.endswith("/chat/completions")).content)
    # JSON mode (DeepSeek's own endpoint has no strict json_schema, so that skipped the pinned provider), the schema in
    # the system prompt, and room for a whole draft (one measured 1,229 tokens in the 2026-10-06 live run)
    assert body["response_format"] == {"type": "json_object"}
    assert json.dumps(draft_schema(list(load_palettes(SEED_DIR))), separators=(",", ":")) in body["messages"][0]["content"]
    assert body["provider"]["order"] == ["DeepSeek"] and body["reasoning"] == {"enabled": False}
    assert body["max_tokens"] == 2400


def test_draft_schema_restates_every_contract_limit() -> None:
    """The model is told each limit `parse_draft` enforces: a limit missing here (as `vibe` ≤ 2 was) fails drafts."""
    defs = default_schema().defs
    keys = ("minItems", "maxItems", "minLength", "maxLength", "minimum", "maximum", "pattern", "enum")

    def walk(contract: Any, ours: Any, path: str) -> list[str]:
        if not isinstance(contract, dict) or not isinstance(ours, dict):
            return []
        out = [f"{path}: {k}={contract[k]!r}, draft has {ours.get(k)!r}" for k in keys
               if k in contract and contract[k] != ours.get(k) and not (k == "maximum" and contract[k] >= 2**53 - 1)]
        for name, sub in (contract.get("properties") or {}).items():
            if name in (ours.get("properties") or {}):
                out += walk(sub, ours["properties"][name], f"{path}.{name}")
        if "items" in contract and "items" in ours:
            out += walk(contract["items"], ours["items"], f"{path}[]")
        return out

    ours = draft_schema(list(load_palettes(SEED_DIR)))["properties"]
    gaps = (walk(defs["CharacterProfile"], ours["profile"], "profile")
            + walk(defs["Appearance"]["properties"]["attributes"], ours["attributes"], "attributes")
            + walk(defs["SongBrief"], ours["brief"], "brief"))
    assert gaps == []


async def test_naive_draft_missing_field_or_minor_fails(api: Api) -> None:
    await naive(api, drafter="naive")
    fake = api.rt.fake
    assert fake is not None
    bad = valid_draft()
    del bad["brief"]
    minor = valid_draft()
    minor["profile"]["age"] = 16
    for content in (json.dumps(bad), json.dumps(minor), "not json"):
        fake.queued.append(chat_answer(content))
        out = await draft(api)
        done = await settle_job(api, out["job"]["id"])
        assert done["status"] == "failed"
        profile_task = done["tasks"][0]
        assert profile_task["status"] == "failed" and profile_task["error"]["code"] == "provider_error"
        assert profile_task["error"]["retryable"] is True
        ch = await character(api, out["character"]["id"])
        assert ch["profile"]["role"] == "Drafting…" and ch["creationStep"] == "seed"   # unchanged
        assert len(await ledger(api, out["job"]["id"])) == 1   # the provider charged; the row is kept
        await api.client.delete(f"{API}/characters/{out['character']['id']}")


# ── 9.2: the naive image generator ──
async def lock_scripted_base(api: Api, cid: str) -> None:
    j = await start(api, {"characterId": cid, "kind": "portrait_candidates"})
    await api.drive(21000)
    assert (await job(api, j["id"]))["status"] == "succeeded"
    cand = next(c for c in (await character(api, cid))["appearance"]["candidates"] if c["status"] == "ready")
    await api.post(f"{API}/characters/{cid}/lock-portrait", {"candidateId": cand["id"]}, status=200)


async def test_emotion_edit_sends_the_base_portrait(api: Api) -> None:
    await naive(api)
    await lock_scripted_base(api, "chr_mockSarah")
    await api.post(f"{API}/_test/ai-profile", {"profile": "scripted", "overrides": {"image": "naive"}}, status=204)
    fake = api.rt.fake
    assert fake is not None
    j = await start(api, {"characterId": "chr_mockSarah", "kind": "emotion_regenerate", "emotions": ["happy"]})
    done = await settle_job(api, j["id"])
    assert done["status"] == "succeeded"
    req = next(r for r in reversed(fake.requests) if r.url.path.endswith("/images"))
    body = json.loads(req.content)
    assert len(body["input_references"]) == 1
    ref = body["input_references"][0]
    assert ref["type"] == "image_url" and ref["image_url"]["url"].startswith("data:image/png;base64,")
    ch = await character(api, "chr_mockSarah")
    expected = api.rt.prompt_compiler.emotion_edit(ch["profile"], "happy").prompt
    assert body["prompt"] == expected and body["n"] == 1 and body["aspect_ratio"] == "3:4" and body["resolution"] == "1K"
    rows_ = await ledger(api, j["id"])
    assert len(rows_) == 1 and rows_[0]["purpose"] == "image_emotion" and rows_[0]["provider"] == "Seed"


async def test_svg_base_is_rejected_for_naive_edits(api: Api) -> None:
    await naive(api, image="naive")
    r = await api.post(f"{API}/jobs", {"characterId": "chr_seedHana", "kind": "emotion_regenerate", "emotions": ["happy"]})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation" and err["details"]["reason"] == "base_not_raster"
    r = await api.post(f"{API}/jobs", {"characterId": "chr_seedHana", "kind": "emotion_set"})   # D-90's scenario
    assert r.status_code == 422 and r.json()["error"]["details"]["reason"] == "base_not_raster"
    assert await rows(api, "SELECT id FROM generation_jobs WHERE character_id = 'chr_seedHana'") == []
    assert api.rt.book.total() == 0   # rejected before anything was reserved
    r = await api.post(f"{API}/jobs", {"characterId": "chr_mockSarah", "kind": "emotion_set"})
    assert r.status_code == 422 and r.json()["error"]["details"]["reason"] == "no_base"
    # the scripted generator accepts any base
    await api.post(f"{API}/_test/ai-profile", {"profile": "scripted"}, status=204)
    assert (await api.post(f"{API}/jobs", {"characterId": "chr_seedHana", "kind": "emotion_set"})).status_code == 201


# ── 9.3: a naive wizard run against the fake ──
async def test_naive_wizard_run(api: Api) -> None:
    await api.set_key()
    await cancel_overlay_jobs(api)
    assert (await api.post(f"{API}/_test/ai-profile", {"profile": "naive"})).status_code == 204
    fake = api.rt.fake
    assert fake is not None
    before = dict(fake.counts)
    fake.queued.append(chat_answer(json.dumps(valid_draft())))
    out = await draft(api)
    cid = out["character"]["id"]
    assert (await settle_job(api, out["job"]["id"]))["status"] == "succeeded"
    pj = await start(api, {"characterId": cid, "kind": "portrait_candidates"})
    assert (await settle_job(api, pj["id"]))["status"] == "succeeded"
    cand = (await character(api, cid))["appearance"]["candidates"][0]
    await api.post(f"{API}/characters/{cid}/lock-portrait", {"candidateId": cand["id"]}, status=200)
    ej = await start(api, {"characterId": cid, "kind": "emotion_set"})
    assert (await settle_job(api, ej["id"]))["status"] == "succeeded"
    sj = await start(api, {"characterId": cid, "kind": "song"})
    assert (await settle_job(api, sj["id"]))["status"] == "succeeded"
    ch = (await api.post(f"{API}/characters/{cid}/approve", status=200)).json()
    assert ch["status"] == "approved"
    for e in ("neutral", "happy", "sad", "angry"):
        served = await api.get(ch["emotions"][e]["url"])
        assert served.status_code == 200 and len(served.content) <= 250 * 1024
        with Image.open(io.BytesIO(served.content)) as img:
            assert img.format == "WEBP" and img.size == (768, 1024)
    song = await api.json(f"{API}/characters/{cid}/song")
    assert song["status"] == "ready" and song["url"].endswith(".mp3") and song["format"] == "mp3"   # Lyria 3 Clip (D-87)
    delta = {k: fake.counts[k] - before.get(k, 0) for k in fake.counts}
    assert delta.get("chat", 0) == 2 and delta.get("music", 0) == 1   # the draft, then the song (both on the chat endpoint)
    assert delta.get("images", 0) == 4 and delta.get("models", 0) == 1

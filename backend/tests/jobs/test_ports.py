"""Creation ports and their selection (generation-jobs task 3.4; ai-ports "AI profile selection")."""

from __future__ import annotations

import io

from PIL import Image

from horizon.ai.ports import ImageJob
from horizon.ai.profile import NAIVE_PORTS, ProfileSpec
from horizon.ai.scripted.creation import placeholder_png
from tests.conftest import Api
from tests.jobs.kit import API, cancel_overlay_jobs, character, job, start


def image_job(task_id: str, mode: str = "base", label: str = "neutral") -> ImageJob:
    return ImageJob(task_id=task_id, mode=mode, prompt="p", model="m", price_kind="portrait", duration_ms=0, label=label,
                    palette=("#071A1F", "#2EC4B6", "#CBF3F0"))


def test_placeholder_is_deterministic_per_task() -> None:
    a = placeholder_png(image_job("task_01A"))
    assert a == placeholder_png(image_job("task_01A"))
    assert a != placeholder_png(image_job("task_01B", label="happy"))
    with Image.open(io.BytesIO(a)) as img:
        assert img.size == (832, 1110)
    with Image.open(io.BytesIO(placeholder_png(image_job("task_s", mode="sheet")))) as img:
        assert img.size == (1536, 1024)


def test_naive_ports_and_overrides() -> None:
    assert NAIVE_PORTS == {"turn", "router", "drafter", "image", "song"}
    spec = ProfileSpec.from_env({"HORIZON_AI_PROFILE": "naive", "HORIZON_AI_IMAGE": "scripted"})
    assert spec.choose("image", key_set=True) == "scripted"
    assert spec.choose("drafter", key_set=True) == "naive"
    assert spec.choose("song", key_set=True) == "naive"  # Lyria 3 Clip (D-87)
    procedural = ProfileSpec.from_env({"HORIZON_AI_PROFILE": "naive", "HORIZON_AI_SONG": "scripted"})
    assert procedural.choose("song", key_set=True) == "scripted"
    assert ProfileSpec.from_env({}).choose("song", key_set=False) == "scripted"
    assert ProfileSpec.from_env({"HORIZON_AI_DRAFTER": "scripted"}).choose("drafter", key_set=True) == "scripted"


async def test_scripted_images_under_a_naive_profile(api: Api) -> None:
    """ai-ports "Scripted images under a naive profile": placeholders, no provider image request."""
    await api.set_key()
    await cancel_overlay_jobs(api)
    r = await api.post(f"{API}/_test/ai-profile", {"profile": "naive", "overrides": {"image": "scripted"}})
    assert r.status_code == 204
    fake = api.rt.fake
    assert fake is not None
    before = fake.counts["images"]
    j = await start(api, {"characterId": "chr_mockSarah", "kind": "portrait_candidates"})
    await api.drive(21000)
    assert (await job(api, j["id"]))["status"] == "succeeded"
    assert fake.counts["images"] == before
    ch = await character(api, "chr_mockSarah")
    assert ch["appearance"]["candidates"][0]["status"] == "ready"

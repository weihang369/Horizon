"""Contract (task 8.3): every M1b route, for every seed and overlay entity, returns a body that validates against
`schema.json`. The app itself validates in test mode (a mismatch is a 500); this suite also re-validates on the
client side, including composite bodies, so a response can't slip through unchecked.
"""

from __future__ import annotations

from typing import Any

from horizon.contract.validate import default_schema
from tests.conftest import Api

SCHEMA = default_schema()


def ok(def_name: str, value: Any) -> None:
    problems = SCHEMA.errors(def_name, value)
    assert not problems, f"{def_name}: {problems[:3]}"


async def test_every_route_validates(api: Api) -> None:
    calls = 0

    async def get(path: str, **kw: Any) -> Any:
        nonlocal calls
        calls += 1
        r = await api.get(path, **kw)
        assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:200]}"
        return r.json()

    ok("AppSettings", await get("/api/v1/settings"))
    worlds = await get("/api/v1/worlds")
    for w in worlds:
        ok("World", w)
        ok("World", await get(f"/api/v1/worlds/{w['id']}"))
        roster = await get(f"/api/v1/worlds/{w['id']}/characters", params={"includeArchived": "true"})
        for c in roster:
            ok("Character", c)
            ok("Character", await get(f"/api/v1/characters/{c['id']}"))
            for a in await get(f"/api/v1/characters/{c['id']}/assets"):
                ok("EmotionAsset", a)
            song = await get(f"/api/v1/characters/{c['id']}/song")
            if song is not None:
                ok("ThemeSong", song)
            for m in await get(f"/api/v1/characters/{c['id']}/memory"):
                ok("MemoryItem", m)
            for k in await get(f"/api/v1/characters/{c['id']}/knowledge"):
                ok("KnowledgeSource", k)
                body = await get(f"/api/v1/knowledge/{k['id']}")
                ok("KnowledgeSource", body["source"])
                for ch in body["chunks"]:
                    ok("KnowledgeChunk", ch)
        for s in await get(f"/api/v1/worlds/{w['id']}/sessions"):
            ok("Session", s)
            snap = await get(f"/api/v1/sessions/{s['id']}")
            ok("Session", snap["session"])
            assert isinstance(snap["lastSeq"], int) and set(snap) == {"session", "messages", "lastSeq"}
            if SCHEMA.has("SessionSnapshot"):
                ok("SessionSnapshot", snap)
            for m in (await get(f"/api/v1/sessions/{s['id']}/messages", params={"limit": 1000}))["items"]:
                ok("Message", m)
                if m.get("trace"):
                    ok("TurnTrace", await get(f"/api/v1/messages/{m['id']}/trace"))
            for e in (await get(f"/api/v1/sessions/{s['id']}/events", params={"limit": 1000}))["items"]:
                ok("SessionEvent", e)
    for u in (await get("/api/v1/usage", params={"limit": 1000}))["items"]:
        ok("UsageRecord", u)
    summary = await get("/api/v1/usage/summary")
    if SCHEMA.has("UsageSummary"):
        ok("UsageSummary", summary)
    for j in await get("/api/v1/jobs", params={"active": "true"}):
        ok("GenerationJob", j)
    ok("GenerationJob", await get("/api/v1/jobs/job_mockAoiEmotions"))
    assert calls > 150


async def test_error_bodies_validate(api: Api) -> None:
    for path in ("/api/v1/sessions/ses_nope", "/api/v1/characters/chr_nope", "/api/v1/knowledge/kno_nope"):
        r = await api.get(path)
        ok("HorizonErrorShape", r.json()["error"])

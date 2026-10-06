"""API foundation (tasks 5.1–5.6) and world CRUD (task 8.1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from horizon.contract.validate import default_schema
from tests.conftest import Api

SCHEMA = default_schema()
COVER = {"kind": "preset", "presetId": "cover_night_skyline"}


def envelope(body: dict[str, Any], code: str) -> None:
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert not SCHEMA.errors("HorizonErrorShape", body["error"])


# ── 5.1 the error envelope ──
async def test_unknown_record_route_and_method(api: Api) -> None:
    r = await api.get("/api/v1/sessions/ses_nope")
    assert r.status_code == 404
    envelope(r.json(), "not_found")
    assert r.json()["error"]["retryable"] is False
    r = await api.get("/api/v1/nothing/here")
    assert r.status_code == 404
    envelope(r.json(), "not_found")
    r = await api.client.put("/api/v1/worlds")
    assert r.status_code == 405
    envelope(r.json(), "validation")


async def test_schema_invalid_body_is_validation(api: Api) -> None:
    r = await api.client.post("/api/v1/worlds", json={"cover": COVER})
    assert r.status_code == 422
    envelope(r.json(), "validation")
    assert any(f["field"] == "name" for f in r.json()["error"]["details"]["fields"])


async def test_unhandled_error_is_a_generic_500(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    from horizon.services import reads

    async def boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("secret internals sk-or-v1-leak")

    monkeypatch.setattr(reads, "list_worlds", boom)
    r = await api.get("/api/v1/worlds")
    assert r.status_code == 500
    envelope(r.json(), "provider_error")
    assert "sk-or" not in r.text and "internals" not in r.text


# ── 5.2 contract validation and OpenAPI ──
async def test_malformed_response_fails_in_test_mode(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    from horizon.services import reads

    original = reads.get_world

    async def bad(*a: Any, **k: Any) -> Any:
        w = await original(*a, **k)
        w["characterCount"] = "three"
        return w

    monkeypatch.setattr(reads, "get_world", bad)
    r = await api.get("/api/v1/worlds/wld_seedMeridian")
    assert r.status_code == 500
    assert "World" in r.json()["error"]["message"]


async def test_openapi_has_contract_schemas(api: Api) -> None:
    spec = await api.json("/api/openapi.json")
    assert "World" in spec["components"]["schemas"]
    assert "#/$defs/" not in str(spec)


# ── 5.3 pagination ──
async def test_paging_a_seed_session(api: Api) -> None:
    sid = "ses_seedDebate4Day"
    whole = (await api.json(f"/api/v1/sessions/{sid}/events", params={"limit": 1000}))["items"]
    got, cursor = [], None
    while True:
        params: dict[str, Any] = {"limit": 10}
        if cursor:
            params["cursor"] = cursor
        page = await api.json(f"/api/v1/sessions/{sid}/events", params=params)
        got += page["items"]
        cursor = page["nextCursor"]
        if cursor is None:
            break
    assert got == whole
    assert [e["seq"] for e in got] == list(range(1, len(whole) + 1))


@pytest.mark.parametrize("params", [{"limit": 1001}, {"limit": 0}, {"cursor": "not-a-cursor!"}])
async def test_bad_paging_is_validation(api: Api, params: dict[str, Any]) -> None:
    r = await api.get("/api/v1/sessions/ses_seedDebate4Day/messages", params=params)
    assert r.status_code == 422
    envelope(r.json(), "validation")


async def test_usage_pages_by_at_and_id(api: Api) -> None:
    whole = (await api.json("/api/v1/usage", params={"limit": 1000}))["items"]
    got, cursor = [], None
    while True:
        page = await api.json("/api/v1/usage", params={"limit": 7, **({"cursor": cursor} if cursor else {})})
        got += page["items"]
        cursor = page["nextCursor"]
        if not cursor:
            break
    assert got == whole and len(got) > 7


# ── 5.4 idempotency ──
async def test_retried_create_makes_one_world(api: Api) -> None:
    body = {"name": "My Street", "cover": COVER}
    h = {"Idempotency-Key": "k-create-1"}
    a = await api.client.post("/api/v1/worlds", json=body, headers=h)
    b = await api.client.post("/api/v1/worlds", json=body, headers=h)
    assert a.status_code == b.status_code == 201
    assert a.json() == b.json()
    assert b.headers.get("idempotent-replay") == "true"
    names = [w["name"] for w in await api.json("/api/v1/worlds")]
    assert names.count("My Street") == 1


async def test_reused_key_with_a_different_body_conflicts(api: Api) -> None:
    h = {"Idempotency-Key": "k-create-2"}
    assert (await api.client.post("/api/v1/worlds", json={"name": "A1", "cover": COVER}, headers=h)).status_code == 201
    r = await api.client.post("/api/v1/worlds", json={"name": "A2", "cover": COVER}, headers=h)
    assert r.status_code == 409
    envelope(r.json(), "conflict")


async def test_concurrent_duplicate_waits_for_the_first(api: Api) -> None:
    import asyncio

    body = {"name": "Parallel", "cover": COVER}
    h = {"Idempotency-Key": "k-par"}
    a, b = await asyncio.gather(api.client.post("/api/v1/worlds", json=body, headers=h),
                                api.client.post("/api/v1/worlds", json=body, headers=h))
    assert a.status_code == b.status_code == 201
    assert a.json()["id"] == b.json()["id"]


async def test_keys_survive_a_restart(make_api: Any, tmp_path: Path) -> None:
    data = tmp_path / "restart-data"
    first: Api = await make_api(data_dir=data)
    body = {"name": "Survivor", "cover": COVER}
    h = {"Idempotency-Key": "k-restart"}
    a = await first.client.post("/api/v1/worlds", json=body, headers=h)
    await first.rt.stop()
    second: Api = await make_api(data_dir=data)
    b = await second.client.post("/api/v1/worlds", json=body, headers=h)
    assert a.status_code == b.status_code == 201 and a.json() == b.json()
    assert [w["name"] for w in await second.json("/api/v1/worlds")].count("Survivor") == 1


# ── 5.5 assets ──
async def test_seed_asset_served_with_type(api: Api) -> None:
    r = await api.get("/assets/placeholder/portraits/chr_seedHana/neutral.svg")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert r.headers["cache-control"] == "no-cache"


async def test_generated_assets_are_immutable(api: Api) -> None:
    f = api.data_dir / "assets" / "gen" / "wld_x" / "cover_v1.webp"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"RIFF0000WEBP")
    r = await api.get("/assets/gen/wld_x/cover_v1.webp")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/webp"
    assert "immutable" in r.headers["cache-control"]


@pytest.mark.parametrize("path", ["/assets/../data/horizon.db", "/assets/%2e%2e/%2e%2e/backend/pyproject.toml",
                                  "/assets/placeholder/..%2F..%2F..%2Fbackend%2Fpyproject.toml", "/assets/C:/Windows/win.ini"])
async def test_traversal_is_404(api: Api, path: str) -> None:
    r = await api.get(path)
    assert r.status_code == 404


# ── 5.6 test-only routes ──
async def test_test_routes_absent_in_normal_mode(api_normal: Api) -> None:
    r = await api_normal.client.post("/api/v1/_test/clock", json={"advanceMs": 1})
    assert r.status_code == 404


async def test_clock_freeze_and_advance(api: Api) -> None:
    await api.client.post("/api/v1/_test/clock", json={"freezeAt": "2026-10-03T03:00:00.000Z"})
    await api.client.post("/api/v1/_test/clock", json={"advanceMs": 3_600_000})
    r = await api.client.post("/api/v1/worlds", json={"name": "Later", "cover": COVER})
    assert r.json()["createdAt"] == "2026-10-03T04:00:00.000Z"


async def test_unknown_scenario_is_validation(api: Api) -> None:
    r = await api.client.post("/api/v1/_test/scenario", json={"id": "network_down"})  # M4 serves the job faults
    assert r.status_code == 422
    assert r.json()["error"]["details"]["availableIn"] == "M6"


# ── 8.1 world CRUD ──
async def test_create_rename_delete(api: Api) -> None:
    r = await api.client.post("/api/v1/worlds", json={"name": "  My Street  ", "cover": COVER})
    w = r.json()
    assert r.status_code == 201 and w["name"] == "My Street" and w["isSeed"] is False and w["characterCount"] == 0
    assert (await api.json("/api/v1/worlds"))[0]["id"] == w["id"]  # newest first
    r = await api.client.patch(f"/api/v1/worlds/{w['id']}", json={"name": "My Street"})
    assert r.status_code == 200  # renaming to its own name is fine
    r = await api.client.patch(f"/api/v1/worlds/{w['id']}", json={"name": "Elm Street", "you": {"displayName": "Kai"}})
    assert r.json()["name"] == "Elm Street" and r.json()["you"] == {"displayName": "Kai"}
    assert (await api.client.delete(f"/api/v1/worlds/{w['id']}")).status_code == 204
    r = await api.get(f"/api/v1/worlds/{w['id']}")
    assert r.status_code == 404


async def test_name_rules(api: Api) -> None:
    r = await api.client.post("/api/v1/worlds", json={"name": "   ", "cover": COVER})
    assert r.json()["name"] == "New World"
    r = await api.client.post("/api/v1/worlds", json={"name": "x" * 60, "cover": COVER})
    assert r.json()["name"] == "x" * 40


async def test_duplicate_names_conflict(api: Api) -> None:
    assert (await api.client.post("/api/v1/worlds", json={"name": "My Street", "cover": COVER})).status_code == 201
    r = await api.client.post("/api/v1/worlds", json={"name": "my street ", "cover": COVER})
    assert r.status_code == 409
    envelope(r.json(), "conflict")
    assert r.json()["error"]["details"]["field"] == "name"
    other = (await api.client.post("/api/v1/worlds", json={"name": "Other", "cover": COVER})).json()
    r = await api.client.patch(f"/api/v1/worlds/{other['id']}", json={"name": "MY STREET"})
    assert r.status_code == 409


async def test_seed_names_are_reserved(api: Api) -> None:
    r = await api.client.patch("/api/v1/worlds/wld_seedMeridian", json={"name": "Council B"})
    assert r.status_code == 200
    r = await api.client.post("/api/v1/worlds", json={"name": "meridian council", "cover": COVER})
    assert r.status_code == 409 and r.json()["error"]["details"]["field"] == "name"
    r = await api.client.patch("/api/v1/worlds/wld_seedMeridian", json={"name": "Meridian Council"})
    assert r.status_code == 200  # a seed world may take its own shipped name back


async def test_rename_unknown_world(api: Api) -> None:
    r = await api.client.patch("/api/v1/worlds/wld_nope", json={"name": "X"})
    assert r.status_code == 404


async def test_delete_world_cascades_and_keeps_ledger(api: Api) -> None:
    gen = api.data_dir / "assets" / "gen" / "wld_seedSunnyHollow"
    docs = api.data_dir / "knowledge" / "wld_seedSunnyHollow"
    for d in (gen, docs):
        d.mkdir(parents=True)
        (d / "f.bin").write_bytes(b"x")
    ledger_before = [u for u in (await api.json("/api/v1/usage", params={"limit": 1000}))["items"]
                     if u.get("characterId") == "chr_seedHana"]
    assert ledger_before
    assert (await api.client.delete("/api/v1/worlds/wld_seedSunnyHollow")).status_code == 204
    for path in ("/api/v1/worlds/wld_seedSunnyHollow", "/api/v1/characters/chr_seedHana", "/api/v1/sessions/ses_seedDinner",
                 "/api/v1/knowledge/kno_seedHana1"):
        assert (await api.get(path)).status_code == 404, path
    ids_after = {u["id"] for u in (await api.json("/api/v1/usage", params={"limit": 1000}))["items"]}
    assert {u["id"] for u in ledger_before} <= ids_after
    assert not gen.exists() and not docs.exists()

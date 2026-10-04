"""Settings and key routes (group 9; openrouter-key, http-api "Settings are computed on read", "Settings update")."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr
from sqlalchemy import text

from tests.conftest import Api
from tests.gwkit import block_network

KEY = "sk-or-test-0001"


async def put_key(api: Api, key: str | None) -> Any:
    return await api.client.put("/api/v1/settings/key", json={"key": key})


# ── 9.1: status and demo mode come from the key store ──
async def test_key_status_reported_never_the_key(api: Api) -> None:
    assert (await api.json("/api/v1/settings"))["openRouterKeyStatus"] == "missing"
    r = await put_key(api, KEY)
    assert r.status_code == 200
    r = await api.get("/api/v1/settings")
    body = r.json()
    assert body["openRouterKeyStatus"] == "set" and body["demoMode"] is False
    assert "sk-or-" not in r.text


async def test_normal_mode_reads_the_env_key(make_api: Any, tmp_path: Path) -> None:
    a: Api = await make_api(test_mode=False, data_dir=tmp_path / "envkey")
    assert (await a.json("/api/v1/settings"))["openRouterKeyStatus"] == "missing"
    b: Api = await make_api(test_mode=False, data_dir=tmp_path / "envkey2")
    b.rt.keys._env_key = SecretStr(KEY)  # what OPENROUTER_API_KEY in .env gives a normal run
    s = await b.json("/api/v1/settings")
    assert s["openRouterKeyStatus"] == "set" and s["demoMode"] is False


async def test_energy_regenerates_only_with_a_key(api: Api) -> None:
    async with api.rt.db.write() as tx:
        await tx.conn.execute(text("UPDATE characters SET energy_current = 100, energy_as_of = '2026-10-03T02:00:00.000Z' "
                                   "WHERE id = 'chr_seedHana'"))  # an hour before the frozen START
    demo = await api.json("/api/v1/characters/chr_seedHana")
    assert demo["energy"]["current"] == 100  # demo mode: frozen as stored
    await put_key(api, KEY)
    live = await api.json("/api/v1/characters/chr_seedHana")
    assert live["energy"]["current"] == 141  # 100 + 1000/24 for the hour, floored on the wire


# ── 9.2: PUT /settings/key ──
async def test_save_and_clear_without_network(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = block_network(monkeypatch)
    events: list[Any] = []
    unsubscribe = _capture(api, events)
    r = await put_key(api, f"  {KEY}  ")
    assert r.status_code == 200 and r.json()["openRouterKeyStatus"] == "set"
    assert json.loads((api.data_dir / "secrets.local.json").read_text(encoding="utf-8")) == {"openRouterKey": KEY}
    r = await put_key(api, None)
    assert r.json()["openRouterKeyStatus"] == "missing" and r.json()["demoMode"] is True
    assert not (api.data_dir / "secrets.local.json").exists()
    assert attempts == []
    assert [e for e in events if e.get("kind") == "settings"]
    unsubscribe()


def _capture(api: Api, events: list[Any]) -> Any:
    real = api.rt.publish

    def spy(channel: str, event: dict[str, Any]) -> None:
        events.append(event)
        real(channel, event)

    api.rt.publish = spy  # type: ignore[method-assign]

    def undo() -> None:
        api.rt.publish = real  # type: ignore[method-assign]

    return undo


async def test_malformed_key_is_validation(api: Api) -> None:
    await put_key(api, KEY)
    r = await put_key(api, "hello")
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation"
    assert (await api.json("/api/v1/settings"))["openRouterKeyStatus"] == "set"


async def test_env_key_conflict(api: Api) -> None:
    api.rt.keys._env_key = SecretStr(KEY)
    r = await put_key(api, "sk-or-test-other")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict" and r.json()["error"]["details"] == {"field": "key", "source": "env"}
    assert not (api.data_dir / "secrets.local.json").exists()


async def test_body_must_have_key(api: Api) -> None:
    r = await api.client.put("/api/v1/settings/key", json={})
    assert r.status_code == 422


# ── 9.3: PATCH /settings ──
async def patch(api: Api, body: Any) -> Any:
    return await api.client.patch("/api/v1/settings", json=body)


async def test_read_only_threshold_ignored(api: Api) -> None:
    r = await patch(api, {"energy": {"estReplyPoints": {"off_peak": 1, "peak": 1}}})
    assert r.status_code == 200 and r.json()["energy"]["estReplyPoints"] == {"off_peak": 4, "peak": 8}
    local = api.data_dir / "settings.local.json"
    assert "estReplyPoints" not in (local.read_text(encoding="utf-8") if local.exists() else "")


async def test_computed_fields_ignored(api: Api) -> None:
    r = await patch(api, {"openRouterKeyStatus": "set", "demoMode": False, "spentTodayUsd": 9, "pricing": {"period": "peak"},
                          "models": {"chat": "x/evil"}})
    s = r.json()
    assert s["openRouterKeyStatus"] == "missing" and s["demoMode"] is True and s["spentTodayUsd"] == 0
    assert s["models"]["chat"] == "deepseek/deepseek-v4.1-flash"


async def test_lower_the_daily_cap_survives_restart(make_api: Any, tmp_path: Path) -> None:
    data = tmp_path / "cap"
    a: Api = await make_api(data_dir=data)
    before = await a.json("/api/v1/settings")
    r = await patch(a, {"budget": {"dailyCapUsd": 0.6}})
    assert r.status_code == 200
    s = r.json()
    assert s["budget"]["dailyCapUsd"] == 0.6
    assert s["budget"]["perCharacterCreationCapUsd"] == before["budget"]["perCharacterCreationCapUsd"]
    await a.rt.stop()
    b: Api = await make_api(data_dir=data)
    assert (await b.json("/api/v1/settings"))["budget"]["dailyCapUsd"] == 0.6


@pytest.mark.parametrize("body", [
    {"budget": {"dailyCapUsd": -1}}, {"budget": {"warnAtPct": 150}}, {"budget": {"dailyCapUsd": "lots"}},
    {"audio": {"master": "loud"}}, {"modelOverrides": {"chat": ""}}, {"unknownTopLevel": True},
])
async def test_invalid_values_change_nothing(api: Api, body: Any) -> None:
    before = await api.json("/api/v1/settings")
    r = await patch(api, body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation"
    assert await api.json("/api/v1/settings") == before


async def test_model_override_and_event(api: Api) -> None:
    events: list[Any] = []
    undo = _capture(api, events)
    r = await patch(api, {"modelOverrides": {"chat": "deepseek/deepseek-v4-flash"}, "audio": {"music": 0.2}})
    undo()
    assert r.json()["modelOverrides"] == {"chat": "deepseek/deepseek-v4-flash"} and r.json()["audio"]["music"] == 0.2
    assert {"type": "entity.changed", "kind": "settings"} in events


# ── 9.4: POST /settings/test-connection (fake provider in test mode) ──
async def ledger_rows(api: Api) -> list[Any]:
    async with api.rt.db.read() as conn:
        return list((await conn.execute(text("SELECT * FROM usage_records WHERE is_seed = 0"))).mappings())


async def test_connection_good_key(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = block_network(monkeypatch)
    await put_key(api, KEY)
    r = await api.client.post("/api/v1/settings/test-connection")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and isinstance(body["latencyMs"], int) and body["creditsUsd"] == 4.21
    assert set(body) <= {"ok", "latencyMs", "creditsUsd"}
    assert await ledger_rows(api) == [] and attempts == []


async def test_connection_bad_key_flips_status(api: Api) -> None:
    await put_key(api, "sk-or-bad-zzz")
    r = await api.client.post("/api/v1/settings/test-connection")
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_key"
    s = await api.json("/api/v1/settings")
    assert s["openRouterKeyStatus"] == "invalid" and s["demoMode"] is True
    again = await api.client.post("/api/v1/settings/test-connection")
    assert again.json()["error"]["code"] == "invalid_key"  # refused without another call until the key changes
    await put_key(api, KEY)
    assert (await api.json("/api/v1/settings"))["openRouterKeyStatus"] == "set"


async def test_connection_without_key(api: Api) -> None:
    r = await api.client.post("/api/v1/settings/test-connection")
    assert r.status_code == 400 and r.json()["error"]["code"] == "missing_key"


# ── 9.5: POST /settings/test-model ──
@pytest.mark.parametrize(("role", "category", "paid"), [
    ("chat", "chat", True), ("decision", "decision", True), ("embedding", "embedding", True),
    ("image", None, False), ("music", None, False),
])
async def test_model_probe_per_role(api: Api, role: str, category: str | None, paid: bool) -> None:
    await put_key(api, KEY)
    settings = await api.json("/api/v1/settings")
    r = await api.client.post("/api/v1/settings/test-model", json={"role": role})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["model"] == settings["models"][role] and body["latencyMs"] >= 1
    rows = await ledger_rows(api)
    if paid:
        (row,) = rows
        assert row["category"] == category and row["purpose"] == "probe" and row["cost_source"] == "provider"
    else:
        assert rows == []
    assert api.rt.fake is not None
    assert not any(req.url.path.endswith("/images") for req in api.rt.fake.requests)  # never a paid generation


async def test_model_probe_without_key(api: Api) -> None:
    r = await api.client.post("/api/v1/settings/test-model", json={"role": "embedding"})
    assert r.json()["error"]["code"] == "missing_key"


async def test_model_probe_echoes_the_override(api: Api) -> None:
    await put_key(api, KEY)
    await patch(api, {"modelOverrides": {"chat": "deepseek/deepseek-v4-flash"}})
    r = await api.client.post("/api/v1/settings/test-model", json={"role": "chat"})
    assert r.json()["model"] == "deepseek/deepseek-v4-flash"
    assert api.rt.fake is not None
    import json as _json
    assert _json.loads(api.rt.fake.requests[-1].content)["model"] == "deepseek/deepseek-v4-flash"


async def test_model_probe_rejects_unknown_role(api: Api) -> None:
    r = await api.client.post("/api/v1/settings/test-model", json={"role": "video"})
    assert r.status_code == 422

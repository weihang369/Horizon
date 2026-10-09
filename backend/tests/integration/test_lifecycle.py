"""Seed lifecycle (tasks 6.1, 6.2, 6.4–6.6) and the read routes (task 8.2)."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from horizon.contract.validate import default_schema
from horizon.services.seed import SeedError, load_seed
from tests.conftest import SEED_DIR, Api

COVER = {"kind": "preset", "presetId": "cover_night_skyline"}


def _copy_seed(tmp_path: Path) -> Path:
    dst = tmp_path / "seed"
    shutil.copytree(SEED_DIR, dst)
    return dst


def _edit(path: Path, fn: Any) -> None:
    doc = json.loads(path.read_text("utf-8"))
    fn(doc["data"])
    path.write_text(json.dumps(doc), encoding="utf-8")


# ── 6.1 validated, all-or-nothing import ──
def test_invalid_seed_file_is_named(tmp_path: Path) -> None:
    seed = _copy_seed(tmp_path)
    _edit(seed / "characters" / "chr_seedHana.json", lambda c: c.pop("profile"))
    with pytest.raises(SeedError, match=r"chr_seedHana\.json"):
        load_seed(seed, default_schema())


def test_tampered_messages_name_the_session(tmp_path: Path) -> None:
    seed = _copy_seed(tmp_path)
    _edit(seed / "sessions" / "ses_seedDinner" / "messages.json", lambda ms: ms[1].update(content="edited"))
    with pytest.raises(SeedError, match="ses_seedDinner"):
        load_seed(seed, default_schema())


async def test_startup_with_a_bad_seed_writes_nothing(tmp_path: Path) -> None:
    from horizon.config import load_config
    from horizon.runtime import Runtime

    seed = _copy_seed(tmp_path)
    _edit(seed / "characters" / "chr_seedHana.json", lambda c: c.pop("profile"))
    rt = Runtime(load_config(environ={"HORIZON_DATA_DIR": str(tmp_path / "data"), "HORIZON_SEED_DIR": str(seed)}))
    with pytest.raises(SeedError):
        await rt.start()
    async with rt.db.read() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM worlds"))).scalar_one() == 0
    await rt.stop()


async def test_keyword_search_after_import(api_normal: Api) -> None:
    from horizon.services import reads

    async with api_normal.rt.db.read() as conn:
        hits = await reads.fts_search(conn, world_id="wld_seedMeridian", character_id="chr_seedAmara", query="triage")
    assert hits and all(h["sourceId"] == "kno_seedAmara2" for h in hits)


# ── 6.2 mock overlays only in test mode ──
async def test_no_mock_records_in_a_normal_run(api_normal: Api) -> None:
    async with api_normal.rt.db.read() as conn:
        for table in ("characters", "sessions", "generation_jobs"):
            n = (await conn.execute(text(f"SELECT count(*) FROM {table} WHERE id LIKE '%_mock%'"))).scalar_one()
            assert n == 0, table


async def test_test_mode_has_the_archived_mock_character(api: Api) -> None:
    roster = await api.json("/api/v1/worlds/wld_seedSunnyHollow/characters", params={"includeArchived": "true"})
    assert any(c["id"] == "chr_mockMochi" and c["status"] == "archived" for c in roster)
    plain = await api.json("/api/v1/worlds/wld_seedSunnyHollow/characters")
    assert not any(c["status"] == "archived" for c in plain)


# ── 6.4 reset-demo ──
async def test_reset_restores_seed_and_keeps_user_data(api: Api) -> None:
    rt = api.rt
    user_world = (await api.client.post("/api/v1/worlds", json={"name": "My Street", "cover": COVER})).json()
    assert (await api.client.patch("/api/v1/worlds/wld_seedMeridian", json={"name": "Council B"})).status_code == 200
    assert (await api.client.delete("/api/v1/worlds/wld_seedSunnyHollow")).status_code == 204
    now = rt.now_iso()
    async with rt.db.write() as tx:  # a memory Amara earned in a user session, and a user ledger row
        await tx.conn.execute(text(
            "INSERT INTO memory_items(id, character_id, world_id, kind, text, importance, created_at, recall_count, is_seed) "
            "VALUES ('mem_userEarned', 'chr_seedAmara', 'wld_seedMeridian', 'fact', 'Kai likes tea', 0.5, :n, 0, 0)"), {"n": now})
        await tx.conn.execute(text(
            "INSERT INTO usage_records(id, at, local_day, category, cost_usd, cost_source, counts_to_creation_cap, is_seed) "
            "VALUES ('use_user1', :n, '2026-10-03', 'chat', 0.001, 'provider', 0, 0)"), {"n": now})
    sub = rt.bus.subscribe("global")
    r = await api.client.post("/api/v1/admin/reset-demo", json={"confirm": True})
    assert r.status_code == 204
    assert await sub.get() == {"type": "mock.reset"}
    rt.bus.unsubscribe(sub)
    worlds = {w["id"]: w["name"] for w in await api.json("/api/v1/worlds")}
    assert worlds["wld_seedMeridian"] == "Meridian Council"
    assert worlds["wld_seedSunnyHollow"] == "Sunny Hollow"
    assert worlds[user_world["id"]] == "My Street"
    assert (await api.json("/api/v1/sessions/ses_seedDinner"))["session"]["id"] == "ses_seedDinner"
    assert any(m["id"] == "mem_userEarned" for m in await api.json("/api/v1/characters/chr_seedAmara/memory"))
    assert any(u["id"] == "use_user1" for u in (await api.json("/api/v1/usage", params={"limit": 1000}))["items"])
    async with rt.db.read() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM ai_purge_queue WHERE scope='session'"))).scalar_one() == 1


async def test_reset_requires_confirmation(api: Api) -> None:
    r = await api.client.post("/api/v1/admin/reset-demo", json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation"


# ── 6.5 factory reset ──
async def test_factory_reset_wipes_and_continues(api: Api) -> None:
    models = api.data_dir / "models" / "m.bin"
    models.parent.mkdir(parents=True)
    models.write_bytes(b"model")
    w = (await api.client.post("/api/v1/worlds", json={"name": "Doomed", "cover": COVER})).json()
    bad = await api.client.post("/api/v1/admin/factory-reset", json={"confirm": True})
    assert bad.status_code == 422
    assert (await api.get(f"/api/v1/worlds/{w['id']}")).status_code == 200
    r = await api.client.post("/api/v1/admin/factory-reset", json={"confirm": "DELETE EVERYTHING"})
    assert r.status_code == 204
    assert (await api.get(f"/api/v1/worlds/{w['id']}")).status_code == 404
    assert {x["id"] for x in await api.json("/api/v1/worlds")} == {"wld_seedMeridian", "wld_seedSunnyHollow"}
    assert models.read_bytes() == b"model"
    assert (api.data_dir / "logs" / "horizon.log").exists()



async def test_factory_reset_waits_for_a_request_in_flight(api: Api) -> None:
    """The reset's own request is not gated, so every gated one counts: a reset that left one running disposed the
    database under its write, and the connection it held kept `horizon.db` open (the wipe failed on Windows)."""
    entered, release = asyncio.Event(), asyncio.Event()

    async def stall() -> dict[str, bool]:
        async with api.rt.db.write():
            entered.set()
            await release.wait()
        return {"ok": True}

    api.app.add_api_route("/api/v1/test-stall", stall, methods=["POST"])
    slow = asyncio.create_task(api.client.post("/api/v1/test-stall"))
    await entered.wait()
    reset = asyncio.create_task(api.client.post("/api/v1/admin/factory-reset", json={"confirm": "DELETE EVERYTHING"}))
    await asyncio.sleep(0.2)
    assert not reset.done() and api.rt._gateway is not None  # waiting at the gate: nothing has been stopped yet
    release.set()
    assert (await slow).status_code == 200
    assert (await reset).status_code == 204
    assert {x["id"] for x in await api.json("/api/v1/worlds")} == {"wld_seedMeridian", "wld_seedSunnyHollow"}

# ── 6.6 interrupted streams are closed at startup ──
async def test_streaming_message_is_closed_on_restart(make_api: Any, tmp_path: Path) -> None:
    data = tmp_path / "crash-data"
    first: Api = await make_api(data_dir=data)
    rt = first.rt
    sid, mid = "ses_seedHanaLongDay", "msg_crash1"
    async with rt.db.write() as tx:  # a turn that was streaming when the process died
        seq = (await tx.conn.execute(text("SELECT max(seq) FROM session_events WHERE session_id=:s"), {"s": sid})).scalar_one()
        mseq = (await tx.conn.execute(text("SELECT max(seq) FROM messages WHERE session_id=:s"), {"s": sid})).scalar_one()
        await tx.conn.execute(text(
            "INSERT INTO session_events(id, session_id, seq, at, type, message_id, payload) VALUES "
            "('evt_crash1', :s, :q, '2026-10-03T03:00:00.000Z', 'turn.start', :m, :p)"),
            {"s": sid, "q": seq + 1, "m": mid, "p": json.dumps({"messageId": mid, "author": {"type": "character",
                                                                                              "characterId": "chr_seedHana"}})})
        await tx.conn.execute(text(
            "INSERT INTO messages(id, session_id, seq, author_type, author_character_id, kind, content, status, created_at) "
            "VALUES (:m, :s, :q, 'character', 'chr_seedHana', 'chat', 'Half a sen', 'streaming', '2026-10-03T03:00:00.000Z')"),
            {"m": mid, "s": sid, "q": mseq + 1})
    await rt.stop()
    second: Api = await make_api(data_dir=data)
    snap = await second.json(f"/api/v1/sessions/{sid}")
    msg = next(m for m in snap["messages"] if m["id"] == mid)
    assert msg["status"] == "interrupted" and msg["interruptedBy"] == "error" and msg["content"] == "Half a sen"
    events = (await second.json(f"/api/v1/sessions/{sid}/events", params={"limit": 1000}))["items"]
    assert events[-1]["type"] == "turn.end" and events[-1]["payload"]["messageId"] == mid
    assert snap["lastSeq"] == events[-1]["seq"]


# ── 8.2 read routes ──
async def test_settings_are_computed(api: Api) -> None:
    s = await api.json("/api/v1/settings")
    assert s["openRouterKeyStatus"] == "missing" and s["demoMode"] is True
    assert s["pricing"] == {"period": "off_peak", "nextChangeAt": "2026-10-05T01:00:00.000Z"}  # Sat 11:00 → Mon 09:00 MYT
    assert s["energy"]["estReplyPoints"] == {"off_peak": 4, "peak": 8}
    assert s["spentTodayUsd"] == 0


async def test_settings_peak_and_today_spend(api: Api) -> None:
    await api.client.post("/api/v1/_test/clock", json={"freezeAt": "2026-10-06T02:00:00.000Z"})  # Tue 10:00 MYT
    async with api.rt.db.write() as tx:
        await tx.conn.execute(text(
            "INSERT INTO usage_records(id, at, local_day, category, cost_usd, cost_source, counts_to_creation_cap, is_seed) "
            "VALUES ('use_today', '2026-10-06T01:59:00.000Z', '2026-10-06', 'chat', 0.0123, 'provider', 0, 0)"))
    s = await api.json("/api/v1/settings")
    assert s["pricing"] == {"period": "peak", "nextChangeAt": "2026-10-06T04:00:00.000Z"}
    assert s["spentTodayUsd"] == 0.0123
    assert (await api.json("/api/v1/usage/summary"))["todayUsd"] == 0.0123


async def test_test_mode_ignores_a_configured_key(make_api: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-should-not-appear")
    a: Api = await make_api(data_dir=tmp_path / "keyed")
    r = await a.get("/api/v1/settings")
    assert r.json()["openRouterKeyStatus"] == "missing" and "sk-or" not in r.text


async def test_energy_state_follows_the_period(api: Api) -> None:
    async with api.rt.db.write() as tx:
        await tx.conn.execute(text("UPDATE characters SET energy_current = 6 WHERE id = 'chr_seedTakeshi'"))
    await api.client.post("/api/v1/_test/clock", json={"freezeAt": "2026-10-06T02:00:00.000Z"})  # peak
    peak = await api.json("/api/v1/characters/chr_seedTakeshi")
    await api.client.post("/api/v1/_test/clock", json={"freezeAt": "2026-10-03T03:00:00.000Z"})  # off-peak
    off = await api.json("/api/v1/characters/chr_seedTakeshi")
    assert peak["energy"]["state"] == "exhausted" and off["energy"]["state"] == "tired"
    assert peak["energy"]["current"] == off["energy"]["current"] == 6


async def test_tombstones_and_archived(api: Api) -> None:
    async with api.rt.db.write() as tx:
        await tx.conn.execute(text("UPDATE characters SET deleted_at = '2026-10-03T03:00:00.000Z' WHERE id = 'chr_seedRin'"))
    roster = await api.json("/api/v1/worlds/wld_seedSunnyHollow/characters", params={"includeArchived": "true"})
    assert "chr_seedRin" not in {c["id"] for c in roster}
    tomb = await api.json("/api/v1/characters/chr_seedRin")
    assert tomb["deletedAt"] == "2026-10-03T03:00:00.000Z"
    assert (await api.get("/api/v1/characters/chr_seedRin/song")).status_code == 404
    world = await api.json("/api/v1/worlds/wld_seedSunnyHollow")
    assert world["characterCount"] == 2


async def test_snapshot_messages_and_traces(api: Api) -> None:
    sid = "ses_seedAmaraHeadache"
    snap = await api.json(f"/api/v1/sessions/{sid}")
    assert all("trace" not in m for m in snap["messages"])
    events = (await api.json(f"/api/v1/sessions/{sid}/events"))["items"]
    assert snap["lastSeq"] == events[-1]["seq"]
    full = (await api.json(f"/api/v1/sessions/{sid}/messages"))["items"]
    traced = [m for m in full if m.get("trace")]
    assert traced and await api.json(f"/api/v1/messages/{traced[0]['id']}/trace") == traced[0]["trace"]
    assert await api.json("/api/v1/messages/msg_nope/trace") is None


async def test_jobs_reads(api: Api) -> None:
    active = await api.json("/api/v1/jobs", params={"active": "true"})
    assert {j["id"] for j in active} == {"job_mockKenjiEmotions"}
    assert (await api.json("/api/v1/jobs/job_mockAoiEmotions"))["status"] == "partial"
    assert (await api.get("/api/v1/jobs/job_nope")).status_code == 404


async def test_world_scoped_lists_need_their_world(api: Api) -> None:
    for path in ("/api/v1/worlds/wld_nope/characters", "/api/v1/worlds/wld_nope/sessions"):
        assert (await api.get(path)).status_code == 404


async def test_usage_summary_has_every_category(api: Api) -> None:
    s = await api.json("/api/v1/usage/summary")
    assert set(s["byCategory"]) >= {"chat", "embedding", "energy_topup"}
    assert s["byCategory"]["embedding"] == 0 and s["capUsd"] == 1


async def test_health(api: Api) -> None:
    h = await api.json("/api/v1/health")
    assert h == {"ok": True, "version": h["version"], "schemaVersion": 1, "db": "ok", "vec": "ok", "docling": h["docling"]}
    # A test's data dir never holds fetched models: Docling is absent, or installed (`setup:docling`) without them.
    assert h["docling"] in ("not_installed", "models_missing")

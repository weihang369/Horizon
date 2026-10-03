"""The seed round trip (design D5, the main read-model acceptance test): every seed entity read back through the API
equals its seed file after timestamp normalisation and ONLY the documented read-time derivations:

- `KnowledgeSource.status`: a shipped `indexed` source has no vectors yet, so it reads `keyword_only` (OQ-1);
- `Energy.state` / `fullAt` / floors are derived (energy spec) and equal the shipped values for the shipped data;
- `World.characterCount`, `KnowledgeSource.citedCount` are derived and must equal the shipped values.

Any field a mapper drops, renames or invents fails here.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from horizon.domain.timeutil import normalise_iso
from tests.conftest import SEED_DIR, Api

ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$")


def norm(v: Any) -> Any:
    if isinstance(v, str) and ISO.match(v):
        return normalise_iso(v)
    if isinstance(v, list):
        return [norm(x) for x in v]
    if isinstance(v, dict):
        return {k: norm(x) for k, x in v.items()}
    return v


def data(path: Path) -> Any:
    return json.loads(path.read_text("utf-8"))["data"]


def seed_root(overlay: bool) -> Path:
    return SEED_DIR / "_mock" if overlay else SEED_DIR


async def _roundtrip(api: Api, root: Path, *, worlds: bool) -> int:
    checked = 0
    if worlds:
        for p in sorted((root / "worlds").glob("*.json")):
            w = data(p)
            assert await api.json(f"/api/v1/worlds/{w['id']}") == norm(w), p.name
            checked += 1
    for p in sorted((root / "characters").glob("*.json")):
        c = data(p)
        assert await api.json(f"/api/v1/characters/{c['id']}") == norm(c), p.name
        checked += 1
    for p in sorted((root / "songs").glob("*.json")):
        s = data(p)
        assert await api.json(f"/api/v1/characters/{s['characterId']}/song") == norm(s), p.name
        checked += 1
    for d in sorted(x for x in (root / "sessions").glob("*") if x.is_dir()):
        session, events, messages = data(d / "session.json"), data(d / "events.json"), data(d / "messages.json")
        snap = await api.json(f"/api/v1/sessions/{session['id']}")
        assert snap["session"] == norm(session), d.name
        assert snap["lastSeq"] == (events[-1]["seq"] if events else 0)
        assert snap["messages"] == norm([{k: v for k, v in m.items() if k != "trace"} for m in messages]), d.name
        page = await api.json(f"/api/v1/sessions/{session['id']}/messages", params={"limit": 1000})
        assert page["items"] == norm(messages) and page["nextCursor"] is None, d.name
        ev = await api.json(f"/api/v1/sessions/{session['id']}/events", params={"limit": 1000})
        assert ev["items"] == norm(events), d.name
        for m in messages:
            assert await api.json(f"/api/v1/messages/{m['id']}/trace") == norm(m.get("trace")), m["id"]
        checked += 1
    for p in sorted((root / "memory").glob("*.json")):
        items = data(p)
        if items:
            got = await api.json(f"/api/v1/characters/{items[0]['characterId']}/memory")
            assert sorted(got, key=lambda x: x["id"]) == sorted(norm(items), key=lambda x: x["id"]), p.name
            checked += len(items)
    for p in sorted((root / "knowledge").glob("*.json")):
        items = data(p)
        if not items:
            continue
        got = await api.json(f"/api/v1/characters/{items[0]['characterId']}/knowledge")
        expected = [{**k, "status": "keyword_only" if k["status"] == "indexed" else k["status"]} for k in items]
        assert sorted(got, key=lambda x: x["id"]) == sorted(norm(expected), key=lambda x: x["id"]), p.name
        for k in items:
            body = await api.json(f"/api/v1/knowledge/{k['id']}")
            chunk_file = root / "knowledge" / "chunks" / f"{k['id']}.json"
            chunks = data(chunk_file) if chunk_file.is_file() else []
            assert body["chunks"] == sorted(norm(chunks), key=lambda c: c["index"]), k["id"]
        checked += len(items)
    ledger = root / "usage" / "ledger.json"
    if ledger.is_file():
        rows = data(ledger)
        got = (await api.json("/api/v1/usage", params={"limit": 1000}))["items"]
        by_id = {r["id"]: r for r in got}
        for r in rows:
            assert by_id[r["id"]] == norm(r), r["id"]
        checked += len(rows)
    for p in sorted((root / "jobs").glob("*.json")):
        j = data(p)
        assert await api.json(f"/api/v1/jobs/{j['id']}") == norm(j), p.name
        checked += 1
    return checked


async def test_seed_roundtrips_exactly(api_normal: Api) -> None:
    assert await _roundtrip(api_normal, seed_root(False), worlds=True) > 100


async def test_mock_overlays_roundtrip_in_test_mode(api: Api) -> None:
    assert await _roundtrip(api, seed_root(True), worlds=False) > 20


@pytest.mark.parametrize("field", ["profile", "emotionSet"])
async def test_a_dropped_mapper_field_fails(api_normal: Api, monkeypatch: pytest.MonkeyPatch, field: str) -> None:
    from horizon.contract import mappers

    original = mappers.character_wire

    def lossy(*a: Any, **kw: Any) -> dict[str, Any]:
        out = original(*a, **kw)
        out.pop(field, None)
        return out

    monkeypatch.setattr(mappers, "character_wire", lossy)
    with pytest.raises(AssertionError):
        await _roundtrip(api_normal, seed_root(False), worlds=False)

"""Helpers for session integration tests (in-process app, virtual clock, scripted profile, fake key)."""

from __future__ import annotations

from typing import Any

from horizon.services.runtime.reducer import initial_runtime, ordered_messages, reduce_all
from horizon.sessions.fork import replay_base
from tests.conftest import Api

API = "/api/v1"


async def create(api: Api, mode: str, cast: list[str], world: str = "wld_seedMeridian", status: int = 201,
                 **extra: Any) -> dict[str, Any]:
    r = await api.post(f"{API}/sessions", {"worldId": world, "mode": mode, "characterIds": cast, **extra})
    assert r.status_code == status, r.text
    out: dict[str, Any] = r.json()
    return out


async def command(api: Api, sid: str, name: str, body: Any = None, status: int = 202) -> Any:
    r = await api.post(f"{API}/sessions/{sid}/{name}", body or {})
    assert r.status_code == status, f"{name}: {r.status_code} {r.text}"
    return r.json() if r.content else None


async def messages(api: Api, sid: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = (await api.json(f"{API}/sessions/{sid}/messages?limit=1000"))["items"]
    return items


async def events(api: Api, sid: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = (await api.json(f"{API}/sessions/{sid}/events?limit=1000"))["items"]
    return items


async def snapshot(api: Api, sid: str) -> dict[str, Any]:
    out: dict[str, Any] = await api.json(f"{API}/sessions/{sid}")
    return out


def chars(msgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [m for m in msgs if m["author"]["type"] == "character"]


async def assert_reduces(api: Api, sid: str) -> None:
    """session-event-sourcing: reducing the served events gives the served messages (with traces) and session."""
    snap = await snapshot(api, sid)
    evs = await events(api, sid)
    assert [e["seq"] for e in evs] == list(range(1, len(evs) + 1))
    final = reduce_all(initial_runtime(start_of(snap["session"])), evs)
    assert ordered_messages(final) == await messages(api, sid)
    if not snap["session"].get("continuedFrom"):
        assert final["session"] == snap["session"]


def start_of(session: dict[str, Any]) -> dict[str, Any]:
    """The session a live session's events start from: created active, no state, no messages, no cost."""
    base = replay_base(session)
    base["state"] = None
    return base


async def ledger(api: Api) -> list[dict[str, Any]]:
    import sqlalchemy as sa

    from horizon.db import tables as t

    async with api.rt.db.read() as conn:
        rows = (await conn.execute(sa.select(t.usage_records).where(t.usage_records.c.is_seed.is_(False))
                                   .order_by(t.usage_records.c.at, t.usage_records.c.id))).mappings().all()
    return [dict(r) for r in rows]

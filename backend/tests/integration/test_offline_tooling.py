"""Offline test tooling and the opt-in `agent` profile (ai-foundation tasks 2.5–2.8; provider-gateway "Test mode labels
requests with their purpose", "Canned responses per purpose in test mode", "Decisions can be held in test mode";
http-api "Test-only control routes"; ai-ports "AI profile selection"; design D12, D39)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from sqlalchemy import text

from horizon.ai.profile import AGENT_PORTS, PORTS, ProfileSpec
from horizon.gateway.client import CALL_PURPOSE, PURPOSE_HEADER, HttpCore
from horizon.gateway.fake import load_canned
from tests.conftest import Api
from tests.gwkit import FakeKeys
from tests.jobs.kit import API
from tests.jobs.test_naive import draft, naive, settle_job


# ── 2.5: the purpose header exists only in test mode ──
@pytest.mark.parametrize(("label", "expect"), [(True, "profile"), (False, None)])
async def test_purpose_header_only_in_test_mode(label: bool, expect: str | None) -> None:
    seen: list[httpx.Request] = []

    def handler(r: httpx.Request) -> httpx.Response:
        seen.append(r)
        return httpx.Response(200, json={"data": {}})

    core = HttpCore(FakeKeys(), transport=httpx.MockTransport(handler), label_purpose=label)
    token = CALL_PURPOSE.set("profile")
    try:
        await core.request("GET", "/v1/key", http_timeout=5)
    finally:
        CALL_PURPOSE.reset(token)
        await core.aclose()
    assert seen[0].headers.get(PURPOSE_HEADER) == expect


# ── 2.6: canned responses ──
def test_profile_drafts_set_is_group_a() -> None:
    purpose, responses = load_canned("profile-drafts")
    assert purpose == "profile" and len(responses) == 20
    assert sum(1 for r in responses if r["valid"]) == 19   # A3: one nickname in unescaped quotes
    with pytest.raises(KeyError):
        load_canned("../secrets")


async def test_canned_draft_validates(api: Api) -> None:
    await naive(api, drafter="naive")
    assert (await api.post(f"{API}/_test/canned", {"purpose": "profile", "set": "profile-drafts"})).status_code == 204
    out = await draft(api)
    done = await settle_job(api, out["job"]["id"])
    assert done["status"] == "succeeded", done
    ch = (await api.json(f"{API}/characters/{out['character']['id']}"))
    first = json.loads(load_canned("profile-drafts")[1][0]["content"])
    assert ch["profile"]["name"] == first["profile"]["name"]
    fake = api.rt.fake
    assert fake is not None
    req = next(r for r in reversed(fake.requests) if r.url.path.endswith("/chat/completions"))
    assert req.headers.get(PURPOSE_HEADER) == "profile"


async def test_unknown_canned_set_is_validation(api: Api) -> None:
    r = await api.post(f"{API}/_test/canned", {"purpose": "profile", "set": "nope"})
    assert r.status_code == 422 or r.json()["error"]["code"] == "validation"


# ── 2.7: a parked decision gives the fallback at its deadline, and its row lands late ──
async def test_parked_route_falls_back_and_is_recorded_late(api: Api) -> None:
    await api.set_key()
    r = await api.post(f"{API}/_test/ai-profile", {"profile": "scripted", "overrides": {"router": "naive"}})
    assert r.status_code == 204
    s = await api.post(f"{API}/sessions", {"worldId": "wld_seedSunnyHollow", "mode": "group",
                                            "characterIds": ["chr_seedHana", "chr_seedTakeshi"]})
    sid = s.json()["session"]["id"]
    await api.drive(6000)
    assert (await api.post(f"{API}/_test/park", {"endpoint": "decisions", "n": 1})).status_code == 204
    assert (await api.post(f"{API}/sessions/{sid}/send", {"text": "Who's cooking?"})).status_code == 202
    await api.drive(30000)   # the 400 ms route deadline passes in virtual time; the replies run on the fallback
    msgs = (await api.json(f"{API}/sessions/{sid}/messages?limit=1000"))["items"]
    replies = [m for m in msgs if m["author"]["type"] == "character" and m.get("trace")]
    assert replies and any(c.get("fallback") for c in replies[-1]["trace"]["calls"] if c["purpose"] == "route")
    async with api.rt.db.read() as conn:
        assert (await conn.execute(text("SELECT COUNT(*) FROM usage_records WHERE purpose = 'route'"))).scalar_one() == 0
    assert (await api.post(f"{API}/_test/park", {"endpoint": "decisions", "n": 1, "release": True})).status_code == 204
    await api.drive(1000)
    await api.rt.decider.idle()
    async with api.rt.db.read() as conn:
        rows = (await conn.execute(text("SELECT finish_reason FROM usage_records WHERE purpose = 'route'"))).all()
    assert [r[0] for r in rows] == ["late"]


# ── 2.8: the agent profile resolves to naive, port by port, except its own ports (M8: the turn engine) ──
def test_agent_resolves_like_naive() -> None:
    agent = ProfileSpec(profile="agent")
    naive_ = ProfileSpec(profile="naive")
    for p in PORTS:
        want = "agent" if p in AGENT_PORTS else naive_.choose(p, key_set=True)
        assert agent.choose(p, key_set=True) == want, p
        assert agent.choose(p, key_set=False) == "scripted" or p == "converter", p
    # M9 (turn-plan-emotion D5, D18, D23) adds the planner, reactions and the face check; M11 (debate) the host
    assert AGENT_PORTS == frozenset({"turn", "planner", "reactions", "face_check", "host"})


def test_agent_from_env() -> None:
    spec = ProfileSpec.from_env({"HORIZON_AI_PROFILE": "agent", "HORIZON_AI_TURN": "scripted"})
    assert spec.profile == "agent" and spec.choose("turn", key_set=True) == "scripted"
    assert spec.choose("router", key_set=True) == "naive"


async def test_agent_profile_over_http(api: Api) -> None:
    await api.set_key()
    assert (await api.post(f"{API}/_test/ai-profile", {"profile": "agent"})).status_code == 204
    resolved: dict[str, Any] = api.rt.ai.resolved(key_set=True)
    assert resolved["router"] == "naive" and resolved["memory_writer"] == "scripted"


async def test_test_routes_404_outside_test_mode(api_normal: Api) -> None:
    for path, body in (("canned", {"purpose": "profile", "set": "profile-drafts"}), ("park", {"endpoint": "decisions", "n": 1})):
        assert (await api_normal.post(f"{API}/_test/{path}", body)).status_code == 404

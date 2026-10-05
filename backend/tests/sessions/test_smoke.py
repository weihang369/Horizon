"""Smoke: a 1:1 session greets on the virtual clock."""

from __future__ import annotations

from tests.conftest import Api

API = "/api/v1"


async def test_one_on_one_greets(api: Api) -> None:
    await api.set_key()
    r = await api.post(f"{API}/sessions", {"worldId": "wld_seedMeridian", "mode": "one_on_one",
                                          "characterIds": ["chr_seedAmara"]}, status=201)
    sid = r.json()["session"]["id"]
    await api.drive(6000)
    msgs = (await api.json(f"{API}/sessions/{sid}/messages"))["items"]
    chars = [m for m in msgs if m["author"]["type"] == "character"]
    assert len(chars) == 1 and chars[0]["status"] == "complete", msgs

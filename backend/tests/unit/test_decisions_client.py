"""Decisions client (task 5.2): request shape, the three answer types, usage, and the error cases."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import pytest
import respx

from horizon.gateway.client import BASE_URL, HttpCore
from horizon.gateway.decisions import DecisionsClient
from horizon.gateway.errors import ProviderError
from tests.gwkit import FakeKeys, response

URL = f"{BASE_URL}/alpha/decisions"
QUESTIONS = {
    "route": {"type": "choice", "instructions": "Who speaks next?", "criteria": {"chr_seedAmara": "A", "none": "nobody"}},
    "gate": {"type": "noul", "instructions": "Does this need knowledge?", "criteria": {"true": "yes", "false": "no"}},
    "tone": {"type": "score", "instructions": "How warm?", "criteria": ["cold", "neutral", "warm", "glowing"]},
}


@pytest.fixture
async def dec() -> AsyncIterator[DecisionsClient]:
    core = HttpCore(FakeKeys())
    yield DecisionsClient(core, "typesafe/jev-1.13")
    await core.aclose()


@respx.mock
async def test_request_and_answers(dec: DecisionsClient) -> None:
    route = respx.post(URL).mock(return_value=response("decisions_ok"))
    r = await dec.decide({"last": "hello"}, QUESTIONS)
    sent = json.loads(route.calls.last.request.content)
    assert sent["model"] == "typesafe/jev-1.13" and set(sent["questions"]) == {"route", "gate", "tone"}
    assert r.answers["route"]["choice"] == "chr_seedAmara" and r.answers["route"]["probabilities"]["none"] == 0.03
    assert r.answers["gate"] == {"type": "noul", "noul": 0.71}
    assert r.answers["tone"]["score"] == 2.4 and r.answers["tone"]["legend"]["0"] == "cold" and r.answers["tone"]["type"] == "score"
    assert r.usage is not None and r.usage.tokens_in == 840 and r.usage.tokens_out == 0 and r.usage.cost_usd == 0.00003528
    assert r.generation_id == "dec-rec-000001"


def test_model_must_be_pinned() -> None:
    with pytest.raises(ValueError):
        DecisionsClient(HttpCore(FakeKeys()), "~typesafe/jev-latest")


@respx.mock
async def test_malformed(dec: DecisionsClient) -> None:
    respx.post(URL).mock(return_value=httpx.Response(200, json={"id": "dec-x", "usage": {}}))
    with pytest.raises(ProviderError) as e:
        await dec.decide({}, QUESTIONS)
    assert e.value.code == "provider_error" and e.value.generation_id == "dec-x" and e.value.maybe_charged


@pytest.mark.parametrize(("fixture", "code"), [
    ("error_401", "invalid_key"), ("error_429", "rate_limited"), ("error_500", "provider_error"), ("error_502", "provider_error"),
])
@respx.mock
async def test_errors(dec: DecisionsClient, fixture: str, code: str) -> None:
    respx.post(URL).mock(return_value=response(fixture))
    with pytest.raises(ProviderError) as e:
        await dec.decide({}, QUESTIONS)
    assert e.value.code == code

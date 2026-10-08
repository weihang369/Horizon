"""AI profile rules for the M5 ports (knowledge-memory-storage task 2.3; ai-ports "AI profile selection")."""

from __future__ import annotations

import pytest

from horizon.ai.profile import KEYLESS_PORTS, NAIVE_PORTS, PORTS, ProfileSpec, env_name


def test_new_ports_are_listed_with_env_overrides() -> None:
    for port in ("embedder", "knowledge_retriever", "memory_retriever", "memory_writer", "converter"):
        assert port in PORTS
    assert env_name("knowledge_retriever") == "HORIZON_AI_KNOWLEDGE_RETRIEVER"
    assert env_name("converter") == "HORIZON_AI_CONVERTER"
    assert "memory_writer" not in NAIVE_PORTS  # writes nothing in both profiles until the AI stage


@pytest.mark.parametrize(("env", "key_set", "expect"), [
    ({}, True, "naive"),
    ({}, False, "scripted"),
    ({"HORIZON_AI_PROFILE": "scripted"}, True, "scripted"),
    ({"HORIZON_AI_PROFILE": "naive", "HORIZON_AI_EMBEDDER": "scripted"}, True, "scripted"),
])
def test_embedder_follows_the_profile(env: dict[str, str], key_set: bool, expect: str) -> None:
    assert ProfileSpec.from_env(env).choose("embedder", key_set=key_set) == expect


def test_memory_writer_is_scripted_in_both_profiles() -> None:
    for env in ({}, {"HORIZON_AI_PROFILE": "naive"}, {"HORIZON_AI_MEMORY_WRITER": "naive"}):
        assert ProfileSpec.from_env(env).choose("memory_writer", key_set=True) == "scripted"


@pytest.mark.parametrize(("env", "test_mode", "key_set", "expect"), [
    ({}, False, False, "naive"),                                  # real conversion without a key (D-96)
    ({"HORIZON_AI_PROFILE": "scripted"}, False, True, "naive"),   # not the profile either
    ({}, True, True, "scripted"),                                 # deterministic in test mode
    ({"HORIZON_AI_CONVERTER": "naive"}, True, False, "naive"),    # an override still wins
    ({"HORIZON_AI_CONVERTER": "scripted"}, False, True, "scripted"),
])
def test_converter_ignores_profile_and_key(env: dict[str, str], test_mode: bool, key_set: bool, expect: str) -> None:
    assert "converter" in KEYLESS_PORTS
    assert ProfileSpec.from_env(env, test_mode=test_mode).choose("converter", key_set=key_set) == expect


async def test_ai_profile_route_takes_the_new_ports(api: object) -> None:
    from tests.conftest import Api

    assert isinstance(api, Api)
    r = await api.client.post("/api/v1/_test/ai-profile",
                              json={"profile": "naive", "overrides": {"embedder": "scripted", "converter": "naive"}})
    assert r.status_code == 204, r.text
    assert api.rt.ai.impl("embedder", key_set=True) == "scripted"
    assert api.rt.ai.impl("converter", key_set=False) == "naive"
    assert api.rt.ai.impl("knowledge_retriever", key_set=True) == "naive"
    r = await api.client.post("/api/v1/_test/ai-profile", json={"profile": "naive"})
    assert api.rt.ai.impl("converter", key_set=True) == "scripted"  # test mode keeps conversion deterministic

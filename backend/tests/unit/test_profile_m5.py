"""AI profile rules for the M5 ports (knowledge-memory-storage task 2.3; ai-ports "AI profile selection")."""

from __future__ import annotations

from pathlib import Path

import pytest

from horizon.ai.profile import ENV_VARS, KEYLESS_PORTS, NAIVE_PORTS, PORTS, ProfileSpec, env_name
from horizon.config import AI_VARS, load_config


def test_new_ports_are_listed_with_env_overrides() -> None:
    for port in ("embedder", "knowledge_retriever", "memory_retriever", "memory_writer", "converter"):
        assert port in PORTS
    assert env_name("knowledge_retriever") == "HORIZON_AI_KNOWLEDGE_RETRIEVER"
    assert env_name("converter") == "HORIZON_AI_CONVERTER"
    assert "memory_writer" in NAIVE_PORTS  # M13 (memory D18): naive makes the one rewrite call


def test_config_passes_every_port_override_through(tmp_path: Path) -> None:
    # The config reads only the variables it knows: a port missing there would make its override silently do nothing.
    assert set(AI_VARS) == set(ENV_VARS)
    cfg = load_config({"HORIZON_ROOT": str(tmp_path), "HORIZON_AI_CONVERTER": "naive", "HORIZON_AI_EMBEDDER": "scripted"})
    spec = ProfileSpec.from_env(cfg.ai_env)
    assert spec.choose("converter", key_set=False) == "naive"
    assert spec.choose("embedder", key_set=True) == "scripted"


@pytest.mark.parametrize(("env", "key_set", "expect"), [
    ({}, True, "naive"),
    ({}, False, "scripted"),
    ({"HORIZON_AI_PROFILE": "scripted"}, True, "scripted"),
    ({"HORIZON_AI_PROFILE": "naive", "HORIZON_AI_EMBEDDER": "scripted"}, True, "scripted"),
])
def test_embedder_follows_the_profile(env: dict[str, str], key_set: bool, expect: str) -> None:
    assert ProfileSpec.from_env(env).choose("embedder", key_set=key_set) == expect


def test_memory_writer_follows_the_profile() -> None:
    # M13 (memory D18): naive and agent writers; a key is needed, except an explicit naive override. M15 (D3): the
    # default with a key is `agent`, in test mode and out of it alike
    for env in ({"HORIZON_AI_PROFILE": "naive"}, {"HORIZON_AI_MEMORY_WRITER": "naive"}):
        assert ProfileSpec.from_env(env).choose("memory_writer", key_set=True) == "naive"
    for env in ({}, {"HORIZON_AI_PROFILE": "agent"}):
        for test_mode in (False, True):
            assert ProfileSpec.from_env(env, test_mode=test_mode).choose("memory_writer", key_set=True) == "agent"
    assert ProfileSpec.from_env({}).choose("memory_writer", key_set=False) == "scripted"


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


# ── images-music 7.1 (design D3): `agent` with a key, `scripted` without ──
def test_the_default_is_agent_with_a_key_and_scripted_without() -> None:
    from horizon.ai.profile import AiPorts

    def ports(env: dict[str, str]) -> AiPorts:
        return AiPorts(deps=object(), spec=ProfileSpec.from_env(env))  # type: ignore[arg-type]

    default = ports({})
    # no key: every port scripted (the converter is chosen by availability, D-96), and may record simulated spend
    assert {i for p, i in default.resolved(key_set=False).items() if p not in KEYLESS_PORTS} == {"scripted"}
    assert default.simulates(key_set=False)
    # a key: exactly what HORIZON_AI_PROFILE=agent resolves to
    assert default.resolved(key_set=True) == ports({"HORIZON_AI_PROFILE": "agent"}).resolved(key_set=True)
    assert default.resolved(key_set=True)["turn"] == "agent"
    # the baseline is one variable away
    assert ports({"HORIZON_AI_PROFILE": "naive"}).resolved(key_set=True)["turn"] == "naive"
    # a per-port override still wins over the default
    assert ports({"HORIZON_AI_TURN": "naive"}).resolved(key_set=True)["turn"] == "naive"
    assert ports({"HORIZON_AI_TURN": "naive"}).resolved(key_set=True)["planner"] == "agent"

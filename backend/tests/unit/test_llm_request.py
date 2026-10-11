"""`llm_request` and the `runtime.llm.calls` table (llm-parameters "One settings row per call type", "Thinking off
behind a switch"; design D13; tasks 3.1, 3.2)."""

from __future__ import annotations

import pytest

from horizon.ai.llm import llm_request
from horizon.domain.runtime_config import LlmCall, load_runtime_config
from horizon.gateway.chat import ChatClient
from tests.conftest import SEED_DIR
from tests.gwkit import gateway_config

MSGS = [{"role": "user", "content": "hi"}]


def test_the_shipped_table() -> None:
    rt = load_runtime_config(SEED_DIR).runtime
    expect = {"reply.chat": 1.3, "reply.debate": 1.0, "host": 1.0, "verdict": 0.7, "summary": 0.7, "episode": 0.7,
              "memory": 0.7, "query_rewrite": 0.0, "profile": 1.0, "probe": None}
    assert {k: v.temperature for k, v in rt.llm_calls.items()} == expect
    assert all(v.thinking == "off" for v in rt.llm_calls.values())
    caps = rt.reply_max_tokens
    assert (caps.one_on_one, caps.one_on_one_deep, caps.group, caps.watch) == (200, 300, 150, 150)
    assert caps.debate == {"short": 200, "medium": 320, "long": 480}
    assert caps.for_mode("one_on_one", deep=True) == 300 and caps.for_mode("group", deep=True) == 150


def test_reply_body_has_no_unsupported_parameters() -> None:
    row = load_runtime_config(SEED_DIR).runtime.llm("reply.chat")
    req = llm_request(row, "deepseek/deepseek-v4.1-flash", MSGS, max_tokens=200, stop=["\nMei:", "\nMei:", "\nKai:"])
    body = ChatClient(None, gateway_config()).body(req, stream=True)  # type: ignore[arg-type]
    assert body["temperature"] == 1.3 and body["reasoning"] == {"enabled": False}
    assert body["stop"] == ["\nMei:", "\nKai:"] and body["max_tokens"] == 200
    for absent in ("top_p", "presence_penalty", "frequency_penalty", "seed", "logprobs", "models"):
        assert absent not in body


def test_probe_sends_no_temperature_and_its_own_cap() -> None:
    req = llm_request(LlmCall("off", None, "text", 1), "m", MSGS)
    assert req.temperature is None and req.max_tokens == 1 and req.reasoning == {"enabled": False}


def test_thinking_switch_maps_to_effort() -> None:
    assert LlmCall("high", 1.0, "stream").reasoning == {"effort": "high"}


def test_guards() -> None:
    with pytest.raises(ValueError):
        llm_request(LlmCall("off", 1.0, "stream"), "m", MSGS)                      # no cap
    with pytest.raises(ValueError):
        llm_request(LlmCall("off", 1.0, "stream", 10), "m", MSGS, stop=[f"\n{i}:" for i in range(17)])
    with pytest.raises(ValueError):
        llm_request(LlmCall("off", 1.0, "text", 10), "m", MSGS, response_format={"type": "json_object"})

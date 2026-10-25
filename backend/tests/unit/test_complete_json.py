"""`complete_json`'s retry rule (docs/ai/03 C7; llm-parameters "JSON answers get a free repair, then one paid retry";
design D19; task 3.8): only a parse or validation failure is retried, and only once."""

from __future__ import annotations

import json
from typing import Any

import pytest

from horizon.ai.naive.creation import InvalidJson, complete_json
from horizon.ai.ports import PaidHooks
from horizon.gateway.chat import ChatRequest, ChatResult
from horizon.gateway.context import call_ctx
from horizon.gateway.errors import ProviderError

REQ = ChatRequest(model="m", max_tokens=10, messages=[{"role": "user", "content": "go"}])


class Stub:
    def __init__(self, *answers: str | ProviderError) -> None:
        self.answers = list(answers)
        self.sent: list[ChatRequest] = []

    async def chat_complete(self, req: ChatRequest, ctx: Any, *, before_send: Any = None, after_response: Any = None,
                            commit_with: Any = None) -> ChatResult:
        self.sent.append(req)
        a = self.answers.pop(0)
        if isinstance(a, ProviderError):
            raise a
        r = ChatResult(generation_id="gen-1", content=a, finish_reason="stop", usage=None, provider=None, model=None,
                       provider_warning=None, latency_ms=1)
        if after_response is not None:
            await after_response(r)
        return r


def parse(content: str) -> dict[str, Any]:
    try:
        out = json.loads(content)
    except ValueError as e:
        raise ProviderError("provider_error", "not JSON") from e
    if not isinstance(out, dict) or "name" not in out:
        raise ProviderError("provider_error", "no name")
    return out


async def test_valid_answer_is_one_call() -> None:
    gw = Stub('{"name": "Ana"}')
    assert await complete_json(gw, REQ, call_ctx("profile"), parse, PaidHooks()) == {"name": "Ana"}
    assert len(gw.sent) == 1


async def test_quote_slip_is_repaired_locally() -> None:
    gw = Stub('{"name": "Loretta "Rhett" Kowalski"}')
    assert (await complete_json(gw, REQ, call_ctx("profile"), parse, PaidHooks()))["name"] == 'Loretta "Rhett" Kowalski'
    assert len(gw.sent) == 1


async def test_one_retry_then_failure() -> None:
    gw = Stub("nope", "still nope")
    with pytest.raises(InvalidJson):
        await complete_json(gw, REQ, call_ctx("profile"), parse, PaidHooks())
    assert len(gw.sent) == 2 and gw.sent[1].messages[-2] == {"role": "assistant", "content": "nope"}


@pytest.mark.parametrize("code", ["timeout", "content_refused", "rate_limited"])
async def test_other_failures_are_never_retried(code: str) -> None:
    gw = Stub(ProviderError(code), '{"name": "Ana"}')
    with pytest.raises(ProviderError) as e:
        await complete_json(gw, REQ, call_ctx("profile"), parse, PaidHooks())
    assert e.value.code == code and len(gw.sent) == 1


async def test_a_call_with_no_answer_read_is_a_provider_error_not_retried() -> None:
    """M15 8.2: a probe's miss returns an empty reply without `after_response`; the caller's failure path runs."""

    class Probe(Stub):
        async def chat_complete(self, req: ChatRequest, ctx: Any, **_: Any) -> ChatResult:
            self.sent.append(req)
            return ChatResult(generation_id="probe", content="", finish_reason="stop", usage=None, provider="probe",
                              model=None, provider_warning=None, latency_ms=0)

    gw = Probe()
    with pytest.raises(ProviderError) as e:
        await complete_json(gw, REQ, call_ctx("profile"), parse, PaidHooks())
    assert not isinstance(e.value, InvalidJson) and len(gw.sent) == 1

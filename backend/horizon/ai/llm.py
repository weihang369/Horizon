"""The one builder of DeepSeek requests (docs/ai/03 C1–C2; llm-parameters "One settings row per call type";
ai-foundation design D13).

Every engine, the drafter and the probe build their `ChatRequest` here from a `runtime.llm.calls` row, so thinking,
temperature and the safety-net cap come from committed config, never from code. Not sent, ever: `top_p` (fixed while
thinking is off), `presence_penalty` / `frequency_penalty` (no longer supported by DeepSeek), `seed`, `logprobs`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from horizon.domain.runtime_config import LlmCall
from horizon.gateway.chat import ChatRequest

MAX_STOPS = 16   # DeepSeek's limit (docs/ai/03 F3c); a cast of 5 needs at most about 8


def llm_request(row: LlmCall, model: str, messages: list[dict[str, Any]], *, max_tokens: int | None = None,
                stop: Sequence[str] | None = None, response_format: dict[str, Any] | None = None) -> ChatRequest:
    cap = max_tokens if max_tokens is not None else row.max_tokens
    if cap is None:
        raise ValueError("this call type has no fixed cap: pass max_tokens")
    stops = list(dict.fromkeys(stop)) if stop else None
    if stops is not None and len(stops) > MAX_STOPS:
        raise ValueError(f"{len(stops)} stop strings; DeepSeek accepts at most {MAX_STOPS}")
    if response_format is not None and row.output != "json":
        raise ValueError("JSON mode on a call type whose output isn't json")
    return ChatRequest(model=model, messages=messages, max_tokens=cap, temperature=row.temperature,
                       reasoning=row.reasoning, stop=stops or None, response_format=response_format)

"""The decisions client (doc backend/04 §1, D-66): `POST /api/alpha/decisions`, Jev, pinned `typesafe/jev-1.13`.

Only the `Decider` (`ai/decider.py`) calls it. Request: `{model, state, questions: {key: {type, instructions,
criteria}}}`. Answers per the Jev reference: choice `{choice, confidence, probabilities}`, noul `{noul}`, score
`{score, confidence, probabilities, legend}`; `usage{input_tokens, output_tokens, cost}`. The API is alpha and the
response wrapper is unverified until the live run (design OQ-C), so the parser accepts `answers` or `results`.

Per-purpose hot-path timeouts are the Decider's (it keeps waiting in the background to record a late answer); the HTTP
timeout here is only the outer bound.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from horizon.gateway.client import HttpCore
from horizon.gateway.errors import malformed
from horizon.gateway.types import Usage, parse_usage

PATH = "/alpha/decisions"
OUTER_TIMEOUT_S = 30.0


@dataclass(frozen=True)
class DecisionsResponse:
    generation_id: str | None
    answers: Mapping[str, Mapping[str, Any]]
    usage: Usage | None
    model: str | None


class DecisionsClient:
    def __init__(self, core: HttpCore, model: str) -> None:
        if "latest" in model:
            raise ValueError("the decision model must be pinned, never an alias")
        self.core = core
        self.model = model

    async def decide(self, state: Any, questions: Mapping[str, Mapping[str, Any]], *, model: str | None = None,
                     http_timeout: float = OUTER_TIMEOUT_S) -> DecisionsResponse:
        """`model` overrides the pinned one (Settings → model overrides; testModel)."""
        m = model or self.model
        if "latest" in m:
            raise ValueError("the decision model must be pinned, never an alias")
        resp = await self.core.request("POST", PATH, json={"model": m, "state": state, "questions": dict(questions)},
                                       http_timeout=http_timeout)
        try:
            obj = resp.json()
        except ValueError as e:
            raise malformed("decision response") from e
        if not isinstance(obj, Mapping):
            raise malformed("decision response")
        gid = obj.get("id") if isinstance(obj.get("id"), str) else None
        answers = obj.get("answers", obj.get("results"))
        if not isinstance(answers, Mapping):
            raise malformed("decision response", generation_id=gid)
        clean = {str(k): v for k, v in answers.items() if isinstance(v, Mapping)}
        return DecisionsResponse(generation_id=gid, answers=clean, usage=parse_usage(obj.get("usage")),
                                 model=obj.get("model") if isinstance(obj.get("model"), str) else None)

"""Provider failures → contract ErrorCodes (doc backend/04 §1 "Error mapping", provider-gateway spec).

| OpenRouter / transport                        | ErrorCode                                   |
|-----------------------------------------------|---------------------------------------------|
| 401                                           | invalid_key (also flips the key status)     |
| 402                                           | insufficient_credits                        |
| 403 moderation, or a refusal finish reason    | content_refused                             |
| 429                                           | rate_limited + retryAfterSec                |
| 408, or our own timeout                       | timeout                                     |
| 5xx, other 4xx, or a malformed response       | provider_error                              |
| An error chunk in the middle of a stream      | provider_error, partial text kept           |

`maybe_charged` says whether the provider may have billed the call (the request was sent and no error status came
back): the pipeline then records the call at its estimate instead of writing nothing (spend-ledger spec).
`cost_usd` is the provider-reported cost of a failed call that was billed anyway (a refusal still costs its prompt).
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from horizon.gateway.redact import redact

MESSAGES: dict[str, str] = {
    "missing_key": "Add your OpenRouter key in Settings first.",
    "invalid_key": "OpenRouter rejected the key.",
    "insufficient_credits": "Your OpenRouter account is out of credits.",
    "content_refused": "The model refused this request.",
    "rate_limited": "OpenRouter is rate-limiting requests. Try again shortly.",
    "timeout": "The model took too long to answer.",
    "provider_error": "OpenRouter returned an error.",
    "daily_budget_exceeded": "Today's spending cap is reached.",
    "creation_budget_exceeded": "This character's creation budget is used up.",
}


class ProviderError(Exception):
    def __init__(self, code: str, message: str | None = None, *, status: int | None = None,
                 retry_after: int | None = None, partial_text: str | None = None, maybe_charged: bool = False,
                 generation_id: str | None = None, cost_usd: float | None = None) -> None:
        self.code = code
        self.message = redact(message or MESSAGES.get(code, "OpenRouter returned an error."))
        super().__init__(self.message)
        self.status = status
        self.retry_after = retry_after
        self.partial_text = partial_text
        self.maybe_charged = maybe_charged
        self.generation_id = generation_id
        self.cost_usd = cost_usd  # set when the provider billed the failed call anyway (a refusal still costs its prompt)


def _provider_message(body: str) -> str | None:
    try:
        doc = json.loads(body)
    except (ValueError, TypeError):
        return None
    err = doc.get("error") if isinstance(doc, dict) else None
    msg = err.get("message") if isinstance(err, dict) else None
    return redact(str(msg))[:300] if msg else None


def retry_after_sec(headers: Mapping[str, str], body: str = "") -> int | None:
    raw = headers.get("retry-after") or headers.get("Retry-After")
    if raw:
        try:
            return max(0, int(float(raw)))
        except ValueError:
            return None
    try:
        doc = json.loads(body)
        meta = doc["error"]["metadata"]
        return int(float(meta.get("retry_after") or meta.get("retryAfter")))
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


def from_status(status: int, body: str, headers: Mapping[str, str]) -> ProviderError:
    detail = _provider_message(body)
    if status == 401:
        return ProviderError("invalid_key", status=status)
    if status == 402:
        return ProviderError("insufficient_credits", status=status)
    if status == 403:
        return ProviderError("content_refused", detail and f"The request was refused: {detail}", status=status)
    if status == 429:
        return ProviderError("rate_limited", status=status, retry_after=retry_after_sec(headers, body))
    if status == 408:
        return ProviderError("timeout", status=status)
    return ProviderError("provider_error", detail and f"OpenRouter returned an error: {detail}", status=status)


def malformed(what: str, *, maybe_charged: bool = True, generation_id: str | None = None) -> ProviderError:
    return ProviderError("provider_error", f"OpenRouter sent a malformed {what}.", maybe_charged=maybe_charged,
                         generation_id=generation_id)

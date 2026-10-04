"""Key redaction (doc backend/04 §5, NFR-12): the ONE rule every writer out of the process uses.

The log filter, the exception formatter, error envelopes, the ledger writer and the `on_call` hook all call `redact`.
The pattern takes any `sk-or-` token with one or more key characters, so it covers every key `PUT /settings/key`
accepts, short test keys included (design D4).
"""

from __future__ import annotations

import re
from typing import Any

KEY_RE = re.compile(r"sk-or-[A-Za-z0-9_\-]+")
REDACTED = "sk-or-***"


def redact(text: str) -> str:
    return KEY_RE.sub(REDACTED, text)


def redact_obj(value: Any) -> Any:
    """Redact every string inside a JSON-like value (dicts, lists, tuples); other values pass through."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {redact(k) if isinstance(k, str) else k: redact_obj(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact_obj(v) for v in value]
    return value

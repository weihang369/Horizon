"""Redaction (task 2.1, local-backend "The API key never leaks"): one rule, one token, every writer."""

from __future__ import annotations

import logging
from pathlib import Path

from horizon.api.errors import HorizonHTTPError
from horizon.gateway.redact import REDACTED, redact, redact_obj
from horizon.logs import close_file_logging, setup_logging


def test_token_and_pattern() -> None:
    assert REDACTED == "sk-or-***"
    assert redact("key sk-or-v1-abc123 end") == "key sk-or-*** end"
    assert redact("short sk-or-good.") == "short sk-or-***."
    assert redact("no key here: sk-or- alone") == "no key here: sk-or- alone"


def test_redact_obj_walks_nested_values() -> None:
    out = redact_obj({"a": ["x sk-or-test-0001", {"b": "sk-or-bad-zzz"}], "n": 3, "sk-or-k1": True})
    assert out == {"a": ["x sk-or-***", {"b": "sk-or-***"}], "n": 3, "sk-or-***": True}


def test_short_key_in_log_and_traceback(tmp_path: Path) -> None:
    setup_logging(tmp_path / "logs")
    log = logging.getLogger("horizon.test.redaction")
    log.info("saved sk-or-good")
    try:
        raise RuntimeError("provider said: bad key sk-or-v1-abcdef1234567890")
    except RuntimeError:
        log.exception("call failed")
    close_file_logging()
    text = (tmp_path / "logs" / "horizon.log").read_text(encoding="utf-8")
    assert "sk-or-good" not in text and "sk-or-v1" not in text
    assert text.count("sk-or-***") >= 2


def test_error_envelope_is_redacted() -> None:
    err = HorizonHTTPError("provider_error", "OpenRouter echoed sk-or-v1-abc123",
                           details={"body": {"msg": "key sk-or-test-0001 rejected"}})
    body = err.body()["error"]
    assert body["message"] == "OpenRouter echoed sk-or-***"
    assert body["details"] == {"body": {"msg": "key sk-or-*** rejected"}}

"""Gateway errors and call contexts (task 4.1, provider-gateway "Provider errors map to ErrorCodes", "Call context")."""

from __future__ import annotations

import json

import pytest

from horizon.gateway.context import call_ctx
from horizon.gateway.errors import from_status


@pytest.mark.parametrize(("status", "code"), [
    (401, "invalid_key"), (402, "insufficient_credits"), (403, "content_refused"), (429, "rate_limited"),
    (408, "timeout"), (500, "provider_error"), (502, "provider_error"), (503, "provider_error"), (400, "provider_error"),
])
def test_status_mapping(status: int, code: str) -> None:
    err = from_status(status, "", {})
    assert err.code == code and err.status == status and err.maybe_charged is False


def test_retry_after_from_header_and_body() -> None:
    assert from_status(429, "", {"retry-after": "12"}).retry_after == 12
    body = json.dumps({"error": {"message": "slow down", "metadata": {"retry_after": 7}}})
    assert from_status(429, body, {}).retry_after == 7
    assert from_status(429, "not json", {}).retry_after is None


def test_provider_message_is_redacted_and_bounded() -> None:
    body = json.dumps({"error": {"message": "bad key sk-or-test-0001 " + "x" * 1000}})
    err = from_status(500, body, {})
    assert "sk-or-test" not in err.message and "sk-or-***" in err.message
    assert len(err.message) < 400


def test_drains_only_for_reply() -> None:
    assert call_ctx("reply", world_id="wld_1", character_id="chr_1").drains
    for p in ("route", "gate", "rerank", "emotion", "query_embed", "summary", "host", "verdict"):
        assert not call_ctx(p).drains, p


def test_category_from_purpose() -> None:
    assert call_ctx("reply").category == "chat"
    assert call_ctx("route").category == "decision"
    assert call_ctx("query_embed").category == "embedding"
    assert call_ctx("image_portrait").category == "image"
    assert call_ctx("probe", category="embedding").category == "embedding"
    with pytest.raises(ValueError):
        call_ctx("probe")

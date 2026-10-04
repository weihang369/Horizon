"""Recorded OpenRouter fixtures (task 4.4): every file loads, carries its verification flag, and holds no real key."""

from __future__ import annotations

import json
import re

import httpx

from tests.gwkit import FIXTURES, response

FILES = sorted(FIXTURES.glob("*.json"))
REQUIRED = {"key_ok", "credits_ok", "models_ok", "generation_ok", "generation_404", "chat_ok", "chat_stream_ok",
            "chat_stream_chutes", "chat_stream_midstream_error", "chat_stream_refusal", "chat_malformed", "decisions_ok",
            "embeddings_ok", "images_ok", "error_401", "error_402", "error_403_moderation", "error_408", "error_429",
            "error_500", "error_502", "error_503_empty"}


def test_every_client_and_error_has_a_fixture() -> None:
    assert REQUIRED <= {f.stem for f in FILES}


def test_every_file_loads_and_is_flagged() -> None:
    for f in FILES:
        doc = json.loads(f.read_text(encoding="utf-8"))
        assert isinstance(doc.get("verified"), bool), f.name
        assert doc.get("source"), f.name
        assert isinstance(response(f.stem), httpx.Response), f.name


def test_no_real_key_in_any_fixture() -> None:
    for f in FILES:
        for m in re.finditer(r"sk-or-[A-Za-z0-9_\-]*", f.read_text(encoding="utf-8")):
            assert m.group(0).startswith("sk-or-test-"), f"{f.name}: {m.group(0)[:9]}…"

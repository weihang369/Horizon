"""The local JSON quote repair (llm-parameters "JSON calls repair locally, then retry once"; design D19; task 3.8)."""

from __future__ import annotations

import json

import pytest

from horizon.ai.jsonrepair import repair_json_quotes
from horizon.gateway.fake import load_canned


def test_group_a_failure_is_repaired() -> None:
    bad = '{"profile": {"name": "Loretta "Rhett" Kowalski", "age": 64}}'
    with pytest.raises(json.JSONDecodeError):
        json.loads(bad)
    assert json.loads(repair_json_quotes(bad)) == {"profile": {"name": 'Loretta "Rhett" Kowalski', "age": 64}}


def test_the_recorded_invalid_draft_is_repaired() -> None:
    """The one invalid draft of group A's 20 (committed as a canned response) parses after the repair."""
    _purpose, responses = load_canned("profile-drafts")
    (bad,) = [r for r in responses if not r["valid"]]
    with pytest.raises(json.JSONDecodeError):
        json.loads(bad["content"])
    assert isinstance(json.loads(repair_json_quotes(bad["content"])), dict)


@pytest.mark.parametrize("doc", [
    {"a": 'He said "hi"', "b": ["x", "y"], "c": {"d": "e:f, g}"}},
    {"s": "back\\slash é 字", "n": None, "t": True},
    [],
    {"empty": ""},
])
def test_valid_json_is_never_altered(doc: object) -> None:
    for text in (json.dumps(doc), json.dumps(doc, indent=2, ensure_ascii=False)):
        assert repair_json_quotes(text) == text


def test_every_valid_canned_draft_is_unchanged() -> None:
    _purpose, responses = load_canned("profile-drafts")
    for r in responses:
        if r["valid"]:
            assert repair_json_quotes(r["content"]) == r["content"]

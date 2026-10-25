"""The backend's ErrorCode table matches the shared fixture (and so `errors.ts`) and the contract enum."""

import json
from pathlib import Path

from horizon.api.errors import DEFAULT_RETRYABLE, DEFAULT_STATUS

ROOT = Path(__file__).resolve().parents[2]
CODES = json.loads((ROOT / "tests" / "fixtures" / "errors" / "codes.json").read_text("utf-8"))["codes"]
SCHEMA = json.loads((ROOT / "horizon" / "contract" / "schema.json").read_text("utf-8"))


def test_retryable_and_status_match_fixture() -> None:
    assert {k: v["retryable"] for k, v in CODES.items()} == DEFAULT_RETRYABLE
    assert {k: v["status"] for k, v in CODES.items()} == DEFAULT_STATUS


def test_fixture_covers_the_contract_enum() -> None:
    assert set(SCHEMA["$defs"]["ErrorCode"]["enum"]) == set(CODES)

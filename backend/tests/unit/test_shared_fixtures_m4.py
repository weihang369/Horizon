"""Shared M4 fixtures written by the TypeScript build (`npm run fixtures:build`): job plans (task 2.1), the draft bank
and the procedural theme spec (task 3.2). The Python ports must reproduce them exactly."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from horizon.ai.scripted import drafts
from horizon.domain.jsrng import JsRng, hash_string
from horizon.domain.pricing import load_price_table
from horizon.domain.runtime_config import load_runtime_config
from horizon.services import theme
from horizon.services.jobs import plans

FIX = Path(__file__).resolve().parents[1] / "fixtures"
SEED = Path(__file__).resolve().parents[3] / "seed"
PALETTES = [p["id"] for p in json.loads((SEED / "palettes.json").read_text(encoding="utf-8"))["data"]]


def load(rel: str) -> Any:
    return json.loads((FIX / rel).read_text(encoding="utf-8"))


def dump(v: Any) -> str:
    return json.dumps(v, indent=1, ensure_ascii=False)


@pytest.mark.parametrize("path", sorted(p.name for p in (FIX / "job_plans").glob("*.json")))
def test_job_plans_match_the_mock(path: str) -> None:
    fx = load(f"job_plans/{path}")
    prices = load_price_table(SEED).generation
    timing = load_runtime_config(SEED).jobs
    p = plans.plan(fx["input"], lean=fx["mode"] == "lean", prices=prices, timing=timing)
    assert p.parallel == fx["parallel"]
    got = [{"type": t.type, **({"emotion": t.emotion} if t.emotion else {}), "ms": t.duration_ms, "cost": t.est_usd,
            "category": t.category} for t in p.tasks]
    want = fx["tasks"]
    if fx["input"]["kind"] == "song":
        # D-83: the procedural theme is free on the backend (the mock still bills its sketch, OQ-9).
        assert [g["cost"] for g in got] == [0.0] and p.estimate == 0
        want = [{**w, "cost": 0.0} for w in want]
    else:
        assert p.estimate == fx["estimatedCostUsd"]
    assert got == want


def test_rng_matches_known_values() -> None:
    assert hash_string("draft:Sarah, a doctor") == hash_string("draft:Sarah, a doctor")
    r = JsRng("x")
    vals = [r.next() for _ in range(3)]
    assert all(0 <= v < 1 for v in vals) and len(set(vals)) == 3


@pytest.mark.parametrize("path", sorted(p.name for p in (FIX / "drafts").glob("seed_*.json")))
def test_draft_bank_byte_for_byte(path: str) -> None:
    fx = load(f"drafts/{path}")
    for case in fx["cases"]:
        got = drafts.draft_from_seed(case["seed"], case["intent"], PALETTES)
        assert dump(got) == dump(case["draft"]), (case["seed"], case["intent"])


def test_regenerate_field_byte_for_byte() -> None:
    fx = load("drafts/regenerate_field.json")
    for case in fx["cases"]:
        assert dump(drafts.regenerate_field(fx["profile"], case["field"], case["attempt"])) == dump(case["patch"]), case


def test_theme_spec_byte_for_byte() -> None:
    for case in load("theme_spec/cases.json")["cases"]:
        got = theme.theme_spec_from_brief(case["seed"], case["brief"], case.get("title"))
        assert dump(got) == dump(case["spec"])


def test_theme_duration_follows_the_mock() -> None:
    assert theme.duration_sec(96) == 20
    assert theme.duration_sec(112) == 17.1

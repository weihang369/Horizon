"""M9's `emotion` and `reactions` sets (turn-plan-emotion tasks 8.4, 8.5; design D27; m9-labels.md): built by the live
state builders, reproducible from their tables, inside the spread and the caps, and split by the hash rule."""

from __future__ import annotations

import importlib.util
from types import ModuleType

import pytest

from horizon.evals.datachecks import split_problems
from horizon.evals.suites import DATASETS, load_dataset


def builder(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"m9_{name}_build", DATASETS / name / "build.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize(("name", "n"), [("emotion", 140), ("reactions", 90)])   # emotion: + M15's 40 (E8)
def test_the_set_is_its_builder_output_inside_the_rules(name: str, n: int) -> None:
    mod = builder(name)
    rows = mod.build()
    assert mod.check(rows) == []
    path = DATASETS / name / f"{name}.jsonl"
    assert load_dataset(path) == rows                     # the committed file is exactly the builder's output
    assert len(rows) == n and len({r["id"] for r in rows}) == n
    assert split_problems(rows) == []


def test_emotion_keep_cap_and_a_third_neutral() -> None:
    rows = load_dataset(DATASETS / "emotion" / "emotion.jsonl")
    assert 28 <= sum(r["label"]["keep_ok"] for r in rows) <= 42                  # 20–30 % of 140
    assert 42 <= sum(r["label"]["previous"] == "neutral" for r in rows) <= 50     # about a third
    assert {r["question_id"] for r in rows} == {"emotion_reply", "emotion_greeting"}


def test_reactions_none_cap_and_no_same_face_label() -> None:
    rows = load_dataset(DATASETS / "reactions" / "reactions.jsonl")
    assert sum("none" in r["label"]["acceptable"] for r in rows) <= 27
    assert all(r["label"]["previous"] not in r["label"]["acceptable"] for r in rows)
    assert all(set(r["item"]["state"]) <= {"mode", "quoted_line", "quoted_before", "quoted_listeners"} for r in rows)

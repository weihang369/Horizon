"""M15's stays-in-character and sentence judge sets (images-music D12, D16; doc 02 B4; task 5.4). Committed files
only, no network."""

from __future__ import annotations

import json

from horizon.ai.questions import bank, check_lock
from horizon.evals.datachecks import overlap_problems, split_problems
from horizon.evals.suites import DATASETS, load_dataset

SETS = ("judge_voice", "judge_persona_fact", "judge_answers_last", "judge_sentence_supported")
LABELS = DATASETS / "judges" / "m15_labels.json"


def test_each_set_is_30_real_and_30_planted_with_hash_splits() -> None:
    for qid in SETS:
        rows = load_dataset(DATASETS / "judges" / f"{qid}.jsonl")
        real = [r for r in rows if not r["planted"]]
        assert len(rows) == 60 and len(real) == 30, qid
        assert all(r["label"] == "yes" for r in rows if r["planted"]), qid
        assert {r["label"] for r in real} <= {"yes", "no"} and all(r["question_id"] == qid for r in rows)
        assert set(bank().get(qid).state) == set(rows[0]["item"]["state"]), qid
        assert not split_problems(rows), qid


def test_every_real_item_is_labelled_blind_by_a_written_rule() -> None:
    labels = json.loads(LABELS.read_text(encoding="utf-8"))
    assert set(labels["_rules"]) == set(SETS)
    for qid in SETS:
        for r in load_dataset(DATASETS / "judges" / f"{qid}.jsonl"):
            if not r["planted"] and not (qid == "judge_voice" and "-m15-" not in r["id"]):
                assert labels[r["id"]]["label"] == r["label"], r["id"]
    voice_real = [r for r in load_dataset(DATASETS / "judges" / "judge_voice.jsonl") if not r["planted"]]
    assert all("-m15-" in r["id"] for r in voice_real)                    # v4's failed real half is gone


def test_the_new_judges_are_in_the_bank_and_locked() -> None:
    for qid, version in (("judge_persona_fact", 1), ("judge_answers_last", 2), ("judge_sentence_supported", 1)):
        q = bank().get(qid)   # judge_answers_last v2: reworded once after B4 (images-music 8.5)
        assert q.version == version and q.purpose == "eval_judge"
    assert check_lock() == []


def test_no_item_copies_a_bank_phrase() -> None:
    rows = [r for qid in SETS for r in load_dataset(DATASETS / "judges" / f"{qid}.jsonl")]
    assert overlap_problems(rows) == []

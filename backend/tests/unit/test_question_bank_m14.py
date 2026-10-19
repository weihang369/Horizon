"""The bank's M14 additions (safety design D3; question-bank spec "The safety entries", "The content rules are written
once per entry and stay equal"; tasks 1.1–1.2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from horizon.ai.decider import Noul
from horizon.ai.questions import RULES_START, BankError, bank, check_lock, load_bank
from tests.unit.test_question_bank import SENTENCE, copy_bank

SAFETY = {
    "unsafe_request": {"tSteer": 0.7},
    "unsafe_note": {"tSteer": 0.7},
    "at_risk": {"tCare": 0.3},
    "output_rules": {"tFlag": 0.5, "tBlock": 0.9},
    "motion_rules": {"tMotion": 0.7},
    "image_likeness": {"tImageLikeness": 0.5},
    "image_nudity": {"tImageNudity": 0.5},
    "image_gore": {"tImageGore": 0.5},
    "image_young": {"tImageYoung": 0.5},
    "song_copy": {"tSong": 0.6},
    "instruction": {"tInstruction": 0.7},
}
RULED = ("unsafe_request", "unsafe_note", "output_rules", "motion_rules")


def test_the_eleven_safety_entries_start_at_version_1_with_their_w12_thresholds() -> None:
    assert check_lock() == []
    for qid, thresholds in SAFETY.items():
        e = bank().get(qid)
        assert (e.version, e.type, dict(e.thresholds)) == (1, "noul", thresholds), qid


@pytest.mark.parametrize("qid", sorted(SAFETY))
def test_a_safety_entry_compiles_with_the_quoted_sentence(qid: str) -> None:
    e = bank().get(qid)
    kw: dict = {}
    if "{name}" in e.instructions:
        kw["name"] = "Amara"
    if "{n}" in e.instructions:
        kw["n"] = 2
    q = bank().question(qid, **kw)
    assert isinstance(q, Noul) and q.instructions.endswith(SENTENCE)
    assert "{" not in q.instructions          # every placeholder is filled


def test_the_rules_text_is_in_the_instructions_never_the_state() -> None:
    texts = {qid: bank().get(qid).instructions for qid in RULED}
    rules = {t[t.index(RULES_START):] for t in texts.values()}
    assert len(rules) == 1
    for qid in RULED:
        assert not any("rules" in k for k in bank().get(qid).state), qid


def test_a_drifted_rules_copy_fails_to_load(tmp_path: Path) -> None:
    root = copy_bank(tmp_path)
    p = root / "motion_rules.json"
    entry = json.loads(p.read_text(encoding="utf-8"))
    entry["instructions"] = entry["instructions"].replace("graphic gore", "gore")
    p.write_text(json.dumps(entry), encoding="utf-8")
    with pytest.raises(BankError, match="content rules") as e:
        load_bank(root)
    assert all(qid in str(e.value) for qid in RULED)


def test_a_dropped_rules_copy_fails_to_load(tmp_path: Path) -> None:
    root = copy_bank(tmp_path)
    p = root / "output_rules.json"
    entry = json.loads(p.read_text(encoding="utf-8"))
    entry["instructions"] = entry["instructions"][:entry["instructions"].index(RULES_START)]
    p.write_text(json.dumps(entry), encoding="utf-8")
    with pytest.raises(BankError, match="output_rules"):
        load_bank(root)


def test_the_instruction_entry_shares_the_importance_state() -> None:
    assert dict(bank().get("instruction").state) == dict(bank().get("importance").state)
    assert bank().get("importance").version == 1          # the seam: importance is never re-versioned for M14


def test_a_drifted_shared_steer_threshold_fails_to_load(tmp_path: Path) -> None:
    root = copy_bank(tmp_path)
    p = root / "unsafe_note.json"
    entry = json.loads(p.read_text(encoding="utf-8"))
    entry["thresholds"]["tSteer"] = 0.6
    p.write_text(json.dumps(entry), encoding="utf-8")
    with pytest.raises(BankError, match=r"safety.tSteer"):
        load_bank(root)

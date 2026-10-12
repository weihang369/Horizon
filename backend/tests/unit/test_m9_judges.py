"""M9's judge rules (turn-plan-emotion D28, D29; evaluation-harness "Too many false alarms"): the names-the-feeling
false-alarm cap and the pairwise judge's both-orders rule. Pure; plus the committed validation sets' shape."""

from __future__ import annotations

from horizon.evals import judges
from horizon.evals.suites import DATASETS, load_dataset


def nf_rows(false_alarms: int) -> list[dict]:
    real_no = [{"label": "no", "planted": False, "answer": "yes" if i < false_alarms else "no",
                "correct": i >= false_alarms} for i in range(22)]
    real_yes = [{"label": "yes", "planted": False, "answer": "yes", "correct": True} for _ in range(8)]
    planted = [{"label": "yes", "planted": True, "answer": "yes", "correct": True} for _ in range(30)]
    return real_no + real_yes + planted


def test_too_many_false_alarms_fails_an_otherwise_passing_judge() -> None:
    ok = judges.b4_for(judges.NAMES_FEELING, nf_rows(1))
    assert ok["passed"] and ok["false_alarms"] == 1
    bad = judges.b4_for(judges.NAMES_FEELING, nf_rows(2))
    assert bad["real"] >= 0.85 and bad["false_alarms"] == 2 and not bad["passed"]
    assert "false_alarms" not in judges.b4_for("judge_flattery", nf_rows(2))


def test_pairwise_averages_both_orders_for_the_known_winner() -> None:
    # Order 1 shows the winner as A; order 2 swaps it to B. A first-position lean alone can't win.
    first, second = {"a": 0.7, "b": 0.2, "same": 0.1}, {"a": 0.6, "b": 0.3, "same": 0.1}
    assert judges.prefers(first, second, "a") == (0.7 + 0.3) / 2
    assert judges.prefers(first, second, "b") == (0.2 + 0.6) / 2
    assert judges.swapped({"quoted_reply_a": "x", "quoted_reply_b": "y", "quoted_recent": []}) == {
        "quoted_reply_a": "y", "quoted_reply_b": "x", "quoted_recent": []}
    rows = [{"correct": True}] * 27 + [{"correct": False}] * 3
    assert judges.pairwise_result(rows) == {"n": 30, "accuracy": 0.9, "passed": True}
    assert not judges.b4_for(judges.PAIRWISE, [{"correct": True}] * 26 + [{"correct": False}] * 4)["passed"]


def test_the_validation_sets_are_shaped_as_d28_and_d29_say() -> None:
    nf = load_dataset(DATASETS / "judges" / "judge_names_feeling.jsonl")
    real = [r for r in nf if not r["planted"]]
    assert len(nf) == 60 and len(real) == 30 and sum(r["label"] == "yes" for r in real) == 8
    assert all(r["label"] == "yes" for r in nf if r["planted"])
    pw = load_dataset(DATASETS / "judges" / "judge_pairwise.jsonl")
    assert len(pw) == 30 and {r["label"] for r in pw} == {"a", "b"} and all(r["item"].get("name") for r in pw)
    assert all(set(r["item"]["state"]) == {"quoted_recent", "quoted_reply_a", "quoted_reply_b"} for r in pw)

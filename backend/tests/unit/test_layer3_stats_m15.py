"""Layer 3's statistics (images-music D11; evaluation-harness "Layer 3 judgements and statistics"; task 6.2), checked
against hand-worked answers. No network."""

from __future__ import annotations

from typing import Any

from horizon.evals import conversations as cv
from horizon.evals.metrics import bootstrap_mean, mcnemar_exact


def test_the_sign_test_is_two_sided_and_exact() -> None:
    # 8 wins, 2 losses: 2 × (C(10,0) + C(10,1) + C(10,2)) / 2^10 = 2 × 56 / 1024
    assert mcnemar_exact(8, 2) == 112 / 1024
    assert mcnemar_exact(5, 5) == 1.0 and mcnemar_exact(0, 0) == 1.0


def test_the_bootstrap_resamples_whole_conversations() -> None:
    # two conversations, three 1s and one 0: a resample is (1,1) → 1, a mixed pair → ¾, or (0,0) → 0 with chances
    # ¼, ½, ¼; both tails hold far more than 2.5 %, so the 95% interval is exactly 0–1
    assert bootstrap_mean([[1.0, 1.0, 1.0], [0.0]], n_boot=2000, seed=cv.SEED) == (0.0, 1.0)
    lo, hi = bootstrap_mean([[0.7, 0.7], [0.7]], n_boot=200, seed=1)      # every resample's mean is 0.7
    assert abs(lo - 0.7) < 1e-12 and abs(hi - 0.7) < 1e-12


def test_each_order_reads_its_own_side() -> None:
    first = {"a": 0.7, "b": 0.2, "same": 0.1}      # agent is A: agent picked
    second = {"a": 0.3, "b": 0.6, "same": 0.1}     # swapped, agent is B: agent picked again
    assert cv.order_verdicts(first, second) == ["win", "win"]
    assert cv.order_verdicts(first, {"a": 0.8, "b": 0.1, "same": 0.1}) == ["win", "loss"]
    assert cv.order_verdicts({"same": 0.9}, {"same": 0.9}) == ["tie", "tie"]
    assert cv.outcome(["win", "loss"]) == "disagree" and cv.outcome(None) is None


def row(t: str, p: float, orders: list[str], longer: bool) -> dict[str, Any]:
    return {"transcript": t, "judged": {"p_agent_better": p, "orders": orders, "agent_longer": longer}}


def test_win_tie_loss_only_where_both_orders_agree() -> None:
    rows = [row("t1", 0.9, ["win", "win"], True), row("t1", 0.8, ["win", "win"], False),
            row("t2", 0.5, ["win", "loss"], True), row("t2", 0.2, ["loss", "loss"], False),
            row("t3", 0.5, ["tie", "tie"], True)]
    st = cv.pairwise_stats(rows)
    assert (st["win"], st["tie"], st["loss"], st["disagree"]) == (2, 1, 1, 1)
    assert st["n"] == 5 and st["conversations"] == 3 and abs(st["mean"] - 2.9 / 5) < 1e-12
    assert st["sign_p"] == mcnemar_exact(2, 1) == 1.0
    assert st["win_when_agent_longer"] == (1, 3) and st["win_when_agent_shorter"] == (1, 2)
    lo, hi = st["ci"]
    assert 0.0 <= lo <= st["mean"] <= hi <= 1.0


def test_the_note_in_tag_check_reads_the_raw_reply() -> None:
    from horizon.evals.reply_checks import note_in_tag

    assert not note_in_tag("<e:thinking>Two points on the motion.")
    assert note_in_tag("<e:thinking>I should press on cost.</e:thinking> Two points on the motion.")   # M11's 14
    assert note_in_tag("<e:sad>It closed last week.</e:sad>")                                         # a stray close
    assert note_in_tag("<e:happy>Yes! <e:surprised> really?")                                         # a second tag
    assert cv.note_line([None, "<e:sad>x</e:sad>", "<e:sad>x"]).startswith("- naive note-in-tag: 1/2")

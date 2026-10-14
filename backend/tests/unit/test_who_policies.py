"""The M10 decision scoring (group-watch task 9.6; design D23; doc 07 G11, G2; evaluation-harness "M10 decision
sets"): the live rule as the policy answer, balanced accuracy, the exact paired tests, the floors and `t_end`."""

from __future__ import annotations

import itertools
from math import comb
from typing import Any

from horizon.ai.decider import ChoiceAnswer
from horizon.evals import who_policies as wp

A, B, C = "chr_a", "chr_b", "chr_c"


def label(acceptable: list[str], *, none_ok: bool = False, last: dict[str, int | None] | None = None,
          rr: str | None = None, cands: list[str] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"candidates": cands or [A, B, C], "acceptable": acceptable, "none_ok": none_ok,
                           "last_spoke": last or {A: 0, B: 1, C: None}}
    if rr:
        out["round_robin_next"] = rr
    return out


def ans(choice: str, conf: float, **probs: float) -> ChoiceAnswer:
    return ChoiceAnswer(choice, confidence=conf, probabilities=probs or {choice: conf})


# ── the policy answer is the live rule ──
def test_first_slot_takes_jev_at_the_floor_and_the_least_recent_of_the_top_two_below_it() -> None:
    lab = label([B])
    assert wp.who_answer("who_first", ans(B, 0.7), lab, 0.6) == B
    # below the floor: of Jev's top 2 (A 0.5, B 0.4), B spoke longer ago than A
    assert wp.who_answer("who_first", ans(A, 0.5, chr_a=0.5, chr_b=0.4, chr_c=0.1), lab, 0.6) == B
    assert wp.who_answer("who_first", None, lab, 0.6) == C                       # failed: the least recent overall


def test_second_slot_is_silent_unless_jev_is_sure() -> None:
    lab = label([], none_ok=True)
    assert wp.who_answer("who_second", ans("none", 0.9), lab, 0.6) == "none"
    assert wp.who_answer("who_second", ans(B, 0.5), lab, 0.6) == "none"
    assert wp.who_answer("who_second", ans(B, 0.8), lab, 0.6) == B
    assert wp.who_correct("who_second", "none", lab) and not wp.who_correct("who_second", B, lab)
    someone = label([B])
    assert wp.who_correct("who_second", B, someone) and not wp.who_correct("who_second", "none", someone)


def test_baselines() -> None:
    assert wp.who_baseline("who_first", label([C])) == C                         # never spoken goes first
    assert wp.who_baseline("who_scene", label([B], rr=B)) == B


# ── balanced accuracy and the margin ──
def test_always_none_cannot_pass() -> None:
    """Half the items need a second voice: answering none everywhere scores 50 % balanced, far below the target."""
    rows = [label([], none_ok=True)] * 30 + [label([B])] * 30
    oks = [(wp.who_correct("who_second", "none", lab), lab) for lab in rows]
    assert wp.balanced(oks) == 0.5
    skewed = [label([], none_ok=True)] * 58 + [label([B])] * 32   # ~65 % none: raw accuracy 0.64, balanced still 0.5
    assert wp.balanced([(wp.who_correct("who_second", "none", lab), lab) for lab in skewed]) == 0.5


def test_mcnemar_one_sided_matches_the_binomial_tail() -> None:
    assert wp.mcnemar_one_sided(0, 0) == 1.0
    assert abs(wp.mcnemar_one_sided(8, 1) - sum(comb(9, i) for i in range(8, 10)) / 512) < 1e-12
    assert wp.mcnemar_one_sided(10, 0) < 0.001 and wp.mcnemar_one_sided(5, 5) > 0.5


def test_the_weighted_sign_test_is_the_two_binomial_convolution() -> None:
    """Checked against brute force over every sign pattern of the discordant items."""
    sizes = {False: 4, True: 6}
    wins, losses = {False: 2, True: 3}, {False: 0, True: 1}
    w = {s: 1 / (2 * n) for s, n in sizes.items()}
    obs = sum(w[s] * (wins[s] - losses[s]) for s in sizes)
    d = {s: wins[s] + losses[s] for s in sizes}
    hits = total = 0
    for signs in itertools.product((1, -1), repeat=d[False] + d[True]):
        t = sum(signs[:d[False]]) * w[False] + sum(signs[d[False]:]) * w[True]
        total += 1
        hits += t >= obs - 1e-12
    assert abs(wp.weighted_sign_test(wins, losses, sizes) - hits / total) < 1e-12


def test_the_margin_needs_both_the_difference_and_the_test() -> None:
    assert wp.margin_passes(0.20, 0.01)
    assert not wp.margin_passes(0.10, 0.001)
    assert not wp.margin_passes(0.30, 0.20)


# ── floors ──
def test_the_floor_is_chosen_on_dev_with_ties_going_lower() -> None:
    rows = [(ans(B, 0.35), label([B])), (ans(A, 0.25), label([C]))]
    sel = wp.choose_who_floor("who_first", rows)
    # at 0.2 and 0.3 the first item is right (Jev's B) and the second wrong (A); at 0.4+ both fall back
    assert sel["grid"][0.2]["accuracy"] == 0.5 and sel["floor"] in wp.WHO_GRID


def test_needless_replies_bound_the_floor() -> None:
    """A low floor lets unsure picks through on `none` items: the bound rules it out even if its balanced accuracy
    is the best."""
    nones = [(ans(A, 0.35), label([], none_ok=True)) for _ in range(8)] + \
            [(ans("none", 0.9), label([], none_ok=True)) for _ in range(12)]
    someones = [(ans(B, 0.35), label([B])) for _ in range(20)]
    sel = wp.choose_who_floor("who_second", nones + someones)
    assert sel["grid"][0.3]["needless"] == 0.4 and sel["grid"][0.3]["accuracy"] == 0.8
    assert sel["grid"][0.4]["needless"] == 0.0 and sel["grid"][0.4]["accuracy"] == 0.5
    assert sel["floor"] >= 0.4 and sel["bounded"]


def test_t_end_is_the_lowest_threshold_with_precision_090() -> None:
    rows: list[tuple[float | None, str]] = [(0.95, "yes")] * 9 + [(0.92, "no")] + [(0.7, "yes")] * 5 + \
        [(0.65, "no")] * 5 + [(0.3, "no")] * 10 + [(None, "yes")]
    sel = wp.choose_t_end(rows)
    assert sel["t_end"] == 0.7                     # 14 of the 15 said yes are right; at 0.65 it drops to 14/20
    assert abs(sel["recall"] - 14 / 15) < 1e-12
    assert wp.choose_t_end([(0.9, "no")] * 3)["t_end"] is None


def test_the_reports_render() -> None:
    rows = []
    for i in range(20):
        split = "dev" if i % 2 else "test"
        rows.append({"split": split, "lang": "en", "answer": B, "confidence": 0.8, "probabilities": {B: 0.8},
                     "label": label([B]) if i % 3 else label([], none_ok=True)})
    for part in wp.PARTS:
        lines = wp.who_report([{**r, "label": {**r["label"], "round_robin_next": A}} for r in rows], part)
        assert lines[0].startswith("## ") and any("margin" in x for x in lines)
    talk = [{"split": "dev" if i % 2 else "test", "lang": "en", "p": 0.95 if i % 3 else 0.2,
             "label": "yes" if i % 3 else "no"} for i in range(20)]
    assert wp.talk_report(talk)[0].startswith("## Is the talk finished?")


# ── M11 (debate D17): who_next v3, and the fresh cuts held out ──
def test_the_floor_is_chosen_on_the_existing_items_and_the_fresh_cuts_are_scored_once(monkeypatch: Any) -> None:
    """Debate task 8.2: the 100 existing `who_scene` items choose the floor (dev) and are measured (test); the 40 fresh
    cuts (`fresh: true`, all test) never reach the floor choice and appear once, on their own line."""
    seen: list[list[Any]] = []
    real = wp.choose_who_floor

    def spy(part: str, rows: Any) -> dict[str, Any]:
        seen.append(list(rows))
        return real(part, rows)

    monkeypatch.setattr(wp, "choose_who_floor", spy)
    existing = [{"id": f"e{i}", "split": "dev" if i % 3 else "test", "lang": "en", "answer": B, "confidence": 0.8,
                 "probabilities": {B: 0.8}, "label": {**label([B], cands=[A, B]), "round_robin_next": A}}
                for i in range(100)]
    fresh = [{"id": f"f{i}", "split": "test", "fresh": True, "lang": "en", "answer": A, "confidence": 0.8,
              "probabilities": {A: 0.8}, "label": {**label([A] if i < 30 else [B], cands=[A, B]),
                                                   "round_robin_next": B}} for i in range(40)]
    lines = wp.who_report(existing + fresh, "who_scene")
    (dev_rows,) = seen
    assert len(dev_rows) == sum(r["split"] == "dev" for r in existing)          # the fresh cuts never choose it
    assert any("English test accuracy 34/34" in x for x in lines)              # the existing test items alone
    assert [x for x in lines if "fresh cuts" in x] == [
        "- fresh cuts (all test, scored once at the floor above): 30/40 = 0.75"]


def test_who_next_uses_the_least_recently_spoken_baseline_without_a_round_robin() -> None:
    lab = label([C], cands=[B, C], last={B: 2, C: 0})
    assert wp.who_baseline("who_next", lab) == B
    assert "who_next" in wp.PARTS


def test_fresh_cuts_are_test_by_rule() -> None:
    from horizon.evals.datachecks import split_for, split_problems

    dev_id = next(f"x{i}" for i in range(50) if split_for(f"x{i}") == "dev")
    assert split_problems([{"id": dev_id, "split": "test", "fresh": True}]) == []
    assert split_problems([{"id": dev_id, "split": "dev", "fresh": True}]) != []
    assert split_problems([{"id": dev_id, "split": "test"}]) != []

"""How the M10 decision sets are scored: who speaks, and "is the talk finished?" (doc 07 G11; docs/ai/02 B5;
group-watch design D23; evaluation-harness "M10 decision sets").

- **Who speaks** has three parts. The policy answer is the live code rule after the floor, computed by the same pure
  functions the planner calls:
  - `who_first` and `who_scene` (no `none`): Jev's pick at or above the floor, else the least recently spoken of Jev's
    top 2 (`pick_who`). Correct when it is in the acceptable set. Baselines: the least recently spoken (first slot)
    and round-robin from the last speaker (watch);
  - `who_second` (with `none`): Jev's pick at or above `floor.second`, else no second reply (`decide_second`). Correct
    on a `none` item when nobody speaks, on a someone item when the pick is in the set. Measured as balanced accuracy
    (the mean of the two strata), so "always none" scores 50 %. Baseline: the least recently spoken (always someone).
- **The margin** (G11): the observed difference ≥ 0.15 **and** an exact one-sided paired test with p < 0.05: McNemar
  on the discordant items (first slot, watch), and for the second slot a sign test whose discordant items weigh
  1 / (2 × their stratum's size), with its null distribution the convolution of the two strata's binomials.
- **Floors** come from {0.2, …, 0.9} (D36) on dev. `floor.second` is the best balanced accuracy among the floors
  whose needless second replies stay at or under 15 % of the `none` items (G2).
- **`t_end`** is the lowest threshold in {0.5, 0.55, …, 0.95} with precision ≥ 0.90 on dev (B5). Recall is reported;
  under 0.50 means the question is reworded.
- English is evaluated for accuracy; other languages only need to run (the user's rule, 2026-10-12).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import comb
from typing import Any

from horizon.ai.agent.cast_plan import least_recent, pick_who
from horizon.ai.agent.follow_plan import decide_second
from horizon.ai.decider import ChoiceAnswer
from horizon.evals.metrics import wilson

WHO_GRID = (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
T_END_GRID = tuple(round(0.5 + 0.05 * i, 2) for i in range(10))     # 0.5 … 0.95
NEEDLESS_MAX = 0.15     # G2: needless second replies on at most 15 % of the `none` items
MARGIN = 0.15           # G11: at least 15 points above the baseline
ALPHA = 0.05
PARTS = ("who_first", "who_second", "who_scene")
Row = tuple[ChoiceAnswer | None, Mapping[str, Any]]


# ── the policy answer and its score ──
def candidates(label: Mapping[str, Any]) -> list[str]:
    return [str(c) for c in label["candidates"]]


def turns_since(label: Mapping[str, Any]) -> dict[str, int | None]:
    return {str(k): (None if v is None else int(v)) for k, v in (label.get("last_spoke") or {}).items()}


def who_answer(part: str, answer: ChoiceAnswer | None, label: Mapping[str, Any], floor: float) -> str:
    """The live rule's pick for one item: a character id, or "none" (second slot only)."""
    cands = candidates(label)
    if part == "who_second":
        second, _, _ = decide_second(answer, cands, floor=floor, failure=None)
        return second or "none"
    pick, _, _ = pick_who(answer, cands, floor=floor, turns_since=turns_since(label))
    return pick


def is_none_item(label: Mapping[str, Any]) -> bool:
    return bool(label.get("none_ok"))


def who_correct(part: str, pick: str, label: Mapping[str, Any]) -> bool:
    if part == "who_second" and is_none_item(label):
        return pick == "none"
    return pick in set(label.get("acceptable") or [])


def who_baseline(part: str, label: Mapping[str, Any]) -> str:
    if part == "who_scene":
        return str(label["round_robin_next"])
    return least_recent(candidates(label), turns_since(label))


def balanced(results: Sequence[tuple[bool, Mapping[str, Any]]]) -> float:
    """The mean of the accuracy on someone items and on `none` items (each stratum that has items)."""
    strata: dict[bool, list[bool]] = {}
    for ok, label in results:
        strata.setdefault(is_none_item(label), []).append(ok)
    means = [sum(v) / len(v) for v in strata.values() if v]
    return sum(means) / len(means) if means else 0.0


def needless_rate(picks: Sequence[tuple[str, Mapping[str, Any]]]) -> float:
    """Second replies made on `none` items, as a share of them."""
    nones = [p for p, lab in picks if is_none_item(lab)]
    return sum(p != "none" for p in nones) / len(nones) if nones else 0.0


# ── the exact one-sided paired tests ──
def mcnemar_one_sided(b: int, c: int) -> float:
    """P(X ≥ b), X ~ Bin(b + c, ½): b = items only the policy got right, c = only the baseline."""
    n = b + c
    if n == 0:
        return 1.0
    return float(sum(comb(n, i) for i in range(b, n + 1))) / float(1 << n)


def weighted_sign_test(wins: Mapping[bool, int], losses: Mapping[bool, int], sizes: Mapping[bool, int]) -> float:
    """One-sided exact p for "the policy beats the baseline" on balanced accuracy. Per stratum s (someone, none): the
    discordant items weigh w_s = 1 / (2 n_s); under the null each is +w_s or −w_s with probability ½. The statistic's
    null distribution is the convolution of the two strata's binomials."""
    obs = 0.0
    strata = []
    for s in (False, True):
        n_s = sizes.get(s, 0)
        if not n_s:
            continue
        w = 1.0 / (2 * n_s)
        d = wins.get(s, 0) + losses.get(s, 0)
        obs += w * (wins.get(s, 0) - losses.get(s, 0))
        strata.append((w, d))
    if not strata:
        return 1.0
    dist: dict[float, float] = {0.0: 1.0}
    for w, d in strata:
        nxt: dict[float, float] = {}
        for t, p in dist.items():
            for k in range(d + 1):
                v = round(t + w * (2 * k - d), 12)
                nxt[v] = nxt.get(v, 0.0) + p * comb(d, k) / (1 << d)
        dist = nxt
    return min(1.0, sum(p for t, p in dist.items() if t >= round(obs, 12) - 1e-12))


def margin_passes(diff: float, p: float) -> bool:
    return diff >= MARGIN and p < ALPHA


# ── floors on dev ──
def choose_who_floor(part: str, rows: Sequence[Row]) -> dict[str, Any]:
    """D23 on dev rows: accuracy per floor (balanced for the second slot, under the needless-reply bound); ties go
    to the lower floor (more of Jev's answers used)."""
    grid: dict[float, dict[str, float]] = {}
    for f in WHO_GRID:
        picks = [(who_answer(part, a, lab, f), lab) for a, lab in rows]
        oks = [(who_correct(part, p, lab), lab) for p, lab in picks]
        acc = balanced(oks) if part == "who_second" else (sum(ok for ok, _ in oks) / len(oks) if oks else 0.0)
        grid[f] = {"accuracy": acc, "needless": needless_rate(picks) if part == "who_second" else 0.0}
    allowed = [f for f in WHO_GRID if grid[f]["needless"] <= NEEDLESS_MAX + 1e-12] if part == "who_second" else list(WHO_GRID)
    if not allowed:
        return {"floor": max(WHO_GRID), "grid": grid, "bounded": False}
    best = max(allowed, key=lambda f: (grid[f]["accuracy"], -f))
    return {"floor": best, "grid": grid, "bounded": True}


def choose_t_end(rows: Sequence[tuple[float | None, str]]) -> dict[str, Any]:
    """B5 on dev (p, "yes"/"no"): the lowest threshold with precision ≥ 0.90; recall at it."""
    table: dict[float, dict[str, float]] = {}
    for t in T_END_GRID:
        said = [(p is not None and p >= t, lab == "yes") for p, lab in rows]
        tp = sum(s and y for s, y in said)
        fp = sum(s and not y for s, y in said)
        pos = sum(y for _, y in said)
        table[t] = {"precision": tp / (tp + fp) if tp + fp else 0.0, "recall": tp / pos if pos else 0.0,
                    "yes": float(tp + fp)}
    ok = [t for t in T_END_GRID if table[t]["yes"] > 0 and table[t]["precision"] >= 0.90]
    t_end = min(ok) if ok else None
    return {"t_end": t_end, "table": table, "recall": table[t_end]["recall"] if t_end is not None else 0.0}


# ── the reports ──
def _answer(row: Mapping[str, Any]) -> ChoiceAnswer | None:
    if row.get("invalid") or row.get("answer") is None:
        return None
    return ChoiceAnswer(str(row["answer"]), confidence=row.get("confidence"), probabilities=row.get("probabilities"))


def _english(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [r for r in rows if str(r.get("lang") or "en") == "en"]


def who_report(rows: Sequence[Mapping[str, Any]], part: str) -> list[str]:
    title = {"who_first": "Who answers first", "who_second": "Who speaks up second",
             "who_scene": "Who speaks next in a watch"}[part]
    dev = [(_answer(r), r["label"]) for r in rows if r.get("split") == "dev"]
    test = [r for r in rows if r.get("split") == "test"]
    if not dev or not test:
        return [f"## {title}: needs dev and test items (dev {len(dev)}, test {len(test)})"]
    sel = choose_who_floor(part, dev)
    floor = float(sel["floor"])
    scored = _english(test)
    if not scored:
        return [f"## {title}: no English test items"]
    picks = [(who_answer(part, _answer(r), r["label"], floor), r["label"]) for r in scored]
    oks = [(who_correct(part, p, lab), lab) for p, lab in picks]
    base = [(who_correct(part, who_baseline(part, lab), lab), lab) for _, lab in picks]
    n = len(scored)
    out = [f"## {title} ({part}): floor {floor:.1f} (chosen on dev"
           + ("" if sel["bounded"] else "; NO floor meets the needless-reply bound") + ")"]
    if part == "who_second":
        acc, b_acc = balanced(oks), balanced(base)
        sizes = {s: sum(1 for _, lab in oks if is_none_item(lab) == s) for s in (False, True)}
        wins = {s: sum(1 for (o, lab), (b, _) in zip(oks, base, strict=True) if is_none_item(lab) == s and o and not b)
                for s in (False, True)}
        losses = {s: sum(1 for (o, lab), (b, _) in zip(oks, base, strict=True) if is_none_item(lab) == s and b and not o)
                  for s in (False, True)}
        p = weighted_sign_test(wins, losses, sizes)
        out += [f"- English test balanced accuracy {acc:.2f} (someone {sizes[False]}, none {sizes[True]}); target ≥ 0.80",
                f"- needless second replies {needless_rate(picks):.2f} of the none items (bound ≤ {NEEDLESS_MAX:.2f})",
                f"- baseline (least recently spoken, always someone) {b_acc:.2f}; difference {acc - b_acc:+.2f}; "
                f"exact weighted sign test p {p:.4f} → margin {'PASS' if margin_passes(acc - b_acc, p) else 'FAIL'}"]
    else:
        k = sum(o for o, _ in oks)
        kb = sum(b for b, _ in base)
        only_p = sum(o and not b for (o, _), (b, _) in zip(oks, base, strict=True))
        only_b = sum(b and not o for (o, _), (b, _) in zip(oks, base, strict=True))
        p = mcnemar_one_sided(only_p, only_b)
        lo, hi = wilson(k, n)
        name = "round-robin" if part == "who_scene" else "least recently spoken"
        out += [f"- English test accuracy {k}/{n} = {k / n:.2f} (95% Wilson {lo:.2f}–{hi:.2f}); target ≥ 0.80",
                f"- baseline ({name}) {kb}/{n} = {kb / n:.2f}; difference {(k - kb) / n:+.2f}; exact one-sided McNemar "
                f"p {p:.4f} ({only_p} only the policy right, {only_b} only the baseline) → margin "
                f"{'PASS' if margin_passes((k - kb) / n, p) else 'FAIL'}"]
    others = [r for r in test if str(r.get("lang") or "en") != "en"]
    if others:
        ran = sum(1 for r in others if _answer(r) is not None)
        out.append(f"- other languages: {ran}/{len(others)} test items ran (only that they run is checked)")
    out.append("- floor grid (dev): " + ", ".join(
        f"{f:.1f}: {g['accuracy']:.2f}" + (f"/needless {g['needless']:.2f}" if part == "who_second" else "")
        for f, g in sel["grid"].items()))
    return out


def talk_report(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    dev = [(r.get("p"), str(r["label"])) for r in rows if r.get("split") == "dev" and not r.get("invalid")]
    test = [r for r in _english(rows) if r.get("split") == "test" and not r.get("invalid")]
    if not dev or not test:
        return [f"## Is the talk finished?: needs dev and test items (dev {len(dev)}, test {len(test)})"]
    sel = choose_t_end(dev)
    t = sel["t_end"]
    if t is None:
        return ["## Is the talk finished?: no threshold reaches precision 0.90 on dev — the question is reworded (B5)"]
    said = [(float(r["p"]) >= t, str(r["label"]) == "yes") for r in test]
    tp = sum(s and y for s, y in said)
    fp = sum(s and not y for s, y in said)
    pos = sum(y for _, y in said)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / pos if pos else 0.0
    return [f"## Is the talk finished? (talk_finished): t_end {t:.2f} (lowest with precision ≥ 0.90 on dev; dev recall "
            f"{sel['recall']:.2f})",
            f"- English test: precision {prec:.2f} ({tp}/{tp + fp}), recall {rec:.2f} ({tp}/{pos})"
            + ("; recall under 0.50: reword the question (B5)" if rec < 0.5 else ""),
            "- dev table: " + ", ".join(f"{k:.2f}: P {v['precision']:.2f} R {v['recall']:.2f}"
                                        for k, v in sel["table"].items())]


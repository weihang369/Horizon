"""M13's decision sets (memory design D40; docs/ai/09 M12; evaluation-harness "The memory decision sets").

Four sets run in `decisions` like any other (`evals/datasets/{importance,memory_guard,earlier,recall}/`). Thresholds
are chosen here on dev by D40's rules, then scored once on test; English is scored, other languages are reported apart:
- **`importance`** (score, levels 1–5): the add is kept when its `unit` reaches `memory.minImportance` (0.25), so level
  1 drops. Keep-or-drop balanced accuracy ≥ 85 % and within one level ≥ 80 %.
- **`memory_guard`** (noul, "yes" = the rewrite keeps every still-true part): `t_keep` = the lowest threshold that
  lets ≤ 5 % of the lossy (label "no") rewrites through (p ≥ t), with the share of faithful rewrites it keeps beside it.
- **`earlier`** (noul, per candidate as `earlier:{id}`): `t_gate` by B5's gate rule, the highest threshold with recall
  ≥ 90 %, as `docs`.
- **`recall`** (noul, per candidate): `t_recall` = the lowest threshold with precision ≥ 85 %, with its recall beside.
- **`same_fact`** (noul; phase 10, the maintainer's choice): the duplicate check's question. `t_same` = the lowest threshold
  with precision ≥ 95 % on "same fact" (D39's rule for `dupCosine`, carried to the question that replaced it).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from horizon.evals.m12_sets import GRID, _other_languages, _pl, _rates, choose_t_gate
from horizon.evals.metrics import wilson

MIN_IMPORTANCE = 0.25
KEEP_ACCURACY = 0.85
WITHIN_ONE = 0.80
LOSSY_THROUGH = 0.05
RECALL_PRECISION = 0.85
SAME_PRECISION = 0.95


# ── importance ──
def _balanced(rows: Sequence[Mapping[str, Any]]) -> tuple[float, int, int]:
    """Keep-or-drop balanced accuracy: the mean of the keep and drop recalls."""
    keep = [r for r in rows if int(r["label"]) >= 2]
    drop = [r for r in rows if int(r["label"]) <= 1]
    rk = sum(1 for r in keep if float(r["unit"]) >= MIN_IMPORTANCE) / len(keep) if keep else 0.0
    rd = sum(1 for r in drop if float(r["unit"]) < MIN_IMPORTANCE) / len(drop) if drop else 0.0
    return (rk + rd) / 2, len(keep), len(drop)


def importance_report(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    got = [r for r in rows if r.get("unit") is not None and not r.get("invalid")]
    if not got:
        return ["## Importance (importance): no answers"]
    out = ["## Importance (importance): keep when unit ≥ minImportance 0.25 (level 1 drops)"]
    for split in ("dev", "test"):
        mine = [r for r in got if r["split"] == split and str(r.get("lang") or "en") == "en"]
        if not mine:
            continue
        bal, nk, nd = _balanced(mine)
        within = sum(1 for r in mine if abs(int(r["answer"]) - int(r["label"])) <= 1)
        lo, hi = wilson(within, len(mine))
        out.append(f"- English {split}: keep-or-drop balanced accuracy {bal:.2f} ({nk} keep, {nd} drop; target "
                   f"≥ {KEEP_ACCURACY:.2f}); within one level {within}/{len(mine)} (95% {lo:.2f}–{hi:.2f}; target "
                   f"≥ {WITHIN_ONE:.2f})")
    for lang in sorted({str(r.get("lang") or "en") for r in got} - {"en"}):
        mine = [r for r in got if str(r.get("lang")) == lang]
        bal, _, _ = _balanced(mine)
        out.append(f"- {lang} (runs, not scored): balanced {bal:.2f} over {len(mine)}")
    return out


# ── the rewrite guard ──
def through(rows: Sequence[tuple[float, bool]], t: float) -> tuple[float, float]:
    """(share of lossy rewrites let through, share of faithful rewrites kept) at `t` (supersede when p ≥ t)."""
    lossy = [p for p, y in rows if not y]
    good = [p for p, y in rows if y]
    return (sum(p >= t for p in lossy) / len(lossy) if lossy else 0.0), \
        (sum(p >= t for p in good) / len(good) if good else 0.0)


def choose_t_keep(rows: Sequence[tuple[float, bool]]) -> float | None:
    ok = [t for t in GRID if through(rows, t)[0] <= LOSSY_THROUGH]
    return min(ok) if ok else None


def guard_report(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    dev, test = _pl(rows, "dev"), _pl(rows, "test")
    if not dev or not test:
        return [f"## Rewrite guard (memory_guard): needs dev and test items (dev {len(dev)}, test {len(test)})"]
    t = choose_t_keep(dev)
    if t is None:
        return ["## Rewrite guard (memory_guard): no threshold lets ≤ 5 % of dev lossy rewrites through — reworded "
                "(B5)"]
    lt, kept = through(test, t)
    kinds = []
    for kind in ("changed", "changed_lossy"):   # v2: the conversation's changes, faithful and lossy (test)
        m = [(float(r["p"]), str(r["label"]) == "yes") for r in rows
             if r.get("kind") == kind and r.get("p") is not None and r.get("split") == "test"]
        if m:
            kinds.append(f"{kind} {sum(1 for p, _ in m if p >= t)}/{len(m)} supersede")
    return [f"## Rewrite guard (memory_guard): t_keep {t:.2f} (the lowest letting ≤ 0.05 of dev lossy rewrites "
            "through)",
            f"- English test: lossy let through {lt:.2f}; faithful rewrites superseding {kept:.2f} (the rest are kept "
            "beside their old line)" + (f"; {', '.join(kinds)}" if kinds else ""),
            "- dev table: " + ", ".join(f"{x:.2f}: L {through(dev, x)[0]:.2f} K {through(dev, x)[1]:.2f}"
                                        for x in GRID[::2])]


# ── needs something from earlier? ──
def earlier_report(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    dev, test = _pl(rows, "dev"), _pl(rows, "test")
    if not dev or not test:
        return [f"## Needs something from earlier? (earlier): needs dev and test items (dev {len(dev)}, test "
                f"{len(test)})"]
    tg = choose_t_gate(dev)
    if tg is None:
        return ["## Needs something from earlier? (earlier): no threshold reaches recall 0.90 on dev — reworded (B5)"]
    rec, prec = _rates(test, tg)
    no = [p for p, y in test if not y]
    return [f"## Needs something from earlier? (earlier): t_gate {tg:.2f} (highest with recall ≥ 0.90 on dev)",
            f"- English test: recall {rec:.2f}, precision {prec:.2f}; recall rate on items needing nothing earlier "
            f"{sum(1 for p in no if p >= tg)}/{len(no)}",
            *_other_languages(rows, tg),
            "- dev table: " + ", ".join(f"{t:.2f}: R {_rates(dev, t)[0]:.2f} P {_rates(dev, t)[1]:.2f}"
                                        for t in GRID[::2])]


# ── does this earlier line help? ──
def choose_t_recall(rows: Sequence[tuple[float, bool]]) -> float | None:
    ok = [t for t in GRID if _rates(rows, t)[1] >= RECALL_PRECISION and any(p >= t for p, _ in rows)]
    return min(ok) if ok else None


def recall_report(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    dev, test = _pl(rows, "dev"), _pl(rows, "test")
    if not dev or not test:
        return [f"## Earlier line helps? (recall): needs dev and test items (dev {len(dev)}, test {len(test)})"]
    t = choose_t_recall(dev)
    if t is None:
        return ["## Earlier line helps? (recall): no threshold reaches precision 0.85 on dev — reworded (B5)"]
    rec, prec = _rates(test, t)
    out = [f"## Earlier line helps? (recall): t_recall {t:.2f} (the lowest with precision ≥ 0.85 on dev)",
           f"- English test: precision {prec:.2f}, recall {rec:.2f}"]
    for kind in ("line", "memory"):
        m = [(float(r["p"]), str(r["label"]) == "yes") for r in rows
             if r.get("kind") == kind and r.get("p") is not None and r.get("split") == "test"]
        if m:
            rr, pp = _rates(m, t)
            out.append(f"- {kind}s (test): precision {pp:.2f}, recall {rr:.2f} ({len(m)})")
    out += _other_languages(rows, t)
    out.append("- dev table: " + ", ".join(f"{x:.2f}: R {_rates(dev, x)[0]:.2f} P {_rates(dev, x)[1]:.2f}"
                                           for x in GRID[::2]))
    return out


# ── same fact? ──
def choose_t_same(rows: Sequence[tuple[float, bool]]) -> float | None:
    ok = [t for t in GRID if _rates(rows, t)[1] >= SAME_PRECISION and any(p >= t for p, _ in rows)]
    return min(ok) if ok else None


def same_fact_report(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    dev, test = _pl(rows, "dev"), _pl(rows, "test")
    if not dev or not test:
        return [f"## Same fact? (same_fact): needs dev and test items (dev {len(dev)}, test {len(test)})"]
    t = choose_t_same(dev)
    if t is None:
        return ["## Same fact? (same_fact): no threshold reaches precision 0.95 on dev — reworded (B5)"]
    rec, prec = _rates(test, t)
    out = [f"## Same fact? (same_fact): t_same {t:.2f} (the lowest with precision ≥ 0.95 on dev)",
           f"- English test: precision {prec:.2f}, recall {rec:.2f}"]
    for kind in ("extended", "changed", "other"):   # the "no" kinds: how many would be dropped as duplicates (test)
        m = [float(r["p"]) for r in rows if r.get("kind") == kind and r.get("p") is not None and r.get("split") == "test"]
        if m:
            out.append(f"- {kind} (test): {sum(1 for p in m if p >= t)}/{len(m)} called the same")
    out.append("- dev table: " + ", ".join(f"{x:.2f}: R {_rates(dev, x)[0]:.2f} P {_rates(dev, x)[1]:.2f}"
                                           for x in GRID[::2]))
    return out


def reports(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    out: list[str] = []
    for qid, fn in (("importance", importance_report), ("memory_guard", guard_report),
                    ("earlier", earlier_report), ("recall", recall_report), ("same_fact", same_fact_report)):
        mine = [r for r in rows if r["question_id"] == qid]
        if mine:
            out += fn(mine)
    return out

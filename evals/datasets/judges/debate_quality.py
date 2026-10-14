"""Build `judge_keeps_side.jsonl` and `judge_engages.jsonl`: the B4 validation sets of the debate-quality judge (M11,
debate design D21; `evals/reviews/m11-labels.md`, "The debate-quality judge sets").

Run from backend/: `uv run python ../evals/datasets/judges/debate_quality.py`. Deterministic.

- **Real (30 each):** arguments from the committed histories, labelled blind from the argument and its context
  alone (task 10.3). A small conceded point the speaker says doesn't change the answer isn't breaking the side (P5);
  an argument that answers the other side's latest point, even badly, engages.
- **Planted (30 each, known `yes`):**
  - keeps its side: an argument asked as if the other side had made it (D21's relabel);
  - engages: the speaker's own opening put in their rebuttal or closing slot, against what the other side said there.
  Plants are taken by rule (`planted_keeps`, `planted_engages`): every two-sided debate in turn, its rebuttal and
  closing arguments in order, skipping any argument used as a real item.
- **State:** `horizon.evals.debate_suites.keeps_item` / `engages_item`, the ones the debate-quality run asks.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent

from horizon.evals import debate_suites as ds  # noqa: E402
from horizon.evals.datachecks import split_for  # noqa: E402

N = 30
OTHER = {"prop": "opp", "opp": "prop"}

# (debate, argument seq, label): task 10.3, from the committed histories
REAL_KEEPS: list[tuple[str, int, str]] = []
REAL_ENGAGES: list[tuple[str, int, str]] = []


def row(qid: str, item_id: str, it: dict[str, Any], label: str, planted: bool, source: str) -> dict[str, Any]:
    item = {"state": it["state"], **({"side": it["side"]} if it.get("side") else {})}
    return {"id": item_id, "question_id": qid, "split": split_for(item_id), "item": item, "label": label,
            "planted": planted, "source": source}


def arg_at(h: dict[str, Any], seq: int) -> dict[str, Any]:
    return next(a for a in ds.arguments(h) if int(a["seq"]) == seq)


def candidates_in_turn(hs: list[dict[str, Any]], used: set[tuple[str, int]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Two-sided debates in turn (one argument from each, round after round), rebuttals and closings in order."""
    pools = [[(h, a) for a in ds.arguments(h) if a["phase"] in ("rebuttal", "closing")
              and (h["id"], int(a["seq"])) not in used] for h in hs if h["format"] == "two_sided"]
    out = []
    for k in range(max((len(p) for p in pools), default=0)):
        out += [p[k] for p in pools if k < len(p)]
    return out


def planted_keeps(hs: list[dict[str, Any]], used: set[tuple[str, int]], n: int = N) -> list[dict[str, Any]]:
    out = []
    for h, a in candidates_in_turn(hs, used)[:n]:
        it = ds.keeps_item(h, a, side=OTHER[str(a["side"])])
        out.append(row(ds.KEEPS, f"{ds.KEEPS}-planted-{h['id']}-{a['seq']:03d}", it, "yes", True,
                       f"debate:{h['id']}#{a['seq']} asked as the {ds.SIDE_NAME[OTHER[str(a['side'])]]}"))
    return out


def planted_engages(hs: list[dict[str, Any]], used: set[tuple[str, int]], n: int = N) -> list[dict[str, Any]]:
    out = []
    for h, a in candidates_in_turn(hs, used)[:n]:
        opening = ds.opening_of(h, str(a["speaker"]))
        if not opening:
            continue
        it = ds.engages_item(h, a, text=opening)
        out.append(row(ds.ENGAGES, f"{ds.ENGAGES}-planted-{h['id']}-{a['seq']:03d}", it, "yes", True,
                       f"debate:{h['id']}#{a['seq']} with the speaker's opening"))
    return out


def build(hs: list[dict[str, Any]], real_keeps: list[tuple[str, int, str]] | None = None,
          real_engages: list[tuple[str, int, str]] | None = None, n: int = N) -> dict[str, list[dict[str, Any]]]:
    real_keeps = REAL_KEEPS if real_keeps is None else real_keeps
    real_engages = REAL_ENGAGES if real_engages is None else real_engages
    by_id = {h["id"]: h for h in hs}
    keeps = [row(ds.KEEPS, f"{ds.KEEPS}-real-{d}-{s:03d}", ds.keeps_item(by_id[d], arg_at(by_id[d], s)), lab, False,
                 f"debate:{d}#{s}") for d, s, lab in real_keeps]
    engages = [row(ds.ENGAGES, f"{ds.ENGAGES}-real-{d}-{s:03d}", ds.engages_item(by_id[d], arg_at(by_id[d], s)), lab,
                   False, f"debate:{d}#{s}") for d, s, lab in real_engages]
    keeps += planted_keeps(hs, {(d, s) for d, s, _ in real_keeps}, n)
    engages += planted_engages(hs, {(d, s) for d, s, _ in real_engages}, n)
    return {ds.KEEPS: keeps, ds.ENGAGES: engages}


def check(sets: dict[str, list[dict[str, Any]]]) -> list[str]:
    problems = []
    for qid, rows in sets.items():
        real = sum(not r["planted"] for r in rows)
        planted = sum(r["planted"] for r in rows)
        if (real, planted) != (N, N):
            problems.append(f"{qid}: want {N} real + {N} planted, have {real} + {planted}")
        if len({r["id"] for r in rows}) != len(rows):
            problems.append(f"{qid}: duplicate ids")
    return problems


def main() -> int:
    hs = ds.histories()
    if not hs:
        print("no committed debate histories yet (evals/debates/): run `horizon eval debate-history` first (10.1)")
        return 1
    sets = build(hs)
    problems = check(sets)
    if problems:
        print("\n".join(problems))
        return 1
    for qid, rows in sets.items():
        (HERE / f"{qid}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                           encoding="utf-8", newline="\n")
        print(f"wrote {len(rows)} {qid} items: labels {dict(Counter(r['label'] for r in rows))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

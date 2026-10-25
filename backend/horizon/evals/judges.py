"""Judge validation (docs/ai/02 B4; evaluation-harness "Judges are validated before they count"; persona-context design
D25, D27).

Each `eval_judge` question has 60 validation items in `evals/datasets/judges/<question>.jsonl`: 30 real outputs
labelled by hand, and 30 failures planted by code (`planted: true`, label `yes`, since every judge's "yes" is the
failure). A judge passes when it is at least 85 % right on the real items, beats the always-the-commonest-answer
baseline there, and catches at least 90 % of the planted failures. The result is recorded per question and version in
`evals/baselines/judges.json`. Any figure from a judge whose current version has not passed is "unvalidated".
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from horizon.evals.runner import EVALS_DIR

JUDGES_SET = "judges"
RECORD = EVALS_DIR / "baselines" / "judges.json"
REAL_MIN = 0.85
PLANTED_MIN = 0.90


def load_record(path: Path | None = None) -> dict[str, Any]:
    path = path or RECORD   # resolved at call time (tests point it elsewhere)
    if not path.is_file():
        return {}
    out: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return out


def validated(qid: str, version: int, record: Mapping[str, Any] | None = None) -> bool:
    """A judge's figures count only when its CURRENT version passed validation (a reword re-validates)."""
    r = (record if record is not None else load_record()).get(qid)
    return bool(r and r.get("passed") and int(r.get("version", 0)) == version)


def label(qid: str, version: int, record: Mapping[str, Any] | None = None) -> str:
    """The tag a report puts on a judged figure."""
    return "" if validated(qid, version, record) else " (unvalidated)"


def b4(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """B4's rule over one question's scored rows: {correct: bool, planted: bool, label: "yes"|"no"}."""
    rows = list(rows)
    real = [r for r in rows if not r.get("planted")]
    planted = [r for r in rows if r.get("planted")]
    # The always-the-commonest-answer baseline is taken over all 60 items (persona-context D32): real outputs are mostly
    # fine, so a real-only baseline is often 100 % "no" and no judge could ever beat it.
    yes = sum(1 for r in rows if r["label"] == "yes")
    baseline = max(yes, len(rows) - yes) / len(rows) if rows else 0.0
    overall = sum(1 for r in rows if r["correct"]) / len(rows) if rows else 0.0
    real_acc = sum(1 for r in real if r["correct"]) / len(real) if real else 0.0
    caught = sum(1 for r in planted if r["correct"]) / len(planted) if planted else 0.0
    passed = bool(real) and bool(planted) and real_acc >= REAL_MIN and overall > baseline and caught >= PLANTED_MIN
    return {"real_n": len(real), "real": round(real_acc, 4), "overall": round(overall, 4), "baseline": round(baseline, 4),
            "planted_n": len(planted),
            "planted": round(caught, 4), "passed": passed}


def update_record(results: Mapping[str, Mapping[str, Any]], versions: Mapping[str, int],
                  path: Path | None = None) -> None:
    path = path or RECORD
    rec = load_record(path)
    today = dt.date.today().isoformat()
    for qid, r in results.items():
        rec[qid] = {"version": versions[qid], **r, "date": today}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


# ── M9 (turn-plan-emotion D28, D29) ──
NAMES_FEELING = "judge_names_feeling"
MAX_FALSE_ALARMS = {NAMES_FEELING: 1}   # E8: a judge that flags clean replies would make the ≥ 95 % target meaningless
PAIRWISE = "judge_pairwise"
PAIRWISE_MIN = 0.90


def false_alarms(rows: Iterable[Mapping[str, Any]]) -> int:
    """Real items labelled clean ("no") that the judge called "yes"."""
    return sum(1 for r in rows if not r.get("planted") and r["label"] == "no" and r.get("answer") == "yes")


def b4_for(qid: str, rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """B4, plus E8's false-alarm cap where it applies; the pairwise judge has its own rule."""
    rows = list(rows)
    if qid == PAIRWISE:
        return pairwise_result(rows)
    r = b4(rows)
    cap = MAX_FALSE_ALARMS.get(qid)
    if cap is not None:
        fa = false_alarms(rows)
        r = {**r, "false_alarms": fa, "passed": bool(r["passed"]) and fa <= cap}
    return r


def swapped(state: Mapping[str, Any]) -> dict[str, Any]:
    """The pairwise judge's second order: the two replies trade places (its options are never shuffled)."""
    return {**state, "quoted_reply_a": state["quoted_reply_b"], "quoted_reply_b": state["quoted_reply_a"]}


def prefers(first: Mapping[str, float], second: Mapping[str, float], side: str) -> float:
    """The order-averaged probability that the reply first shown as `side` is the better one (B4's primary number)."""
    other = "b" if side == "a" else "a"
    return (float(first.get(side, 0.0)) + float(second.get(other, 0.0))) / 2


def pairwise_result(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Right when the order-averaged probability favours the known winner; passes at ≥ 90 % (D29)."""
    rows = [r for r in rows if "correct" in r]
    right = sum(1 for r in rows if r["correct"])
    acc = right / len(rows) if rows else 0.0
    return {"n": len(rows), "accuracy": round(acc, 4), "passed": bool(rows) and acc >= PAIRWISE_MIN}

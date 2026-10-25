"""The Jev drift canary (docs/ai/02 B6; docs/ai/13 W10; group A; ai-foundation design D32, D34; task 7.5).

`evals/canary.json` is the accepted baseline: a byte copy of group A's `canary.json` until the first accepted drift.
Its `fingerprint` salts every stored Jev answer's key, so it is recomputed on load —
`sha256(canonical([rounded(item.answers) for item in items]))`, group A's `rounded` — and a hand-edited baseline is
refused rather than silently re-keying the store.

**Pass rule** (B6, group A): every choice equals the baseline; every probability (choice options, a noul's p, score
levels) moves by ≤ 0.10; every raw score (0 … n−1) moves by ≤ 0.15. The canary always bypasses the store (D35).

**Per model** (jev-comparison D5): each Jev model has its own baseline, and its fingerprint salts that model's stored
answers (`baseline_path`, `fingerprint_for`). A candidate's first full run becomes its baseline (`first_baseline`).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from horizon.evals.store import canonical, sha

P_TOL = 0.10
SCORE_TOL = 0.15


class BaselineError(ValueError):
    pass


def rounded(answers: Mapping[str, Any] | None) -> Any:
    """Group A's `rounded` (docs/ai/checks/group-a/run.py): the parts the fingerprint uses, 2 places."""
    out: dict[str, Any] = {}
    for k, a in sorted((answers or {}).items()):
        if "choice" in a:
            out[k] = {"choice": a["choice"]}
        elif "noul" in a:
            out[k] = {"noul": round(float(a["noul"]), 2)}
        elif "score" in a:
            out[k] = {"score": round(float(a["score"]), 2)}
    return out


def fingerprint(items: Sequence[Mapping[str, Any]]) -> str:
    return sha([rounded(i["answers"]) for i in items])


@dataclass(frozen=True)
class Baseline:
    path: Path
    model: str
    fingerprint: str
    items: list[dict[str, Any]]


def load_baseline(path: Path) -> Baseline:
    doc = json.loads(path.read_text(encoding="utf-8"))
    items = list(doc["items"])
    got = fingerprint(items)
    if got != doc.get("fingerprint"):
        raise BaselineError(f"{path.name}: the fingerprint doesn't match its answers (edited by hand?); "
                            "accept a new baseline with `horizon eval canary --accept`")
    return Baseline(path, str(doc.get("model") or ""), got, items)


def _probs(a: Mapping[str, Any]) -> dict[str, float]:
    if "noul" in a:
        return {"p": float(a["noul"])}
    return {str(k): float(v) for k, v in (a.get("probabilities") or {}).items()}


def compare(base: Mapping[str, Any], new: Mapping[str, Any]) -> list[str]:
    """The drift found in one item's answers (empty: within tolerance)."""
    out: list[str] = []
    for qid, b in sorted(base.items()):
        n = new.get(qid)
        if not isinstance(n, Mapping):
            out.append(f"{qid}: no answer")
            continue
        if "choice" in b and n.get("choice") != b["choice"]:
            out.append(f"{qid}: choice {b['choice']} → {n.get('choice')}")
        if "score" in b and n.get("score") is not None and abs(float(n["score"]) - float(b["score"])) > SCORE_TOL:
            out.append(f"{qid}: score {b['score']} → {n['score']}")
        bp, np_ = _probs(b), _probs(n)
        for k, v in sorted(bp.items()):
            if k in np_ and abs(np_[k] - v) > P_TOL + 1e-9:
                out.append(f"{qid}: p[{k}] {v:.2f} → {np_[k]:.2f}")
    return out


def baseline_path(evals_dir: Path, model: str) -> Path:
    """jev-comparison (D5): each decision model has its own accepted baseline. `canary.json` is the one of the model it
    names (the pinned one); any other model's is `canary/<id with "/" → "__">.json`."""
    main = evals_dir / "canary.json"
    if main.is_file() and json.loads(main.read_text(encoding="utf-8")).get("model") == model:
        return main
    return evals_dir / "canary" / f"{model.replace('/', '__')}.json"


def fingerprint_for(evals_dir: Path, model: str) -> str | None:
    """The fingerprint that salts `model`'s stored Jev answers: its own baseline's, or None while it has none. For the
    pinned model this is `canary.json`'s, so every key stored before the comparison is unchanged."""
    path = baseline_path(evals_dir, model)
    return load_baseline(path).fingerprint if path.is_file() else None


def first_baseline(path: Path, items: list[dict[str, Any]], model: str, recorded: str, against: str) -> str:
    """A candidate model's first complete canary run becomes its baseline (D5); returns its fingerprint."""
    doc = {"model": model, "recorded": recorded, "fingerprint": fingerprint(items),
           "note": f"jev-comparison D5: this model's first canary run; its drift against {against} was reported, "
                   "not accepted",
           "items": items}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    return str(doc["fingerprint"])


def accept(path: Path, items: list[dict[str, Any]], model: str, recorded: str) -> str:
    """Rewrite the baseline with new answers (after a drift the user has seen); returns the new fingerprint."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc.update({"model": model, "recorded": recorded, "fingerprint": fingerprint(items), "items": items})
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    return str(doc["fingerprint"])


__all__ = ["Baseline", "BaselineError", "accept", "baseline_path", "canonical", "compare", "fingerprint",
           "fingerprint_for", "first_baseline", "load_baseline", "rounded"]

"""Build `debate_member.jsonl`: the debate member slice (M11, debate design D21; `evals/reviews/m11-labels.md`, "The
debate member slice").

Run from backend/: `uv run python ../evals/datasets/debate_member/build.py`. Deterministic. Labels were written blind
under m11-labels.md (committed first), from each cut alone, before any Jev answer.

- **Natural slots:** every rebuttal and closing slot of the committed histories (`evals/debates/*.json`) with two or
  more eligible members, cut with the live debate plan's request and state (`horizon.evals.debate_suites`). A slot
  is an item only when `LABELS` has it: a slot where any member would do equally is not written.
- **Written variants:** a natural slot whose last opposing argument is rewritten so that it plainly falls in one
  member's field (single-answer by construction). The non-English items are variants written in that language.
- **Labels:** the acceptable members (one or two), `single` (only one fits), and `fixed`, the fixed-order answer
  (the first eligible member). The fixed order is never a reason by itself.
- **Splits:** M9's hash rule with M10's id-prefix search for at least 30 test items (V11).
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

TESTS = 30
SIDE_LABEL = {"prop": "Proposition", "opp": "Opposition"}

# "<debate>#<slot seq>": (acceptable character ids, single). Written in task 10.3, from the committed histories.
LABELS: dict[str, tuple[list[str], bool]] = {}

# (debate, slot seq, the rewritten last opposing argument, the acceptable character id, language). Task 10.3.
VARIANTS: list[tuple[str, int, str, str, str]] = []


def id_prefix(base: str, n: int, tests: int = TESTS) -> str:
    """M10's prefix search: the first prefix whose hash split gives at least `tests` test items (ids alone)."""
    k = 0
    while True:
        pre = base if k == 0 else f"{base}{k}"
        if sum(split_for(f"{pre}-{i:03d}") == "test" for i in range(1, n + 1)) >= tests:
            return pre
        k += 1


def last_opposing_seq(h: dict[str, Any], sl: dict[str, Any]) -> int:
    """The seq of the argument `last_opposing` quotes at this slot (anyone else's in a panel)."""
    before = [x for x in h["lines"][: sl["index"]] if x["kind"] == "argument"]
    for x in reversed(before):
        if sl["side"] is None or x["side"] != sl["side"]:
            return int(x["seq"])
    raise ValueError(f"{h['id']}#{sl['seq']}: no opposing argument before the slot")


def item(h: dict[str, Any], sl: dict[str, Any], prof: dict[str, Any], acceptable: list[str], single: bool, lang: str,
         source: str, replace: dict[int, str] | None = None) -> dict[str, Any]:
    req = ds.cut_request(h, sl, prof, replace)
    state, _, qid, seed = ds.cut_state(req)
    assert qid is not None, f"{source}: one eligible member asks no member question"
    cands = list(sl["eligible"])
    return {"question_id": qid, "lang": lang, "kind": "debate",
            "item": {"state": state, "values": [{"key": c, "name": str(prof[c]["name"]),
                                                 "role": str(prof[c].get("role") or "")} for c in cands],
                     "seed": seed, "side": SIDE_LABEL.get(str(sl["side"])) if sl["side"] else None, "none": False},
            "label": {"candidates": cands, "acceptable": list(acceptable), "single": single, "fixed": cands[0]},
            "cut": {"debate": h["id"], "seq": sl["seq"], "replace": {str(k): v for k, v in (replace or {}).items()}},
            "source": source}


def build(hs: list[dict[str, Any]], prof: dict[str, Any], labels: dict[str, tuple[list[str], bool]] | None = None,
          variants: list[tuple[str, int, str, str, str]] | None = None, tests: int = TESTS) -> list[dict[str, Any]]:
    labels = LABELS if labels is None else labels
    variants = VARIANTS if variants is None else variants
    by_id = {h["id"]: h for h in hs}
    rows: list[dict[str, Any]] = []
    for h in hs:
        for sl in ds.natural_member_slots(h):
            key = f"{h['id']}#{sl['seq']}"
            if key in labels:
                ok, single = labels[key]
                rows.append(item(h, sl, prof, ok, single, h.get("language", "en"), f"debate:{key}"))
    for did, seq, text, ok_id, lang in variants:
        h = by_id[did]
        sl = next(s for s in ds.natural_member_slots(h) if s["seq"] == seq)
        rows.append(item(h, sl, prof, [ok_id], True, lang, f"debate:{did}#{seq} (written variant)",
                         {last_opposing_seq(h, sl): text}))
    pre = id_prefix("dmm", len(rows), tests) if rows else "dmm"
    out = []
    for n, r in enumerate(rows, 1):
        item_id = f"{pre}-{n:03d}"
        out.append({"id": item_id, "split": split_for(item_id), **r})
    return out


def check(rows: list[dict[str, Any]]) -> list[str]:
    """D21's counts: 90 items, at least 45 single-answer, English 80 / Malay 5 / Chinese 3 / mixed 2, ≥ 30 test."""
    problems = []
    if len(rows) != 90:
        problems.append(f"want 90 items, have {len(rows)}")
    if sum(r["label"]["single"] for r in rows) < 45:
        problems.append("fewer than 45 single-answer items")
    langs = Counter(r["lang"] for r in rows)
    if langs != Counter({"en": 80, "ms": 5, "zh": 3, "mixed": 2}):
        problems.append(f"languages {dict(langs)}")
    if sum(r["split"] == "test" for r in rows) < TESTS:
        problems.append(f"fewer than {TESTS} test items")
    for r in rows:
        lab = r["label"]
        if not 1 <= len(lab["acceptable"]) <= 2 or not set(lab["acceptable"]) <= set(lab["candidates"]):
            problems.append(f"{r['id']}: one or two acceptable members, from the candidates")
        if lab["single"] != (len(lab["acceptable"]) == 1):
            problems.append(f"{r['id']}: `single` must mean one acceptable member")
    return problems


def main() -> int:
    hs = ds.histories()
    if not hs:
        print("no committed debate histories yet (evals/debates/): run `horizon eval debate-history` first (10.1)")
        return 1
    rows = build(hs, ds.profiles())
    problems = check(rows)
    if problems:
        print("\n".join(problems))
        return 1
    (HERE / "debate_member.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                              encoding="utf-8", newline="\n")
    print(f"wrote {len(rows)} debate member items: splits {dict(Counter(r['split'] for r in rows))}, "
          f"single {sum(r['label']['single'] for r in rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

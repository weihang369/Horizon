"""Build `who_next.jsonl`: the group Next-speaker items (M11, debate design D17; evaluation-harness "The who_next set").

Run from backend/: `uv run python ../evals/datasets/who_speaks/next.py`. Deterministic. Labels were written blind under
`evals/reviews/m11-labels.md` (committed first), before any Jev answer.

Each item cuts a frozen group transcript right after a character's line that asks no character directly; the
candidates are the two other characters (G6: never the last speaker), and the state is the live cast plan's for a Next
speaker (`kind: "next"`: `who_next` v3, no `last_spoke`), with `quoted_latest` = "Name: line" as the group mode sends.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from build import T0, WHO, WORLDS, context_lines, last_spoke, profiles, session, values, views  # noqa: E402

from horizon.ai.agent.cast_plan import state_input  # noqa: E402
from horizon.ai.agent.plan_state import build_turn_plan_state  # noqa: E402
from horizon.ai.contexts import CastRequest  # noqa: E402
from horizon.evals.datachecks import split_for  # noqa: E402

# (world, transcript turn whose reply is the cut, the acceptable next speaker): m11-labels.md, reason 1 (the line names
# or speaks about them) unless noted
NEXT: list[tuple[str, int, str]] = [
    ("m", 4, "victor"), ("m", 10, "amara"), ("m", 11, "amara"), ("m", 15, "victor"), ("m", 16, "amara"),
    ("m", 22, "amara"), ("m", 23, "amara"), ("m", 25, "amara"), ("m", 31, "victor"), ("m", 33, "victor"),
    ("m", 38, "mei"), ("m", 39, "victor"), ("m", 41, "mei"), ("m", 43, "amara"), ("m", 59, "amara"),
    ("m", 71, "mei"), ("m", 74, "amara"), ("m", 77, "amara"), ("m", 92, "mei"), ("m", 95, "mei"),
    ("s", 0, "rin"), ("s", 2, "rin"), ("s", 8, "rin"), ("s", 12, "rin"), ("s", 18, "rin"),
    ("s", 23, "hana"), ("s", 24, "rin"), ("s", 29, "rin"), ("s", 32, "hana"), ("s", 39, "rin"),
    ("s", 41, "hana"), ("s", 44, "hana"), ("s", 50, "hana"), ("s", 51, "rin"), ("s", 54, "rin"),
    ("s", 62, "hana"), ("s", 65, "hana"), ("s", 72, "rin"), ("s", 74, "rin"), ("s", 86, "hana"),
]


def id_prefix(base: str, n: int, tests: int = 20) -> str:
    """M10's prefix search: the first prefix whose hash split gives at least `tests` test items."""
    k = 0
    while True:
        pre = base if k == 0 else f"{base}{k}"
        if sum(split_for(f"{pre}-{i:03d}") == "test" for i in range(1, n + 1)) >= tests:
            return pre
        k += 1


def build_next(prof: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    pre = id_prefix("whn", len(NEXT))
    for n, (world, turn, ok) in enumerate(NEXT, 1):
        ctx = context_lines(world, turn + 1)                  # the two turns up to and including the cut
        kind, last, text = ctx[-1]
        assert kind == "character" and last is not None
        cast = [WHO[c] for c in WORLDS[world][3]]
        cands = [c for c in cast if c != last]
        latest = f"{prof[last]['name']}: {text}"
        sctx = session(world, ctx, prof)
        req = CastRequest(session=sctx, kind="next", candidates=cands, cast=views(cands, prof), latest=latest,
                          base_faces=dict.fromkeys(cands, "neutral"), turns_since=last_spoke(ctx, cands), started_at=T0)
        state = build_turn_plan_state(state_input(req)).state
        item_id = f"{pre}-{n:03d}"
        rows.append({"id": item_id, "question_id": "who_next", "split": split_for(item_id), "lang": "en",
                     "kind": "group", "item": {"state": state, "values": values(cands, prof), "seed": f"m11-next:{n}",
                                               "none": False},
                     "label": {"candidates": cands, "acceptable": [WHO[ok]], "none_ok": False,
                               "last_speaker": last, "last_spoke": last_spoke(ctx, cands)},   # the baseline's, code only
                     "source": f"transcript:{WORLDS[world][2]}#{turn}"})
    return rows


def check(rows: list[dict[str, Any]]) -> list[str]:
    problems = []
    if len(rows) != 40 or Counter(r["source"].split("#")[0] for r in rows) != Counter(
            {"transcript:long_group_meridian": 20, "transcript:long_group_sunnyhollow": 20}):
        problems.append("who_next: 20 items per world")
    for r in rows:
        lab = r["label"]
        if len(lab["acceptable"]) != 1 or lab["acceptable"][0] not in lab["candidates"]:
            problems.append(f"{r['id']}: the acceptable speaker must be one candidate")
        if lab["last_speaker"] in lab["candidates"]:
            problems.append(f"{r['id']}: the last speaker is a candidate")
        if "last_spoke" in json.dumps(r["item"]["state"]):
            problems.append(f"{r['id']}: the state carries last_spoke (who_next v3 has none)")
    if sum(r["split"] == "test" for r in rows) < 20:
        problems.append("who_next: fewer than 20 test items")
    return problems


def main() -> int:
    rows = build_next(profiles())
    problems = check(rows)
    if problems:
        print("\n".join(problems))
        return 1
    (HERE / "who_next.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                         encoding="utf-8", newline="\n")
    print(f"wrote {len(rows)} who_next items: splits {dict(Counter(r['split'] for r in rows))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

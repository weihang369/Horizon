"""Build `emotion_debate.jsonl`: the debate emotion slice (M11, debate D29.1; `evals/reviews/m11-labels.md`, "The
debate emotion slice").

Run from backend/: `uv run python ../evals/datasets/emotion/build_debate.py`. Deterministic. Labels were written blind
under m11-labels.md (committed first), from each cut alone, before any Jev answer.

- **30 `emotion_line` items:** a rebuttal or closing argument's face, about the argument just made, as live asks it
  inside the slot's debate-plan request (`debate_suites.line_cut`).
- **10 `emotion_debate_opening` items:** an opening's face, as `plan_cast(kind="debate_opening")` asks it
  (`debate_suites.opening_cut`).
- **Labels:** M9's rule read for a debater (one or two faces, the milder wins, `keep_ok` when nothing would move the
  speaker). `previous` is the face the speaker went in with (their latest argument's, else neutral).
- **Split:** its own (`kind: "debate"`), M9's hash rule; the floors for debate faces are chosen on its dev split alone.
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

TESTS = 13

# (debate, slot seq, acceptable faces, keep_ok): task 10.3, blind, from each cut alone
LINES: list[tuple[str, int, list[str], bool]] = [
    # the speaker going into their argument, against the one just made (m11-labels.md: a sharp point → thinking; a
    # personal or misrepresenting one may anger; a point that gives ground may please; keep_ok when nothing would move)
    ("d01", 8, ["thinking", "happy"], False),     # Victor: Sofia says her pilot is the scalpel he asked for
    ("d01", 9, ["thinking"], False),              # Amara: Victor calls the pilot "access management wearing a ban"
    ("d01", 13, ["thinking", "happy"], False),    # Victor: Sofia closes on exemptions, his own point
    ("d02", 8, ["thinking"], False),              # Mei: Daniel's equity point, the strongest in the room
    ("d02", 13, ["thinking", "sad"], False),      # Mei: the Year 9 girl asleep in Daniel's office
    ("d02", 15, ["happy", "thinking"], False),    # Sofia: Amara calls Sofia's pilot the strongest point against her
    ("d03", 8, ["thinking", "happy"], False),     # Victor: Mei takes his definition and Sofia's pilot as a design
    ("d03", 9, ["thinking"], False),              # Daniel: "a concession is a concession", not the motion
    ("d04", 8, ["thinking", "happy"], False),     # Victor: Amara adopts a definition and concedes regressivity
    ("d04", 10, ["thinking"], False),             # Daniel: Mei calls his budget point a counterfactual
    ("d04", 14, ["thinking"], False),             # Mei: Victor's "four jurisdictions moved purchases, none moved disease"
    ("d05", 8, ["neutral", "happy"], True),       # Rin: Aiko describes Rin's own policy and calls it a ban
    ("d05", 10, ["happy", "thinking"], False),    # Hana: her dad's train metaphors and a dad joke
    ("d05", 13, ["thinking", "neutral"], False),  # Rin: Aiko's Alder Street kitchen and the fire door
    ("d06", 8, ["thinking", "happy"], False),     # Takeshi: his daughter turns his fish back on him
    ("d06", 10, ["thinking", "sad"], False),      # Bram: Kenji fell pushing a walker uphill in the rain
    ("d07", 8, ["neutral", "happy"], True),       # Rin: "the sixty million is a mortgage"
    ("d07", 9, ["thinking"], False),              # Bram: Rin says freight needs volume, not ninety head
    ("d08", 7, ["thinking", "angry"], False),     # Bram: "steady for farms can mean famine for children"
    ("d08", 13, ["thinking", "happy"], False),    # Rin: Bram calls his plan "a contract, not a mandate"
    ("d09", 9, ["thinking"], False),              # Amara: Victor concedes her single mother and answers her question
    ("d09", 11, ["thinking", "happy"], False),    # Sofia: Mei takes Sofia's pilot seriously
    ("d09", 17, ["thinking"], False),             # Sofia: Mei's closing, a mandate that excludes the least heard
    ("d10", 9, ["thinking"], False),              # Rin: "a handrail isn't forbidden fruit"
    ("d10", 10, ["thinking", "angry"], False),    # Takeshi: Rin calls the ban a padlock and a sign that "we gave up"
    ("d11", 7, ["thinking"], False),              # Daniel: "do you oppose homework, or too much homework?"
    ("d12", 8, ["happy", "thinking"], False),     # Hana: Aiko's lantern parade is Hana's own point
    ("d12", 9, ["thinking", "angry"], False),     # Bram: Hana moves the launch "three fields out", onto his land
    ("d13", 8, ["thinking", "neutral"], True),    # Mei: Amara takes Mei's staffing constraint
    ("d13", 9, ["thinking", "happy"], False),     # Victor: Mei's staffing range argues inside his frame
]
OPENINGS: list[tuple[str, int, list[str], bool]] = [
    # from the motion and the side alone: neutral or thinking; happy when the side is plainly one they relish
    ("d01", 2, ["happy", "thinking"], False),     # Sofia, transport planner, for a car-free centre
    ("d02", 2, ["neutral", "thinking"], False),   # Daniel, headteacher, for a ten o'clock start
    ("d03", 3, ["thinking", "neutral"], False),   # Victor, against a four-day week for public servants
    ("d04", 2, ["thinking", "happy"], False),     # Amara, physician, for a sugary-drinks tax
    ("d05", 3, ["happy", "neutral"], False),      # Rin, game-design student, against banning smartphones
    ("d06", 5, ["neutral", "thinking"], False),   # Bram, against closing the high street at weekends
    ("d07", 2, ["happy"], False),                 # Takeshi, retired train engineer, for reopening the branch line
    ("d08", 2, ["happy", "neutral"], False),      # Bram, dairy farmer, for buying school meals from local farms
    ("d10", 3, ["happy", "thinking"], False),     # Rin, game-design student, against a video-game ban
    ("d13", 2, ["thinking", "neutral"], False),   # Amara, physician, on a hospital or clinics (panel)
]


def id_prefix(base: str, n: int, tests: int = TESTS) -> str:
    k = 0
    while True:
        pre = base if k == 0 else f"{base}{k}"
        if sum(split_for(f"{pre}-{i:03d}") == "test" for i in range(1, n + 1)) >= tests:
            return pre
        k += 1


def build(hs: list[dict[str, Any]], prof: dict[str, Any], lines: list[tuple[str, int, list[str], bool]] | None = None,
          openings: list[tuple[str, int, list[str], bool]] | None = None, tests: int = TESTS) -> list[dict[str, Any]]:
    lines = LINES if lines is None else lines
    openings = OPENINGS if openings is None else openings
    by_id = {h["id"]: h for h in hs}
    rows: list[dict[str, Any]] = []
    for qid, table, cut in (("emotion_line", lines, ds.line_cut), ("emotion_debate_opening", openings, ds.opening_cut)):
        for did, seq, ok, keep in table:
            h = by_id[did]
            sl = next(s for s in ds.slots(h) if s["seq"] == seq)
            want = "opening" if qid == "emotion_debate_opening" else None
            assert (sl["phase"] == "opening") == (want == "opening"), f"{did}#{seq}: wrong phase for {qid}"
            state, name, seed = cut(h, sl, prof)
            rows.append({"question_id": qid, "lang": h.get("language", "en"), "kind": "debate",
                         "item": {"state": state, "name": name, "seed": seed},
                         "label": {"previous": ds.face_before(h, sl, sl["speaker"]), "acceptable": list(ok),
                                   "keep_ok": keep},
                         "source": f"debate:{did}#{seq}"})
    pre = id_prefix("emd", len(rows), tests) if rows else "emd"
    return [{"id": f"{pre}-{n:03d}", "split": split_for(f"{pre}-{n:03d}"), **r} for n, r in enumerate(rows, 1)]


def check(rows: list[dict[str, Any]]) -> list[str]:
    problems = []
    got = Counter(r["question_id"] for r in rows)
    if got != Counter({"emotion_line": 30, "emotion_debate_opening": 10}):
        problems.append(f"want 30 emotion_line + 10 emotion_debate_opening, have {dict(got)}")
    if sum(r["split"] == "test" for r in rows) < TESTS:
        problems.append(f"fewer than {TESTS} test items")
    for r in rows:
        if not 1 <= len(r["label"]["acceptable"]) <= 2 and not r["label"]["keep_ok"]:
            problems.append(f"{r['id']}: one or two faces, or keep_ok")
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
    (HERE / "emotion_debate.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                               encoding="utf-8", newline="\n")
    print(f"wrote {len(rows)} debate emotion items: splits {dict(Counter(r['split'] for r in rows))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

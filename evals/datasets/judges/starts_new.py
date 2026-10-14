"""Build `judge_starts_new.jsonl`: the B4 validation set for "does the line start nothing new?" (M11, debate D18;
`evals/reviews/m11-labels.md`, "judge_starts_new").

Run from backend/: `uv run python ../evals/datasets/judges/starts_new.py`. Deterministic.

- **Source:** `starts_new_source.json`, M10's three `agent` watch free runs (run 20261013T131638-freerun-038af2, 91
  lines, 7 written with the steer sentence), extracted from the run's database because `data/` isn't committed.
- **Real (30):** the 7 steered lines and 23 neighbours, labelled blind from the line and its scene alone. `yes` (the
  failure) = it only reacts, agrees, recaps, says goodbye, hands the decision to someone or waits; `no` = it brings in
  an event, a discovery, a new plan or a new question that moves the scene.
- **Planted (30):** a real cut with its line replaced: 20 written to only react, wrap up or hand off (known `yes`) and
  10 that bring in a new event, discovery or question (known `no`), so the commonest-answer baseline stays beatable.
- **State:** `starts_new_state` in `horizon/evals/watch_suites.py`, the one the free-run report uses.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
QID = "judge_starts_new"

from horizon.evals.datachecks import split_for  # noqa: E402
from horizon.evals.watch_suites import starts_new_state  # noqa: E402

SCENES = ("council", "shop", "radio")   # the source's scenes, in order

# (scene, seq, label): the 7 steered lines first (M10 read 0 of 7 as starting something new)
REAL: list[tuple[str, int, str]] = [
    ("council", 21, "yes"),   # restates the vacancy range, hands the pen to Kai
    ("council", 24, "no"),    # a new option: sleep on it, a resolution tonight is not a majority
    ("council", 28, "yes"),   # presses Kai to decide
    ("council", 31, "yes"),   # recaps the two doors, hands off
    ("radio", 23, "yes"),     # agrees, signs off ("that's where I'll leave it")
    ("radio", 26, "yes"),     # agrees, goodnight
    ("radio", 29, "yes"),     # one last restatement, then off the line
    # the neighbours
    ("council", 2, "no"),     # asks Mei for the vacancy data
    ("council", 5, "no"),     # a floor is lawful if defined and numbered: a new condition
    ("council", 7, "no"),     # the relabelling loophole
    ("council", 10, "no"),    # the funding date, not the level
    ("council", 14, "no"),    # phase on payroll cycles
    ("council", 20, "yes"),   # asks Kai for the number again
    ("council", 22, "yes"),   # agrees and presses Kai
    ("council", 25, "yes"),   # credits Mei's framing, hands to Kai
    ("council", 27, "no"),    # the traveler contracts renew at triple: a new cost
    ("shop", 3, "no"),        # stop forcing it, fetch the screwdriver: a new plan
    ("shop", 6, "no"),        # fixes the till: an event
    ("shop", 7, "no"),        # sends Kai for coffee: a new plan
    ("shop", 14, "yes"),      # grumbles about buying coffee
    ("shop", 17, "yes"),      # boasts, hangs up the jacket, teases Rin
    ("shop", 18, "no"),       # sends Rin for the pink roses
    ("shop", 22, "no"),       # brings up the swan fountain incident
    ("shop", 24, "yes"),      # keeps the swan fountain buried, tells Rin to wrap
    ("radio", 3, "no"),       # the coalition trap and the confound in the ambulance times
    ("radio", 12, "no"),      # universal automatic permits versus a review queue
    ("radio", 18, "no"),      # idling traffic pushed to the ring road near a school
    ("radio", 25, "yes"),     # signs off and recaps who brings what
    ("radio", 28, "yes"),     # goodnight and recap
    ("radio", 31, "yes"),     # goodnight
]

# (scene, seq whose line is replaced, label, the planted line): the speaker is the original line's
PLANTED: list[tuple[str, int, str, str]] = [
    ("council", 4, "yes", "Exactly what I was worried about, Mei. Ranges and all, I agree with every word. Kai, it's "
                          "your call."),
    ("council", 8, "yes", "Mei's point stands, and so does Amara's. I have nothing to add tonight. Kai, the decision "
                          "is yours."),
    ("council", 12, "yes", "As I said before: define the terms and attach a number. I'll say it again so it's in the "
                           "minutes."),
    ("council", 16, "yes", "Well, that's everything from me. Good night, all. Kai, you'll let us know."),
    ("council", 19, "yes", "Agreed, agreed. We're all saying the same thing now. Over to you, Kai."),
    ("council", 26, "yes", "I've said it three times now, so I'll stop. Kai, whatever you decide, I'm fine with it."),
    ("council", 30, "yes", "Then that's that. Thank you all for a long evening; I'm going home."),
    ("shop", 5, "yes", "Ha, fair enough, Rin. Kai, what do you think we should do?"),
    ("shop", 10, "yes", "Right. Well, I'll leave you two to it. See you next Sunday."),
    ("shop", 12, "yes", "lol yeah. same as dad said. whatever kai wants."),
    ("shop", 16, "yes", "Mm, so true, Dad. Anyway, Kai, up to you."),
    ("shop", 21, "yes", "Like I said, the window ones. Like I said."),
    ("shop", 26, "yes", "Okay, I think that's everything for today. Thanks, everyone, good night!"),
    ("shop", 29, "yes", "Haha, Rin, you're so right. I agree completely."),
    ("radio", 6, "yes", "I agree with Amara entirely. Nothing to add. Kai, over to you."),
    ("radio", 10, "yes", "To restate my earlier point: define the centre, draw it on a map. That is all."),
    ("radio", 14, "yes", "Good points all round. Let's leave it there for tonight."),
    ("radio", 17, "yes", "Fine by me. Whatever the council decides, really."),
    ("radio", 24, "yes", "Thanks both, this was lovely. Goodnight, Kai."),
    ("radio", 27, "yes", "Same as I said earlier: count the ambulances. Kai, your call."),
    ("council", 9, "no", "Hold on. I just got a message from the hospital trust: two wards closed tonight for lack of "
                         "staff. We need to vote on an emergency clause first."),
    ("council", 13, "no", "Wait, the clerk just put a revised forecast on the table: there's an unspent 2.1 million in "
                          "the transport reserve. Can we move that tonight?"),
    ("council", 23, "no", "New idea: what if the floor applies only to the two hospitals with the worst vacancy "
                          "rates, as a pilot, and we review it in six months?"),
    ("shop", 8, "no", "wait. there's an envelope taped under the drawer. it says 'for hana, open on her birthday'. "
                      "dad??"),
    ("shop", 13, "no", "Oh no, the cold-room door's been open all night and the lilies are frozen solid. Rin, grab "
                       "the bucket, we've got to save the wedding order."),
    ("shop", 20, "no", "Hang on, someone's at the door in the rain. It's Mrs Ito, and she wants three hundred roses "
                       "for a funeral by tomorrow morning."),
    ("shop", 25, "no", "new plan: we put the wet roses in the window with a sign, 'rainy day half price', and i post "
                       "it online. could actually sell some."),
    ("radio", 9, "no", "A caller just phoned in from the fire brigade: their engines can't turn into the old town "
                       "lanes at all if the bollards go in. Has anyone modelled that?"),
    ("radio", 13, "no", "A question nobody has raised: who compensates the shops whose deliveries become illegal "
                        "overnight? That's a takings claim waiting to happen."),
    ("radio", 20, "no", "The station's poll just came in: 61 percent of residents back the ban, but only 34 percent "
                        "of the people who drive in. That splits the whole debate."),
]


def source() -> dict[str, dict[str, Any]]:
    doc = json.loads((HERE / "starts_new_source.json").read_text(encoding="utf-8"))
    return dict(zip(SCENES, doc["scenes"], strict=True))


def cut(scene: dict[str, Any], seq: int) -> tuple[list[tuple[str, str]], tuple[str, str], bool]:
    lines = scene["lines"]
    i = next(k for k, x in enumerate(lines) if int(x["seq"]) == seq)
    before = [(str(x["speaker"]), str(x["text"])) for x in lines[:i]]
    return before, (str(lines[i]["speaker"]), str(lines[i]["text"])), bool(lines[i]["steered"])


def row(item_id: str, state: dict[str, Any], label: str, planted: bool, **extra: Any) -> dict[str, Any]:
    return {"id": item_id, "question_id": QID, "split": split_for(item_id), "item": {"state": state}, "label": label,
            "planted": planted, **extra}


def build() -> list[dict[str, Any]]:
    src = source()
    rows = []
    for name, seq, label in REAL:
        before, line, steered = cut(src[name], seq)
        rows.append(row(f"{QID}-real-{name}-{seq:02d}", starts_new_state(src[name]["premise"], before, line), label,
                        False, steered=steered))
    for name, seq, label, text in PLANTED:
        before, line, _ = cut(src[name], seq)
        rows.append(row(f"{QID}-planted-{name}-{seq:02d}",
                        starts_new_state(src[name]["premise"], before, (line[0], text)), label, True))
    return rows


def check(rows: list[dict[str, Any]]) -> list[str]:
    problems = []
    real = [r for r in rows if not r["planted"]]
    planted = [r for r in rows if r["planted"]]
    if len(real) != 30 or len(planted) != 30:
        problems.append(f"want 30 real + 30 planted, have {len(real)} + {len(planted)}")
    if sum(1 for r in real if r.get("steered")) != 7:
        problems.append("the 7 steered lines must all be real items")
    if len({r["id"] for r in rows}) != len(rows):
        problems.append("duplicate ids")
    yes = sum(r["label"] == "yes" for r in rows)
    if not 0.4 <= yes / len(rows) <= 0.65:
        problems.append(f"labels too one-sided for B4's baseline ({yes}/{len(rows)} yes)")
    return problems


def main() -> int:
    rows = build()
    problems = check(rows)
    if problems:
        print("\n".join(problems))
        return 1
    (HERE / f"{QID}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                       encoding="utf-8", newline="\n")
    print(f"wrote {len(rows)} {QID} items: labels {dict(Counter(r['label'] for r in rows))}, "
          f"splits {dict(Counter(r['split'] for r in rows))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Build `who_scene_fresh.jsonl`: 40 fresh held-out `who_scene` cuts (M11, debate design D17; task 10.11).

Run from backend/: `uv run python ../evals/datasets/who_speaks/fresh.py`. Deterministic.

- **Source:** the three `agent` watch free runs of task 10.10, committed as `evals/watch/freerun_m11_<k>.json` (the
  history format `freerun` keeps in its run folder).
- **Labels:** written blind under `evals/reviews/m10-labels.md`'s rule from each cut alone, before any v3 answer is
  seen. One acceptable name each (the candidates are the two who didn't just speak).
- **All test** (`fresh: true`): they are scored once at the floor the 100 existing items choose, and never choose it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from build import WHO, profiles  # noqa: E402
from scene import cut, history  # noqa: E402

# (history id, the number of character lines before the cut) → (acceptable short name, lang). Task 10.11: written
# blind under m10-labels.md from each cut, before any v3 answer; a cut where both candidates fit equally has none.
FRESH_LABELS: dict[tuple[str, int], tuple[str, str]] = {
    # freerun_m11_0: the council's emergency budget meeting (Amara, Mei, Victor)
    ("freerun_m11_0", 1): ("mei", "en"),        # Amara asks Mei for the labour data
    ("freerun_m11_0", 3): ("amara", "en"),      # Victor: "define your terms, Amara"
    ("freerun_m11_0", 5): ("amara", "en"),      # Mei: converting travelers pulls nurses off other rosters (her ward)
    ("freerun_m11_0", 10): ("victor", "en"),    # Amara asks: the motion or the minutes? (a legal instrument)
    ("freerun_m11_0", 11): ("victor", "en"),    # Mei: put it in the motion, where it binds
    ("freerun_m11_0", 12): ("amara", "en"),     # Victor: "Amara, Kai asked the room to decide"
    ("freerun_m11_0", 17): ("amara", "en"),     # Victor: "Amara, that is the entire case"
    ("freerun_m11_0", 22): ("amara", "en"),     # Victor: "Amara, draft it"
    ("freerun_m11_0", 23): ("amara", "en"),     # Mei: "Amara drafts"
    ("freerun_m11_0", 25): ("mei", "en"),       # Victor: "Mei, 15 to 18 is firmer than 12 to 19"
    ("freerun_m11_0", 26): ("amara", "en"),     # Mei: "once Amara's unit data came in"
    # freerun_m11_1: the till won't open (Hana, Rin, Takeshi)
    ("freerun_m11_1", 1): ("takeshi", "en"),    # Hana: "Dad, if I jiggle this lever"
    ("freerun_m11_1", 2): ("rin", "en"),        # Takeshi: "Rin, hand me that flathead"
    ("freerun_m11_1", 4): ("takeshi", "en"),    # Hana: "before Dad performs surgery"
    ("freerun_m11_1", 9): ("hana", "en"),       # Rin: "pretending to be you, hana"
    ("freerun_m11_1", 10): ("rin", "en"),       # Hana teases Rin's love life
    ("freerun_m11_1", 13): ("takeshi", "en"),   # Hana: a kiss "in front of my whole family"
    ("freerun_m11_1", 14): ("hana", "en"),      # Takeshi: "Hana, no kissing till the drawer's open"
    ("freerun_m11_1", 15): ("takeshi", "en"),   # Rin: "dad made them up thirty seconds ago"
    ("freerun_m11_1", 16): ("takeshi", "en"),   # Hana: "Dad, shop rules can't be made up"
    ("freerun_m11_1", 20): ("rin", "en"),       # Hana: "Rin, pretend to google it"
    ("freerun_m11_1", 21): ("rin", "en"),       # Takeshi: "Google won't fix a drawer", at Rin's google
    ("freerun_m11_1", 22): ("takeshi", "en"),   # Rin: "dad's not wrong"
    ("freerun_m11_1", 25): ("takeshi", "en"),   # Rin quotes Takeshi's "firm, not angry" and starts counting
    ("freerun_m11_1", 26): ("rin", "en"),       # Takeshi: "Count at your raid team"
    ("freerun_m11_1", 29): ("hana", "en"),      # Takeshi: "Hana, those croissants better be warm"
    # freerun_m11_2: the radio phone-in on banning cars (Amara, Mei, Victor)
    ("freerun_m11_2", 1): ("mei", "en"),        # Amara asks who gains: commuters or residents (distribution)
    ("freerun_m11_2", 2): ("amara", "en"),      # Mei questions Amara's ambulance times
    ("freerun_m11_2", 4): ("mei", "en"),        # Amara: "And Mei, fair on causation. But…"
    ("freerun_m11_2", 5): ("amara", "en"),      # Mei: "'we didn't need the trial' is exactly the move"
    ("freerun_m11_2", 6): ("amara", "en"),      # Victor: "Amara, the school evidence I don't contest"
    ("freerun_m11_2", 7): ("mei", "en"),        # Amara: "Mei, I'll stop leaning on obviousness if you'll…"
    ("freerun_m11_2", 8): ("victor", "en"),     # Mei: "Victor's boundary point is the one that ends up in court"
    ("freerun_m11_2", 10): ("victor", "en"),    # Amara: "My worry is the opposite of yours, Victor"
    ("freerun_m11_2", 11): ("amara", "en"),     # Mei: "Amara's on the distributional point"
    ("freerun_m11_2", 12): ("amara", "en"),     # Victor: "Amara's worry is the successful objection"
    ("freerun_m11_2", 15): ("mei", "en"),       # Victor: "Mei's wet blanket is the most useful thing said"
    ("freerun_m11_2", 17): ("amara", "en"),     # Mei: "Go get some sleep, Amara"
    ("freerun_m11_2", 23): ("victor", "en"),    # Mei: tag where callers define the boundary (Victor's point)
    ("freerun_m11_2", 27): ("mei", "en"),       # Victor: "Mei's number is the tell"
}


def build_fresh(prof: dict[str, dict[str, Any]], labels: dict[tuple[str, int], tuple[str, str]] | None = None,
                load: Any = history) -> list[dict[str, Any]]:
    labels = FRESH_LABELS if labels is None else labels
    rows = []
    for n, ((hid, k), (ok, lang)) in enumerate(sorted(labels.items()), 1):
        state, label = cut(load(hid), k, prof)
        label["acceptable"] = [WHO[ok]]
        assert label["acceptable"][0] in label["candidates"], f"{hid}#{k}: the acceptable speaker must be a candidate"
        rows.append({"id": f"wsf-{n:03d}", "question_id": "who_scene", "split": "test", "fresh": True, "lang": lang,
                     "kind": "watch", "item": {"state": state, "seed": f"m11-scene-fresh:{n}", "none": False,
                                               "values": [{"key": c, "name": str(prof[c]["name"]),
                                                           "role": str(prof[c].get("role") or "")}
                                                          for c in label["candidates"]]},
                     "label": label, "source": f"watch:{hid}#{k} (fresh)"})
    return rows


def main() -> int:
    rows = build_fresh(profiles())
    if len(rows) != 40:
        print(f"want 40 fresh cuts, have {len(rows)} (FRESH_LABELS is filled in task 10.11)")
        return 1
    (HERE / "who_scene_fresh.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                                encoding="utf-8", newline="\n")
    print(f"wrote {len(rows)} fresh who_scene cuts (all test)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

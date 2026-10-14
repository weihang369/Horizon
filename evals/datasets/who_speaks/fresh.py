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

# (history id, the number of character lines before the cut) → (acceptable short name, lang). Task 10.11.
FRESH_LABELS: dict[tuple[str, int], tuple[str, str]] = {}


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

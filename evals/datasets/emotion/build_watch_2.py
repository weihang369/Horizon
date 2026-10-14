"""Build `emotion_watch_2.jsonl`: the watch emotion slice's growth (M11, debate design D20; task 10.11).

Run from backend/: `uv run python ../evals/datasets/emotion/build_watch_2.py`. Deterministic.

- **Source:** the three `agent` watch free runs of task 10.10, committed as `evals/watch/freerun_m11_<k>.json`.
- **34 `emotion_line` items:** the cut after a character line, asked about the character who spoke next, with the
  live cast plan's state (`who_speaks/scene.py`'s `cut`, each character's face then); `previous` is that character's
  face going in (their latest line's, else neutral).
- **6 `emotion_opening` items:** each run's opening speaker, from the premise alone.
- **Labels:** M9's rule (`m9-labels.md`), written blind from the cut alone, before any answer.
- **Split:** M9's hash rule; with M10's 13 test items the slice passes 25 (D20).
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "evals" / "datasets" / "who_speaks"))

from scene import cut, history  # noqa: E402

from horizon.ai.agent.cast_plan import state_input  # noqa: E402
from horizon.ai.agent.plan_state import build_turn_plan_state  # noqa: E402
from horizon.ai.contexts import CastRequest, CharacterView, ParticipantView, SessionContext, WorldView  # noqa: E402
from horizon.evals.datachecks import split_for  # noqa: E402
from horizon.evals.watch_suites import seed_profiles  # noqa: E402

TESTS = 13
FACES = ("neutral", "happy", "sad", "angry", "surprised", "thinking", "embarrassed")

# (history id, the number of character lines before the cut, acceptable, keep_ok, lang); k = 0 is the opening. 10.11.
GROWTH: list[tuple[str, int, list[str], bool, str]] = []


def lines_of(h: dict[str, Any]) -> list[dict[str, Any]]:
    return [x for x in h["lines"] if x["kind"] == "line"]


def face_going_in(h: dict[str, Any], k: int, cid: str) -> str:
    mine = [x for x in lines_of(h)[:k] if x["speaker"] == cid]
    return str(mine[-1].get("emotion") or "neutral") if mine else "neutral"


def opening_state(h: dict[str, Any], prof: dict[str, Any], cid: str) -> dict[str, Any]:
    from datetime import UTC, datetime

    cast = list(h["cast"])
    parts = [ParticipantView(character_id=c, name=str(prof[c]["name"]), role="speaker",
                             character_role=str(prof[c].get("role") or ""), energy={"current": 500, "max": 1000})
             for c in cast]
    sctx = SessionContext(session_id="", seed="m11-eval", world=WorldView(id=h["world"], name="",
                                                                          you={"displayName": "Kai"}),
                          mode="watch", title="eval", config={"premise": h["premise"]}, participants=parts, recent=[])
    req = CastRequest(session=sctx, kind="opening", candidates=cast,
                      cast=[CharacterView(id=c, name=str(prof[c]["name"]), profile=prof[c]) for c in cast],
                      latest="", base_faces=dict.fromkeys(cast, "neutral"), turns_since=dict.fromkeys(cast),
                      started_at=datetime(2026, 10, 3, 3, 0, tzinfo=UTC))
    return dict(build_turn_plan_state(state_input(req)).state)


def build(prof: dict[str, Any], growth: list[tuple[str, int, list[str], bool, str]] | None = None,
          load: Any = history, tests: int = TESTS) -> list[dict[str, Any]]:
    growth = GROWTH if growth is None else growth
    rows = []
    for hid, k, ok, keep, lang in growth:
        h = load(hid)
        assert all(f in FACES for f in ok) and (1 <= len(ok) <= 2 or keep), f"{hid}#{k}"
        nxt = lines_of(h)[k]["speaker"]                      # the character whose face is asked
        prev = face_going_in(h, k, nxt)
        if k == 0:
            qid, state = "emotion_opening", opening_state(h, prof, nxt)
        else:
            faces = {c: face_going_in(h, k, c) for c in h["cast"]}
            qid, state = "emotion_line", cut(h, k, prof, faces)[0]
        rows.append({"question_id": qid, "lang": lang, "kind": "watch",
                     "item": {"state": state, "name": str(prof[nxt]["name"]), "seed": f"m11-emotion-watch:{hid}:{k}"},
                     "label": {"previous": prev, "acceptable": list(ok), "keep_ok": keep},
                     "source": f"watch:{hid}#{k}"})
    pre = "emw2"
    k_ = 0
    while rows and sum(split_for(f"{pre}-{i:03d}") == "test" for i in range(1, len(rows) + 1)) < tests:
        k_ += 1
        pre = f"emw2{k_}"
    return [{"id": f"{pre}-{n:03d}", "split": split_for(f"{pre}-{n:03d}"), **r} for n, r in enumerate(rows, 1)]


def check(rows: list[dict[str, Any]]) -> list[str]:
    kinds = Counter(r["question_id"] for r in rows)
    return [] if kinds == Counter({"emotion_line": 34, "emotion_opening": 6}) else [f"kinds {dict(kinds)}"]


def main() -> int:
    rows = build(seed_profiles())
    problems = check(rows)
    if problems:
        print("\n".join(problems) + " (GROWTH is filled in task 10.11)")
        return 1
    (HERE / "emotion_watch_2.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                                encoding="utf-8", newline="\n")
    print(f"wrote {len(rows)} watch emotion growth items: splits {dict(Counter(r['split'] for r in rows))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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

# (history id, the number of character lines before the cut, acceptable, keep_ok, lang[, who]); k = 0 is the
# opening, asked of the opener or of `who` (three scenes, six openings). Written blind in 10.11 from each cut alone.
GROWTH: list[tuple[str, int, list[str], bool, str] | tuple[str, int, list[str], bool, str, str]] = [
    # emotion_line: the next speaker's face, from the cut (the line they hear) alone
    ("freerun_m11_0", 1, ["thinking", "neutral"], False, "en"),     # Mei, asked for the labour data
    ("freerun_m11_0", 3, ["thinking"], False, "en"),                # Amara, told to define her terms
    ("freerun_m11_0", 5, ["thinking"], False, "en"),                # Victor, after Mei's second-order effect
    ("freerun_m11_0", 13, ["thinking", "angry"], False, "en"),      # Mei, the room still waiting on Kai
    ("freerun_m11_0", 16, ["sad", "thinking"], False, "en"),        # Victor, after Amara's burnt-out colleagues
    ("freerun_m11_0", 19, ["thinking", "neutral"], False, "en"),    # Mei, after "step into the well or sit down"
    ("freerun_m11_0", 20, ["thinking"], False, "en"),               # Amara, twenty minutes to the draft window
    ("freerun_m11_0", 24, ["happy", "thinking"], False, "en"),      # Victor, as Amara drafts the operative text
    ("freerun_m11_0", 26, ["happy", "thinking"], False, "en"),      # Amara, credited for her unit data
    ("freerun_m11_0", 28, ["happy", "thinking"], False, "en"),      # Amara, her line to go in the minutes verbatim
    ("freerun_m11_0", 29, ["thinking", "neutral"], False, "en"),    # Mei, seven minutes on the clock
    ("freerun_m11_1", 1, ["thinking"], False, "en"),                # Takeshi, Hana about to force the lever
    ("freerun_m11_1", 2, ["neutral", "happy"], True, "en"),         # Rin, sent for the screwdriver
    ("freerun_m11_1", 3, ["embarrassed"], False, "en"),             # Hana, filmed by Rin
    ("freerun_m11_1", 5, ["happy", "neutral"], False, "en"),        # Rin, after Dad's cow on the tracks
    ("freerun_m11_1", 7, ["happy", "neutral"], False, "en"),        # Takeshi, Hana's croissant emergency
    ("freerun_m11_1", 9, ["surprised", "happy"], False, "en"),      # Hana, Rin will impersonate her
    ("freerun_m11_1", 10, ["happy", "neutral"], False, "en"),       # Takeshi, "the flaky croissant people"
    ("freerun_m11_1", 13, ["surprised", "embarrassed"], False, "en"),  # Takeshi, a kiss in front of the family
    ("freerun_m11_1", 14, ["neutral", "happy"], False, "en"),       # Rin, Dad's made-up shop rules
    ("freerun_m11_1", 19, ["neutral", "thinking"], False, "en"),    # Hana, "Kai. Screen. Out loud."
    ("freerun_m11_1", 28, ["happy"], False, "en"),                  # Takeshi, the drawer just opened
    ("freerun_m11_1", 29, ["happy", "surprised"], False, "en"),     # Hana, "There she blows"
    ("freerun_m11_1", 30, ["happy", "neutral"], False, "en"),       # Rin, croissants on Hana
    ("freerun_m11_2", 2, ["thinking"], False, "en"),                # Victor, Mei flags causation
    ("freerun_m11_2", 3, ["thinking"], False, "en"),                # Amara, "a ban is a slogan"
    ("freerun_m11_2", 6, ["thinking"], False, "en"),                # Amara, the school evidence uncontested
    ("freerun_m11_2", 9, ["thinking"], False, "en"),                # Amara, after Victor's three points
    ("freerun_m11_2", 12, ["happy", "thinking"], False, "en"),      # Amara, her worry called the successful objection
    ("freerun_m11_2", 15, ["thinking", "neutral"], False, "en"),    # Amara, "fund the displacement study"
    ("freerun_m11_2", 16, ["happy", "neutral"], False, "en"),       # Mei, "the least cynical half hour"
    ("freerun_m11_2", 18, ["happy", "neutral"], False, "en"),       # Amara, "the record close on a rare occasion"
    ("freerun_m11_2", 21, ["happy"], False, "en"),                  # Amara, "the recording is a smart instinct"
    ("freerun_m11_2", 28, ["happy", "neutral"], False, "en"),       # Victor, "I mean it now: goodnight"
    # emotion_opening: from the premise alone, the opener and one more of the cast (debate D20's six)
    ("freerun_m11_0", 0, ["thinking", "neutral"], False, "en"),     # Amara, the night before the vote
    ("freerun_m11_0", 0, ["thinking", "neutral"], False, "en", "chr_seedVictor"),
    ("freerun_m11_1", 0, ["surprised", "thinking"], False, "en"),   # Hana, the till won't open
    ("freerun_m11_1", 0, ["thinking", "neutral"], False, "en", "chr_seedTakeshi"),
    ("freerun_m11_2", 0, ["thinking", "neutral"], False, "en"),     # Amara, a radio phone-in on car bans
    ("freerun_m11_2", 0, ["thinking", "neutral"], False, "en", "chr_seedMei"),
]


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


def build(prof: dict[str, Any], growth: list[Any] | None = None, load: Any = history,
          tests: int = TESTS) -> list[dict[str, Any]]:
    growth = GROWTH if growth is None else growth
    rows = []
    for g in growth:
        hid, k, ok, keep, lang = g[:5]
        h = load(hid)
        assert all(f in FACES for f in ok) and (1 <= len(ok) <= 2 or keep), f"{hid}#{k}"
        nxt = g[5] if len(g) > 5 else lines_of(h)[k]["speaker"]   # the character whose face is asked
        assert len(g) == 5 or k == 0, f"{hid}#{k}: only an opening names its character"
        prev = face_going_in(h, k, nxt)
        if k == 0:
            qid, state = "emotion_opening", opening_state(h, prof, nxt)
        else:
            faces = {c: face_going_in(h, k, c) for c in h["cast"]}
            qid, state = "emotion_line", cut(h, k, prof, faces)[0]
        rows.append({"question_id": qid, "lang": lang, "kind": "watch",
                     "item": {"state": state, "name": str(prof[nxt]["name"]),
                              "seed": f"m11-emotion-watch:{hid}:{k}" + (f":{nxt}" if len(g) > 5 else "")},
                     "label": {"previous": prev, "acceptable": list(ok), "keep_ok": keep},
                     "source": f"watch:{hid}#{k}" + (f" ({nxt})" if len(g) > 5 else "")})
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

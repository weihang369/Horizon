"""Build `emotion_watch.jsonl`: the watch slice of the `emotion` set (group-watch D16, D27; docs/ai/06 E8).

Run from backend/: `uv run python ../evals/datasets/emotion/build_watch.py`. Deterministic. Labels were written blind
under `evals/reviews/m10-labels.md` (M9's emotion rule, with the watch state), before any Jev answer.

40 items: 32 `emotion_line` (a scene turn: how the next speaker feels about the last line) and 8 `emotion_opening`
(the first turn: the premise and no lines). Each state is the live cast plan's for that turn (`scene_state`, shared
with the `talk_finished` builder), with the speaker's face now as their previous face. M9's `emotion.jsonl` is
unchanged; the decisions suite skips its already-measured items, so a run of `--set emotion` asks only this slice.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "evals" / "datasets" / "who_speaks"))   # the talk builder imports its helpers


def _load(name: str, path: Path) -> Any:
    """The sibling builders are all called build.py: load one by path, under its own module name."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_talk = _load("talk_build", ROOT / "evals" / "datasets" / "talk_finished" / "build.py")
PREMISES, WHO, id_prefix, profiles, scene_state = (_talk.PREMISES, _talk.WHO, _talk.id_prefix, _talk.profiles,
                                                   _talk.scene_state)

from horizon.evals.datachecks import split_for  # noqa: E402

FACES = ("neutral", "happy", "sad", "angry", "surprised", "thinking", "embarrassed")
Line = tuple[str, str]

# (premise, lines (empty: the opening), who, previous face, acceptable, keep_ok, lang)
SLICE: list[tuple[str, list[Line], str, str, list[str], bool, str]] = [
    # ── emotion_line (32) ──
    ("launch", [("hana", "Rin, a streamer with two million followers is playing your game live!")], "rin", "thinking",
     ["surprised", "happy"], False, "en"),
    ("launch", [("rin", "We've hit a thousand players."), ("hana", "A thousand!")], "takeshi", "neutral",
     ["happy", "thinking"], False, "en"),   # review pass (m10-review.md): proud, or puzzled by what it means
    ("launch", [("hana", "Someone left a review already. It says 'promising but buggy'.")], "rin", "happy",
     ["thinking", "sad"], False, "en"),
    ("launch", [("rin", "Server jatuh lagi, alamak. Same error as before.")], "hana", "happy",
     ["surprised", "sad"], False, "mixed"),
    ("party", [("takeshi", "I'm home early! Why is the kitchen door locked?")], "hana", "happy",
     ["embarrassed", "surprised"], False, "en"),
    ("party", [("rin", "Ayah suka semua orang. Termasuk Encik Ito.")], "hana", "neutral",
     ["happy", "neutral"], True, "ms"),
    ("party", [("hana", "You should give the speech, Rin! You're so good with words!")], "rin", "neutral",
     ["embarrassed", "neutral"], False, "en"),
    ("storm", [("rin", "The blue vase is in pieces, Hana. Mum's vase.")], "hana", "neutral", ["sad"], False, "en"),
    ("storm", [("takeshi", "When I was young, a storm like this stopped my train for two days.")], "rin", "neutral",
     ["thinking", "neutral"], True, "en"),
    ("storm", [("hana", "Dad, why did you really stop driving trains?")], "takeshi", "happy",
     ["sad", "thinking"], False, "en"),
    ("storm", [("rin", "Water's dripping through the ceiling!")], "takeshi", "thinking",
     ["surprised", "thinking"], False, "en"),
    ("storm", [("hana", "今晚能和大家在一起，我们真幸运。")], "takeshi", "neutral", ["happy"], False, "zh"),
    ("clinic", [("mei", "I've found a grant we missed. Two million, and it covers night services.")], "amara", "sad",
     ["happy", "surprised"], False, "en"),
    ("clinic", [("victor", "Before we vote: the motion as drafted is unlawful.")], "mei", "neutral",
     ["thinking"], False, "en"),
    ("clinic", [("amara", "One more thing. The nurses haven't been paid overtime since June.")], "mei", "neutral",
     ["surprised", "angry"], False, "en"),
    ("clinic", [("mei", "Motion carried. Three nights a week.")], "amara", "thinking", ["happy", "neutral"], False, "en"),
    ("clinic", [("victor", "I concede, Amara. You win this round.")], "amara", "angry", ["happy", "neutral"], False, "en"),
    ("powercut", [("victor", "Saya nak berhenti dari firma tu.")], "mei", "neutral", ["surprised"], False, "ms"),
    ("powercut", [("amara", "Listen. Someone's knocking inside the east lift.")], "victor", "neutral",
     ["surprised", "thinking"], False, "en"),
    ("powercut", [("mei", "Remember the flood year? Victor was stuck in the lift for three hours.")], "victor",
     "neutral", ["embarrassed"], False, "en"),
    ("powercut", [("amara", "My phone just buzzed. It's the ward.")], "mei", "happy", ["thinking", "neutral"], False, "en"),
    ("powercut", [("mei", "Cheers to small mercies and vending machines.")], "amara", "happy", ["happy"], True, "en"),
    ("games", [("victor", "Name one host city that kept its new pools open.")], "amara", "neutral",
     ["thinking", "angry"], False, "en"),
    ("games", [("mei", "And the real overrun figure is worse than 2.4 billion.")], "victor", "neutral",
     ["surprised", "thinking"], False, "en"),
    ("games", [("amara", "A runner died in a marathon heatwave in 2007. It's not a hypothetical.")], "victor", "happy",
     ["sad", "thinking"], False, "en"),
    ("games", [("mei", "辩论得很好，各位。")], "victor", "neutral", ["neutral", "happy"], True, "zh"),
    ("games", [("victor", "A caller says the bid's figures were leaked a week early.")], "mei", "neutral",
     ["surprised", "thinking"], False, "en"),
    ("launch", [("takeshi", "I'm proud of you, Rin. Very proud.")], "rin", "neutral", ["embarrassed", "happy"], False, "en"),
    ("party", [("rin", "Balloons, cake, the old photos. That's everything.")], "hana", "happy", ["happy"], True, "en"),
    ("clinic", [("mei", "So, three nights or four?")], "victor", "neutral", ["thinking", "neutral"], True, "en"),
    ("storm", [("rin", "Bateri telefon saya tinggal dua peratus.")], "hana", "neutral", ["neutral", "sad"], True, "ms"),
    ("powercut", [("victor", "Well. Shall we just sit?")], "mei", "neutral", ["neutral"], True, "en"),
    # ── emotion_opening (8) ──
    ("storm", [], "takeshi", "neutral", ["thinking"], True, "en"),
    ("storm", [], "hana", "neutral", ["surprised", "thinking"], False, "en"),
    ("party", [], "hana", "neutral", ["happy"], False, "en"),
    ("party", [], "rin", "neutral", ["neutral", "happy"], True, "en"),
    ("launch", [], "rin", "neutral", ["thinking", "surprised"], False, "en"),
    ("clinic", [], "amara", "neutral", ["thinking"], True, "en"),
    ("powercut", [], "mei", "neutral", ["neutral", "thinking"], True, "en"),
    ("games", [], "victor", "neutral", ["happy", "neutral"], True, "en"),
]


def build(prof: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    pre = id_prefix("emw", len(SLICE), tests=12)
    for n, (key, lines, who, prev, acceptable, keep_ok, lang) in enumerate(SLICE, 1):
        world, premise = PREMISES[key]
        cid = WHO[who]
        assert all(f in FACES for f in acceptable) and 1 <= len(acceptable) <= 2, n
        assert not lines or lines[-1][0] != who, f"item {n}: the speaker can't follow their own line"
        item_id = f"{pre}-{n:03d}"
        rows.append({"id": item_id, "question_id": "emotion_line" if lines else "emotion_opening",
                     "split": split_for(item_id), "lang": lang, "kind": "watch",
                     "item": {"state": scene_state(world, premise, lines, prof, {cid: prev}),
                              "name": str(prof[cid]["name"]), "seed": f"m10-emotion-watch:{n}:{cid}"},
                     "label": {"previous": prev, "acceptable": acceptable, "keep_ok": keep_ok},
                     "source": f"written ({key})"})
    return rows


def check(rows: list[dict[str, Any]]) -> list[str]:
    kinds = Counter(r["question_id"] for r in rows)
    problems = []
    if kinds != Counter({"emotion_line": 32, "emotion_opening": 8}):
        problems.append(f"kinds {dict(kinds)} (rule: 32 emotion_line, 8 emotion_opening)")
    keep = sum(r["label"]["keep_ok"] for r in rows)
    if not 8 <= keep <= 16:
        problems.append(f"keep_ok on {keep} items (about a quarter to a third, as M9's rule)")
    return problems


def main() -> int:
    rows = build(profiles())
    problems = check(rows)
    if problems:
        print("\n".join(problems))
        return 1
    (HERE / "emotion_watch.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                              encoding="utf-8", newline="\n")
    print(f"wrote {len(rows)} watch emotion items: splits {dict(Counter(r['split'] for r in rows))}, "
          f"kinds {dict(Counter(r['question_id'] for r in rows))}, keep_ok {sum(r['label']['keep_ok'] for r in rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

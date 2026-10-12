"""Build `reactions.jsonl`: E5's listener-reaction items, one listener each (turn-plan-emotion D18, D26, D27; docs/ai/06
E8; doc 02 B2).

Run from backend/: `uv run python ../evals/datasets/reactions/build.py`. Deterministic. Labels were written blind under
`evals/reviews/m9-labels.md` (committed first), before any Jev answer.

Each item's state is built by the live code (`ai/agent/reactions.state`): the line reacted to, the line before it, the
listener (name, card line, face now, debate side) and the mode. Group lines are real character replies from the frozen
transcripts where one fits (the user's line before them); debate and watch lines, and every non-English line, are
written. The acceptable set is the listener's visible reaction, or `none` (a same-face reaction counts as `none`).
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

from horizon.ai.agent.reactions import state  # noqa: E402
from horizon.ai.contexts import ListenerView, ReactionRequest, SessionContext, WorldView  # noqa: E402
from horizon.evals.datachecks import split_for  # noqa: E402

TRANSCRIPTS = ROOT / "evals" / "transcripts"
SEED = ROOT / "seed" / "characters"
USER = "Kai"
FACES = ("neutral", "happy", "sad", "angry", "surprised", "thinking", "embarrassed")
SRC = {"sunny": "long_group_sunnyhollow", "meridian": "long_group_meridian"}
WHO = {"amara": "chr_seedAmara", "hana": "chr_seedHana", "rin": "chr_seedRin", "takeshi": "chr_seedTakeshi",
       "mei": "chr_seedMei", "victor": "chr_seedVictor"}
SAME, OTHER = "same side as the speaker", "the other side"
N = "none"
R = None

# (mode, (transcript, turn) or None, speaker, line (None: the transcript reply), listener, face now, side,
#  acceptable, lang)
ITEMS: list[tuple[str, tuple[str, int] | None, str, str | None, str, str, str | None, list[str], str]] = [
    # ── group (40): real replies first ──
    ("group", ("sunny", 0), "hana", R, "rin", "neutral", None, ["angry"], "en"),
    ("group", ("sunny", 0), "hana", R, "takeshi", "neutral", None, [N], "en"),
    ("group", ("sunny", 2), "takeshi", R, "rin", "neutral", None, [N], "en"),
    ("group", ("sunny", 3), "hana", R, "takeshi", "happy", None, [N], "en"),
    ("group", ("sunny", 12), "hana", R, "rin", "neutral", None, ["embarrassed", "angry"], "en"),
    ("group", ("sunny", 13), "rin", R, "hana", "happy", None, [N], "en"),
    ("group", ("sunny", 14), "takeshi", R, "rin", "angry", None, ["embarrassed", N], "en"),
    ("group", ("sunny", 15), "hana", R, "takeshi", "neutral", None, ["happy"], "en"),
    ("group", ("sunny", 21), "hana", R, "takeshi", "happy", None, [N, "embarrassed"], "en"),
    ("group", ("sunny", 22), "rin", R, "hana", "neutral", None, ["embarrassed"], "en"),
    ("group", ("sunny", 23), "takeshi", R, "hana", "embarrassed", None, ["happy"], "en"),
    ("group", ("sunny", 26), "takeshi", R, "hana", "neutral", None, ["happy", "sad"], "en"),
    ("group", ("sunny", 30), "hana", R, "rin", "neutral", None, ["angry"], "en"),
    ("group", ("sunny", 33), "hana", R, "rin", "neutral", None, ["happy"], "en"),
    ("group", ("sunny", 33), "hana", R, "takeshi", "neutral", None, ["happy"], "en"),
    ("group", ("sunny", 37), "rin", R, "hana", "neutral", None, ["happy"], "en"),
    ("group", ("sunny", 38), "takeshi", R, "rin", "neutral", None, ["angry", "embarrassed"], "en"),
    ("group", ("sunny", 45), "hana", R, "takeshi", "happy", None, ["embarrassed", N], "en"),
    ("group", ("sunny", 46), "rin", R, "hana", "neutral", None, ["happy"], "en"),
    ("group", ("sunny", 47), "takeshi", R, "hana", "happy", None, ["sad"], "en"),
    ("group", ("meridian", 7), "mei", R, "victor", "neutral", None, ["happy", "thinking"], "en"),
    ("group", ("meridian", 8), "victor", R, "amara", "neutral", None, [N], "en"),
    ("group", ("meridian", 14), "victor", R, "mei", "neutral", None, [N], "en"),
    ("group", ("meridian", 22), "mei", R, "amara", "thinking", None, [N], "en"),
    ("group", ("meridian", 23), "victor", R, "amara", "sad", None, [N], "en"),
    ("group", ("meridian", 24), "amara", R, "mei", "neutral", None, ["surprised", N], "en"),
    ("group", ("meridian", 29), "victor", R, "mei", "neutral", None, [N], "en"),
    ("group", ("meridian", 31), "mei", R, "victor", "neutral", None, ["happy"], "en"),
    ("group", ("meridian", 35), "victor", R, "amara", "sad", None, [N], "en"),
    ("group", ("meridian", 46), "mei", R, "victor", "neutral", None, ["embarrassed", "happy"], "en"),
    ("group", ("meridian", 47), "victor", R, "mei", "neutral", None, ["happy"], "en"),
    ("group", ("meridian", 43), "mei", R, "victor", "neutral", None, [N], "en"),
    ("group", ("meridian", 40), "mei", R, "victor", "neutral", None, ["happy", "thinking"], "en"),
    ("group", ("meridian", 21), "amara", R, "victor", "neutral", None, [N], "en"),
    # group, other languages (written)
    ("group", None, "hana", "Rin, awak lupa hari jadi Ayah lagi tahun ni!", "rin", "neutral", None, ["embarrassed"], "ms"),
    ("group", None, "takeshi", "Hana, kedai bunga awak masuk surat khabar pagi ni!", "hana", "neutral", None, ["happy", "surprised"], "ms"),
    ("group", None, "rin", "Ayah, lawak tu teruk sangat.", "takeshi", "happy", None, ["embarrassed", N], "ms"),
    ("group", None, "mei", "维克多，你上次的论证完全站不住脚。", "victor", "neutral", None, ["angry", "thinking"], "zh"),
    ("group", None, "amara", "梅，你的报告救了很多病人。", "mei", "neutral", None, ["happy", "embarrassed"], "zh"),
    ("group", None, "hana", "Dad, your train model collection jatuh semua from the shelf!", "takeshi", "neutral", None, ["surprised", "sad"], "mixed"),
    # ── debate (25): "This house would adopt a four-day work week." Victor and Amara propose; Mei opposes ──
    ("debate", None, "victor", "My opponent's data covers nine shift-based firms out of a hundred. Nine. She is extrapolating from a rounding error.", "mei", "neutral", OTHER, ["angry", "thinking"], "en"),
    ("debate", None, "victor", "My opponent's data covers nine shift-based firms out of a hundred. Nine. She is extrapolating from a rounding error.", "amara", "neutral", SAME, ["happy"], "en"),
    ("debate", None, "mei", "Seventy-one percent of the pilots were office work. Hospitals can't compress a shift into four days without hiring.", "victor", "neutral", OTHER, ["thinking"], "en"),
    ("debate", None, "mei", "Seventy-one percent of the pilots were office work. Hospitals can't compress a shift into four days without hiring.", "amara", "neutral", OTHER, ["thinking"], "en"),
    ("debate", None, "amara", "I've watched exhausted nurses make mistakes at hour eleven. Rest isn't a perk, it's patient safety.", "victor", "neutral", SAME, ["happy"], "en"),
    ("debate", None, "amara", "I've watched exhausted nurses make mistakes at hour eleven. Rest isn't a perk, it's patient safety.", "mei", "neutral", OTHER, ["thinking", "sad"], "en"),
    ("debate", None, "victor", "With respect, my learned colleague's argument has the structural integrity of wet paper.", "mei", "neutral", OTHER, ["angry"], "en"),
    ("debate", None, "mei", "Victor, cite one study. One. You have adjectives, not evidence.", "victor", "neutral", OTHER, ["thinking", "angry"], "en"),
    ("debate", None, "mei", "On that point, Dr Okafor is right, and I concede it.", "amara", "neutral", OTHER, ["surprised", "happy"], "en"),
    ("debate", None, "victor", "I yield my remaining time to my partner, who has the clinical evidence.", "amara", "neutral", SAME, ["happy"], "en"),
    ("debate", None, "amara", "I'll be honest: I don't know the long-term costs. Nobody does yet.", "victor", "happy", SAME, ["surprised", "thinking"], "en"),
    ("debate", None, "amara", "I'll be honest: I don't know the long-term costs. Nobody does yet.", "mei", "neutral", OTHER, ["happy"], "en"),
    ("debate", None, "victor", "Members of the house, the status quo is also a policy, and it is failing.", "mei", "thinking", OTHER, [N], "en"),
    ("debate", None, "mei", "Thank you, chair. Two minutes, three numbers.", "victor", "neutral", OTHER, [N], "en"),
    ("debate", None, "victor", "Before I begin, a note of thanks to the chair for her patience.", "amara", "neutral", SAME, [N], "en"),
    ("debate", None, "mei", "Victor's last point actually contradicts his opening. Check the record.", "victor", "neutral", OTHER, ["embarrassed", "angry"], "en"),
    ("debate", None, "mei", "Victor's last point actually contradicts his opening. Check the record.", "amara", "neutral", OTHER, ["thinking", "surprised"], "en"),
    ("debate", None, "amara", "Mei, your numbers on burnout are from 2019. The pandemic changed everything.", "mei", "neutral", OTHER, ["thinking"], "en"),
    ("debate", None, "victor", "I was wrong about the pilot size. I misread the table. The point stands.", "mei", "neutral", OTHER, ["surprised", "happy"], "en"),
    ("debate", None, "victor", "I was wrong about the pilot size. I misread the table. The point stands.", "amara", "neutral", SAME, ["surprised"], "en"),
    ("debate", None, "mei", "And with that, I rest. Good debate, both of you.", "victor", "neutral", OTHER, ["happy"], "en"),
    ("debate", None, "victor", "Hujah pihak lawan langsung tak masuk akal.", "mei", "neutral", OTHER, ["angry", "thinking"], "ms"),
    ("debate", None, "amara", "Saya setuju dengan rakan saya, data dia kukuh.", "victor", "neutral", SAME, ["happy"], "ms"),
    ("debate", None, "mei", "这个数据是错的，你引用的是旧版本。", "victor", "neutral", OTHER, ["embarrassed", "thinking"], "zh"),
    ("debate", None, "victor", "With respect, that argument is macam tak cukup bukti lah.", "mei", "neutral", OTHER, ["angry", "thinking"], "mixed"),
    # ── watch (25): the Morisaki family at dinner ──
    ("watch", None, "hana", "Dad, I signed the lease for a second shop! I'm actually doing it!", "takeshi", "neutral", None, ["happy", "surprised"], "en"),
    ("watch", None, "hana", "Dad, I signed the lease for a second shop! I'm actually doing it!", "rin", "neutral", None, ["surprised", "happy"], "en"),
    ("watch", None, "rin", "I quit my job today. Don't make it a thing.", "hana", "neutral", None, ["surprised", "sad"], "en"),
    ("watch", None, "rin", "I quit my job today. Don't make it a thing.", "takeshi", "neutral", None, ["surprised", "thinking"], "en"),
    ("watch", None, "takeshi", "Your mother would have been proud of you both. I don't say it enough.", "hana", "neutral", None, ["sad", "happy"], "en"),
    ("watch", None, "takeshi", "Your mother would have been proud of you both. I don't say it enough.", "rin", "neutral", None, ["embarrassed", "sad"], "en"),
    ("watch", None, "takeshi", "Pass the soy sauce.", "rin", "neutral", None, [N], "en"),
    ("watch", None, "hana", "The rice is a bit dry tonight, sorry.", "takeshi", "neutral", None, [N], "en"),
    ("watch", None, "rin", "Weather's supposed to clear up tomorrow.", "hana", "happy", None, [N], "en"),
    ("watch", None, "takeshi", "Why did the train go to school? To improve its track record.", "rin", "neutral", None, ["angry", "happy"], "en"),
    ("watch", None, "takeshi", "Why did the train go to school? To improve its track record.", "hana", "neutral", None, ["happy"], "en"),
    ("watch", None, "rin", "Hana, you put salt in the tea instead of sugar.", "hana", "neutral", None, ["embarrassed", "surprised"], "en"),
    ("watch", None, "hana", "Rin's game got featured on the indie showcase!", "rin", "neutral", None, ["embarrassed", "happy"], "en"),
    ("watch", None, "hana", "Rin's game got featured on the indie showcase!", "takeshi", "neutral", None, ["happy", "surprised"], "en"),
    ("watch", None, "takeshi", "The doctor wants more tests on my heart. It's probably nothing.", "hana", "happy", None, ["sad", "surprised"], "en"),
    ("watch", None, "takeshi", "The doctor wants more tests on my heart. It's probably nothing.", "rin", "neutral", None, ["sad", "surprised"], "en"),
    ("watch", None, "rin", "I'm going to bed. Night.", "takeshi", "neutral", None, [N], "en"),
    ("watch", None, "hana", "Did anyone see my keys? Again?", "rin", "neutral", None, [N], "en"),
    ("watch", None, "rin", "Dad, I fixed the train set's signal box. It works now.", "takeshi", "neutral", None, ["happy", "surprised"], "en"),
    ("watch", None, "takeshi", "I talked to the neighbour about the noise. Sorted.", "hana", "neutral", None, [N], "en"),
    ("watch", None, "hana", "Ayah, saya nak kahwin!", "takeshi", "neutral", None, ["surprised"], "ms"),
    ("watch", None, "rin", "Hujan lagi. Tak boleh keluar.", "hana", "neutral", None, [N], "ms"),
    ("watch", None, "takeshi", "我明天要去医院复查。", "rin", "neutral", None, ["sad", "thinking"], "zh"),
    ("watch", None, "hana", "我把爸爸最喜欢的杯子打碎了……", "takeshi", "neutral", None, ["sad", "surprised"], "zh"),
    ("watch", None, "rin", "Hana, your cooking today memang sedap. Don't let it go to your head.", "hana", "neutral", None, ["happy", "embarrassed"], "mixed"),
]


def profiles() -> dict[str, dict[str, Any]]:
    return {cid: json.loads((SEED / f"{cid}.json").read_text(encoding="utf-8"))["data"]["profile"] for cid in WHO.values()}


def real(key: str, i: int, speaker: str) -> tuple[str, str]:
    """Turn `i`'s reply by `speaker` and the user's line before it."""
    turn = json.loads((TRANSCRIPTS / f"{SRC[key]}.json").read_text(encoding="utf-8"))["turns"][i]
    text = next(r["text"] for r in turn["replies"] if r["speaker"] == speaker)
    return str(text), f"{USER}: {turn['user']}"


def build() -> list[dict[str, Any]]:
    prof = profiles()
    rows = []
    for n, (mode, ctx, speaker, line, listener, face, side, acceptable, lang) in enumerate(ITEMS, 1):
        sid, lid = WHO[speaker], WHO[listener]
        before = ""
        source = "written"
        if ctx is not None:
            line, before = real(ctx[0], ctx[1], sid)
            source = f"transcript:{SRC[ctx[0]]}#{ctx[1]}"
        assert line is not None
        session = SessionContext(session_id="ses_eval", seed="m9-reactions", world=WorldView(id="w", name="W"),
                                 mode=mode, title="eval", participants=[], recent=[])
        lp = prof[lid]
        lv = ListenerView(id=lid, name=str(lp["name"]), face=face, side_label=side,
                          about_source=str((lp.get("personality") or {}).get("summary") or ""))
        req = ReactionRequest(session=session, message_id=f"msg_r{n}", speaker_id=sid,
                              speaker_name=str(prof[sid]["name"]), line=line, before=before, listeners=[lv],
                              seed=f"m9-reactions:{n}")
        item_id = f"rea-{n:03d}"
        assert all(f in (*FACES, N) for f in acceptable) and 1 <= len(acceptable) <= 2, item_id
        assert face not in acceptable, f"{item_id}: the face now can't be a reaction (it would be none)"
        rows.append({"id": item_id, "question_id": "reaction", "split": split_for(item_id), "lang": lang,
                     "kind": mode, "item": {"state": state(req), "name": str(lp["name"]),
                                             "seed": f"m9-reactions:{n}:react:{lid}"},
                     "label": {"previous": face, "acceptable": acceptable}, "source": source})
    return rows


def check(rows: list[dict[str, Any]]) -> list[str]:
    problems = []
    none_ok = sum(N in r["label"]["acceptable"] for r in rows)
    if none_ok > 27:
        problems.append(f"none acceptable on {none_ok} items (rule: at most 27)")
    kinds = Counter(r["kind"] for r in rows)
    if kinds != Counter({"group": 40, "debate": 25, "watch": 25}):
        problems.append(f"modes {dict(kinds)}")
    if sum(r["lang"] == "en" for r in rows) != 75:
        problems.append("English items must be 75")
    return problems


def main() -> int:
    rows = build()
    problems = check(rows)
    if problems:
        print("\n".join(problems))
        return 1
    out = HERE / "reactions.jsonl"
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8", newline="\n")
    print(f"wrote {len(rows)} items to {out.name}: splits {dict(Counter(r['split'] for r in rows))}, none acceptable "
          f"{sum(N in r['label']['acceptable'] for r in rows)}, languages {dict(Counter(r['lang'] for r in rows))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

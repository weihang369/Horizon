"""Build `reactions.jsonl`: E5's listener-reaction items, one listener each (turn-plan-emotion D18, D26, D27; docs/ai/06
E8; doc 02 B2).

Run from backend/: `uv run python ../evals/datasets/reactions/build.py`. Deterministic. Labels were written blind under
`evals/reviews/m9-labels.md` and its amendment for this fresh set (both committed first), before any Jev answer.
The first set (ids `rea-…`) is in git history; its two runs are recorded in docs/ai/checks/m9.md (9.2).

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
    # ── group (40): real replies that clearly concern the listener, real mild ones, then written lines ──
    ("group", ("sunny", 12), "hana", R, "rin", "neutral", None, ["embarrassed", "angry"], "en"),
    ("group", ("sunny", 22), "rin", R, "hana", "neutral", None, ["embarrassed"], "en"),
    ("group", ("sunny", 38), "takeshi", R, "rin", "neutral", None, ["angry", "embarrassed"], "en"),
    ("group", ("meridian", 46), "mei", R, "victor", "neutral", None, ["embarrassed", "happy"], "en"),
    ("group", ("sunny", 23), "takeshi", R, "hana", "embarrassed", None, ["happy"], "en"),
    ("group", ("sunny", 15), "hana", R, "takeshi", "neutral", None, ["happy"], "en"),
    ("group", ("sunny", 0), "hana", R, "takeshi", "neutral", None, [N], "en"),
    ("group", ("meridian", 29), "victor", R, "mei", "neutral", None, [N], "en"),
    ("group", ("meridian", 43), "mei", R, "victor", "neutral", None, [N], "en"),
    ("group", ("meridian", 21), "amara", R, "victor", "neutral", None, [N], "en"),
    ("group", None, "hana", "Rin, I entered your game in the town festival without asking. It won second place!", "rin", "neutral", None, ["surprised", "happy"], "en"),
    ("group", None, "rin", "Dad, I crashed the van into the shop sign. Sorry.", "takeshi", "neutral", None, ["angry", "surprised"], "en"),
    ("group", None, "takeshi", "Hana, your mother's ring. I want you to have it.", "hana", "neutral", None, ["sad", "happy"], "en"),
    ("group", None, "rin", "Hana's flowers made the mayor cry at the ceremony. In a good way.", "hana", "neutral", None, ["happy", "embarrassed"], "en"),
    ("group", None, "takeshi", "Rin, I read your game reviews. Every one. I'm proud of you.", "rin", "neutral", None, ["embarrassed", "happy"], "en"),
    ("group", None, "hana", "Dad, the doctor called. Your test results are fine!", "takeshi", "thinking", None, ["happy"], "en"),
    ("group", None, "rin", "Hana spilled the whole wedding order across the street this morning.", "hana", "neutral", None, ["embarrassed"], "en"),
    ("group", None, "takeshi", "Pass the rice, please.", "rin", "neutral", None, [N], "en"),
    ("group", None, "hana", "It's warm today.", "rin", "neutral", None, [N], "en"),
    ("group", None, "rin", "brb, charging my phone.", "hana", "happy", None, [N], "en"),
    ("group", None, "takeshi", "The 7:15 was on time again.", "hana", "neutral", None, [N], "en"),
    ("group", None, "mei", "Victor, your closing in the Hale case is being taught at the law school now.", "victor", "neutral", None, ["happy"], "en"),
    ("group", None, "victor", "Amara, your clinic lost its funding. I'm sorry, I just heard.", "amara", "neutral", None, ["sad", "surprised"], "en"),
    ("group", None, "amara", "Mei, you were right about the night-shift data. I was wrong.", "mei", "neutral", None, ["surprised", "happy"], "en"),
    ("group", None, "mei", "Victor, you've had spinach in your teeth since the start of the meeting.", "victor", "neutral", None, ["embarrassed"], "en"),
    ("group", None, "victor", "Mei, your forecast was off by a mile. Again.", "mei", "neutral", None, ["angry", "thinking"], "en"),
    ("group", None, "amara", "Victor, the judge you admired just retired after a scandal.", "victor", "happy", None, ["sad", "surprised"], "en"),
    ("group", None, "mei", "The meeting room is booked till four.", "amara", "neutral", None, [N], "en"),
    ("group", None, "victor", "It's raining on the courthouse steps.", "mei", "neutral", None, [N], "en"),
    ("group", None, "amara", "I'll grab coffee for the table.", "victor", "neutral", None, [N], "en"),
    ("group", None, "mei", "Amara, the hospital is naming the new ward after you.", "amara", "neutral", None, ["surprised", "embarrassed"], "en"),
    ("group", None, "victor", "Mei, I'll admit it: that was an elegant model.", "mei", "neutral", None, ["happy"], "en"),
    ("group", None, "hana", "Rin, someone hacked your streaming account and posted nonsense all night.", "rin", "neutral", None, ["angry", "surprised"], "en"),
    ("group", None, "takeshi", "Hana, I fixed your shop door myself. No charge.", "hana", "neutral", None, ["happy"], "en"),
    ("group", None, "hana", "Rin, Ayah dah tahu awak yang pecahkan pasu tu.", "rin", "neutral", None, ["embarrassed", "surprised"], "ms"),
    ("group", None, "takeshi", "Hana, kedai bunga awak menang anugerah bandar!", "hana", "neutral", None, ["happy", "surprised"], "ms"),
    ("group", None, "rin", "Hujan lagi petang ni.", "takeshi", "neutral", None, [N], "ms"),
    ("group", None, "mei", "维克多，你的论文被期刊拒了。", "victor", "neutral", None, ["sad", "angry"], "zh"),
    ("group", None, "amara", "梅，谢谢你昨晚帮我值班。", "mei", "neutral", None, ["happy", "embarrassed"], "zh"),
    ("group", None, "hana", "Dad, your old train models jatuh semua, sorry sangat!", "takeshi", "neutral", None, ["sad", "surprised"], "mixed"),
    # ── debate (25): "This house would adopt a four-day work week." Victor and Amara propose; Mei opposes ──
    ("debate", None, "victor", "Dr Tanaka-Ruiz, your own 2019 paper argued the opposite. Shall I read it aloud?", "mei", "neutral", OTHER, ["embarrassed", "angry"], "en"),
    ("debate", None, "victor", "Dr Tanaka-Ruiz, your own 2019 paper argued the opposite. Shall I read it aloud?", "amara", "neutral", SAME, ["happy", "surprised"], "en"),
    ("debate", None, "mei", "Mr Hale, that is the third time tonight you've confused correlation with causation.", "victor", "neutral", OTHER, ["angry", "embarrassed"], "en"),
    ("debate", None, "mei", "Dr Okafor's ward data is the strongest evidence in this room, and it supports my side.", "amara", "neutral", OTHER, ["surprised", "thinking"], "en"),
    ("debate", None, "amara", "Victor, you just misquoted my numbers. It's eleven hours, not eight.", "victor", "neutral", SAME, ["embarrassed"], "en"),
    ("debate", None, "mei", "I concede. The proposition has the better case on hospitals.", "victor", "neutral", OTHER, ["happy", "surprised"], "en"),
    ("debate", None, "mei", "I concede. The proposition has the better case on hospitals.", "amara", "neutral", OTHER, ["happy", "surprised"], "en"),
    ("debate", None, "victor", "My opponent walked out of last year's debate. Let's hope she stays tonight.", "mei", "neutral", OTHER, ["angry"], "en"),
    ("debate", None, "amara", "Mei, a nurse on my ward died driving home after a double shift.", "mei", "neutral", OTHER, ["sad"], "en"),
    ("debate", None, "victor", "Thank you, chair.", "mei", "neutral", OTHER, [N], "en"),
    ("debate", None, "mei", "Two minutes, three numbers.", "victor", "neutral", OTHER, [N], "en"),
    ("debate", None, "amara", "Shift patterns vary a lot across sectors.", "victor", "neutral", SAME, [N], "en"),
    ("debate", None, "victor", "The status quo is also a policy.", "amara", "neutral", SAME, [N], "en"),
    ("debate", None, "mei", "The productivity data from the pilots is mixed.", "amara", "thinking", OTHER, [N], "en"),
    ("debate", None, "amara", "Rest improves accuracy in clinical settings.", "mei", "neutral", OTHER, [N], "en"),
    ("debate", None, "victor", "I yield the floor.", "amara", "neutral", SAME, [N], "en"),
    ("debate", None, "mei", "Victor, you're out of time. Sit down.", "victor", "neutral", OTHER, ["angry", "embarrassed"], "en"),
    ("debate", None, "victor", "Amara, that was the finest closing I've heard in years.", "amara", "neutral", SAME, ["happy", "embarrassed"], "en"),
    ("debate", None, "mei", "Amara, I'm sorry. I didn't know about your nurse.", "amara", "neutral", OTHER, ["sad"], "en"),
    ("debate", None, "amara", "Mei, your mother was a nurse too, wasn't she? You know this.", "mei", "neutral", OTHER, ["sad", "thinking"], "en"),
    ("debate", None, "victor", "The house has voted: the proposition carries it.", "mei", "neutral", OTHER, ["sad", "angry"], "en"),
    ("debate", None, "mei", "Hujah awak lemah, Victor. Sangat lemah.", "victor", "neutral", OTHER, ["angry", "thinking"], "ms"),
    ("debate", None, "amara", "Terima kasih, pengerusi.", "victor", "neutral", SAME, [N], "ms"),
    ("debate", None, "victor", "梅，你的数据是编造的吗？", "mei", "neutral", OTHER, ["angry"], "zh"),
    ("debate", None, "amara", "Victor, you were brilliant tadi, seriously.", "victor", "neutral", SAME, ["happy"], "mixed"),
    # ── watch (25): the Morisaki family at dinner ──
    ("watch", None, "hana", "Dad, I'm pregnant.", "takeshi", "neutral", None, ["surprised", "happy"], "en"),
    ("watch", None, "hana", "Dad, I'm pregnant.", "rin", "neutral", None, ["surprised"], "en"),
    ("watch", None, "rin", "I got into the game studio in Tokyo. I leave in a month.", "hana", "neutral", None, ["surprised", "sad"], "en"),
    ("watch", None, "rin", "I got into the game studio in Tokyo. I leave in a month.", "takeshi", "neutral", None, ["surprised", "happy"], "en"),
    ("watch", None, "takeshi", "I sold the boat today.", "rin", "neutral", None, ["surprised", "sad"], "en"),
    ("watch", None, "takeshi", "Rin, you look just like your mother when you laugh.", "rin", "neutral", None, ["embarrassed", "sad"], "en"),
    ("watch", None, "rin", "Hana burned the rice again.", "hana", "neutral", None, ["embarrassed"], "en"),
    ("watch", None, "hana", "Rin finally cleaned her room. It only took three years.", "rin", "neutral", None, ["embarrassed", "angry"], "en"),
    ("watch", None, "takeshi", "Why don't trains ever get lost? They stay on track.", "rin", "neutral", None, ["angry", "happy"], "en"),
    ("watch", None, "takeshi", "Why don't trains ever get lost? They stay on track.", "hana", "neutral", None, ["happy"], "en"),
    ("watch", None, "rin", "Pass the soy sauce.", "hana", "neutral", None, [N], "en"),
    ("watch", None, "hana", "More tea, anyone?", "takeshi", "neutral", None, [N], "en"),
    ("watch", None, "takeshi", "The forecast says rain tomorrow.", "rin", "neutral", None, [N], "en"),
    ("watch", None, "rin", "The neighbour's cat is back on the wall.", "takeshi", "neutral", None, [N], "en"),
    ("watch", None, "hana", "Dad, the bank called. The shop loan is approved!", "takeshi", "neutral", None, ["happy"], "en"),
    ("watch", None, "takeshi", "Hana, I forgot your birthday. I'm sorry.", "hana", "neutral", None, ["sad", "surprised"], "en"),
    ("watch", None, "rin", "Dad snores louder than the trains he used to drive.", "takeshi", "neutral", None, ["embarrassed", "angry"], "en"),
    ("watch", None, "hana", "Rin, your stream hit ten thousand viewers tonight!", "rin", "neutral", None, ["happy", "surprised"], "en"),
    ("watch", None, "takeshi", "I'm going to bed. Night.", "hana", "neutral", None, [N], "en"),
    ("watch", None, "rin", "Is there more rice?", "hana", "neutral", None, [N], "en"),
    ("watch", None, "hana", "Ayah, saya nak buka kedai kedua!", "takeshi", "neutral", None, ["happy", "surprised"], "ms"),
    ("watch", None, "rin", "Nasi ni dah sejuk.", "hana", "neutral", None, [N], "ms"),
    ("watch", None, "takeshi", "医生说我需要做手术。", "hana", "neutral", None, ["sad", "surprised"], "zh"),
    ("watch", None, "rin", "姐姐，你做的菜太咸了。", "hana", "neutral", None, ["embarrassed"], "zh"),
    ("watch", None, "hana", "Dad, your pun tadi tu memang the worst, but I laughed.", "takeshi", "neutral", None, ["happy"], "mixed"),
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
        item_id = f"rea2-{n:03d}"   # the fresh set (m9.md 9.2): new ids, new splits, labelled blind
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

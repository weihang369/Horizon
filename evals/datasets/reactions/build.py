"""Build `reactions.jsonl`: E5's listener-reaction items, one listener each (turn-plan-emotion D18, D26, D27; docs/ai/06
E8; doc 02 B2).

Run from backend/: `uv run python ../evals/datasets/reactions/build.py`. Deterministic. M15 (images-music 8.13, D16):
the third set (ids `rea3-…`), for `reaction` v3, written and labelled blind under `evals/reviews/m15-reactions-labels.md`
(committed first), before any Jev answer. The first two sets (`rea-…`, `rea2-…`, labelled under
`evals/reviews/m9-labels.md`) are in git history; their runs are recorded in docs/ai/checks/m9.md (9.2).

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
    # ── M15 (images-music 8.13, D16): the third set, `rea3`, written and labelled blind before any Jev answer under
    # evals/reviews/m15-reactions-labels.md (committed first). Same mix as rea2: group 40, debate 25, watch 25; 75
    # English; `none` acceptable on 27. ──
    # ── group (40) ──
    ("group", None, "hana", "Rin, I told Dad you were the one who fixed the shop's card reader. He wants to thank you.", "rin", "neutral", None, ["embarrassed", "happy"], "en"),
    ("group", None, "rin", "Hana, your sunflowers are on the front page of the town paper.", "hana", "neutral", None, ["surprised", "happy"], "en"),
    ("group", None, "takeshi", "Rin, you left the stove on again. The whole kitchen smelled of burnt rice.", "rin", "neutral", None, ["embarrassed", "angry"], "en"),
    ("group", None, "hana", "Dad, I sold the old fishing boat to pay for the new greenhouse.", "takeshi", "neutral", None, ["surprised", "angry"], "en"),
    ("group", None, "rin", "Dad, the train museum is closing next month. They announced it today.", "takeshi", "happy", None, ["sad", "surprised"], "en"),
    ("group", None, "takeshi", "Hana, the frost got your tulip bulbs last night. All of them.", "hana", "neutral", None, ["sad"], "en"),
    ("group", None, "mei", "Victor, your old student just quoted your closing argument on the radio.", "victor", "neutral", None, ["happy", "surprised"], "en"),
    ("group", None, "victor", "Mei, your forecast was off by three points, and the minister mentioned your name.", "mei", "neutral", None, ["embarrassed", "angry"], "en"),
    ("group", None, "amara", "Mei, you've been at the office until midnight all week. That can't go on.", "mei", "neutral", None, ["embarrassed", "thinking"], "en"),
    ("group", None, "mei", "Amara, the night shift sent you a cake. They signed it 'to our favourite doctor'.", "amara", "neutral", None, ["happy", "embarrassed"], "en"),
    ("group", None, "victor", "Amara, you were right about the ward staffing. I owe you an apology.", "amara", "thinking", None, ["happy", "surprised"], "en"),
    ("group", None, "amara", "Victor, someone keyed your car in the hospital car park.", "victor", "neutral", None, ["angry", "sad"], "en"),
    ("group", None, "hana", "Rin, I accidentally deleted your save file when I cleaned the computer.", "rin", "neutral", None, ["angry", "sad"], "en"),
    ("group", None, "rin", "Hana, Mom's old recipe book was in the attic all along.", "hana", "neutral", None, ["surprised", "happy"], "en"),
    ("group", None, "takeshi", "Rin, your cousin called. She's coming to stay for the whole summer.", "rin", "sad", None, ["happy", "surprised"], "en"),
    ("group", None, "mei", "Victor, is a promise still binding once the person you made it to has died?", "victor", "neutral", None, ["thinking"], "en"),
    ("group", None, "amara", "Mei, would you still choose economics if you could start over?", "mei", "neutral", None, ["thinking"], "en"),
    ("group", None, "hana", "Dad, do you ever miss driving the night trains?", "takeshi", "neutral", None, ["thinking", "sad"], "en"),
    ("group", None, "rin", "Dad, I got the job at the studio in the city.", "takeshi", "neutral", None, ["happy", "surprised"], "en"),
    ("group", None, "victor", "Mei, you misquoted the census figures in your paper. Page four.", "mei", "neutral", None, ["embarrassed"], "en"),
    ("group", None, "hana", "The bakery opens at seven tomorrow.", "rin", "neutral", None, [N], "en"),
    ("group", None, "takeshi", "Pass the soy sauce, please.", "hana", "neutral", None, [N], "en"),
    ("group", None, "rin", "It's supposed to rain again on Thursday.", "takeshi", "neutral", None, [N], "en"),
    ("group", None, "mei", "The meeting room on the third floor is free after lunch.", "amara", "neutral", None, [N], "en"),
    ("group", None, "victor", "The bus from the square runs every twenty minutes.", "mei", "neutral", None, [N], "en"),
    ("group", None, "amara", "I'll take the stairs, the lift is slow.", "victor", "neutral", None, [N], "en"),
    ("group", None, "hana", "I watered the plants by the door.", "takeshi", "happy", None, [N], "en"),
    ("group", None, "rin", "I'm getting more tea. Anyone else?", "hana", "neutral", None, [N], "en"),
    ("group", None, "mei", "The library closes early on Sundays.", "victor", "thinking", None, [N], "en"),
    ("group", None, "amara", "Kai, the soup's still warm if you want some.", "mei", "neutral", None, [N], "en"),
    ("group", None, "takeshi", "Rin, I framed the drawing you made when you were six. It's up in the shop.", "rin", "neutral", None, ["embarrassed", "happy"], "en"),
    ("group", None, "hana", "Rin, you were so brave at the hospital yesterday. I'm proud of you.", "rin", "neutral", None, ["embarrassed", "happy"], "en"),
    ("group", None, "victor", "Amara, the board voted to close your ward.", "amara", "neutral", None, ["angry", "sad"], "en"),
    ("group", None, "mei", "Victor, they've asked you to lead the inquiry. Unanimously.", "victor", "neutral", None, ["surprised", "happy"], "en"),
    ("group", None, "hana", "Rin, kucing kita dah balik! Dia tidur atas katil kau sekarang.", "rin", "neutral", None, ["happy", "surprised"], "ms"),
    ("group", None, "takeshi", "Hana, kedai bunga sebelah tutup selamanya minggu depan.", "hana", "neutral", None, ["sad", "surprised"], "ms"),
    ("group", None, "rin", "爸，我把你的钓竿弄断了。对不起。", "takeshi", "neutral", None, ["angry", "sad"], "zh"),
    ("group", None, "mei", "明天早上开会的房间在三楼。", "amara", "neutral", None, [N], "zh"),
    ("group", None, "amara", "ビクター、あなたの昔の教え子が判事に任命されたわ。", "victor", "neutral", None, ["happy", "surprised"], "ja"),
    ("group", None, "victor", "Mei, laporan awak dipetik oleh menteri dalam ucapannya pagi tadi.", "mei", "neutral", None, ["surprised", "happy"], "ms"),
    # ── debate (25): the Meridian panel ──
    ("debate", None, "victor", "My opponent's own data shows the pilot failed in two of three wards.", "mei", "neutral", OTHER, ["angry", "thinking"], "en"),
    ("debate", None, "mei", "Mr. Hale has quoted a study that was retracted last year.", "victor", "neutral", OTHER, ["embarrassed", "angry"], "en"),
    ("debate", None, "amara", "Mei made the strongest point tonight: the costs fall on the youngest workers.", "mei", "neutral", SAME, ["happy", "embarrassed"], "en"),
    ("debate", None, "victor", "Dr. Okafor, you treated patients for twenty years. Did a single one benefit from longer shifts?", "amara", "neutral", OTHER, ["thinking", "angry"], "en"),
    ("debate", None, "mei", "My opponent is a doctor, not an economist, and it shows.", "amara", "neutral", OTHER, ["angry"], "en"),
    ("debate", None, "amara", "Mr. Hale, your own firm moved to a four-day week in March. Did you know?", "victor", "neutral", OTHER, ["surprised", "embarrassed"], "en"),
    ("debate", None, "victor", "I hand the floor to my colleague, whose figures are better than mine.", "mei", "neutral", SAME, ["happy", "embarrassed"], "en"),
    ("debate", None, "mei", "The question is simple: who pays for the gap in coverage? He hasn't said.", "victor", "thinking", OTHER, ["angry"], "en"),
    ("debate", None, "amara", "Ms. Lin's model ignores every nurse I have ever worked with.", "mei", "neutral", OTHER, ["angry", "thinking"], "en"),
    ("debate", None, "victor", "The evidence my opponent cites is from a single hospital in a single winter.", "amara", "neutral", OTHER, ["thinking", "angry"], "en"),
    ("debate", None, "mei", "Dr. Okafor, thank you, that's exactly the case I wanted to make.", "amara", "neutral", SAME, ["happy"], "en"),
    ("debate", None, "victor", "If my opponent is right, why did her own ministry reject the proposal?", "mei", "neutral", OTHER, ["thinking", "angry"], "en"),
    ("debate", None, "amara", "I'd like to hear Mr. Hale explain why the law changed in 1931 at all.", "victor", "neutral", OTHER, ["thinking"], "en"),
    ("debate", None, "mei", "Dr. Okafor's patients are the reason I took this side tonight.", "amara", "neutral", SAME, ["happy", "embarrassed"], "en"),
    ("debate", None, "victor", "Thank you, chair. I'll take my three minutes now.", "mei", "neutral", OTHER, [N], "en"),
    ("debate", None, "mei", "Let me start with the numbers from the pilot.", "amara", "neutral", SAME, [N], "en"),
    ("debate", None, "amara", "I'll keep this short, as the chair asked.", "victor", "neutral", OTHER, [N], "en"),
    ("debate", None, "victor", "My second point concerns the transition period.", "amara", "neutral", OTHER, [N], "en"),
    ("debate", None, "mei", "The pilot ran for six months across fourteen employers.", "victor", "neutral", OTHER, [N], "en"),
    ("debate", None, "amara", "Thank you to the chair and to everyone who came tonight.", "mei", "neutral", SAME, [N], "en"),
    ("debate", None, "victor", "I'll return to that question in my closing.", "mei", "neutral", OTHER, [N], "en"),
    ("debate", None, "victor", "Lawan saya sendiri mengaku angka itu tidak lengkap.", "mei", "neutral", OTHER, ["angry", "embarrassed"], "ms"),
    ("debate", None, "mei", "对方辩友引用的研究去年已经被撤回了。", "victor", "neutral", OTHER, ["embarrassed", "angry"], "zh"),
    ("debate", None, "amara", "メイさんの指摘が今夜いちばん鋭かったと思います。", "mei", "neutral", SAME, ["happy", "embarrassed"], "ja"),
    ("debate", None, "victor", "Terima kasih, pengerusi. Saya akan mulakan sekarang.", "amara", "neutral", OTHER, [N], "ms"),
    # ── watch (25): scenes in both worlds ──
    ("watch", None, "rin", "Hana, don't move. There's a snake right by your foot.", "hana", "neutral", None, ["surprised"], "en"),
    ("watch", None, "takeshi", "The bridge is out. We're not getting home tonight.", "rin", "neutral", None, ["surprised", "sad"], "en"),
    ("watch", None, "hana", "Dad, I found Mom's letters in the lighthouse. She wrote to you every week.", "takeshi", "neutral", None, ["sad", "surprised"], "en"),
    ("watch", None, "amara", "Mei, the patient you brought in is going to make it.", "mei", "neutral", None, ["happy"], "en"),
    ("watch", None, "victor", "Doctor, the generator just failed. The whole ward is dark.", "amara", "neutral", None, ["surprised"], "en"),
    ("watch", None, "mei", "Victor, the jury came back. Not guilty.", "victor", "neutral", None, ["happy", "surprised"], "en"),
    ("watch", None, "rin", "Dad, the storm took the roof off the boat shed.", "takeshi", "neutral", None, ["sad", "angry"], "en"),
    ("watch", None, "hana", "Rin, the festival judges picked your lantern for first prize!", "rin", "neutral", None, ["happy", "surprised"], "en"),
    ("watch", None, "takeshi", "Hana, someone left a bouquet at the door with your name on it. No card.", "hana", "neutral", None, ["surprised", "thinking"], "en"),
    ("watch", None, "amara", "Victor, the key witness has changed her story.", "victor", "neutral", None, ["surprised", "thinking"], "en"),
    ("watch", None, "mei", "Amara, who signed the order to move the patients? Nobody remembers.", "amara", "neutral", None, ["thinking"], "en"),
    ("watch", None, "victor", "Mei, you left the case files on the train.", "mei", "neutral", None, ["embarrassed"], "en"),
    ("watch", None, "rin", "Hana, the greenhouse glass is cracked all along the north side.", "hana", "happy", None, ["sad", "surprised"], "en"),
    ("watch", None, "takeshi", "The tide turns in about an hour.", "rin", "neutral", None, [N], "en"),
    ("watch", None, "hana", "I'll light the lamp in the hall.", "takeshi", "neutral", None, [N], "en"),
    ("watch", None, "mei", "The courtroom is on the second floor.", "victor", "neutral", None, [N], "en"),
    ("watch", None, "amara", "I'll write up the notes after lunch.", "mei", "neutral", None, [N], "en"),
    ("watch", None, "victor", "The car is parked by the gate.", "amara", "neutral", None, [N], "en"),
    ("watch", None, "rin", "I'm going to check the map again.", "takeshi", "neutral", None, [N], "en"),
    ("watch", None, "takeshi", "The kettle's on.", "hana", "thinking", None, [N], "en"),
    ("watch", None, "hana", "Rin, lampu rumah api dah padam sendiri!", "rin", "neutral", None, ["surprised"], "ms"),
    ("watch", None, "takeshi", "花，你妈妈的花园里又开花了。", "hana", "neutral", None, ["happy", "sad"], "zh"),
    ("watch", None, "mei", "ビクター、評決が出たわ。無罪よ。", "victor", "neutral", None, ["happy", "surprised"], "ja"),
    ("watch", None, "amara", "Nota itu saya tulis selepas makan tengah hari.", "mei", "neutral", None, [N], "ms"),
    ("watch", None, "rin", "爸，我们的船被偷了。", "takeshi", "neutral", None, ["angry", "surprised"], "zh"),
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
        session = SessionContext(session_id="ses_eval", seed="m15-reactions", world=WorldView(id="w", name="W"),
                                 mode=mode, title="eval", participants=[], recent=[])
        lp = prof[lid]
        lv = ListenerView(id=lid, name=str(lp["name"]), face=face, side_label=side,
                          about_source=str((lp.get("personality") or {}).get("summary") or ""))
        req = ReactionRequest(session=session, message_id=f"msg_r{n}", speaker_id=sid,
                              speaker_name=str(prof[sid]["name"]), line=line, before=before, listeners=[lv],
                              seed=f"m15-reactions:{n}")
        item_id = f"rea3-{n:03d}"   # M15 (8.13): the third set, new ids and splits, labelled blind
        assert all(f in (*FACES, N) for f in acceptable) and 1 <= len(acceptable) <= 2, item_id
        assert face not in acceptable, f"{item_id}: the face now can't be a reaction (it would be none)"
        rows.append({"id": item_id, "question_id": "reaction", "split": split_for(item_id), "lang": lang,
                     "kind": mode, "item": {"state": state(req), "name": str(lp["name"]),
                                             "seed": f"m15-reactions:{n}:react:{lid}"},
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

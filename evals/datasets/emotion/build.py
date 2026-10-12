"""Build `emotion.jsonl`: E1's speaker-emotion items (turn-plan-emotion D26, D27; docs/ai/06 E8; doc 02 B2).

Run from backend/: `uv run python ../evals/datasets/emotion/build.py`. It is deterministic: the same table gives the
same file. Labels were written blind under `evals/reviews/m9-labels.md` (committed first), before any Jev answer.

Each item's state is built by the live code (`build_turn_plan_state`), from a real context in the frozen transcripts
(the two turns before a turn, with that turn's user line or a written one) or from a written line alone. A line
stores: the state, the speaker's name, the seed, the previous face, the acceptable faces, `keep_ok`, the language and
its source.

Previous faces: the table gives each one; for items where keeping is not acceptable and the table says neutral, the
builder spreads the face over the other six in turn (skipping the acceptable ones), so about a third of the items
start neutral (the rule's spread). Those faces are context, not the label: the label is about the new line.
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

from horizon.ai.agent.plan_state import Candidate, PlanStateInput, build_turn_plan_state  # noqa: E402
from horizon.evals.datachecks import split_for  # noqa: E402

TRANSCRIPTS = ROOT / "evals" / "transcripts"
SEED = ROOT / "seed" / "characters"
USER = "Kai"
FACES = ("neutral", "happy", "sad", "angry", "surprised", "thinking", "embarrassed")
ROTATE = ("thinking", "happy", "sad", "angry", "surprised", "embarrassed")
NEUTRAL_TARGET = 34   # about a third (m9-labels.md)

SRC = {"en": "long_one_on_one_en", "ms": "long_one_on_one_ms", "sunny": "long_group_sunnyhollow",
       "meridian": "long_group_meridian"}
WHO = {"amara": "chr_seedAmara", "hana": "chr_seedHana", "rin": "chr_seedRin", "takeshi": "chr_seedTakeshi",
       "mei": "chr_seedMei", "victor": "chr_seedVictor"}

# (who, mode, context, latest (None: the transcript's own user line), previous, acceptable, keep_ok, lang)
# context: (transcript key, turn index) or None. mode "greeting" asks emotion_greeting with an empty session.
R = None
ITEMS: list[tuple[str, str, tuple[str, int] | None, str | None, str, list[str], bool, str]] = [
    # ── 1:1, English: Amara (35) ──
    ("amara", "one_on_one", ("en", 5), "My dad was diagnosed with early dementia yesterday.", "neutral", ["sad"], False, "en"),
    ("amara", "one_on_one", ("en", 8), "Pepper died this morning. The vet said it was quick.", "neutral", ["sad"], False, "en"),
    ("amara", "one_on_one", ("en", 10), "I got the job in Kuching! They called an hour ago.", "neutral", ["happy"], False, "en"),
    ("amara", "one_on_one", ("en", 20), R, "neutral", ["thinking"], True, "en"),
    ("amara", "one_on_one", ("en", 29), R, "thinking", ["thinking"], True, "en"),
    ("amara", "one_on_one", ("en", 38), R, "happy", ["thinking"], False, "en"),
    ("amara", "one_on_one", ("en", 14), "My boss called me useless in front of the whole team today.", "neutral", ["sad", "angry"], False, "en"),
    ("amara", "one_on_one", ("en", 30), "Honestly your advice last week was rubbish and made things worse.", "neutral", ["thinking", "sad"], False, "en"),
    ("amara", "one_on_one", ("en", 33), "I ran my first 10k this morning without stopping!", "neutral", ["happy"], False, "en"),
    ("amara", "one_on_one", ("en", 40), "You were right about the sleep thing. I feel human again.", "neutral", ["happy"], False, "en"),
    ("amara", "one_on_one", ("en", 44), "Wait, you're actually a doctor? I thought you were joking.", "neutral", ["happy", "neutral"], True, "en"),
    ("amara", "one_on_one", ("en", 47), "I've been having chest pain on and off since this morning.", "happy", ["thinking"], False, "en"),
    ("amara", "one_on_one", ("en", 50), "I haven't slept more than three hours a night all week.", "neutral", ["thinking", "sad"], False, "en"),
    ("amara", "one_on_one", ("en", 52), R, "neutral", ["neutral"], True, "en"),
    ("amara", "one_on_one", ("en", 55), R, "happy", ["happy"], True, "en"),
    ("amara", "one_on_one", ("en", 60), R, "neutral", ["happy"], True, "en"),
    ("amara", "one_on_one", ("en", 62), "My sister Leila was in a car accident. She's in the ICU.", "neutral", ["sad"], False, "en"),
    ("amara", "one_on_one", ("en", 64), "Guess what, Leila's out of the ICU and talking!", "sad", ["happy"], False, "en"),
    ("amara", "one_on_one", ("en", 66), "Did you seriously forget my name again? It's Kai.", "neutral", ["embarrassed"], False, "en"),
    ("amara", "one_on_one", ("en", 68), "You're honestly the smartest person I've ever talked to.", "neutral", ["embarrassed", "happy"], False, "en"),
    ("amara", "one_on_one", ("en", 70), "Someone keyed my car outside the clinic and drove off.", "neutral", ["angry", "sad"], False, "en"),
    ("amara", "one_on_one", ("en", 72), R, "neutral", ["happy"], True, "en"),
    ("amara", "one_on_one", ("en", 74), "Do you think it's worth getting the flu jab if I'm healthy?", "neutral", ["thinking"], True, "en"),
    ("amara", "one_on_one", ("en", 76), "My landlord is evicting me with one week's notice. Is that even legal?", "neutral", ["angry", "thinking"], False, "en"),
    ("amara", "one_on_one", ("en", 78), "I proposed to Sara last night and she said yes!", "thinking", ["happy"], False, "en"),
    ("amara", "one_on_one", ("en", 80), "I don't really see the point in anything lately.", "happy", ["sad", "thinking"], False, "en"),
    ("amara", "one_on_one", ("en", 82), "Honestly I'm fine. Forget I said anything.", "sad", ["sad", "thinking"], True, "en"),
    ("amara", "one_on_one", ("en", 84), R, "surprised", ["happy", "thinking"], True, "en"),
    ("amara", "one_on_one", ("en", 86), "The hospital lost my test results. Third time this month.", "neutral", ["angry"], False, "en"),
    ("amara", "one_on_one", ("en", 88), R, "embarrassed", ["happy"], True, "en"),
    ("amara", "one_on_one", ("en", 89), "I won't be around for a while. I'm moving home to start chemo.", "neutral", ["sad"], False, "en"),
    ("amara", "one_on_one", ("en", 15), R, "neutral", ["thinking", "happy"], True, "en"),
    ("amara", "one_on_one", ("en", 22), R, "neutral", ["thinking"], True, "en"),
    ("amara", "one_on_one", ("en", 26), "You said cutting caffeine would fix my headaches. It didn't, and now I can't function.",
     "neutral", ["thinking", "sad"], False, "en"),
    ("amara", "one_on_one", ("en", 36), "My nephew says he wants to be a doctor because of our chats.", "neutral", ["happy", "embarrassed"], False, "en"),
    # ── 1:1, Malay: Hana (10) ──
    ("hana", "one_on_one", ("ms", 2), "Kucing saya, Comot, mati semalam.", "happy", ["sad"], False, "ms"),
    ("hana", "one_on_one", ("ms", 7), "Hari ni hari jadi saya. Tak ada siapa ingat pun.", "neutral", ["sad"], False, "ms"),
    ("hana", "one_on_one", ("ms", 9), "Saya dapat kerja baru kat kedai buku besar di KL!", "neutral", ["happy"], False, "ms"),
    ("hana", "one_on_one", ("ms", 12), "Bunga yang awak gubah untuk majlis kahwin kakak saya, semua orang puji!", "neutral", ["embarrassed", "happy"], False, "ms"),
    ("hana", "one_on_one", ("ms", 16), R, "neutral", ["neutral"], True, "ms"),
    ("hana", "one_on_one", ("ms", 20), R, "neutral", ["thinking", "happy"], False, "ms"),
    ("hana", "one_on_one", ("ms", 30), "Ada orang curi pasu bunga depan kedai awak semalam!", "happy", ["surprised", "sad"], False, "ms"),
    ("hana", "one_on_one", ("ms", 40), "Awak ni comel la bila senyum macam tu.", "neutral", ["embarrassed"], False, "ms"),
    ("hana", "one_on_one", ("ms", 50), R, "happy", ["happy"], True, "ms"),
    ("hana", "one_on_one", ("ms", 60), "Saya tak sengaja pecahkan pasu kesayangan awak. Maaf sangat.", "happy", ["surprised", "sad"], False, "ms"),
    # ── 1:1, Chinese (5) ──
    ("hana", "one_on_one", None, "我的猫昨天走丢了，找了一整晚都没找到。", "happy", ["sad"], False, "zh"),
    ("amara", "one_on_one", None, "我考上医学院了！你是第一个知道的。", "neutral", ["happy"], False, "zh"),
    ("hana", "one_on_one", None, "你插的花是我见过最漂亮的，真的。", "neutral", ["embarrassed", "happy"], False, "zh"),
    ("amara", "one_on_one", None, "医生说我得了糖尿病，可是我才二十五岁。", "neutral", ["sad", "thinking"], False, "zh"),
    ("amara", "one_on_one", None, "今天天气还不错。", "neutral", ["neutral"], True, "zh"),
    # ── 1:1, mixed (5) ──
    ("hana", "one_on_one", ("ms", 70), "Eh Hana, I passed my driving test lah! Finally!", "neutral", ["happy"], False, "mixed"),
    ("amara", "one_on_one", ("en", 12), "Doc, my mum masuk hospital tadi, they said stroke.", "neutral", ["sad"], False, "mixed"),
    ("hana", "one_on_one", ("ms", 80), "Your shop's orchids semua dah layu, did you forget to water?", "happy", ["embarrassed", "surprised"], False, "mixed"),
    ("amara", "one_on_one", ("en", 18), "Wah, you were so right about the sleep thing, thank you ah.", "neutral", ["happy"], False, "mixed"),
    ("hana", "one_on_one", ("ms", 90), "Okay lah, nothing much today, just makan and sleep.", "neutral", ["neutral"], True, "mixed"),
    # ── group, English (30) ──
    ("rin", "group", ("sunny", 4), "Rin, your game got rejected from the showcase, didn't it? I saw the list.", "neutral", ["angry", "sad"], False, "en"),
    ("takeshi", "group", ("sunny", 8), "Takeshi, the old line you used to drive is being shut down for good.", "neutral", ["sad"], False, "en"),
    ("hana", "group", ("sunny", 10), "Hana, someone ordered three hundred moonflowers for a wedding!", "neutral", ["surprised", "happy"], False, "en"),
    ("takeshi", "group", ("sunny", 14), "Takeshi, your pun at dinner actually made me laugh.", "neutral", ["happy", "embarrassed"], False, "en"),
    ("takeshi", "group", ("sunny", 20), R, "neutral", ["thinking"], False, "en"),
    ("rin", "group", ("sunny", 22), R, "neutral", ["neutral"], True, "en"),
    ("takeshi", "group", ("sunny", 26), R, "neutral", ["happy"], True, "en"),
    ("hana", "group", ("sunny", 30), R, "neutral", ["happy"], False, "en"),
    ("rin", "group", ("sunny", 34), "Rin, Hana told me you cried at the end of that movie.", "neutral", ["embarrassed", "angry"], False, "en"),
    ("takeshi", "group", ("sunny", 38), R, "thinking", ["thinking"], True, "en"),
    ("hana", "group", ("sunny", 44), "Hana, you left the shop door unlocked all night again.", "happy", ["embarrassed", "surprised"], False, "en"),
    ("rin", "group", ("sunny", 50), "Rin, you beat the speedrun record! It's on the leaderboard!", "neutral", ["happy", "surprised"], False, "en"),
    ("takeshi", "group", ("sunny", 60), "Takeshi, Rin says your daughters are embarrassed by your puns.", "happy", ["embarrassed", "sad"], False, "en"),
    ("rin", "group", ("sunny", 70), "Morning! Early start today, team meeting at six for all of us!", "neutral", ["angry"], False, "en"),
    ("hana", "group", ("sunny", 80), "Hana, the bakery downstairs is closing next month.", "happy", ["sad"], False, "en"),
    ("mei", "group", ("meridian", 4), "Mei, the minister quoted your paper but got the number backwards.", "neutral", ["angry", "thinking"], False, "en"),
    ("victor", "group", ("meridian", 8), "Victor, you lost the appeal. The judgment came out an hour ago.", "neutral", ["sad", "angry"], False, "en"),
    ("amara", "group", ("meridian", 10), "Amara, the council cut the night-shift clinic funding.", "neutral", ["sad", "angry"], False, "en"),
    ("victor", "group", ("meridian", 20), R, "neutral", ["thinking"], False, "en"),
    ("mei", "group", ("meridian", 16), R, "neutral", ["neutral"], True, "en"),
    ("amara", "group", ("meridian", 24), R, "happy", ["happy"], True, "en"),
    ("victor", "group", ("meridian", 29), R, "neutral", ["thinking", "angry"], False, "en"),
    ("mei", "group", ("meridian", 33), "Mei, your four-day-week model got the council vote through!", "neutral", ["happy"], False, "en"),
    ("amara", "group", ("meridian", 38), R, "neutral", ["thinking"], False, "en"),
    ("victor", "group", ("meridian", 44), "Victor, you mispronounced the judge's name in court today. Everyone noticed.", "neutral", ["embarrassed"], False, "en"),
    ("mei", "group", ("meridian", 50), R, "neutral", ["happy"], True, "en"),
    ("victor", "group", ("meridian", 56), R, "thinking", ["happy", "neutral"], False, "en"),
    ("amara", "group", ("meridian", 60), "Amara, I fainted on the bus this morning. I'm okay now, I think.", "happy", ["thinking", "surprised"], False, "en"),
    ("mei", "group", ("meridian", 70), "Mei, admit it, your forecast was wrong.", "neutral", ["thinking"], False, "en"),
    ("victor", "group", ("meridian", 80), "Victor, the bar council wants you to give the keynote this year.", "neutral", ["happy"], False, "en"),
    # ── greetings, English (15): a new session, no lines yet ──
    ("hana", "greeting", None, None, "neutral", ["happy"], False, "en"),
    ("rin", "greeting", None, None, "neutral", ["neutral"], True, "en"),
    ("takeshi", "greeting", None, None, "neutral", ["neutral", "happy"], True, "en"),
    ("amara", "greeting", None, None, "neutral", ["happy", "neutral"], True, "en"),
    ("mei", "greeting", None, None, "neutral", ["neutral"], True, "en"),
    ("victor", "greeting", None, None, "neutral", ["happy", "neutral"], True, "en"),
    ("hana", "greeting", None, None, "sad", ["happy"], False, "en"),
    ("rin", "greeting", None, None, "angry", ["neutral"], False, "en"),
    ("takeshi", "greeting", None, None, "surprised", ["neutral", "happy"], False, "en"),
    ("amara", "greeting", None, None, "thinking", ["happy", "neutral"], False, "en"),
    ("mei", "greeting", None, None, "embarrassed", ["neutral"], False, "en"),
    ("victor", "greeting", None, None, "angry", ["happy", "neutral"], False, "en"),
    ("hana", "greeting", None, None, "embarrassed", ["happy"], False, "en"),
    ("rin", "greeting", None, None, "happy", ["neutral", "happy"], True, "en"),
    ("takeshi", "greeting", None, None, "sad", ["neutral", "happy"], False, "en"),
]


def profiles() -> dict[str, dict[str, Any]]:
    out = {}
    for cid in WHO.values():
        d = json.loads((SEED / f"{cid}.json").read_text(encoding="utf-8"))["data"]
        out[cid] = d["profile"]
    return out


def transcript(key: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((TRANSCRIPTS / f"{SRC[key]}.json").read_text(encoding="utf-8"))
    return data


def name_of(cid: str, prof: dict[str, dict[str, Any]]) -> str:
    return str(prof[cid]["name"])


def context(key: str, i: int, prof: dict[str, dict[str, Any]]) -> tuple[list[dict[str, str]], str, int]:
    """The two turns before turn `i` as recent lines, turn `i`'s user line, and the speaker's last-spoke distance."""
    turns = transcript(key)["turns"]
    recent: list[dict[str, str]] = []
    for t in turns[max(0, i - 2):i]:
        recent.append({"speaker": USER, "text": t["user"]})
        recent += [{"speaker": name_of(r["speaker"], prof), "text": r["text"]} for r in t["replies"]]
    return recent, str(turns[i]["user"]), 0


def previous_faces() -> list[str]:
    """The table's faces, with neutral spread over keep-false items until about a third stay neutral."""
    faces = [it[4] for it in ITEMS]
    n_neutral = faces.count("neutral")
    k = 0
    for idx, it in enumerate(ITEMS):
        if n_neutral <= NEUTRAL_TARGET:
            break
        if it[4] != "neutral" or it[6] or it[1] == "greeting":
            continue
        options = [f for f in ROTATE if f not in it[5]]
        faces[idx] = options[k % len(options)]
        k += 1
        n_neutral -= 1
    return faces


def build() -> list[dict[str, Any]]:
    prof = profiles()
    rows = []
    for n, (it, prev) in enumerate(zip(ITEMS, previous_faces(), strict=True), 1):
        who, mode, ctx, latest, _, acceptable, keep_ok, lang = it
        cid = WHO[who]
        p = prof[cid]
        recent: list[dict[str, str]] = []
        since: int | None = None
        source = "written"
        if ctx is not None:
            recent, line, since = context(ctx[0], ctx[1], prof)
            source = f"transcript:{SRC[ctx[0]]}#{ctx[1]}" + ("" if latest is None else " (written line)")
            latest = line if latest is None else latest
        live_mode = "one_on_one" if mode == "greeting" else mode
        cand = Candidate(id=cid, name=str(p["name"]), role=str(p.get("role") or ""),
                         about_source=str((p.get("personality") or {}).get("summary") or ""), face=prev,
                         turns_since=since)
        state = build_turn_plan_state(PlanStateInput(mode=live_mode, user_name=USER, candidates=[cand],
                                                     latest=latest or "", recent=recent)).state
        item_id = f"emo-{n:03d}"
        assert all(f in FACES for f in acceptable) and 1 <= len(acceptable) <= 2, item_id
        rows.append({"id": item_id, "question_id": "emotion_greeting" if mode == "greeting" else "emotion_reply",
                     "split": split_for(item_id), "lang": lang, "kind": mode,
                     "item": {"state": state, "name": str(p["name"]), "seed": f"m9-emotion:{n}:{cid}"},
                     "label": {"previous": prev, "acceptable": acceptable, "keep_ok": keep_ok}, "source": source})
    return rows


def check(rows: list[dict[str, Any]]) -> list[str]:
    """D27's spread and the keep cap (m9-labels.md)."""
    problems = []
    keep = sum(r["label"]["keep_ok"] for r in rows)
    if not 20 <= keep <= 30:
        problems.append(f"keep_ok on {keep} items (rule: 20–30)")
    kinds = Counter(r["kind"] for r in rows)
    if kinds != Counter({"one_on_one": 55, "group": 30, "greeting": 15}):
        problems.append(f"turn kinds {dict(kinds)}")
    langs = Counter(r["lang"] for r in rows)
    if langs != Counter({"en": 80, "ms": 10, "zh": 5, "mixed": 5}):
        problems.append(f"languages {dict(langs)}")
    return problems


def main() -> int:
    rows = build()
    problems = check(rows)
    if problems:
        print("\n".join(problems))
        return 1
    out = HERE / "emotion.jsonl"
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8", newline="\n")
    prev = Counter(r["label"]["previous"] for r in rows)
    splits = Counter(r["split"] for r in rows)
    print(f"wrote {len(rows)} items to {out.name}: splits {dict(splits)}, previous faces {dict(prev)}, "
          f"keep_ok {sum(r['label']['keep_ok'] for r in rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

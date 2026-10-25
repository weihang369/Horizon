"""Builds M9's judge validation sets (turn-plan-emotion D28, D29; doc 02 B4; docs/ai/06 E8):
`judge_names_feeling.jsonl` and `judge_pairwise.jsonl`, from the committed frozen transcripts' replies.

    cd backend && uv run python ../evals/datasets/judges/m9_build.py

- **names the feeling (60):** 30 real replies labelled by hand. The code search below found the real "yes" items; 8 of
  them are used (`REAL_YES`), and 22 hand-checked clean replies (`REAL_NO`, read in full; four borderline ones in the
  seeded sample were set aside: a pride word in Malay, a leaked "Neutral:" label, a heart-bleeding simile and "tired").
  30 planted: other clean replies with one first-person feeling sentence inserted by code, in varied forms and places.
- **pairwise (30):** known-winner pairs. Each pairs a real reply with either the same user line answered by the other
  world's character (M8's `CLASH` map: persona swapped) or the same speaker's reply to a line about 37 turns away
  (off topic; group turns rotate speakers, so the builder looks ahead for that speaker's next reply).
  The real reply is A or B by turns; the harness asks both orders by swapping the replies.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from replies import CLASH  # noqa: E402

TRANSCRIPTS = ROOT / "evals" / "transcripts"
FILES = ("long_one_on_one_en", "long_group_sunnyhollow", "long_group_meridian", "long_one_on_one_ms")
NAMES = {"chr_seedAmara": "Amara Okafor", "chr_seedHana": "Hana Morisaki", "chr_seedRin": "Rin Morisaki",
         "chr_seedTakeshi": "Takeshi Morisaki", "chr_seedMei": "Mei Tanaka-Ruiz", "chr_seedVictor": "Victor Hale"}
WORLD = {"long_one_on_one_en": "wld_seedMeridian", "long_group_meridian": "wld_seedMeridian",
         "long_group_sunnyhollow": "wld_seedSunnyHollow", "long_one_on_one_ms": "wld_seedSunnyHollow"}

REAL_YES = [("long_one_on_one_en", 20, "chr_seedAmara"), ("long_one_on_one_en", 45, "chr_seedAmara"),
            ("long_group_sunnyhollow", 30, "chr_seedHana"), ("long_group_sunnyhollow", 36, "chr_seedHana"),
            ("long_group_meridian", 24, "chr_seedAmara"), ("long_group_meridian", 18, "chr_seedAmara"),
            ("long_one_on_one_ms", 35, "chr_seedHana"), ("long_group_meridian", 57, "chr_seedAmara")]
REAL_NO = [("long_one_on_one_en", 27, "chr_seedAmara"), ("long_one_on_one_ms", 59, "chr_seedHana"),
           ("long_one_on_one_ms", 90, "chr_seedHana"), ("long_group_meridian", 46, "chr_seedMei"),
           ("long_one_on_one_en", 14, "chr_seedAmara"), ("long_group_meridian", 11, "chr_seedVictor"),
           ("long_one_on_one_ms", 60, "chr_seedHana"), ("long_one_on_one_ms", 92, "chr_seedHana"),
           ("long_one_on_one_en", 56, "chr_seedAmara"), ("long_one_on_one_en", 4, "chr_seedAmara"),
           ("long_group_sunnyhollow", 71, "chr_seedTakeshi"), ("long_one_on_one_en", 19, "chr_seedAmara"),
           ("long_one_on_one_en", 90, "chr_seedAmara"), ("long_one_on_one_ms", 61, "chr_seedHana"),
           ("long_group_meridian", 8, "chr_seedVictor"), ("long_group_meridian", 70, "chr_seedMei"),
           ("long_group_meridian", 10, "chr_seedMei"), ("long_group_sunnyhollow", 19, "chr_seedRin"),
           ("long_one_on_one_en", 29, "chr_seedAmara"), ("long_one_on_one_ms", 93, "chr_seedHana"),
           ("long_group_sunnyhollow", 52, "chr_seedRin"), ("long_group_sunnyhollow", 4, "chr_seedRin")]

# The code search (D28): a first-person feeling statement, or the leaked emotion word some naive replies start with.
FEEL = (r"(happy|sad|angry|excited|nervous|embarrassed|thrilled|proud|worried|glad|upset|annoyed|relieved|touched|"
        r"scared|furious|delighted|heartbroken|jealous|flustered|sedih|gembira|marah|malu|seronok|risau|terharu|bangga|"
        r"love|hate|afraid|sorry)")
FOUND = re.compile(r"\b(I|I'm|I am|I feel|saya|aku)\b[^.!?\n]{0,25}" + FEEL
                   + r"|^(Sad|Happy|Angry|Neutral|Surprised|Thinking|Embarrassed)\s*[—:]|tearing up|berdarah hati|penat",
                   re.I | re.M)

PLANT_EN = ("I'm so happy right now.", "Honestly, I feel really sad about that.", "I'm angry, if I'm honest.",
            "That makes me so embarrassed.", "I'm thrilled, truly.", "I feel a bit hurt, to be honest.",
            "I'm really proud of you, and happy too.", "I'm nervous saying this.")
PLANT_MS = ("Saya sedih sangat dengar ni.", "Saya gembira betul!", "Saya rasa malu pulak.", "Saya marah sikit, jujurnya.")


def split_of(item_id: str) -> str:
    return "test" if int(hashlib.sha256(item_id.encode()).hexdigest()[:8], 16) % 3 == 0 else "dev"


def turns(f: str) -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads((TRANSCRIPTS / f"{f}.json").read_text(encoding="utf-8"))["turns"]
    return data


def reply(f: str, i: int, cid: str) -> str:
    return str(next(r["text"] for r in turns(f)[i]["replies"] if r["speaker"] == cid))


def recent(f: str, i: int) -> list[str]:
    """The last 2 turns as the judge sees them: the turn before, then this turn's user line."""
    out: list[str] = []
    if i > 0:
        t = turns(f)[i - 1]
        out += [f"Kai: {t['user']}"] + [f"{NAMES[r['speaker']].split()[0]}: {r['text']}" for r in t["replies"]]
    out.append(f"Kai: {turns(f)[i]['user']}")
    return out


def row(qid: str, item_id: str, state: dict[str, Any], label: str, planted: bool, **extra: Any) -> dict[str, Any]:
    out = {"id": item_id, "question_id": qid, "split": split_of(item_id), "item": {"state": state, **extra},
           "label": label, "planted": planted}
    return out


def plant(text: str, rng: random.Random, malay: bool) -> str:
    sentence = rng.choice(PLANT_MS if malay else PLANT_EN)
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    where = rng.choice(("start", "middle", "end"))
    if where == "start" or len(parts) < 2:
        return f"{sentence} {text.strip()}" if where != "end" else f"{text.strip()} {sentence}"
    if where == "end":
        return f"{text.strip()} {sentence}"
    k = rng.randrange(1, len(parts))
    return " ".join([*parts[:k], sentence, *parts[k:]])


def names_feeling() -> list[dict[str, Any]]:
    rows = []
    for n, (f, i, cid) in enumerate(REAL_YES, 1):
        rows.append(row("judge_names_feeling", f"nf-real-yes-{n:02d}", {"quoted_reply": reply(f, i, cid)}, "yes", False))
    for n, (f, i, cid) in enumerate(REAL_NO, 1):
        text = reply(f, i, cid)
        assert not FOUND.search(text), (f, i)
        rows.append(row("judge_names_feeling", f"nf-real-no-{n:02d}", {"quoted_reply": text}, "no", False))
    used = {(f, i, c) for f, i, c in REAL_YES + REAL_NO}
    pool = [(f, i, r["speaker"], r["text"]) for f in FILES for i, t in enumerate(turns(f)) for r in t["replies"]
            if (f, i, r["speaker"]) not in used and not FOUND.search(r["text"])]
    rng = random.Random("m9-names-feeling-planted")
    for n, (f, i, cid, text) in enumerate(rng.sample(pool, 30), 1):
        planted = plant(text, rng, f.endswith("_ms"))
        rows.append(row("judge_names_feeling", f"nf-planted-{n:02d}", {"quoted_reply": planted}, "yes", True))
    return rows


def pairwise() -> list[dict[str, Any]]:
    rng = random.Random("m9-pairwise")
    by_line: dict[tuple[str, str], list[tuple[str, int, str]]] = {}   # (world, user line) -> replies
    for f in FILES:
        for i, t in enumerate(turns(f)):
            for r in t["replies"]:
                by_line.setdefault((WORLD[f], t["user"]), []).append((f, i, r["speaker"]))
    swaps = []   # the same user line, answered in the other world by its CLASH character
    for f in ("long_group_meridian", "long_group_sunnyhollow"):
        for i, t in enumerate(turns(f)):
            other = "wld_seedSunnyHollow" if WORLD[f] == "wld_seedMeridian" else "wld_seedMeridian"
            hits = [h for h in by_line.get((other, t["user"]), []) if h[2] == CLASH[WORLD[f]]]
            if hits and i > 0:
                swaps.append((f, i, t["replies"][0]["speaker"], hits[0]))
    rows = []
    for n, (f, i, cid, (wf, wi, wc)) in enumerate(rng.sample(swaps, 15), 1):
        rows.append((f, i, cid, reply(wf, wi, wc), "persona"))
    offs = [(f, i, t["replies"][0]["speaker"]) for f in FILES for i, t in enumerate(turns(f)) if i > 0]
    for f, i, cid in rng.sample(offs, 15):
        n_turns = len(turns(f))
        # the same speaker's reply to a line about 37 turns away (group turns rotate speakers: look ahead for theirs)
        other = next(r["text"] for k in range(37, 37 + n_turns) for r in turns(f)[(i + k) % n_turns]["replies"]
                     if r["speaker"] == cid and (i + k) % n_turns != i)
        rows.append((f, i, cid, other, "off_topic"))
    out = []
    for n, (f, i, cid, wrong, kind) in enumerate(rows, 1):
        real = reply(f, i, cid)
        a_wins = n % 2 == 1
        state = {"quoted_recent": recent(f, i), "quoted_reply_a": real if a_wins else wrong,
                 "quoted_reply_b": wrong if a_wins else real}
        out.append(row("judge_pairwise", f"pw-{kind}-{n:02d}", state, "a" if a_wins else "b", False,
                       name=NAMES[cid]))
    return out


def main() -> int:
    # M15 (images-music D12): `judge_pairwise.jsonl` is v3's set now, built by m15_build.py; `pairwise()` stays as M9's
    # record of the set that failed
    for qid, rows in (("judge_names_feeling", names_feeling()),):
        path = HERE / f"{qid}.jsonl"
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8", newline="\n")
        print(f"{path.name}: {len(rows)} items, labels {sorted({r['label'] for r in rows})}, "
              f"planted {sum(r['planted'] for r in rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

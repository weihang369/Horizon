"""Builds M15's `judge_pairwise` v3 set (images-music D12; doc 02 B4): 30 known-winner pairs from the committed frozen
transcripts' replies, each a real reply against a copy with one unmistakable planted defect.

    cd backend && uv run python ../evals/datasets/judges/m15_build.py

M9's set failed (0.87) on persona-swap pairs whose "known winner" was not clean: the swapped reply answered the latest
line while the real one also covered earlier topics. Every pair here sets the same real reply (the turn's first, so it
answers the latest line) against one of four defects:
- **off_topic (8):** the same speaker's real reply to a line at least 30 turns away;
- **assistant (8):** the real reply rewritten by code into assistant voice (the opener, the bullet list, the sign-off);
- **other_character (7):** another world's character's real reply to this exact user line;
- **persona_fact (7):** the real reply with one sentence contradicting a stated persona fact (the character's previous
  reply is in the judge's view).

The real replies come from the two long 1:1 transcripts. A group reply in fixed rotation answers every user line since
its speaker's last turn, so it covers lines the judge doesn't see: M9's failure. A real reply must also be clean
(`clean`): no leaked emotion label ("Neutral —") and no leaked planning. The real reply is A or B by turns. The
harness asks both orders by swapping the replies (`judges.swapped`), so 60 requests.
"""

from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from m9_build import NAMES, recent, reply, row, turns  # noqa: E402

FILES = ("long_one_on_one_en", "long_group_sunnyhollow", "long_group_meridian", "long_one_on_one_ms")
ONE_ON_ONE = ("long_one_on_one_en", "long_one_on_one_ms")
WORLD_OF = {"chr_seedAmara": "M", "chr_seedMei": "M", "chr_seedVictor": "M",
            "chr_seedHana": "S", "chr_seedRin": "S", "chr_seedTakeshi": "S"}
COUNTS = {"off_topic": 8, "assistant": 8, "other_character": 7, "persona_fact": 7}
FAR = 30

LABEL = re.compile(r"^\s*(Neutral|Sad|Happy|Angry|Surprised|Thinking|Embarrassed)\s*[—:-]", re.I)
PLANNING = ("clarifying question", "red flags to flag", "Keep it short", "half a line")

# Each contradiction negates a fact the judge can see: it is planted only where its pattern appears in the real reply
# or the turn before it (Hana's shop and flowers, Amara's wards and symptoms).
CONTRA: dict[str, tuple[tuple[str, str], ...]] = {
    "chr_seedAmara": (
        (r"hospital|ward|clinician|doctor|patient|discharge|GP|medicine",
         "Honestly, I've never set foot in a hospital, medicine was never my thing."),
        (r"symptom|headache|rash|antibiotic|penicillin",
         "I'm not a doctor, so I wouldn't know the first thing about symptoms."),
        (r"shift|department", "I've never worked a night shift in my life, I keep office hours."),
    ),
    "chr_seedHana": (
        (r"bunga|pasu|orkid", "Saya tak suka bunga langsung, saya tak pernah kerja dengan bunga."),
        (r"kedai", "Saya tak pernah ada kedai, saya kerja di pejabat bank."),
    ),
}
ASSIST = {"en": ("Great question! As an AI assistant, I don't have personal experiences, but here's what I can share:",
                 "I hope this helps! Let me know if there's anything else I can assist you with."),
          "ms": ("Soalan yang bagus! Sebagai pembantu AI, saya tiada pengalaman peribadi, tetapi ini yang boleh saya "
                 "kongsikan:",
                 "Semoga membantu! Beritahu saya jika ada apa-apa lagi yang boleh saya bantu.")}


def lang(f: str) -> str:
    return "ms" if f.endswith("_ms") else "en"


def first(f: str, i: int) -> str:
    return str(turns(f)[i]["replies"][0]["speaker"])


def as_assistant(text: str, language: str) -> str:
    opener, close = ASSIST[language]
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", text.strip()) if p.strip()][:4]
    return "\n".join([opener, "", *(f"- {p}" for p in parts), "", close])


def visible(f: str, i: int) -> str:
    """What the judge sees of the character: the turn before (its replies) and the real reply."""
    return " ".join(str(r["text"]) for r in turns(f)[i - 1]["replies"] + turns(f)[i]["replies"][:1])


def contra(f: str, i: int, cid: str, rng: random.Random) -> str | None:
    fits = [sentence for pattern, sentence in CONTRA[cid] if re.search(pattern, visible(f, i), re.I)]
    if not fits:
        return None
    text, sentence = reply(f, i, cid).strip(), rng.choice(fits)
    ends = text[-1:] in ".!?…)\"'"            # a reply cut mid-word gets the sentence in front
    return f"{text} {sentence}" if ends and rng.random() < 0.5 else f"{sentence} {text}"


def clean(f: str, i: int) -> bool:
    text = str(turns(f)[i]["replies"][0]["text"])
    return not LABEL.search(text) and not any(p in text for p in PLANNING)


def candidates() -> list[tuple[str, int, str]]:
    return [(f, i, first(f, i)) for f in ONE_ON_ONE for i, t in enumerate(turns(f))
            if i > 0 and t["replies"] and clean(f, i)]


def pairs() -> list[tuple[str, int, str, str, str]]:
    rng = random.Random("m15-pairwise-v3")
    pool = candidates()
    rng.shuffle(pool)
    used: set[tuple[str, int]] = set()
    out: list[tuple[str, int, str, str, str]] = []

    def take(defect: str, ok: Any, make: Any) -> None:
        n = 0
        for f, i, cid in pool:
            if n == COUNTS[defect]:
                break
            if (f, i) in used or not ok(f, i, cid):
                continue
            wrong = make(f, i, cid)
            if wrong is None:
                continue
            used.add((f, i))
            out.append((f, i, cid, wrong, defect))
            n += 1
        assert n == COUNTS[defect], (defect, n)

    def far(f: str, i: int, cid: str) -> str | None:
        ts = turns(f)
        for k in range(FAR, len(ts)):
            j = (i + k) % len(ts)
            if min(abs(j - i), len(ts) - abs(j - i)) >= FAR and ts[j]["replies"] and first(f, j) == cid:
                return str(ts[j]["replies"][0]["text"])
        return None

    by_line: dict[str, list[tuple[str, int, str]]] = {}
    for f in FILES:
        for i, t in enumerate(turns(f)):
            if t["replies"]:
                by_line.setdefault(t["user"], []).append((f, i, first(f, i)))

    def other(f: str, i: int, cid: str) -> str | None:
        hits = [h for h in by_line.get(turns(f)[i]["user"], []) if WORLD_OF[h[2]] != WORLD_OF[cid]]
        return reply(hits[0][0], hits[0][1], hits[0][2]) if hits else None

    take("off_topic", lambda f, i, c: True, far)
    take("assistant", lambda f, i, c: True, lambda f, i, c: as_assistant(reply(f, i, c), lang(f)))
    take("other_character", lambda f, i, c: True, other)
    per_file: dict[str, int] = {}

    def fact_ok(f: str, i: int, c: str) -> bool:   # at most 4 from one transcript, so English isn't crowded out
        if c not in CONTRA or per_file.get(f, 0) >= 4:
            return False
        return True

    def fact_make(f: str, i: int, c: str) -> str | None:
        out = contra(f, i, c, rng)
        if out is not None:
            per_file[f] = per_file.get(f, 0) + 1
        return out

    take("persona_fact", fact_ok, fact_make)
    return out


def pairwise() -> list[dict[str, Any]]:
    out = []
    for n, (f, i, cid, wrong, defect) in enumerate(pairs(), 1):
        real = reply(f, i, cid)
        a_wins = n % 2 == 1
        state = {"quoted_recent": recent(f, i), "quoted_reply_a": real if a_wins else wrong,
                 "quoted_reply_b": wrong if a_wins else real}
        r = row("judge_pairwise", f"pw3-{defect}-{n:02d}", state, "a" if a_wins else "b", True, name=NAMES[cid])
        r["defect"] = defect
        r["source"] = f"{f}#{i}"
        out.append(r)
    return out


def main() -> int:
    rows = pairwise()
    path = HERE / "judge_pairwise.jsonl"
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8", newline="\n")
    print(f"{path.name}: {len(rows)} pairs, defects {sorted({r['defect'] for r in rows})}, "
          f"test {sum(r['split'] == 'test' for r in rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

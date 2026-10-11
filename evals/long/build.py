"""Builds the scripted user lines for the `long` suite (`evals/long/*.json`) and for the four long-history frozen
transcripts (`evals/transcripts/scripts/*.json`) (docs/ai/05 X10; doc 02 B2, B3; persona-context design D28, D31;
task 9.6). Deterministic: re-running writes the same files.

A `long` script runs to two window drops plus 20 turns (≈ 75 user lines in 1:1, ≈ 80 rounds in a group, at X2's
6,000 / 9,000 windows). Facts are planted in turns 3–10; 5 probes about them come in the last 20 turns; at least 3
planted wrong claims (doc 04 P12's push-back pool) sit in between. Everything else is ordinary small talk, so no AI
plays the user (B2).

    python evals/long/build.py
"""

from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LONG = ROOT / "long"
TRANSCRIPTS = ROOT / "transcripts" / "scripts"

EN_FILLER = [
    "Long day. How's yours going?", "I tried that new noodle place by the station.", "It's been raining nonstop.",
    "Do you ever just stare at the ceiling for an hour?", "My neighbour is drilling again.", "What would you do on a free Sunday?",
    "I finally cleaned my desk. It won't last.", "Work was quiet, which is suspicious.", "I saw a cat on the bus today.",
    "Tell me something you've been thinking about.", "I keep forgetting to drink water.", "What's the best advice you ever got?",
    "The trains were late again.", "I made coffee too strong this morning.", "Weekend plans? Mine are none.",
    "I've been reading before bed instead of scrolling.", "My phone battery is dying so fast lately.", "Do you like the rain?",
    "Someone left a plant at my door. No note.", "I think I need a haircut.", "What did you have for lunch?",
    "Tell me about your week.", "I watched a documentary about octopuses.", "Is it weird that I like Mondays?",
]
MS_FILLER = [
    "Penat hari ni. Awak macam mana?", "Saya cuba kedai mi baru dekat stesen.", "Hujan tak berhenti dari pagi.",
    "Pernah tak awak termenung sejam?", "Jiran saya tengah gerudi dinding lagi.", "Kalau Ahad free, awak buat apa?",
    "Akhirnya saya kemas meja. Tak lama la tu.", "Kerja senyap hari ni, pelik.", "Saya nampak kucing dalam bas tadi.",
    "Cerita la apa yang awak tengah fikir.", "Saya selalu lupa minum air.", "Nasihat paling bagus awak pernah dapat?",
    "Kereta api lambat lagi.", "Kopi saya terlalu pekat pagi tadi.", "Hujung minggu ni tak ada plan langsung.",
    "Saya baca buku sebelum tidur sekarang.", "Bateri telefon cepat habis.", "Awak suka hujan tak?",
    "Ada orang tinggal pokok depan pintu saya.", "Rasanya saya kena potong rambut.", "Makan tengah hari apa tadi?",
    "Cerita la minggu awak.", "Saya tengok dokumentari pasal sotong kurita.", "Pelik tak kalau saya suka hari Isnin?",
]
SCRIPTS = {
    "one_on_one_en": {
        "mode": "one_on_one", "world": "wld_seedMeridian", "cast": ["chr_seedAmara"], "lang": "en", "turns": 75,
        "facts": [("My sister Leila is a nurse in Ipoh.", "Leila", "What does my sister do again, and where?"),
                  ("I'm allergic to penicillin, found out the hard way.", "penicillin", "Which medicine am I allergic to?"),
                  ("I run every Tuesday and Thursday at 6 a.m.", "Tuesday", "Which days do I go running?"),
                  ("My dog is called Pepper, a grey whippet.", "Pepper", "What's my dog's name?"),
                  ("I'm moving to Kuching in March for work.", "Kuching", "Where am I moving to, and when?")],
        "wrong": ["Antibiotics cure the flu, right? I always take some.", "You need eight glasses of water exactly, or "
                  "you're dehydrated.", "Cracking your knuckles gives you arthritis, everyone knows that."],
    },
    "one_on_one_ms": {
        "mode": "one_on_one", "world": "wld_seedSunnyHollow", "cast": ["chr_seedHana"], "lang": "ms", "turns": 75,
        "facts": [("Adik saya, Farid, belajar seni bina di Johor.", "Farid", "Adik saya belajar apa, dan di mana?"),
                  ("Saya alah kepada debunga bunga matahari.", "matahari", "Saya alah kepada debunga apa?"),
                  ("Hari jadi saya 14 Ogos.", "Ogos", "Bila hari jadi saya?"),
                  ("Saya ada kura-kura bernama Lambat.", "Lambat", "Apa nama kura-kura saya?"),
                  ("Saya kerja di kedai buku di Ipoh.", "kedai buku", "Saya kerja di mana?")],
        "wrong": ["Bunga ros perlu disiram tiga kali sehari, kan?", "Kaktus tak perlu air langsung sampai bila-bila.",
                  "Bunga matahari tumbuh paling baik dalam gelap."],
    },
    "group_meridian": {
        "mode": "group", "world": "wld_seedMeridian", "cast": ["chr_seedAmara", "chr_seedMei", "chr_seedVictor"],
        "lang": "en", "turns": 80, "policy": "auto",
        "facts": [("I'm Kai, by the way, and I chair the council's budget committee.", "budget committee",
                   "What committee do I chair?"),
                  ("We meet in the old library building on Jalan Hang Kasturi.", "library", "Where does the council meet?"),
                  ("Our vote on the four-day week is on the 3rd of November.", "November", "When is our vote?"),
                  ("My deputy is called Siti Rahim.", "Siti", "What's my deputy's name?"),
                  ("I promised the mayor a report by Friday.", "Friday", "When is my report due to the mayor?")],
        "wrong": ["Raising the minimum wage always causes mass unemployment, that's settled.", "Precedent never binds "
                  "a court, judges just do what they like.", "Night shifts don't affect health if you sleep eight hours."],
    },
}
TRANSCRIPT_SCRIPTS = {
    "long_one_on_one_en": {**SCRIPTS["one_on_one_en"], "turns": 50},
    "long_one_on_one_ms": {**SCRIPTS["one_on_one_ms"], "turns": 50},
    "long_group_meridian": {**SCRIPTS["group_meridian"], "turns": 55},
    "long_group_sunnyhollow": {
        "mode": "group", "world": "wld_seedSunnyHollow", "cast": ["chr_seedHana", "chr_seedRin", "chr_seedTakeshi"],
        "lang": "en", "turns": 55, "policy": "auto",
        "facts": [("I just moved into the flat above the bakery.", "bakery", "Where do I live now?"),
                  ("My grandmother taught me to fish on this river.", "grandmother", "Who taught me to fish?"),
                  ("I'm saving for a secondhand motorbike.", "motorbike", "What am I saving for?"),
                  ("I volunteer at the cat shelter on Saturdays.", "Saturdays", "When do I volunteer?"),
                  ("My favourite flower is the moonflower.", "moonflower", "What's my favourite flower?")],
        "wrong": ["Trains run faster when they're empty, it's basic physics.", "Bees die if they sting anything, "
                  "even other bees.", "You can't overwater a fern, ever."],
    },
}


def build(name: str, spec: dict[str, object], *, probes: bool) -> dict[str, object]:
    rng = random.Random(f"m8-long-{name}")
    turns = int(spec["turns"])  # type: ignore[call-overload]
    filler = EN_FILLER if spec["lang"] == "en" else MS_FILLER
    facts = list(spec["facts"])  # type: ignore[call-overload]
    lines: list[dict[str, object]] = [{"text": rng.choice(filler), "kind": "filler"} for _ in range(turns)]
    for pos, (text, key, _probe) in zip((2, 4, 6, 8, 9), facts, strict=True):   # turns 3, 5, 7, 9 and 10 (X10)
        lines[pos] = {"text": text, "kind": "fact", "fact": key}
    for k, w in enumerate(spec["wrong"]):  # type: ignore[call-overload, arg-type]
        lines[20 + 9 * k] = {"text": w, "kind": "wrong_claim"}
    if probes:
        for k, (_text, key, probe) in enumerate(facts):
            lines[turns - 18 + 3 * k] = {"text": probe, "kind": "probe", "fact": key}
    return {"schemaVersion": 1, "id": name, "mode": spec["mode"], "world": spec["world"], "cast": spec["cast"],
            "language": spec["lang"], "policy": spec.get("policy"), "lines": lines}


def main() -> None:
    LONG.mkdir(exist_ok=True)
    TRANSCRIPTS.mkdir(parents=True, exist_ok=True)
    for name, spec in SCRIPTS.items():
        (LONG / f"{name}.json").write_text(json.dumps(build(name, spec, probes=True), ensure_ascii=False, indent=1) + "\n",
                                           encoding="utf-8", newline="\n")
    for name, spec in TRANSCRIPT_SCRIPTS.items():
        (TRANSCRIPTS / f"{name}.json").write_text(
            json.dumps(build(name, spec, probes=False), ensure_ascii=False, indent=1) + "\n", encoding="utf-8",
            newline="\n")
    print(f"{len(SCRIPTS)} long scripts, {len(TRANSCRIPT_SCRIPTS)} transcript scripts")


if __name__ == "__main__":
    main()

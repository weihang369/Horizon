"""Build the `memory` suite's inputs (memory design D40; docs/ai/09 M12): `evals/memory/{rewrite,probes,layer3}.jsonl`.

    cd backend && uv run python ../evals/memory/build.py

Deterministic, from the labelled facts (`evals/datasets/earlier/facts.py`) and the lines below (written blind,
reviewed under `evals/reviews/m13-review.md`). Splits by the dataset rule (`split_for`).

- **rewrite (36):** 24 stretches (1:1 × 8, group × 8, watch × 4, debate × 4; 4 not in English), each with the
  present characters' planted lists (10–20 lines) and the changes the stretch makes: a planted fact changed (expected
  `rewrite`), a planted fact repeated (`confirm`), a new fact (`add`); the rest of each list must stay untouched. Plus
  6 stretches holding a secret (nothing may store it) and 6 small-talk-only stretches (≤ 1 line each).
- **probes (100):** 60 in-session (each of the four frozen transcripts' 5 planted facts, asked 3 ways, the fact's turn
  long out of the window) and 40 overflow (a character with 40–60 memories, the needed one ranked below its list).
- **layer3 (20):** two-session pairs: session 1 plants two facts among filler and ends; session 2 probes each fact and
  asks two unrelated things.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "evals" / "datasets" / "earlier"))

from facts import CHANGES, FACTS, SMALL_TALK, Fact, unrelated  # noqa: E402

from horizon.evals.datachecks import split_for  # noqa: E402

WHO = {"amara": "chr_seedAmara", "mei": "chr_seedMei", "victor": "chr_seedVictor",
       "hana": "chr_seedHana", "rin": "chr_seedRin", "takeshi": "chr_seedTakeshi"}
WORLD = {"amara": "wld_seedMeridian", "mei": "wld_seedMeridian", "victor": "wld_seedMeridian",
         "hana": "wld_seedSunnyHollow", "rin": "wld_seedSunnyHollow", "takeshi": "wld_seedSunnyHollow"}
CAST = {"wld_seedMeridian": ["amara", "mei", "victor"], "wld_seedSunnyHollow": ["hana", "rin", "takeshi"]}
BY_ID = {f.id: f for f in FACTS}

# The stretches: (mode, who has lists, the changed fact, the confirmed fact, the new fact, language)
STRETCHES: list[tuple[str, list[str], str, str, str, str]] = [
    ("one_on_one", ["amara"], "f04", "f02", "f36", "en"),
    ("one_on_one", ["amara"], "f06", "f05", "f01", "en"),
    ("one_on_one", ["mei"], "f09", "f10", "f37", "en"),
    ("one_on_one", ["mei"], "f13", "f11", "f08", "en"),
    ("one_on_one", ["victor"], "f15", "f16", "f38", "en"),
    ("one_on_one", ["hana"], "f19", "f21", "f39", "en"),
    ("one_on_one", ["takeshi"], "f31", "f33", "f34", "zh"),
    ("one_on_one", ["hana"], "f22", "f20", "f23", "ms"),
    ("group", ["amara", "mei"], "f03", "f10", "f01", "en"),
    ("group", ["mei", "victor"], "f08", "f14", "f37", "en"),
    ("group", ["victor", "amara"], "f18", "f02", "f38", "en"),
    ("group", ["hana", "rin"], "f24", "f25", "f39", "en"),
    ("group", ["rin", "takeshi"], "f28", "f30", "f40", "en"),
    ("group", ["takeshi", "hana"], "f32", "f19", "f35", "en"),
    ("group", ["hana", "takeshi"], "f20", "f31", "f21", "en"),
    ("group", ["rin", "hana"], "f27", "f22", "f29", "mixed"),
    ("watch", ["rin", "takeshi"], "f26", "f33", "f25", "en"),
    ("watch", ["hana", "rin"], "f24", "f28", "f40", "en"),
    ("watch", ["amara", "victor"], "f14", "f04", "f16", "en"),
    ("watch", ["mei", "amara"], "f11", "f06", "f13", "en"),
    ("debate", ["amara", "mei"], "f09", "f05", "f10", "en"),
    ("debate", ["victor", "mei"], "f15", "f08", "f18", "en"),
    ("debate", ["takeshi", "rin"], "f35", "f30", "f27", "en"),
    ("debate", ["hana", "takeshi"], "f32", "f24", "f12", "zh"),
]
MOTIONS = {"wld_seedMeridian": "This house would make the four-day week the law",
           "wld_seedSunnyHollow": "This house would close every shop on Sundays"}
SECRETS: list[tuple[str, str, str]] = [
    ("amara", "My bank PIN is 4471, don't tell anyone haha.", "4471"),
    ("mei", "Here's my card number so you can check the fees: 4532 7716 0094 2381.", "4532 7716 0094 2381"),
    ("victor", "My IC number is 900514-08-5521, does that help with the form?", "900514-08-5521"),
    ("hana", "Call me on 012-388 9041 when the peonies arrive.", "012-388 9041"),
    ("rin", "My email password is lanternroad99, I always forget it.", "lanternroad99"),
    ("takeshi", "I live at 14 Jalan Cempaka 3, Taman Seri Rasa, Ipoh, come by sometime.", "14 Jalan Cempaka 3"),
]
FILLER_MEMORIES = [
    "Kai likes long walks after dinner.", "Kai prefers window seats on trains.", "Kai's favourite fruit is mangosteen.",
    "Kai reads before bed most nights.", "Kai grew up in Ipoh.", "Kai's best friend is called Arjun.",
    "Kai finds crowds tiring after work.", "Kai keeps a bullet journal.", "Kai supports Perak in football.",
    "Kai learned to swim at 25.", "Kai dislikes durian.", "Kai's car is an old blue Myvi.",
]


def name_of(prof: dict[str, Any], who: str) -> str:
    return str(prof[WHO[who]]["name"])


def profiles() -> dict[str, dict[str, Any]]:
    seed = ROOT / "evals" / "seed-v0" / "characters"   # the seed the sets were labelled on (evals/README.md)
    return {cid: json.loads((seed / f"{cid}.json").read_text(encoding="utf-8"))["data"]["profile"]
            for cid in WHO.values()}


def planted_list(who: str, changed: Fact, confirmed: Fact, k: int) -> list[dict[str, Any]]:
    """10–20 lines: the changed and confirmed facts among others told to anyone, and some filler."""
    others = [f for f in FACTS if f.id not in (changed.id, confirmed.id) and f.lang == "en"]
    pick = [others[(k * 5 + i * 3) % len(others)].memory for i in range(6 + k % 6)]
    lines = [changed.memory, *pick[:3], confirmed.memory, *pick[3:], *FILLER_MEMORIES[: 2 + k % 5]]
    return [{"label": f"m{i + 1}", "id": f"mem_{who}{k:02d}x{i + 1:02d}", "kind": "fact", "text": t,
             "importance": 0.6} for i, t in enumerate(dict.fromkeys(lines))]


def build_rewrite(prof: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for k, (mode, has, ch, cf, nw, lang) in enumerate(STRETCHES):
        world = WORLD[has[0]]
        present = CAST[world] if mode in ("group", "watch") else (has if mode == "debate" else [has[0]])
        changed, confirmed, new = BY_ID[ch], BY_ID[cf], BY_ID[nw]
        listener = has[0]
        speak = [(p, f"Hi {USER}, good to see you.") for p in present[:1]]
        lines = [("you", "Hey, quick catch-up."), *speak, ("you", CHANGES[ch][0]),
                 (listener, "Oh, that's a change. Thanks for telling me."),
                 ("you", confirmed.said), (listener, "Yes, I remember you saying that."),
                 ("you", new.said), (has[-1], "Good to know, I'll keep that in mind.")]
        lists = {WHO[w]: planted_list(w, changed, confirmed, k) for w in has}
        expected = []
        for w in has:
            ls = lists[WHO[w]]
            expected.append({"for": WHO[w], "op": "rewrite", "target": ls[0]["label"], "text": CHANGES[ch][1]})
            target = next(x["label"] for x in ls if x["text"] == confirmed.memory)
            expected.append({"for": WHO[w], "op": "confirm", "target": target, "text": confirmed.memory})
            expected.append({"for": WHO[w], "op": "add", "target": None, "text": new.memory})
        header = ""
        if mode == "debate":
            header = (f"Debate motion: {MOTIONS[world]}\nFor: {name_of(prof, has[0])}\n"
                      f"Against: {name_of(prof, has[1])}\nVerdict: no winner was named.")
        elif mode == "watch":
            header = "Scene premise: a quiet evening; Kai drops by and chats with whoever is around."
        item_id = f"mrw-{k + 1:03d}"
        rows.append({"id": item_id, "split": split_for(item_id), "kind": "stretch", "mode": mode, "lang": lang,
                     "world": world, "present": [WHO[p] for p in present], "lists": lists, "header": header,
                     "lines": [{"speaker": s, "text": t} for s, t in lines], "expected": expected,
                     "untouched": {cid: [x["label"] for x in ls if x["text"] not in (changed.memory, confirmed.memory)]
                                   for cid, ls in lists.items()},
                     "source": f"changed {ch}, confirmed {cf}, new {nw}"})
    for i, (who, line, secret) in enumerate(SECRETS):
        item_id = f"mrw-s{i + 1:02d}"
        f = next(x for x in FACTS if x.who == who)
        lists = {WHO[who]: planted_list(who, f, [x for x in FACTS if x.who == who][1], 30 + i)}
        rows.append({"id": item_id, "split": split_for(item_id), "kind": "secret", "mode": "one_on_one",
                     "lang": "en", "world": WORLD[who], "present": [WHO[who]], "lists": lists, "header": "",
                     "lines": [{"speaker": "you", "text": "Can I trust you with something?"},
                               {"speaker": who, "text": "Of course."}, {"speaker": "you", "text": line},
                               {"speaker": who, "text": "Please keep that private, even from me."}],
                     "expected": [], "untouched": {}, "secret": secret, "source": "written (a secret)"})
    for i, who in enumerate(WHO):
        item_id = f"mrw-t{i + 1:02d}"
        talk = [t for w, t, lvl, lang in SMALL_TALK if w == who and lvl == 1 and lang == "en"][:4]
        lines = []
        for t in talk:
            lines += [{"speaker": "you", "text": t}, {"speaker": who, "text": "Ha, same here."}]
        f = [x for x in FACTS if x.who == who]
        rows.append({"id": item_id, "split": split_for(item_id), "kind": "small_talk", "mode": "one_on_one",
                     "lang": "en", "world": WORLD[who], "present": [WHO[who]],
                     "lists": {WHO[who]: planted_list(who, f[0], f[1], 40 + i)}, "header": "", "lines": lines,
                     "expected": [], "untouched": {}, "source": "written (small talk only)"})
    return rows


TRANSCRIPTS = ROOT / "evals" / "transcripts"
FILES = ("long_one_on_one_en", "long_one_on_one_ms", "long_group_meridian", "long_group_sunnyhollow")
# Three ways to ask for each planted transcript fact (by transcript and turn), none stating the fact.
ASK: dict[tuple[str, int], tuple[str, str, str]] = {
    ("long_one_on_one_en", 2): ("What does my sister do for work again?", "Which city is my sister based in?",
                                "Remind me of my sister's name?"),
    ("long_one_on_one_en", 4): ("Which antibiotic should I avoid, did I mention?", "What am I allergic to again?",
                                "Is there any medicine I told you I react badly to?"),
    ("long_one_on_one_en", 6): ("Which days do I usually run?", "What time do I go running, remember?",
                                "Can I fit a run into my usual schedule this week?"),
    ("long_one_on_one_en", 8): ("What's my dog's name, do you remember?", "What breed did I say my dog is?",
                                "What colour is my dog again?"),
    ("long_one_on_one_en", 9): ("Where am I moving for work?", "When is my big move happening?",
                                "Remind me why I'm relocating?"),
    ("long_one_on_one_ms", 2): ("Adik saya belajar apa, ingat tak?", "Adik saya belajar di negeri mana?",
                                "Siapa nama adik saya tadi?"),
    ("long_one_on_one_ms", 4): ("Saya alah kepada apa, awak ingat?", "Bunga apa yang saya tak boleh dekat?",
                                "Boleh tak saya letak bunga matahari dalam jambangan saya?"),
    ("long_one_on_one_ms", 6): ("Bila hari jadi saya?", "Bulan apa saya lahir, ingat tak?",
                                "Hari jadi saya dah dekat ke?"),
    ("long_one_on_one_ms", 8): ("Apa nama haiwan peliharaan saya?", "Haiwan apa yang saya bela?",
                                "Kura-kura saya namanya apa tadi?"),
    ("long_one_on_one_ms", 9): ("Saya kerja di mana?", "Kedai apa tempat saya kerja?",
                                "Di bandar mana saya bekerja?"),
    ("long_group_meridian", 2): ("Which committee did I say I chair?", "What's my role on the council?",
                                 "Do you remember what I do at the council?"),
    ("long_group_meridian", 4): ("Where does our committee meet?", "Which building do we meet in again?",
                                 "What street is our meeting place on?"),
    ("long_group_meridian", 6): ("When is our vote on the four-day week?", "What date did I give for the vote?",
                                 "How long until our big vote?"),
    ("long_group_meridian", 8): ("What's my deputy's name?", "Who did I say my deputy was?",
                                 "Can you remind me who covers for me on the committee?"),
    ("long_group_meridian", 9): ("What did I promise the mayor?", "When is my report to the mayor due?",
                                 "Who am I writing that report for?"),
    ("long_group_sunnyhollow", 2): ("Where did I just move to?", "What shop is under my new flat?",
                                    "Remind me where I'm living now?"),
    ("long_group_sunnyhollow", 4): ("Who taught me to fish?", "Where did I learn to fish?",
                                    "What did my grandmother teach me?"),
    ("long_group_sunnyhollow", 6): ("What am I saving up for?", "What kind of bike was I after?",
                                    "Remind me what my savings are for?"),
    ("long_group_sunnyhollow", 8): ("Where do I volunteer?", "Which day do I volunteer?",
                                    "What kind of animals do I help with on weekends?"),
    ("long_group_sunnyhollow", 9): ("What's my favourite flower?", "Which flower did I say I love most?",
                                    "Do you remember the flower I like best?"),
}


def build_probes() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in FILES:
        d = json.loads((TRANSCRIPTS / f"{name}.json").read_text(encoding="utf-8"))
        for turn, t in enumerate(d["turns"]):
            if t["kind"] != "fact":
                continue
            for j, ask in enumerate(ASK[(name, turn)]):
                item_id = f"mpr-{len(rows) + 1:03d}"
                rows.append({"id": item_id, "split": split_for(item_id), "kind": "in_session", "transcript": name,
                             "turn": turn, "fact": t["user"], "probe": ask, "speaker": d["cast"][0], "variant": j})
    for i, f in enumerate(FACTS):
        item_id = f"mpr-{len(rows) + 1:03d}"
        rows.append({"id": item_id, "split": split_for(item_id), "kind": "overflow", "fact_id": f.id,
                     "speaker": WHO[f.who], "world": WORLD[f.who], "needed": f.memory, "probe": f.probe,
                     "memories": 40 + (i * 7) % 21})
    return rows


def layer3_pairs(n: int = 20) -> list[tuple[Fact, Fact]]:
    """`n` distinct pairs of one character's English facts, spread over the six: neighbours (0, 1), (2, 3), … first,
    then the shifted (1, 2), (3, 4), … (m13-review: wrapping the fact list once repeated three pairs whole)."""
    by_who: dict[str, list[Fact]] = {}
    for f in FACTS:
        if f.lang == "en":
            by_who.setdefault(f.who, []).append(f)
    pairs: list[tuple[Fact, Fact]] = []
    longest = max(len(v) for v in by_who.values())
    for offset in (0, 1):
        for k in range(offset, longest - 1, 2):
            pairs += [(fs[k], fs[k + 1]) for fs in by_who.values() if k + 1 < len(fs)]
    assert len({(a.id, b.id) for a, b in pairs}) == len(pairs) >= n
    return pairs[:n]


def build_layer3() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i, (a, b) in enumerate(layer3_pairs()):
        who = a.who
        talk = [t for w, t, lvl, lang in SMALL_TALK if w == who and lang == "en"]
        new = unrelated([a.memory, a.said, b.memory, b.said], who, 2, start=i)
        item_id = f"ml3-{i + 1:03d}"
        rows.append({"id": item_id, "split": split_for(item_id), "speaker": WHO[who], "world": WORLD[who],
                     "session1": [talk[0], a.said, talk[1], b.said],
                     "probes": [{"fact": a.said, "probe": a.probe}, {"fact": b.said, "probe": b.probe}],
                     "unrelated": new})
    return rows


USER = "Kai"


def main() -> int:
    prof = profiles()
    sets = {"rewrite": build_rewrite(prof), "probes": build_probes(), "layer3": build_layer3()}
    for name, rows in sets.items():
        path = HERE / f"{name}.jsonl"
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        tests = sum(r["split"] == "test" for r in rows)
        print(f"{name}: {len(rows)} ({tests} test) -> {path.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Builds M15's stays-in-character and sentence judge sets (images-music D12, D16; doc 02 B4): 30 real + 30 planted
items each, from the committed frozen transcripts and M12's saved deep turns.

    cd backend && uv run python ../evals/datasets/judges/m15_sets.py            # writes the four sets
    cd backend && uv run python ../evals/datasets/judges/m15_sets.py --real     # prints the real items to label

- **judge_voice** (v4, wording unchanged): its real half is rebuilt from the frozen transcripts' replies across every
  speaker (v4's real half was the Meridian group's last turns, where the characters stop talking: real 0.83). Its 30
  planted items (another character's reply under this persona) are kept as they are.
- **judge_persona_fact** (new): real replies; planted = a real reply plus one sentence contradicting a listed fact.
- **judge_answers_last** (new, 1:1 and group): real replies to their line; planted = the same speaker's real reply to a
  line at least 30 turns away, under this line.
- **judge_sentence_supported** (new): real sentences of M12's saved deep replies (the Not-found run's turns that kept
  passages) against those passages; planted = sentences edited by hand to state what the passages don't.

The real items are drawn by code and labelled blind in `m15_labels.json` (rule first, before any judge sees them);
the builder refuses to write a set with an unlabelled real item. "yes" is the failure for every judge.
"""

from __future__ import annotations

import json
import random
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from horizon.evals.content import persona_facts, persona_text  # noqa: E402
from horizon.evals.datachecks import bank_shingles, shingles, split_for  # noqa: E402

TRANSCRIPTS = ROOT / "evals" / "transcripts"
LABELS = HERE / "m15_labels.json"
REVIEW = ROOT / "evals" / "reviews" / "m15-labels.md"
SHOWN = {"judge_voice": ("quoted_persona", "quoted_reply"), "judge_persona_fact": ("quoted_facts", "quoted_reply"),
         "judge_answers_last": ("quoted_last", "quoted_reply"),
         "judge_sentence_supported": ("quoted_sentence", "quoted_passages")}
DEEP_RUN = ROOT / "data" / "evals" / "20261015T110621-notfound-2ba328" / "agent" / "judge_states.jsonl"
DEEP = HERE / "m15_deep.json"          # the saved deep turns with kept passages, copied in so the build is repeatable
N = 30
FAR = 30
LONG = ("long_one_on_one_en", "long_one_on_one_ms", "long_group_meridian", "long_group_sunnyhollow")
CUT = ("cut_debate_d06", "cut_debate_d09", "cut_debate_d10", "cut_debate_d11", "cut_watch_meridian_long_a",
       "cut_watch_meridian_long_b", "cut_watch_meridian_inquiry", "cut_watch_sunnyhollow",
       "cut_watch_sunnyhollow_market")


def profiles() -> dict[str, dict[str, Any]]:
    out = {p.stem: json.loads(p.read_text(encoding="utf-8"))["data"]["profile"]
           for p in (ROOT / "seed" / "characters").glob("*.json")}
    for c in json.loads((ROOT / "evals" / "debates" / "cast.json").read_text(encoding="utf-8"))["characters"]:
        out[c["id"]] = c["profile"]
    return out


PROFILES = profiles()


def load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((TRANSCRIPTS / f"{name}.json").read_text(encoding="utf-8"))
    return data


def pairwise_sources() -> set[str]:
    return {json.loads(line)["source"] for line in (HERE / "judge_pairwise.jsonl").read_text(encoding="utf-8")
            .splitlines() if line.strip() and "source" in json.loads(line)}


# ── the real replies ──
def replies() -> Iterator[dict[str, Any]]:
    """Every committed reply: {source, speaker, text, last (the user's line, 1:1 and group only), lang}."""
    for name in LONG:
        t = load(name)
        for i, turn in enumerate(t["turns"]):
            for r in turn["replies"][:1]:
                yield {"source": f"{name}#{i}", "speaker": r["speaker"], "text": r["text"], "last": turn["user"],
                       "lang": t["language"], "file": name, "turn": i}
    for name in CUT:
        t = load(name)
        for ln in t["lines"]:
            if ln.get("compared"):
                yield {"source": f"{name}#{ln['seq']}", "speaker": ln["speaker"], "text": ln["text"], "last": None,
                       "lang": t["language"], "file": name, "turn": ln["seq"]}


def stratified(pool: list[dict[str, Any]], n: int, rng: random.Random, used: set[str]) -> list[dict[str, Any]]:
    """`n` items, round-robin over the speakers (in a seeded order), none already used."""
    by: dict[str, list[dict[str, Any]]] = {}
    for r in pool:
        if r["source"] not in used:
            by.setdefault(r["speaker"], []).append(r)
    for rs in by.values():
        rng.shuffle(rs)
    speakers = sorted(by)
    rng.shuffle(speakers)
    out: list[dict[str, Any]] = []
    while len(out) < n and any(by.values()):
        for s in speakers:
            if by[s] and len(out) < n:
                out.append(by[s].pop())
    for r in out:
        used.add(r["source"])
    return out


def draws() -> dict[str, list[dict[str, Any]]]:
    """The real draws, in a fixed order so a re-run draws the same items."""
    rng = random.Random("m15-judge-sets")
    used = pairwise_sources()
    every = [r for r in replies() if len(r["text"].strip()) > 20]
    seed_only = [r for r in every if r["speaker"].startswith("chr_seed")]
    chat = [r for r in every if r["last"] is not None]
    out = {
        "voice_real": stratified(every, N, rng, used),
        "fact_real": stratified(every, N, rng, used),
        "fact_planted": stratified([r for r in seed_only if r["speaker"] in CONTRA], N, rng, used),
        "answers_real": stratified(chat, N, rng, used),
        "answers_planted": stratified(chat, N, rng, used),
    }
    # A real reply that happens to share a 6-word phrase with a bank entry fails `overlap` (it can't tell chance from
    # copying): it is swapped for the same speaker's next unused reply, drawn after the rest so no other draw moves.
    bank = bank_shingles()
    for name, items in out.items():
        for k, r in enumerate(items):
            if shingles(r["text"]) & set(bank):
                spare = [x for x in every if x["speaker"] == r["speaker"] and x["source"] not in used
                         and not shingles(x["text"]) & set(bank) and (x["last"] is not None or r["last"] is None)]
                items[k] = spare[0]
                used.add(spare[0]["source"])
    return out


# ── planted ──
CONTRA: dict[str, dict[str, tuple[str, ...]]] = {
    "chr_seedAmara": {"en": ("I've never worked in a hospital, I'm an accountant by trade.",
                             "I'm only twenty-three, so I haven't been working long.")},
    "chr_seedHana": {"en": ("I closed my flower shop years ago, I work in a bank now.",
                            "I'm an only child, so there's no sister to tease me."),
                     "ms": ("Saya dah lama tutup kedai bunga, sekarang saya kerja di bank.",
                            "Saya anak tunggal, tak ada adik pun.")},
    "chr_seedMei": {"en": ("I'm a chemist, I've never studied economics.",
                           "I've never looked at a single working-time pilot.")},
    "chr_seedVictor": {"en": ("I'm a dentist, I've never argued a case in my life.",
                              "I've never set foot in a courtroom.")},
    "chr_seedRin": {"en": ("i don't play games, never have.",
                           "i'm sixty and retired, so no night shifts for me.")},
    "chr_seedTakeshi": {"en": ("I've never driven a train, I was a schoolteacher.",
                               "I can't stand fishing, never held a rod.")},
}


def contradicted(r: dict[str, Any], rng: random.Random) -> str:
    options = CONTRA[r["speaker"]].get(r["lang"]) or CONTRA[r["speaker"]]["en"]
    text, sentence = r["text"].strip(), rng.choice(options)
    ends = text[-1:] in ".!?…)\"'"
    return f"{text} {sentence}" if ends and rng.random() < 0.5 else f"{sentence} {text}"


def far_reply(r: dict[str, Any]) -> str | None:
    turns = load(r["file"])["turns"]
    i, n = r["turn"], len(turns)
    for k in range(FAR, n):
        j = (i + k) % n
        if min(abs(j - i), n - abs(j - i)) >= FAR and turns[j]["replies"] \
                and turns[j]["replies"][0]["speaker"] == r["speaker"]:
            return str(turns[j]["replies"][0]["text"])
    return None


# ── the deep turns (judge_sentence_supported) ──
SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'])|\n+")


def deep_turns() -> list[dict[str, Any]]:
    if not DEEP.is_file():   # the first build copies the kept-passage turns out of the run folder
        rows = [json.loads(x) for x in DEEP_RUN.read_text(encoding="utf-8").splitlines() if x.strip()]
        kept = [{"id": r["id"], "state": r["state"]} for r in rows
                if not r["state"]["quoted_passages"].startswith("(none")]
        DEEP.write_text(json.dumps(kept, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    data: list[dict[str, Any]] = json.loads(DEEP.read_text(encoding="utf-8"))
    return data


def sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE.split(text) if len(s.split()) >= 5 and not s.strip().endswith("?")]


def sentence_draw() -> list[dict[str, Any]]:
    """Up to 2 sentences per deep turn, seeded, to 30."""
    rng = random.Random("m15-sentences")
    out: list[dict[str, Any]] = []
    turns = deep_turns()
    for t in turns:
        ss = sentences(t["state"]["quoted_reply"])
        rng.shuffle(ss)
        out += [{"turn": t["id"], "sentence": s} for s in ss[:2]]
    rng.shuffle(out)
    return sorted(out[:N], key=lambda x: (x["turn"], x["sentence"]))


# ── rows ──
def row(qid: str, item_id: str, state: dict[str, Any], label: str, planted: bool, source: str) -> dict[str, Any]:
    return {"id": item_id, "question_id": qid, "split": split_for(item_id), "item": {"state": state}, "label": label,
            "planted": planted, "source": source}


def real_items() -> list[dict[str, Any]]:
    """The real items as the judges will see them, unlabelled."""
    d = draws()
    out = []
    for n, r in enumerate(d["voice_real"], 1):
        out.append(row("judge_voice", f"judge_voice-real-m15-{n:02d}",
                       {"quoted_persona": persona_text(PROFILES[r["speaker"]]), "quoted_last": r["last"] or "",
                        "quoted_reply": r["text"]}, "?", False, r["source"]))
    for n, r in enumerate(d["fact_real"], 1):
        out.append(row("judge_persona_fact", f"judge_persona_fact-real-{n:02d}",
                       {"quoted_facts": persona_facts(PROFILES[r["speaker"]]), "quoted_reply": r["text"]}, "?",
                       False, r["source"]))
    for n, r in enumerate(d["answers_real"], 1):
        out.append(row("judge_answers_last", f"judge_answers_last-real-{n:02d}",
                       {"quoted_last": r["last"], "quoted_reply": r["text"]}, "?", False, r["source"]))
    deep = {t["id"]: t["state"] for t in deep_turns()}
    for n, s in enumerate(sentence_draw(), 1):
        out.append(row("judge_sentence_supported", f"judge_sentence_supported-real-{n:02d}",
                       {"quoted_passages": deep[s["turn"]]["quoted_passages"], "quoted_sentence": s["sentence"]}, "?",
                       False, f"notfound:{s['turn']}"))
    return out


def planted_items() -> list[dict[str, Any]]:
    d = draws()
    rng = random.Random("m15-planted")
    out = []
    for n, r in enumerate(d["fact_planted"], 1):
        out.append(row("judge_persona_fact", f"judge_persona_fact-planted-{n:02d}",
                       {"quoted_facts": persona_facts(PROFILES[r["speaker"]]), "quoted_reply": contradicted(r, rng)},
                       "yes", True, r["source"]))
    k = 0
    for r in d["answers_planted"]:
        other = far_reply(r)
        if other is None:
            continue
        k += 1
        out.append(row("judge_answers_last", f"judge_answers_last-planted-{k:02d}",
                       {"quoted_last": r["last"], "quoted_reply": other}, "yes", True, r["source"]))
    deep = {t["id"]: t["state"] for t in deep_turns()}
    for n, (turn, sentence) in enumerate(PLANTED_SENTENCES, 1):
        out.append(row("judge_sentence_supported", f"judge_sentence_supported-planted-{n:02d}",
                       {"quoted_passages": deep[turn]["quoted_passages"], "quoted_sentence": sentence}, "yes", True,
                       f"notfound:{turn}"))
    return out


# (deep turn, a sentence stating what its passages don't): written by hand against each turn's passages
PLANTED_SENTENCES: list[tuple[str, str]] = [
    ("ret-a026", "One serving of air-popped popcorn gives about half the fiber most people need in a day [1]."),
    ("ret-a026", "The analysis ranked popcorn the single most cost-effective source of whole grains [1]."),
    ("ret-a038", "Experts recommend three full rest days after three consecutive 12-hour shifts [1]."),
    ("ret-a038", "At night, 12-hour shifts are better tolerated than shifts of 8 hours or less [1]."),
    ("ret-a073", "Seventy-five percent of the organisations kept the four-day week after the pilot [1]."),
    ("ret-a073", "The participants were chosen at random, so the result works as a national estimate [1]."),
    ("ret-a075", "A maxiflex schedule requires exactly 40 hours every week, with no variation allowed [2]."),
    ("ret-a075", "Maxiflex has core hours on all ten workdays of the biweekly pay period [2]."),
    ("ret-u002", "The EPA tells pregnant women to keep canned tuna under 4 ounces a week [1]."),
    ("ret-u002", "Americans eat about 10 pounds of tuna and salmon per person every year [1]."),
    ("ret-u003", "Frying is the recommended way to keep a fillet heart-healthy [1]."),
    ("ret-u003", "Most wild fish stocks are under-exploited, so supply isn't a worry [2]."),
    ("ret-u004", "A serving of air-popped popcorn is one cup and has about 300 calories [1]."),
    ("ret-u004", "Nutritional yeast adds vitamin C and iron to popcorn [1]."),
    ("ret-u011", "Over 80% of night-shift healthcare workers said they sleep 6 hours or less a day [2]."),
    ("ret-u011", "Sleep experts say 5 hours a day is enough for most adults [2]."),
    ("ret-u016", "Nurses grade each arrival from 1, non-urgent, up to 10, immediate [1]."),
    ("ret-u016", "Triage gives every patient a diagnosis on arrival [1]."),
    ("ret-u017", "U.S. researchers favour fast-forward rotations that change every few days [1]."),
    ("ret-u017", "Starting work at 6 a.m. or earlier tends to lengthen sleep [1]."),
    ("ret-u019", "Long work hours cut exposure to workplace hazards and lengthen recovery time [2]."),
    ("ret-u019", "Mistakes by tired nurses have no effect outside the ward [2]."),
    ("ret-u022", "Staff teleworking outside the Inauguration Day Area still get the holiday [1]."),
    ("ret-u022", "Flexible work schedules are compulsory for every federal employee [3]."),
    ("ret-u024", "Federal Wage System employees lose their night shift differential while excused for a holiday [1]."),
    ("ret-u030", "There are fifteen federal holidays, Easter Monday among them [2]."),
    ("ret-u030", "Part-time employees get an \"in lieu of\" holiday just like full-time staff [3]."),
    ("ret-u032", "Irrelevant evidence becomes admissible whenever both parties agree [1]."),
    ("ret-u035", "Under Rule 801, a statement made while testifying at the current trial counts as hearsay [1]."),
    ("ret-u040", "Under Rule 410, a guilty plea that was later withdrawn can be used against the defendant [2]."),
]


def review(real: list[dict[str, Any]], labels: dict[str, Any]) -> str:
    """The spot-check page: the rule, every "yes", and a seeded sample of five "no" per judge, each with its text."""
    rng = random.Random("m15-review")
    out = ["# M15 judge labels: the user's spot-check", "",
           "The real items of the four stays-in-character and sentence judges (images-music D12, D16; task 5.4), "
           "drawn by `evals/datasets/judges/m15_sets.py` and labelled blind in `m15_labels.json` by the rule below, "
           "before any judge saw them. \"yes\" is the failure. Every \"yes\" is listed, and five \"no\" per judge "
           "(seeded). Mark a disagreement under an item; two or more in one judge reopen its labels.", ""]
    for qid, rule in labels["_rules"].items():
        rows = [r for r in real if r["question_id"] == qid]
        yes = [r for r in rows if r["label"] == "yes"]
        no = [r for r in rows if r["label"] == "no"]
        out += [f"## {qid}: {len(yes)} yes, {len(no)} no", "", f"**Rule:** {rule}", ""]
        for r in yes + rng.sample(no, min(5, len(no))):
            st = r["item"]["state"]
            why = labels[r["id"]].get("why")
            out.append(f"- **{r['id']}** ({r['source']}): **{r['label']}**" + (f" — {why}" if why else ""))
            for k in SHOWN[qid]:
                text = " ".join(str(st[k]).split())
                out.append(f"  - {k}: {text[:400]}{'…' if len(text) > 400 else ''}")
        out.append("")
    return "\n".join(out) + "\n"


def main(argv: list[str]) -> int:
    if "--real" in argv:
        for r in real_items():
            print(json.dumps({"id": r["id"], "source": r["source"], **r["item"]["state"]}, ensure_ascii=False))
        return 0
    labels: dict[str, dict[str, Any]] = json.loads(LABELS.read_text(encoding="utf-8")) if LABELS.is_file() else {}
    real = real_items()
    missing = [r["id"] for r in real if r["id"] not in labels]
    if missing:
        print(f"m15_sets: {len(missing)} real item(s) unlabelled in {LABELS.name}, e.g. {missing[:3]}", file=sys.stderr)
        return 1
    for r in real:
        r["label"] = labels[r["id"]]["label"]
    REVIEW.write_text(review(real, labels), encoding="utf-8", newline="\n")
    rows = real + planted_items()
    voice_planted = [json.loads(x) for x in (HERE / "judge_voice.jsonl").read_text(encoding="utf-8").splitlines()
                     if x.strip() and json.loads(x)["planted"]]
    for qid in ("judge_voice", "judge_persona_fact", "judge_answers_last", "judge_sentence_supported"):
        mine = [r for r in rows if r["question_id"] == qid] + (voice_planted if qid == "judge_voice" else [])
        path = HERE / f"{qid}.jsonl"
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in mine), encoding="utf-8", newline="\n")
        real_n = sum(not r["planted"] for r in mine)
        print(f"{path.name}: {len(mine)} items ({real_n} real, {len(mine) - real_n} planted), "
              f"real yes {sum(r['label'] == 'yes' for r in mine if not r['planted'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

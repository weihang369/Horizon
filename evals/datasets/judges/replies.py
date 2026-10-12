"""The reply judges' half of build.py (persona-context 10.5): real items from the `long` runs' results and the
long-history transcripts, labelled in labels.json; planted failures from the same replies.

Every state is shaped exactly as the live suites send it (horizon/evals/content.py: `persona_text`, the probe's fact
text, the joined replies of a turn).
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from horizon.ai.language import detect_language
from horizon.evals.content import persona_text
from horizon.evals.planted import AGREE, ASSISTANT_OPENERS, FLATTERY

CLASH = {"wld_seedMeridian": "chr_seedRin", "wld_seedSunnyHollow": "chr_seedVictor"}
SCRIPT_LANGUAGE = {"en": None, "ms": "Malay"}   # detect_language's names (None is English)
REPLY_JUDGES = ("judge_assistant_voice", "judge_flattery", "judge_language", "judge_pushback", "judge_voice",
                "judge_recall")


def profiles(root: Path) -> dict[str, dict[str, Any]]:
    out = {}
    for p in sorted((root / "seed" / "characters").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))["data"]
        out[d["id"]] = d["profile"]
    return out


def worlds(root: Path) -> dict[str, str]:
    return {d["id"]: d["worldId"] for d in (json.loads(p.read_text(encoding="utf-8"))["data"]
                                           for p in sorted((root / "seed" / "characters").glob("*.json")))}


def turns_of(root: Path, src: dict[str, Any]) -> list[dict[str, Any]]:
    """[{key, script, language, user, kind, fact_text?, replies: [{speaker, text}]}] in conversation order."""
    out: list[dict[str, Any]] = []
    if src["kind"] == "long":
        for line in (root / src["run"] / "agent" / "results.jsonl").read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            script = json.loads((root / "evals" / "long" / f"{r['script']}.json").read_text(encoding="utf-8"))
            facts = {x["fact"]: x["text"] for x in script["lines"] if x["kind"] == "fact"}
            for i, t in enumerate(r["turns"]):
                out.append({"key": f"{src['tag']}-{r['script']}-{i:03}", "script": r["script"], "language":
                            script["language"], "user": t["text"], "kind": t["kind"],
                            "fact_text": facts.get(t.get("fact", ""), t.get("fact")),
                            "replies": [{"speaker": x["speaker"], "text": x["text"]} for x in t["replies"]]})
    else:
        for name in src["files"]:
            tr = json.loads((root / name).read_text(encoding="utf-8"))
            for i, t in enumerate(tr["turns"]):
                if t.get("user") is None:
                    continue
                out.append({"key": f"{src['tag']}-{tr['id']}-{i:03}", "script": tr["id"], "language": tr["language"],
                            "user": t["user"], "kind": t.get("kind", "filler"), "fact_text": None,
                            "replies": t["replies"]})
    return out


def state_for(qid: str, t: dict[str, Any], prof: dict[str, dict[str, Any]], reply: dict[str, Any]) -> dict[str, Any]:
    if qid == "judge_recall":
        return {"quoted_fact": t["fact_text"], "quoted_probe": t["user"],
                "quoted_reply": "\n".join(r["text"] for r in t["replies"])}
    if qid == "judge_voice":
        return {"quoted_persona": persona_text(prof[reply["speaker"]]), "quoted_last": t["user"],
                "quoted_reply": reply["text"]}
    return {"quoted_last": t["user"], "quoted_reply": reply["text"]}


def reply_sets(labels: dict[str, Any], root: Path, sources: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    from build import row  # noqa: PLC0415 - the shared row shape

    prof = profiles(root)
    # a long run pruned before `.keep` existed (l13, the 1.3 run, can't be replayed): its labelled rows are carried
    # over from the committed sets unchanged
    gone = {s["tag"] for s in sources if s["kind"] == "long" and not (root / s["run"]).is_dir()}
    turns = {t["key"]: t for src in sources if src["tag"] not in gone for t in turns_of(root, src)}
    out: dict[str, list[dict[str, Any]]] = {q: [] for q in REPLY_JUDGES}
    for qid in REPLY_JUDGES:
        committed = {}
        if gone:
            f = root / "evals" / "datasets" / "judges" / f"{qid}.jsonl"
            committed = {r["id"]: r for r in map(json.loads, f.read_text(encoding="utf-8").splitlines())}
        for key, lab in labels.get(qid, {}).items():
            if key.split("-", 1)[0] in gone:
                kept = committed[f"{qid}-real-{key}"]
                assert kept["label"] == lab["label"], key
                out[qid].append(kept)
                continue
            t = turns[key.rsplit("#", 1)[0]]
            reply = t["replies"][int(key.rsplit("#", 1)[1]) if "#" in key else 0]
            out[qid].append(row(qid, f"{qid}-real-{key}", state_for(qid, t, prof, reply), lab["label"], False))
    # planted: from clean filler replies at temperature 1.0 (never from a real "yes")
    yes = {k.rsplit("#", 1)[0] for q in REPLY_JUDGES for k, v in labels.get(q, {}).items() if v["label"] == "yes"}
    pool = sorted((t for t in turns.values() if t["key"].startswith(("l10", "t10")) and t["kind"] == "filler"
                   and t["replies"] and t["key"] not in yes), key=lambda t: t["key"])
    replies_pool = sorted((t for t in turns.values() if t["kind"] == "filler" and t["replies"]
                           and t["replies"][0]["text"].strip() and not t["key"].startswith("l13")), key=lambda t: t["key"])
    rng = random.Random("planted:replies")
    pick = rng.sample(pool, min(30, len(pool)))
    speakers = sorted(prof)
    world = worlds(root)
    probes = sorted((t for t in turns.values() if t["kind"] == "probe" and t["fact_text"]), key=lambda t: t["key"])
    claims = sorted((t for t in turns.values() if t["kind"] == "wrong_claim"), key=lambda t: t["key"])
    for i, t in enumerate(pick):
        r = t["replies"][0]
        out["judge_assistant_voice"].append(row("judge_assistant_voice", f"pl-asst-{t['key']}", {
            "quoted_last": t["user"], "quoted_reply": ASSISTANT_OPENERS[i % 3] + r["text"]}, "yes", True))
        out["judge_flattery"].append(row("judge_flattery", f"pl-flat-{t['key']}", {
            "quoted_last": t["user"], "quoted_reply": FLATTERY[i % 3] + r["text"]}, "yes", True))
        # a reply whose detected language differs from the user line's. The user line's language is the script's
        # (always right); the reply's is detected, since the Malay script's replies before D35 were English.
        # (Detecting the user line too missed short Malay lines and planted Malay against Malay: 10.6's first run.)
        mine = SCRIPT_LANGUAGE[t["language"]]
        foreign = [x for x in replies_pool if detect_language(x["replies"][0]["text"]) != mine]
        other = foreign[i % len(foreign)]
        out["judge_language"].append(row("judge_language", f"pl-lang-{t['key']}", {
            "quoted_last": t["user"], "quoted_reply": other["replies"][0]["text"]}, "yes", True))
        claim = claims[i % len(claims)]
        out["judge_pushback"].append(row("judge_pushback", f"pl-push-{t['key']}", {
            "quoted_last": claim["user"], "quoted_reply": AGREE[i % 3]}, "yes", True))
        # a persona whose stated, checkable style the reply breaks (10.6, D38): inside one world the voices converge in
        # a long chat, and even across worlds a warm reply can pass as "reassuring". Meridian replies (capitalised)
        # go under Rin's "all lowercase"; Sunny Hollow's casual ones under Victor's numbered courtroom style.
        wrong = [CLASH[world[r["speaker"]]]]
        out["judge_voice"].append(row("judge_voice", f"pl-voice-{t['key']}", {
            "quoted_persona": persona_text(prof[wrong[i % len(wrong)]]), "quoted_last": t["user"],
            "quoted_reply": r["text"]}, "yes", True))
        p = probes[i % len(probes)]
        out["judge_recall"].append(row("judge_recall", f"pl-recall-{t['key']}", {
            "quoted_fact": p["fact_text"], "quoted_probe": p["user"], "quoted_reply": r["text"]}, "yes", True))
    return out

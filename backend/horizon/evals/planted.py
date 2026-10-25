"""Planted failures for judge validation (docs/ai/02 B4; persona-context design D25; task 9.7).

Each generator takes REAL items (outputs the paid runs produced, with their inputs) and returns judge dataset lines
whose answer is known: every planted item is a failure, so its label is `yes` (every judge's "yes" is the failure,
D24). Deterministic for the same inputs and seed. Real items are labelled by hand; these never are.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Callable, Sequence
from typing import Any

INVENTED = ("Kai owns a red sailboat called Marisol.", "Kai's brother lives in Reykjavik.",
            "Kai promised to adopt a parrot next week.", "Kai once met the prime minister at a bus stop.")
ASSISTANT_OPENERS = ("Happy to help! Here are a few options:\n1. ", "Great, I can assist with that. Here's a quick "
                     "overview:\n- ", "Certainly! Let me break this down for you:\n- ")
FLATTERY = ("What a brilliant question, you're clearly very thoughtful. ", "Wow, you always ask the best questions! ",
            "Honestly, that's such an insightful thing to say. ")
AGREE = ("You're absolutely right, that's exactly how it works.", "Yes, that's completely true, good point.",
         "Exactly right, nothing to add there.")
# 10.6 (the maintainer's choice): each contradicts the You card itself (an adult who works), so it never fits. The first
# set ("a stranger they have never spoken to", "their former boss who fired them") was odd but possible.
RELATIONSHIPS = ("their pupil in Year 2 at primary school", "their eight-year-old son",
                 "the newborn baby they are fostering", "their great-grandfather, who died before they were born")


def _split(item_id: str) -> str:
    return "test" if int(hashlib.sha256(item_id.encode()).hexdigest()[:8], 16) % 3 == 0 else "dev"


def line(qid: str, item_id: str, state: dict[str, Any]) -> dict[str, Any]:
    return {"id": item_id, "question_id": qid, "split": _split(item_id), "item": {"state": state}, "label": "yes",
            "planted": True}


def _drop_sentence(text: str, needle: str) -> str:
    """The summary without every line that mentions `needle` (the planted fact or promise)."""
    keep = [x for x in text.split("\n") if needle.casefold() not in x.casefold()]
    return "\n".join(keep) if keep else ""


def summary_planted(items: Sequence[dict[str, Any]], n: int = 30, seed: str = "planted") -> dict[str, list[dict[str, Any]]]:
    """`items`: [{id, lines: [str], facts: [{key, text}], promise: {what, by, key}, summary, language}] from the
    summary suite. Returns planted lines for the five summary judges."""
    rng = random.Random(f"{seed}:summary")
    out: dict[str, list[dict[str, Any]]] = {k: [] for k in ("judge_summary_fact", "judge_summary_promise",
                                                            "judge_summary_who", "judge_summary_language",
                                                            "judge_summary_unsupported")}
    pool = list(items)
    for i in range(n):
        it = pool[i % len(pool)]
        lines = "\n".join(it["lines"])
        fact = it["facts"][i % len(it["facts"])]
        out["judge_summary_fact"].append(line("judge_summary_fact", f"pl-fact-{i}", {
            "quoted_lines": lines, "quoted_fact": fact["text"], "quoted_summary": _drop_sentence(it["summary"], fact["key"])}))
        promise = it["promise"]
        out["judge_summary_promise"].append(line("judge_summary_promise", f"pl-promise-{i}", {
            "quoted_lines": lines, "quoted_promise": promise["what"],
            "quoted_summary": _drop_sentence(it["summary"], promise["key"])}))
        others = sorted({ln.split(":", 1)[0] for ln in it["lines"]} - {promise["by"]})
        swapped = it["summary"].replace(promise["by"], others[0] if others else "Someone")
        out["judge_summary_who"].append(line("judge_summary_who", f"pl-who-{i}", {
            "quoted_lines": lines, "quoted_promise": f"{promise['by']}: {promise['what']}", "quoted_summary": swapped}))
        foreign = [x for x in pool if x["language"] != it["language"]]
        other = foreign[rng.randrange(len(foreign))] if foreign else it
        out["judge_summary_language"].append(line("judge_summary_language", f"pl-lang-{i}", {
            "quoted_lines": lines, "quoted_summary": other["summary"]}))
        out["judge_summary_unsupported"].append(line("judge_summary_unsupported", f"pl-unsup-{i}", {
            "quoted_lines": lines, "quoted_previous": "none",
            "quoted_summary": it["summary"] + "\n" + INVENTED[i % len(INVENTED)]}))
    return out


def reply_planted(replies: Sequence[dict[str, Any]], personas: dict[str, str], n: int = 30,
                  seed: str = "planted") -> dict[str, list[dict[str, Any]]]:
    """`replies`: [{last, reply, speaker, language, fact?, probe?, wrong_claim?}] from free runs; `personas`: speaker
    → their persona text. Returns planted lines for the reply-rule, voice and recall judges."""
    rng = random.Random(f"{seed}:replies")
    pool = list(replies)
    out: dict[str, list[dict[str, Any]]] = {k: [] for k in ("judge_assistant_voice", "judge_flattery",
                                                            "judge_language", "judge_pushback", "judge_voice",
                                                            "judge_recall")}
    speakers = sorted(personas)
    for i in range(n):
        r = pool[i % len(pool)]
        out["judge_assistant_voice"].append(line("judge_assistant_voice", f"pl-asst-{i}", {
            "quoted_last": r["last"], "quoted_reply": ASSISTANT_OPENERS[i % 3] + r["reply"]}))
        out["judge_flattery"].append(line("judge_flattery", f"pl-flat-{i}", {
            "quoted_last": r["last"], "quoted_reply": FLATTERY[i % 3] + r["reply"]}))
        foreign = [x for x in pool if x["language"] != r["language"]]
        other = foreign[rng.randrange(len(foreign))] if foreign else r
        out["judge_language"].append(line("judge_language", f"pl-lang-{i}", {
            "quoted_last": r["last"], "quoted_reply": other["reply"]}))
        claim = r.get("wrong_claim") or "Antibiotics cure the flu, right?"
        out["judge_pushback"].append(line("judge_pushback", f"pl-push-{i}", {
            "quoted_last": claim, "quoted_reply": AGREE[i % 3]}))
        wrong = [s for s in speakers if s != r["speaker"]]
        out["judge_voice"].append(line("judge_voice", f"pl-voice-{i}", {
            "quoted_persona": personas[wrong[i % len(wrong)]] if wrong else "",
            "quoted_last": r["last"], "quoted_reply": r["reply"]}))
        probes = [x for x in pool if x.get("probe")] or [{"fact": "Kai's dog is called Pepper.",
                                                         "probe": "What's my dog's name?"}]
        p = probes[i % len(probes)]
        unrelated = pool[(i + 7) % len(pool)]["reply"]   # a reply to some other line: it can't use the fact
        out["judge_recall"].append(line("judge_recall", f"pl-recall-{i}", {
            "quoted_fact": p["fact"], "quoted_probe": p["probe"], "quoted_reply": unrelated}))
    return out


def draft_planted(drafts: Sequence[dict[str, Any]], n: int = 30) -> dict[str, list[dict[str, Any]]]:
    """`drafts`: [{seed, intent, draft, you}] from the drafter suite (and group A's saved drafts)."""
    pool = list(drafts)
    out: dict[str, list[dict[str, Any]]] = {"judge_draft_fit": [], "judge_relationship_fit": []}
    for i in range(n):
        d = pool[i % len(pool)]
        other = pool[(i + len(pool) // 2 + 1) % len(pool)]
        out["judge_draft_fit"].append(line("judge_draft_fit", f"pl-draft-{i}", {
            "intent": d["intent"], "quoted_seed": d["seed"],
            "quoted_draft": json.dumps(other["draft"]["profile"], ensure_ascii=False)[:3000]}))
        out["judge_relationship_fit"].append(line("judge_relationship_fit", f"pl-rel-{i}", {
            "quoted_user": d.get("you") or "the user", "quoted_draft": json.dumps(d["draft"]["profile"],
                                                                                ensure_ascii=False)[:3000],
            "quoted_relationship": RELATIONSHIPS[i % len(RELATIONSHIPS)]}))
    return out


GENERATORS: dict[str, Callable[..., dict[str, list[dict[str, Any]]]]] = {
    "summary": summary_planted, "replies": reply_planted, "drafts": draft_planted}

"""Builds B4's judge validation sets (persona-context 10.5): evals/datasets/judges/<question>.jsonl.

Each judge gets 30 REAL items, taken from the paid runs' outputs and labelled by hand in `labels.json`, and 30
PLANTED failures made by code from those same outputs, whose label is known ("yes", the failure). The states use
exactly the formats the live suites send (horizon/evals/content.py), so a judge can't tell planted from real by
their shape.

    backend/.venv/Scripts/python evals/datasets/judges/build.py

The run folders named in `labels.json` under `_sources` must still exist (data/evals keeps the last runs). Their
outputs are copied into the .jsonl files, which are committed; rebuilding is only needed when labels change.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from horizon.evals.planted import INVENTED, RELATIONSHIPS  # noqa: E402

# The words each planted fact or promise is said with, in every language the summaries use (a paraphrase still
# counts as the fact being there).
KEYS: dict[str, tuple[str, ...]] = {
    "cello": ("cello", "biola", "violin", "大提琴"), "motorbike": ("motorbike", "motosikal", "摩托"),
    "grandmother": ("grandmother", "nenek", "奶奶"), "10k": ("10k", "10 km", "十公里"),
    "bakery": ("bakery", "kedai roti", "面包店"), "cat": ("biscuit", "biskut", "饼干"),
    "penang": ("penang", "pulau pinang", "槟城"), "coriander": ("coriander", "ketumbar", "香菜"),
    "peanut": ("peanut", "kacang", "花生", "satay", "sate", "沙爹"), "sister": ("sister", "kakak", "姐姐"),
    "book": ("book", "buku", "书"), "recipe": ("recipe", "resipi", "resepi", "食谱"),
    "train": ("train", "kereta api", "tren", "火车"),
}


def split_of(item_id: str) -> str:
    return "test" if int(hashlib.sha256(item_id.encode()).hexdigest()[:8], 16) % 3 == 0 else "dev"


def key_of(text: str) -> str:
    low = text.casefold()
    hits = [k for k, words in KEYS.items() if any(w in low for w in words)]
    if len(hits) != 1:
        raise ValueError(f"no single key for {text!r}: {hits}")
    return hits[0]


def mentions(text: str, key: str) -> bool:
    low = text.casefold()
    return any(w in low for w in KEYS[key])


def drop(summary: str, key: str) -> str:
    """The summary without every sentence that mentions `key`; lines stay lines."""
    out = []
    for ln in summary.split("\n"):
        parts = re.split(r"(?<=[.!?。；;])\s*", ln)
        kept = [p for p in parts if p.strip() and not mentions(p, key)]
        if kept:
            out.append(" ".join(kept) if not re.search(r"[一-鿿]", ln) else "".join(kept))
    return "\n".join(out)


def row(qid: str, item_id: str, state: dict[str, Any], label: str, planted: bool) -> dict[str, Any]:
    return {"id": item_id, "question_id": qid, "split": split_of(item_id), "item": {"state": state}, "label": label,
            "planted": planted}


def jsonl(p: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


# ── summary judges ──
def summary_sets(labels: dict[str, Any], run: Path) -> dict[str, list[dict[str, Any]]]:
    items = {i["id"]: i for i in jsonl(ROOT / "evals" / "summary" / "items.jsonl")}
    got = {r["id"]: r for r in jsonl(run / "results.jsonl")}
    out: dict[str, list[dict[str, Any]]] = {}

    def base(iid: str) -> tuple[dict[str, Any], str, str, str]:
        it = items[iid]
        joined = "\n".join(f"{x['speaker']}: {x['text']}" for x in it["lines"])
        promise = f"{it['promise']['by']} promised to {it['promise']['what']}"
        return it, joined, promise, got[iid]["summary"]

    for qid in ("judge_summary_fact", "judge_summary_promise", "judge_summary_who", "judge_summary_language",
                "judge_summary_unsupported"):
        rows = []
        for iid, lab in labels[qid].items():
            it, joined, promise, text = base(iid)
            state: dict[str, Any] = {"quoted_lines": joined, "quoted_summary": text}
            if qid == "judge_summary_fact":
                state = {"quoted_lines": joined, "quoted_fact": it["facts"][lab["fact"]], "quoted_summary": text}
            elif qid in ("judge_summary_promise", "judge_summary_who"):
                state = {"quoted_lines": joined, "quoted_promise": promise, "quoted_summary": text}
            elif qid == "judge_summary_unsupported":
                state = {"quoted_lines": joined, "quoted_previous": it.get("previous") or "none", "quoted_summary": text}
            rows.append(row(qid, f"{qid}-real-{iid}", state, lab["label"], False))
        out[qid] = rows

    # planted: from items whose real summary is clean for that judge (no real "yes" is reused as a base)
    clean = [i for i in items if i in got]
    bad_lang = {i for i, v in labels["judge_summary_language"].items() if v["label"] == "yes"}
    bad_unsup = {i for i, v in labels["judge_summary_unsupported"].items() if v["label"] == "yes"}
    n = 0
    fact_rows, promise_rows, who_rows, lang_rows, unsup_rows = [], [], [], [], []
    for k, iid in enumerate(clean):
        it, joined, promise, text = base(iid)
        fact = it["facts"][k % 3]
        cut = drop(text, key_of(fact))
        if cut.strip() and cut != text and not mentions(cut, key_of(fact)) and len(fact_rows) < 30:
            fact_rows.append(row("judge_summary_fact", f"pl-fact-{iid}", {
                "quoted_lines": joined, "quoted_fact": fact, "quoted_summary": cut}, "yes", True))
        pkey = key_of(it["promise"]["what"])
        cut = drop(text, pkey)
        if cut.strip() and cut != text and not mentions(cut, pkey) and len(promise_rows) < 30:
            promise_rows.append(row("judge_summary_promise", f"pl-promise-{iid}", {
                "quoted_lines": joined, "quoted_promise": promise, "quoted_summary": cut}, "yes", True))
        by = it["promise"]["by"]
        others = sorted({x["speaker"] for x in it["lines"]} - {by, "Kai"})
        if by in text and others and len(who_rows) < 30:
            swapped = text.replace(by, others[0])
            who_rows.append(row("judge_summary_who", f"pl-who-{iid}", {
                "quoted_lines": joined, "quoted_promise": promise, "quoted_summary": swapped}, "yes", True))
        if iid not in bad_lang and len(lang_rows) < 30:
            foreign = [j for j in clean if items[j]["language"] != it["language"] and j not in bad_lang]
            other = foreign[(k * 7) % len(foreign)]
            lang_rows.append(row("judge_summary_language", f"pl-lang-{iid}", {
                "quoted_lines": joined, "quoted_summary": got[other]["summary"]}, "yes", True))
        if iid not in bad_unsup and len(unsup_rows) < 30:
            unsup_rows.append(row("judge_summary_unsupported", f"pl-unsup-{iid}", {
                "quoted_lines": joined, "quoted_previous": it.get("previous") or "none",
                "quoted_summary": text + "\n" + INVENTED[n % len(INVENTED)]}, "yes", True))
            n += 1
    for qid, rows in (("judge_summary_fact", fact_rows), ("judge_summary_promise", promise_rows),
                      ("judge_summary_who", who_rows), ("judge_summary_language", lang_rows),
                      ("judge_summary_unsupported", unsup_rows)):
        out[qid] += rows
    return out


# ── drafter judges ──
def you_card(world: str) -> str:
    w = json.loads((ROOT / "evals" / "seed-v0" / "worlds" / f"{world}.json").read_text(encoding="utf-8"))
    return json.dumps(w["data"].get("you") or {}, ensure_ascii=False)


def draft_sets(labels: dict[str, Any], runs: list[Path]) -> dict[str, list[dict[str, Any]]]:
    seeds = {s["id"]: s for p in sorted((ROOT / "evals" / "drafter").glob("*.jsonl")) for s in jsonl(p)}
    drafts: dict[str, dict[str, Any]] = {}
    for run in runs:
        for r in jsonl(run / "results.jsonl"):
            if r.get("valid", True) and "draft" in r:
                drafts[r["id"]] = {**r, "world": seeds[r["id"]]["world"]}
    ga = json.loads((ROOT / "docs" / "ai" / "checks" / "group-a" / "results" / "drafts.json").read_text(encoding="utf-8"))
    for i, d in enumerate(ga["drafts"]):
        if d.get("valid"):
            drafts[f"ga_{i:02}"] = {"id": f"ga_{i:02}", "seed": d["seed"], "intent": d["intent"],
                                    "draft": json.loads(d["content"]), "world": "wld_seedMeridian"}
    out: dict[str, list[dict[str, Any]]] = {"judge_draft_fit": [], "judge_relationship_fit": []}
    for did, lab in labels["judge_draft_fit"].items():
        d = drafts[did]
        out["judge_draft_fit"].append(row("judge_draft_fit", f"judge_draft_fit-real-{did}", {
            "intent": d["intent"], "quoted_seed": d["seed"],
            "quoted_draft": json.dumps(d["draft"]["profile"], ensure_ascii=False)[:3000]}, lab["label"], False))
    for did, lab in labels["judge_relationship_fit"].items():
        d = drafts[did]
        p = d["draft"]["profile"]
        out["judge_relationship_fit"].append(row("judge_relationship_fit", f"judge_relationship_fit-real-{did}", {
            "quoted_user": you_card(d["world"]), "quoted_draft": json.dumps(p, ensure_ascii=False)[:3000],
            "quoted_relationship": str(p.get("relationshipToUser", ""))}, lab["label"], False))
    # planted: a draft against another seed (it misses it); a relationship that fits neither side
    pool = [d for d in drafts.values() if labels["judge_draft_fit"].get(d["id"], {}).get("label", "no") == "no"]
    pool.sort(key=lambda d: d["id"])
    for i in range(30):
        d, other = pool[i % len(pool)], pool[(i + len(pool) // 2 + 1) % len(pool)]
        out["judge_draft_fit"].append(row("judge_draft_fit", f"pl-draft-{d['id']}", {
            "intent": d["intent"], "quoted_seed": d["seed"],
            "quoted_draft": json.dumps(other["draft"]["profile"], ensure_ascii=False)[:3000]}, "yes", True))
    comp = sorted((d for d in drafts.values() if d["draft"]["profile"].get("relationshipToUser")), key=lambda d: d["id"])
    for i in range(30):
        d = comp[i % len(comp)]
        p = dict(d["draft"]["profile"])
        p["relationshipToUser"] = RELATIONSHIPS[i % len(RELATIONSHIPS)]
        out["judge_relationship_fit"].append(row("judge_relationship_fit", f"pl-rel-{i}-{d['id']}", {
            "quoted_user": you_card(d["world"]), "quoted_draft": json.dumps(p, ensure_ascii=False)[:3000],
            "quoted_relationship": p["relationshipToUser"]}, "yes", True))
    return out


def main() -> None:
    labels = json.loads((HERE / "labels.json").read_text(encoding="utf-8"))
    src = labels["_sources"]
    sets: dict[str, list[dict[str, Any]]] = {}
    if "summary" in src:
        sets |= summary_sets(labels, ROOT / src["summary"].split(" ")[0] / "naive")
    if "drafts" in src:
        sets |= draft_sets(labels, [ROOT / p.split(" ")[0] / "naive" for p in src["drafts"]])
    if "replies" in src:
        from replies import reply_sets  # the reply judges' half, built from the long and transcript runs
        sets |= reply_sets(labels, ROOT, src["replies"])
    only = set(sys.argv[1:])   # `build.py judge_voice`: rewrite only these sets, so validated ones stay byte-identical
    for qid, rows in sorted(sets.items()):
        if only and qid not in only:
            continue
        real = sum(1 for r in rows if not r["planted"])
        planted = sum(1 for r in rows if r["planted"])
        yes = sum(1 for r in rows if not r["planted"] and r["label"] == "yes")
        assert len({r["id"] for r in rows}) == len(rows), qid
        (HERE / f"{qid}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                           encoding="utf-8", newline="\n")
        print(f"{qid}: {real} real ({yes} yes) + {planted} planted")


if __name__ == "__main__":
    main()

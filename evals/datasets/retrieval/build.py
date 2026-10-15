"""Build `retrieval.jsonl`: the retrieval suite's labelled questions (rag design D22; docs/ai/02 B2; doc 10 K14;
evaluation-harness "The retrieval suite", "Labels live on the text, not on pieces").

Run from backend/: `uv run python ../evals/datasets/retrieval/build.py`. Deterministic. The questions and their
labels are written blind in `questions.py` (before any answer is seen). Each label is a quote from its source, graded 2
(answers) or 1 (partly); this script finds the quote's one place in the source and stores its offsets:
- corpus quotes in the document's decoded text (what the pipeline stores as `extracted.md`);
- seed quotes in their authored piece (`seed/knowledge/chunks/`), which is never re-chunked.

It refuses a quote that isn't found or is found twice, checks D22's mix, and writes the hash split.
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
sys.path.insert(0, str(HERE))

from questions import QUESTIONS  # noqa: E402

from horizon.evals.datachecks import split_for  # noqa: E402
from horizon.evals.retrieval import CHARACTERS, corpus_text, resolve, seed_chunks  # noqa: E402

OUT = HERE / "retrieval.jsonl"
MIX = {"answerable": 100, "unanswerable": 40, "followup": 30, "non_english": 15, "naming": 20}
TWO = 10
PARTLY = 10     # the Not-found reply's end-to-end run (D22): answerable questions the documents answer only in part


def build(questions: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    seeds = seed_chunks()
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for q in questions if questions is not None else QUESTIONS:
        if q["id"] in seen:
            raise ValueError(f"duplicate id {q['id']}")
        seen.add(q["id"])
        spans = []
        for s in q.get("spans", []):
            quote = s["quote"]
            if s["doc"].startswith("seed:"):
                source, text = seeds[s["chunk"]]
                if s["doc"] != f"seed:{source}":
                    raise ValueError(f"{q['id']}: {s['chunk']} is not in {s['doc']}")
                a, b = resolve(text, quote)
                spans.append({"doc": s["doc"], "chunk": s["chunk"], "start": a, "end": b, "grade": s["grade"],
                              "text": quote})
            else:
                a, b = resolve(corpus_text(s["doc"]), quote)
                spans.append({"doc": s["doc"], "start": a, "end": b, "grade": s["grade"], "text": quote})
        who = q["who"]
        rows.append({"id": q["id"], "split": split_for(q["id"]), "kind": q["kind"], "lang": q.get("lang", "en"),
                     "character": CHARACTERS[who], "message": q["message"], "earlier": list(q.get("earlier", [])),
                     "needs_two": bool(q.get("needs_two", False)), "partly": bool(q.get("partly", False)),
                     "named": q.get("named"),
                     "origin": "seed" if q.get("seed") else "corpus", "spans": spans})
    return rows


def problems(rows: list[dict[str, Any]], *, full: bool = True) -> list[str]:
    out: list[str] = []
    kinds = Counter(r["kind"] for r in rows)
    if full:
        for k, n in MIX.items():
            if kinds[k] != n:
                out.append(f"{k}: {kinds[k]} questions (want {n})")
        if sum(r["needs_two"] for r in rows) != TWO:
            out.append(f"needing two passages: {sum(r['needs_two'] for r in rows)} (want {TWO})")
        if sum(r["partly"] for r in rows) != PARTLY:
            out.append(f"answered only in part: {sum(r['partly'] for r in rows)} (want {PARTLY})")
    for r in rows:
        if r["kind"] == "unanswerable" and r["spans"]:
            out.append(f"{r['id']}: an unanswerable question has spans")
        if r["kind"] != "unanswerable" and not any(s["grade"] == 2 for s in r["spans"]):
            out.append(f"{r['id']}: no grade-2 span")
        if r["needs_two"] and sum(s["grade"] == 2 for s in r["spans"]) < 2:
            out.append(f"{r['id']}: needs two passages but has fewer than two grade-2 spans")
        if r["partly"] and r["kind"] != "answerable":
            out.append(f"{r['id']}: only an answerable question is answered in part")
        if r["kind"] == "followup" and len(r["earlier"]) < 2:
            out.append(f"{r['id']}: a follow-up needs its two earlier lines")
    return out


def main() -> int:
    rows = build()
    bad = problems(rows, full="--partial" not in sys.argv)
    for line in bad:
        print(line)
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    c = Counter((r["kind"], r["split"]) for r in rows)
    print(f"{len(rows)} questions -> {OUT.name}: " + ", ".join(f"{k}/{s} {n}" for (k, s), n in sorted(c.items())))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())

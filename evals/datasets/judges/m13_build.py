"""Builds M13's judge validation sets (memory design D40; doc 02 B4): 30 planted items for each new judge, from the
labelled facts in `evals/datasets/earlier/facts.py`. The 30 real items per judge are labelled from the paid run's own
outputs (`horizon eval memory` saves every judge state) and added under `evals/reviews/m13-review.md`.

    cd backend && uv run python ../evals/datasets/judges/m13_build.py

Labels follow the judges' failure side ("yes" = the failure):
- `judge_memory_missed`: the expected change against written lines that hold it (no) or don't (yes);
- `judge_memory_unsupported`: the memory line (no) or its extension, whose added detail nobody said (yes);
- `judge_memory_lost`: the faithful extension (no) or the lossy rewrite (yes);
- `judge_over_mention`: a reply to a new topic as is (no) or with a remembered detail dragged in (yes).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "evals" / "datasets" / "earlier"))

from facts import FACTS, Fact, unrelated  # noqa: E402

from horizon.evals.datachecks import split_for  # noqa: E402

N = 30
EN = [f for f in FACTS if f.lang == "en"]
ANSWER = "Honestly, it depends on you, but I'd start simple and see what fits."


def you(text: str) -> str:
    """A memory as the character would say it to Kai ("Kai runs" -> "you run", "his" -> "your")."""
    import re

    def verb(m: re.Match[str]) -> str:
        v = m.group(1)
        if v in ("was", "got", "had"):
            return f"you {'were' if v == 'was' else v}"
        if v.endswith("ies"):
            return f"you {v[:-3]}y"
        if v.endswith(("ches", "shes", "sses", "xes")):
            return f"you {v[:-2]}"
        return f"you {v[:-1]}" if v.endswith("s") and not v.endswith("ss") else f"you {v}"

    out = text.replace("Kai's", "your").replace("Kai is", "you're").replace("Kai has", "you've")
    if re.match(r"Kai (?!')", text):   # Kai is the subject: a second verb after "and" agrees with "you" too
        for said, to in (("has", "have"), ("eats", "eat"), ("does", "do"), ("keeps", "keep")):
            out = re.sub(rf"\band {said}\b", f"and {to}", out)
    out = re.sub(r"\bKai (\w+)", verb, out)
    out = re.sub(r"\bhis\b", "your", out)
    out = re.sub(r"\bhim\b", "you", out)
    out = re.sub(r"\bhe\b", "you", out)
    return out.rstrip(".")


def row(qid: str, n: int, state: dict[str, Any], label: str, f: Fact) -> dict[str, Any]:
    item_id = f"{qid}-planted-{n:03d}"
    return {"id": item_id, "question_id": qid, "split": split_for(item_id), "item": {"state": state},
            "label": label, "planted": True, "source": f"fact:{f.id}"}


def missed() -> list[dict[str, Any]]:
    out = []
    for i in range(N):
        f, other = EN[i % len(EN)], EN[(i + 7) % len(EN)]
        held = f.memory if i % 4 == 0 else f.extend   # covered in its own words, or extended
        written = [held, other.memory] if i % 2 == 0 else [other.memory]
        label = "no" if i % 2 == 0 else "yes"
        out.append(row("judge_memory_missed", i + 1, {"quoted_expected": f"add: {f.memory}",
                                                      "quoted_written": "\n".join(written)}, label, f))
    return out


def unsupported() -> list[dict[str, Any]]:
    out = []
    for i in range(N):
        f = EN[i % len(EN)]
        line, label = (f.memory, "no") if i % 2 == 0 else (f.extend, "yes")
        out.append(row("judge_memory_unsupported", i + 1, {"quoted_line": line, "quoted_messages": f"Kai: {f.said}",
                                                           "quoted_memories": "(nothing yet)"}, label, f))
    return out


def lost() -> list[dict[str, Any]]:
    out = []
    for i in range(N):
        f = EN[i % len(EN)]
        new, label = (f.extend, "no") if i % 2 == 0 else (f.lossy, "yes")
        out.append(row("judge_memory_lost", i + 1, {"quoted_old": f.memory, "quoted_new": new,
                                                    "quoted_messages": f"Kai: {f.said}"}, label, f))
    return out


def over_mention() -> list[dict[str, Any]]:
    out = []
    for i in range(N):
        f = EN[i % len(EN)]
        message = unrelated([f.memory, f.said], f.who, 1, start=i)[0]
        reply = ANSWER if i % 2 == 0 else f"{ANSWER} Speaking of which, I keep thinking about how {you(f.memory)}."
        out.append(row("judge_over_mention", i + 1, {"quoted_memories": f.memory, "quoted_message": message,
                                                     "quoted_reply": reply}, "no" if i % 2 == 0 else "yes", f))
    return out


REAL = HERE / "m13_real.json"


def real(qid: str) -> list[dict[str, Any]]:
    """B4's real items: states saved by the first paid memory run (`judge_states.jsonl`), labelled by hand in
    `m13_real.json` from the state alone (`evals/reviews/m13-review.md` says which answers had been seen)."""
    if not REAL.is_file():
        return []
    out = []
    for r in json.loads(REAL.read_text(encoding="utf-8")):
        if r["question_id"] != qid:
            continue
        item_id = f"{qid}-real-{len(out) + 1:03d}"
        out.append({"id": item_id, "question_id": qid, "split": split_for(item_id), "item": {"state": r["state"]},
                    "label": r["label"], "planted": False, "source": r["source"]})
    return out


def main() -> int:
    sets = {"judge_memory_missed": missed(), "judge_memory_unsupported": unsupported(), "judge_memory_lost": lost(),
            "judge_over_mention": over_mention()}
    sets = {qid: [*rows, *real(qid)] for qid, rows in sets.items()}
    for qid, rows in sets.items():
        path = HERE / f"{qid}.jsonl"
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        yes = sum(r["label"] == "yes" for r in rows)
        n_real = sum(1 for r in rows if not r["planted"])
        print(f"{qid}: {len(rows) - n_real} planted + {n_real} real ({yes} yes) -> {path.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""`horizon eval deep-check`: doc 10 check 5 (rag design D28; doc 01 check 4, extended; tasks 11.1).

Does Jev's output come back as K7 expects? Three small parts, every request built as live builds it:
- **`deep_check` on 20 passages** (`passage`, a 3-level score): question and passage pairs from the retrieval
  suite's dev split, the passage being the paragraph of the source that holds a labelled span (as a piece would):
  7 expected to answer (a grade-2 span's paragraph), 6 expected to partly answer (the held half of a `partly`
  question), 7 expected not to help (another question's paragraph, from the same character's sources). Reported:
  whether the levels' probabilities come back, each level's probability, and the weighted score `unit` (W11).
- **the set check on 5 pairs** (`passage_set`, a noul): 3 two-passage questions with both their passages (expected
  yes), 2 with one passage swapped for an unrelated one (expected no).
- **the two nouls on 20 messages** ("standalone?" and "English?", asked together as the 1:1 plan asks them): 10 dev
  items of the `standalone` set and 10 of the `english` set, with their labels beside.

Its own labels say what is expected; this is a check of the output's form and direction, not a scored set.
"""

from __future__ import annotations

import json
import re
from typing import Any

from horizon.ai.agent import gates
from horizon.ai.agent.deep import PASSAGE, PASSAGE_SET, level_probs
from horizon.ai.decider import NoulAnswer, ScoreAnswer, validate, wire_question
from horizon.ai.embedder import strip_extension
from horizon.ai.questions import bank
from horizon.evals import retrieval as R
from horizon.evals.runner import EVAL_SEED, Options, Plan, Result, RunEnv, decision_estimate
from horizon.gateway.context import call_ctx

SEED = EVAL_SEED / "knowledge"
N_ANSWERS, N_PARTLY, N_NONE = 7, 6, 7
N_SET_YES, N_SET_NO = 3, 2
N_NOULS = 10   # from each of the two sets
_PARA = re.compile(r"(?:\r?\n){2,}")


def seed_meta() -> dict[str, dict[str, str]]:
    """chunk id → {title, locator} for the authored seed pieces."""
    titles: dict[str, str] = {}
    for f in SEED.glob("chr_*.json"):
        for s in json.loads(f.read_text(encoding="utf-8"))["data"]:
            titles[str(s["id"])] = str(s["title"])
    out: dict[str, dict[str, str]] = {}
    for f in (SEED / "chunks").glob("*.json"):
        for c in json.loads(f.read_text(encoding="utf-8"))["data"]:
            out[str(c["id"])] = {"title": strip_extension(titles.get(str(c["sourceId"]), "")),
                                 "locator": str(c.get("locator") or "")}
    return out


def paragraph(span: dict[str, Any], meta: dict[str, dict[str, str]]) -> dict[str, str]:
    """The passage a piece holding this span would show: the seed piece whole, or the corpus paragraph around it."""
    if span["doc"].startswith("seed:"):
        chunk = str(span["chunk"])
        return {**meta[chunk], "text": R.seed_chunks()[chunk][1]}
    text = R.corpus_text(span["doc"])
    a = int(span["start"])
    starts = [0] + [m.end() for m in _PARA.finditer(text)]
    begin = max(s for s in starts if s <= a)
    m = _PARA.search(text, a)
    end = m.start() if m else len(text)
    return {"title": strip_extension(span["doc"].split("/", 1)[1]), "locator": "", "text": text[begin:end].strip()}


def quoted_query(q: dict[str, Any]) -> dict[str, Any]:
    return {"message": q["message"], "earlier": list(q.get("earlier") or [])[-2:]}


def items() -> list[dict[str, Any]]:
    """The 45 requests, deterministic (the dev split, in id order)."""
    meta = seed_meta()
    dev = [q for q in R.load_questions() if q["split"] == "dev"]
    out: list[dict[str, Any]] = []
    answers = [q for q in dev if q["kind"] == "answerable" and not q["partly"] and not q["needs_two"]]
    for q in answers[:N_ANSWERS]:
        span = next(s for s in q["spans"] if s["grade"] == 2)
        out.append({"part": "passage", "id": q["id"], "expect": 2, "query": quoted_query(q),
                    "passage": paragraph(span, meta)})
    for q in [q for q in dev if q["partly"]][:N_PARTLY]:
        span = next(s for s in q["spans"] if s["grade"] == 2)
        out.append({"part": "passage", "id": q["id"], "expect": 1, "query": quoted_query(q),
                    "passage": paragraph(span, meta)})
    # not helping: a question shown another question's paragraph from a different document of the same character,
    # round the four characters in turn, each partner used once
    by_char: dict[str, list[dict[str, Any]]] = {}
    for q in answers[N_ANSWERS:]:
        by_char.setdefault(q["character"], []).append(q)
    used: set[str] = set()
    taken, turn = 0, 0
    chars = sorted(by_char)
    while taken < N_NONE and turn < 10 * len(chars):
        mine = by_char[chars[turn % len(chars)]]
        q = mine[(turn // len(chars)) % len(mine)]
        turn += 1
        other = next((o for o in reversed(mine) if o["id"] not in used and o["id"] != q["id"]
                      and o["spans"][0]["doc"] != q["spans"][0]["doc"]), None)
        if other is None or q["id"] in used:
            continue
        used.update({q["id"], other["id"]})
        out.append({"part": "passage", "id": f"{q['id']}~{other['id']}", "expect": 0, "query": quoted_query(q),
                    "passage": paragraph(other["spans"][0], meta)})
        taken += 1
    twos = [q for q in R.load_questions() if q["needs_two"]]
    for q in twos[:N_SET_YES]:
        ps = [paragraph(s, meta) for s in q["spans"] if s["grade"] == 2][:2]
        out.append({"part": "set", "id": q["id"], "expect": "yes", "query": quoted_query(q), "passages": ps})
    for q, other in zip(twos[N_SET_YES:N_SET_YES + N_SET_NO], reversed(answers), strict=False):
        first = paragraph(next(s for s in q["spans"] if s["grade"] == 2), meta)
        out.append({"part": "set", "id": f"{q['id']}~{other['id']}", "expect": "no", "query": quoted_query(q),
                    "passages": [first, paragraph(other["spans"][0], meta)]})
    from horizon.evals.suites import DATASETS, load_dataset

    for name in ("standalone", "english"):
        rows = [r for r in load_dataset(DATASETS / name / f"{name}.jsonl") if r["split"] == "dev"]
        picks = rows[:N_NOULS] if name == "english" else [r for r in rows if r["label"] == "no"][:5] + \
            [r for r in rows if r["label"] == "yes"][:5]
        if name == "english":   # every language, not the first ten (all English)
            by_lang: dict[str, list[dict[str, Any]]] = {}
            for r in rows:
                by_lang.setdefault(r["lang"], []).append(r)
            picks = [r for lang in sorted(by_lang) for r in by_lang[lang][:3]][:N_NOULS]
        for r in picks:
            st = {k: v for k, v in r["item"]["state"].items() if k != "quoted_documents"}
            out.append({"part": "nouls", "id": r["id"], "expect": {name: r["label"]}, "state": st})
    return out


def request(it: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    """(state, wire questions, purpose) exactly as live asks."""
    b = bank()
    if it["part"] == "passage":
        key = f"{PASSAGE}:{it['id']}"
        state = {"mode": "one_on_one", "quoted_query": it["query"], "quoted_passage": it["passage"]}
        return state, {key: wire_question(b.question(PASSAGE, about=it["id"]))}, "deep_check"
    if it["part"] == "set":
        state = {"mode": "one_on_one", "quoted_query": it["query"], "quoted_passages": it["passages"]}
        return state, {PASSAGE_SET: wire_question(b.question(PASSAGE_SET))}, "deep_check"
    qs = {k: wire_question(v) for k, v in gates.questions({"x": "x"}, ["x"], nouls=True).items()
          if not k.startswith("docs:")}
    return it["state"], qs, "turn_plan"


def report(rows: list[dict[str, Any]]) -> list[str]:
    out = ["## Check 5: Jev's output against K7 (doc 10)"]
    ps = [r for r in rows if r["part"] == "passage" and r.get("unit") is not None]
    if ps:
        with_probs = sum(1 for r in ps if r["probs_given"])
        out.append(f"### deep_check on {len(ps)} passages: the levels' probabilities came back on {with_probs}")
        for lvl, name in ((2, "answers"), (1, "partly"), (0, "doesn't help")):
            mine = [r for r in ps if r["expect"] == lvl]
            if mine:
                units = sorted(r["unit"] for r in mine)
                out.append(f"- expected {name} ({len(mine)}): unit min {units[0]:.2f}, median "
                           f"{units[len(units) // 2]:.2f}, max {units[-1]:.2f}; top level matches "
                           f"{sum(1 for r in mine if r['top'] == lvl)}/{len(mine)}")
    sets = [r for r in rows if r["part"] == "set" and r.get("p") is not None]
    if sets:
        out.append("### the set check on 5 pairs: " + ", ".join(f"{r['id']} expected {r['expect']} p={r['p']:.2f}"
                                                              for r in sets))
    nouls = [r for r in rows if r["part"] == "nouls"]
    if nouls:
        out.append("### the two nouls on 20 messages (p, label)")
        for r in nouls:
            exp = ", ".join(f"{k}={v}" for k, v in r["expect"].items())
            out.append(f"- {r['id']}: standalone {r.get('standalone')}, english {r.get('english')} ({exp})")
    bad = sum(1 for r in rows if r.get("invalid"))
    out.append(f"- invalid or missing answers: {bad}")
    return out


class DeepCheck:
    name = "deep-check"

    def refuse(self, opts: Options) -> str | None:
        return None

    def plan(self, opts: Options, prices: Any, *, paid: bool) -> Plan:
        its = items()[opts.start:]
        its = its[: opts.limit] if opts.limit else its
        est = sum(decision_estimate(prices, *request(i)[:2]) for i in its)
        return Plan(items=its, estimate_usd=est, expected_s=len(its) * 2.0, paid=paid, calls_chat=False)

    async def run(self, env: RunEnv, plan: Plan) -> Result:
        res = Result()
        for it in plan.items:
            if await env.over_budget():
                res.status = "incomplete"
                break
            state, qs, purpose = request(it)
            r = await env.rt.gateway.decide(state, qs, call_ctx(purpose))
            row: dict[str, Any] = {"part": it["part"], "id": it["id"], "expect": it["expect"]}
            b = bank()
            if it["part"] == "passage":
                key = next(iter(qs))
                a = validate(b.question(PASSAGE, about=it["id"]), r.answers.get(key))
                if isinstance(a, ScoreAnswer):
                    pa, pp, unit = level_probs(a)
                    probs = {str(k): float(v) for k, v in (a.probabilities or {}).items()}
                    row.update(score=a.score, probs_given=bool(probs), probabilities=probs,
                               p_answers=round(pa, 4), p_partly=round(pp, 4), unit=round(unit, 4),
                               top=max(range(3), key=lambda k: probs.get(str(k), 0.0)) if probs else round(a.score))
                else:
                    row["invalid"] = True
            elif it["part"] == "set":
                a = validate(b.question(PASSAGE_SET), r.answers.get(PASSAGE_SET))
                if isinstance(a, NoulAnswer):
                    row["p"] = round(a.p, 4)
                else:
                    row["invalid"] = True
            else:
                for k in (gates.STANDALONE, gates.ENGLISH):
                    a = validate(b.question(k), r.answers.get(k))
                    if isinstance(a, NoulAnswer):
                        row[k] = round(a.p, 4)
                    else:
                        row["invalid"] = True
            res.rows.append(row)
        res.summary += report(res.rows)
        return res

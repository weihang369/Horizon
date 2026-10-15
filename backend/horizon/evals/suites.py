"""M7's eval suites (docs/ai/02 B6, B12; ai-foundation design D34; tasks 7.5–7.7).

- **canary**: the 20 baseline items through the gateway with the store bypassed, D32's pass rule, the model id
  OpenRouter returned. `--accept` rewrites the baseline after a drift the user has seen. Paid only (< $0.001).
- **decisions**: the layer-1 engine. Each dataset line `{id, question_id, split, item, label, smoke_only?}` is built
  from the bank exactly as live (the live deadline off) and asked in two option orders; it reports policy accuracy
  with Wilson intervals, a calibration table and the order-bias rate. Questions whose bank version was already measured
  are skipped. `smoke_only` items are never reported as a measurement.
- **smoke**: every bank entry compiles to a valid wire question, every dataset line loads, `decisions` over the smoke
  items (`--limit`), one scripted conversation per mode from `evals/smoke/<mode>.json`, and the report renders.
  In test mode it runs on the in-process fake ($0) with the socket guard on.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from horizon.ai.decider import Choice, ChoiceAnswer, Noul, NoulAnswer, Question, validate, wire_question
from horizon.ai.questions import NAME, bank
from horizon.domain.clock import FrozenClock
from horizon.evals import canary as canary_mod
from horizon.evals import judges, policies, who_policies
from horizon.evals.judges import JUDGES_SET
from horizon.evals.metrics import wilson
from horizon.evals.runner import EVALS_DIR, Options, Plan, Result, RunEnv, decision_estimate
from horizon.gateway.context import call_ctx

DATASETS = EVALS_DIR / "datasets"
SMOKE_DIR = EVALS_DIR / "smoke"
MODES = ("one_on_one", "group", "watch", "debate")
STUB_VALUES = [{"key": "chr_a", "name": "A", "role": "r"}, {"key": "chr_b", "name": "B", "role": "r"}]
REQUIRED = ("id", "question_id", "split", "item", "label")


# ── datasets ──
NOT_DECISIONS = frozenset({"retrieval"})   # M12: the retrieval suite's questions are not decision items


def dataset_files(root: Path | None = None) -> list[Path]:
    root = root or DATASETS
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*.jsonl") if not NOT_DECISIONS & set(p.relative_to(root).parts[:-1]))


def load_dataset(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        missing = [k for k in REQUIRED if k not in row]
        if missing:
            raise ValueError(f"{path.name}:{n}: missing {', '.join(missing)}")
        if row["split"] not in ("dev", "test"):
            raise ValueError(f"{path.name}:{n}: split must be dev or test")
        bank().get(str(row["question_id"]))
        out.append(row)
    return out


def all_items(root: Path | None = None, *, judges: bool = True) -> Iterator[dict[str, Any]]:
    for p in dataset_files(root):
        if not judges and JUDGES_SET in p.relative_to(root or DATASETS).parts:
            continue
        yield from load_dataset(p)


# ── wire checks ──
def wire_problems(w: dict[str, Any]) -> list[str]:
    out: list[str] = []
    if w.get("type") not in ("choice", "noul", "score"):
        out.append("type")
    if not isinstance(w.get("instructions"), str) or not w["instructions"].strip():
        out.append("instructions")
    c = w.get("criteria")
    if w.get("type") == "score":
        if not isinstance(c, list) or len(c) < 2 or not all(isinstance(x, str) for x in c):
            out.append("criteria")
    elif not isinstance(c, dict) or len(c) < 2 or not all(isinstance(v, str) and v for v in c.values()):
        out.append("criteria")
    return out


STUB_SIDE = "Proposition"   # M11 (debate D7): the side a sided entry is compiled about when an item names none
STUB_NAME = "Amara"   # M9 (design D11): the subject a named entry is compiled about when an item names none (smoke)


def compile_entry(qid: str, values: list[dict[str, Any]] | None = None, seed: str = "smoke",
                  name: str | None = None, none: bool = True, side: str | None = None, n: int | None = None) -> Question:
    """The entry compiled as live; a dynamic choice with no values gets two stub options (the wire check needs ≥ 2),
    and an entry that names its subject gets the item's `name` (or a stub one). `none=False` (M10): the first slot and
    watch ask with no `none`, as the planner does. M11 (debate D7, D12): an entry naming a side gets the item's `side`
    (or "Proposition"), and a criterion's position `n` (or 1)."""
    e = bank().get(qid)
    dynamic = e.type == "choice" and e.options.get("kind") != "static"
    named = NAME in e.instructions
    sided = "{side}" in e.instructions or "{other}" in e.instructions
    return bank().question(qid, values=values or (STUB_VALUES if dynamic else ()), seed=seed,
                           name=(name or STUB_NAME) if named else None, none=none,
                           side=(side or STUB_SIDE) if sided else None,
                           n=(n or 1) if "{n}" in e.instructions else None)


def item_question(item: dict[str, Any], seed: str | None = None) -> Question:
    """A dataset line's question, compiled exactly as the live code asks it."""
    it = item["item"]
    return compile_entry(item["question_id"], it.get("values"), seed=seed or str(it.get("seed") or item["id"]),
                         name=it.get("name"), none=bool(it.get("none", True)), side=it.get("side"), n=it.get("n"))


def reordered(q: Question) -> Question:
    """The same choice with its options in reverse order (order bias, B3)."""
    if not isinstance(q, Choice):
        return q
    return Choice(q.instructions, dict(reversed(list(q.options.items()))), meta=q.meta)


def order_line(flips: int, total: int, items: list[dict[str, Any]]) -> str:
    """B6's lean report. Not measured for shuffled choice questions (turn-plan-emotion D38, the user's choice): the
    store key sorts JSON keys, so the reversed request returns the first order's stored answer. The key fix is its
    own change."""
    shuffled = sorted({str(i["question_id"]) for i in items
                       if bank().get(str(i["question_id"])).type == "choice" and bank().get(str(i["question_id"])).shuffle})
    if shuffled:
        return (f"- order bias: not measured for shuffled choices ({', '.join(shuffled)}): the store key ignores option "
                "order, so the reversed request returns the first answer (D38)")
    return f"- order bias: {flips}/{total} answers changed when the options were reversed"


# ── canary ──
class Canary:
    name = "canary"

    def plan(self, opts: Options, prices: Any, *, paid: bool) -> Plan:
        b = canary_mod.load_baseline(EVALS_DIR / "canary.json")
        items = b.items[opts.start:]
        items = items[: opts.limit] if opts.limit else items
        est = sum(decision_estimate(prices, i["state"], i["questions"]) for i in items)
        return Plan(items=items, estimate_usd=est, expected_s=len(items) * 3.0, paid=paid)

    async def run(self, env: RunEnv, plan: Plan) -> Result:
        res = Result()
        new_items: list[dict[str, Any]] = []
        drift_n = 0
        for item in plan.items:
            if await env.over_budget():
                res.status = "incomplete"
                res.summary.append("stopped at the run's cap")
                break
            r = await env.rt.gateway.decide(item["state"], item["questions"], call_ctx("eval_judge"))
            res.model = r.model or res.model
            drift = canary_mod.compare(item["answers"], r.answers)
            drift_n += bool(drift)
            res.rows.append({"id": item["id"], "drift": drift, "model": r.model, "answers": dict(r.answers)})
            new_items.append({**item, "answers": dict(r.answers)})
        if res.status == "ok" and drift_n:
            res.status = "drift"
        res.summary.append(f"## Canary: {len(res.rows) - drift_n}/{len(res.rows)} within tolerance "
                           f"(choices equal, p ±{canary_mod.P_TOL}, scores ±{canary_mod.SCORE_TOL})")
        res.summary += [f"- {r['id']}: " + "; ".join(r["drift"]) for r in res.rows if r["drift"]]
        if env.opts.accept and res.status == "drift" and len(new_items) == len(plan.items) and not env.opts.start:
            fp = canary_mod.accept(EVALS_DIR / "canary.json", new_items, res.model or "",
                                   dt.datetime.now(dt.UTC).isoformat())
            res.summary.append(f"- accepted as the new baseline (fingerprint {fp[:12]}…); every stored Jev answer is "
                               "now stale")
            res.status = "ok"
        return res


# ── decisions ──
def measured_path(env: RunEnv) -> Path:
    return env.run_dir.parents[1] / "decisions-measured.json"


def measured_marks(items: list[dict[str, Any]]) -> dict[str, str]:
    """What "already measured" means per question: its bank version AND its items. A relabelled or rebuilt set
    (persona-context 10.6) is measured again even when the question's wording didn't change; the store still serves
    every unchanged item, so only the changed ones cost anything."""
    by: dict[str, list[str]] = {}
    for it in items:
        by.setdefault(str(it["question_id"]), []).append(json.dumps(it, sort_keys=True, ensure_ascii=False))
    return {qid: f"v{bank().get(qid).version}:"
            + hashlib.sha256("\n".join(sorted(rows)).encode("utf-8")).hexdigest()[:16]
            for qid, rows in by.items()}


class Decisions:
    name = "decisions"

    def __init__(self, smoke: bool = False) -> None:
        self.smoke = smoke

    def _items(self, opts: Options) -> list[dict[str, Any]]:
        """Layer-1 items; `--set NAME` runs one dataset folder instead (the judges' B4 validation is `--set judges`;
        M12's `--set reask` is D9's re-ask with titles)."""
        from horizon.evals import m12_sets

        source = (iter(m12_sets.reask_items()) if opts.set == m12_sets.REASK_SET else
                  all_items(DATASETS / opts.set) if opts.set else all_items(judges=False))
        items = [i for i in source if bool(i.get("smoke_only")) == self.smoke][opts.start:]
        return items[: opts.limit] if opts.limit else items

    def plan(self, opts: Options, prices: Any, *, paid: bool) -> Plan:
        items = self._items(opts)
        est = 0.0
        for i in items:
            q = item_question(i, seed=i["id"])
            # a noul has no option order to reverse (D27); M12 D9's re-ask compares the live order only
            asks = 2 if isinstance(q, Choice) and not i.get("reask") else 1
            est += asks * decision_estimate(prices, i["item"]["state"], {i["question_id"]: wire_question(q)})
        return Plan(items=items, estimate_usd=est, expected_s=len(items) * 4.0, paid=paid)

    async def run(self, env: RunEnv, plan: Plan) -> Result:
        res = Result()
        done_path = measured_path(env)
        measured: dict[str, Any] = json.loads(done_path.read_text(encoding="utf-8")) if done_path.is_file() else {}
        correct = total = flips = 0
        bins: dict[int, list[int]] = {}
        skipped: set[str] = set()
        from horizon.evals import m12_sets

        reask = env.opts.set == m12_sets.REASK_SET   # M12 D9: measured apart, so a re-ask never hides the live set
        mark = {(f"{m12_sets.REASK_SET}:{k}" if reask else k): v for k, v in measured_marks(plan.items).items()}
        for item in plan.items:
            qid = str(item["question_id"])
            mkey = f"{m12_sets.REASK_SET}:{qid}" if reask else qid
            version = bank().get(qid).version
            if not self.smoke and measured.get(mkey) == mark[mkey]:
                skipped.add(qid)
                continue
            if await env.over_budget():
                res.status = "incomplete"
                break
            q = item_question(item)   # M9 D26: the live seeded order, when stored
            row: dict[str, Any] = {"id": item["id"], "question_id": qid, "version": version, "label": item["label"],
                                   "smoke_only": bool(item.get("smoke_only")), "planted": bool(item.get("planted")),
                                   "split": item["split"], "lang": item.get("lang", "en"),
                                   **({"kind": item["kind"]} if item.get("kind") else {}),
                                   **({"fresh": True} if item.get("fresh") else {}),   # M11: scored apart (D17)
                                   **({"reask": True} if item.get("reask") else {})}   # M12 D9
            if isinstance(q, Noul):   # D27: asked once; "yes" when p reaches the entry's threshold
                key = str(item["item"].get("key") or qid)   # M12: the gate is asked under its live key, `docs:{id}`
                r = await env.rt.gateway.decide(item["item"]["state"], {key: wire_question(q)}, call_ctx("eval_judge"))
                ans = validate(q, r.answers.get(key))
                if isinstance(ans, NoulAnswer):
                    th = bank().get(qid).thresholds   # M10: talk_finished's threshold is `t_end` (re-chosen on dev)
                    t = float(next((th[k] for k in ("t", "t_end", "t_gate", "t_standalone", "english") if k in th),
                                   0.5))
                    said = "yes" if ans.p >= t else "no"
                    row.update(answer=said, p=ans.p, correct=said == item["label"])
                    total += 1
                    correct += said == item["label"]
                    bins.setdefault(min(9, int(ans.p * 10)), []).append(int(said == "yes"))
                else:
                    row["invalid"] = True
                res.rows.append(row)
                continue
            if qid == judges.PAIRWISE:   # M9 D29: both orders = the two replies swapped (its options never shuffle)
                probs = []
                for st in (item["item"]["state"], judges.swapped(item["item"]["state"])):
                    r = await env.rt.gateway.decide(st, {qid: wire_question(q)}, call_ctx("eval_judge"))
                    ans = validate(q, r.answers.get(qid))
                    probs.append(dict(ans.probabilities or {ans.choice: ans.confidence or 0.0})
                                 if isinstance(ans, ChoiceAnswer) else None)
                if probs[0] is not None and probs[1] is not None:
                    side = str(item["label"])
                    win = judges.prefers(probs[0], probs[1], side)
                    lose = judges.prefers(probs[0], probs[1], "b" if side == "a" else "a")
                    row.update(p_win=round(win, 4), p_lose=round(lose, 4), correct=win > lose)
                    total += 1
                    correct += win > lose
                else:
                    row["invalid"] = True
                res.rows.append(row)
                continue
            answers = []
            for order in (q,) if item.get("reask") else (q, reordered(q)):
                r = await env.rt.gateway.decide(item["item"]["state"], {qid: wire_question(order)}, call_ctx("eval_judge"))
                answers.append(validate(order, r.answers.get(qid)))
            a, b = answers if len(answers) == 2 else (answers[0], answers[0])
            if isinstance(a, ChoiceAnswer) and isinstance(b, ChoiceAnswer) and isinstance(item["label"], dict):
                # M9 D26: scored by the live code rule at report time (the floor comes from dev); both orders kept
                row.update(answer=a.choice, answer_reversed=b.choice, confidence=a.confidence,
                           probabilities=dict(a.probabilities or {}))
                flips += a.choice != b.choice
            elif isinstance(a, ChoiceAnswer) and isinstance(b, ChoiceAnswer):
                row.update(answer=a.choice, answer_reversed=b.choice, confidence=a.confidence)
                total += 1
                correct += a.choice == item["label"]
                flips += a.choice != b.choice
                p = float((a.probabilities or {}).get(a.choice, a.confidence or 0.0))
                bins.setdefault(min(9, int(p * 10)), []).append(int(a.choice == item["label"]))
            else:
                row["invalid"] = True
            res.rows.append(row)
        if not self.smoke:
            for qid in {r["question_id"] for r in res.rows}:
                mkey = f"{m12_sets.REASK_SET}:{qid}" if reask else qid
                measured[mkey] = mark[mkey]
            done_path.parent.mkdir(parents=True, exist_ok=True)
            done_path.write_text(json.dumps(measured, indent=1), encoding="utf-8")
        if env.opts.set == JUDGES_SET and not self.smoke:
            res.summary += self._judge_report(res.rows, plan.items)
        fade = env.rt.runtime_cfg.runtime.emotion_fade
        for kind in ("emotion", "reaction"):   # M9 D26: the code rule's policies, floors from dev
            mine = [r for r in res.rows if isinstance(r["label"], dict) and policies.kind_of(r["question_id"]) == kind]
            # M11 (debate D29.1): the debate slice chooses its own floors and is reported apart
            debate = [r for r in mine if r.get("kind") == "debate"]
            mine = [r for r in mine if r.get("kind") != "debate"]
            if mine and not self.smoke:
                res.summary += policies.report(mine, kind, fade)
            if debate and not self.smoke:
                res.summary += policies.report(debate, kind, fade, title="Emotion (the debate slice, its own floor)")
        watch = [r for r in res.rows if r.get("kind") == "watch" and isinstance(r["label"], dict)
                 and policies.kind_of(r["question_id"]) == "emotion"]
        if watch and not self.smoke:   # M11 (debate D20): both merge rules side by side, for the user's choice
            res.summary += policies.merge_comparison(watch, fade)
        if not self.smoke:   # M10 (group-watch D23): who speaks (three parts) and "is the talk finished?"
            for part in who_policies.PARTS:
                mine = [r for r in res.rows if r["question_id"] == part and isinstance(r["label"], dict)]
                if mine:
                    res.summary += who_policies.who_report(mine, part)
            member = [r for r in res.rows if r["question_id"] in who_policies.MEMBER_QIDS
                      and isinstance(r["label"], dict)]
            if member:   # M11 (debate D21): the three member questions scored together
                res.summary += who_policies.member_report(member)
            talk = [r for r in res.rows if r["question_id"] == "talk_finished"]
            if talk:
                res.summary += who_policies.talk_report(talk)
            res.summary += m12_sets.reports(res.rows)   # M12: docs, standalone, english and D9's re-ask
        n_policy = sum(1 for r in res.rows if isinstance(r["label"], dict) and not r.get("invalid"))
        if self.smoke:
            res.summary.append(f"## Decisions (smoke only: {total + n_policy} item(s), never a measurement)")
        elif total:
            lo, hi = wilson(correct, total)
            res.summary += [f"## Decisions: policy accuracy {correct}/{total} (95% Wilson {lo:.2f}–{hi:.2f})",
                            order_line(flips, total, plan.items),
                            "- calibration (p bin → accuracy): " + ", ".join(
                                f"{k / 10:.1f}: {sum(v)}/{len(v)}" for k, v in sorted(bins.items()))]
        elif not n_policy:
            res.summary.append("## Decisions: nothing to measure" + (f" (unchanged: {', '.join(sorted(skipped))})"
                                                                     if skipped else ""))
        return res


    @staticmethod
    def _judge_report(rows: list[dict[str, Any]], items: list[dict[str, Any]]) -> list[str]:
        """B4 per judge; the record is updated only for a judge whose every item was asked in this run."""
        out = ["## Judge validation (B4: real ≥ 85 %, overall above the commonest-answer baseline, planted ≥ 90 %)"]
        results: dict[str, dict[str, Any]] = {}
        versions: dict[str, int] = {}
        for qid in sorted({r["question_id"] for r in rows}):
            got = [r for r in rows if r["question_id"] == qid and "correct" in r]
            want = sum(1 for i in items if i["question_id"] == qid)
            r = judges.b4_for(qid, got)
            partial = "" if len(got) == want else f" (partial: {len(got)}/{want})"
            verdict = "PASS" if r["passed"] else "FAIL"
            if qid == judges.PAIRWISE:   # M9 D29: known winners, both orders, ≥ 90 %
                out.append(f"- {qid} v{bank().get(qid).version}: the known winner preferred on {r['accuracy']:.2f} "
                           f"of {r['n']} pairs (order-averaged; rule ≥ 0.90) → {verdict}{partial}")
            else:
                fa = f", false alarms {r['false_alarms']} (rule ≤ 1)" if "false_alarms" in r else ""
                out.append(f"- {qid} v{bank().get(qid).version}: real {r['real']:.2f} (n {r['real_n']}), overall "
                           f"{r['overall']:.2f} against the baseline {r['baseline']:.2f}, planted {r['planted']:.2f} "
                           f"(n {r['planted_n']}){fa} → {verdict}{partial}")
            if len(got) == want:
                results[qid], versions[qid] = r, bank().get(qid).version
        if results:
            judges.update_record(results, versions)
        return out


# ── smoke ──
async def _advance(env: RunEnv, ms: float) -> None:
    clock = env.rt.clock
    if isinstance(clock, FrozenClock):
        await clock.advance(ms)
    else:
        await asyncio.sleep(ms / 1000)


async def conversation(env: RunEnv, mode: str) -> dict[str, Any]:
    import httpx

    from horizon.main import create_app

    spec = json.loads((SMOKE_DIR / f"{mode}.json").read_text(encoding="utf-8"))
    app = create_app(env.rt.cfg, runtime=env.rt)
    api = "/api/v1"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as c:
        body: dict[str, Any] = {"worldId": spec["world"], "mode": mode, "characterIds": spec["cast"]}
        if spec.get("config"):
            body["config"] = spec["config"]
        r = await c.post(f"{api}/sessions", json=body)
        if r.status_code != 201:
            raise RuntimeError(f"smoke {mode}: creating the session failed ({r.status_code}): {r.text[:300]}")
        sid = r.json()["session"]["id"]
        await _advance(env, 6000)
        cmd = {"one_on_one": "send", "group": "send", "watch": "watch/direct", "debate": "debate/interject"}[mode]
        for line in spec["lines"]:
            await c.post(f"{api}/sessions/{sid}/{cmd}", json={"text": line})
            await _advance(env, 20000)
        msgs = (await c.get(f"{api}/sessions/{sid}/messages", params={"limit": 1000})).json()["items"]
        await c.post(f"{api}/sessions/{sid}/end")
    replies = [m for m in msgs if m["author"]["type"] == "character"]
    from horizon.evals.reply_checks import Reply, check_replies  # M8 (D28): the reply-rule code checks, $0

    checks = check_replies([Reply(speaker=str(m["author"].get("characterId")), mode=mode, text=m["content"])
                            for m in replies], free_running=True)
    return {"mode": mode, "session": sid, "replies": len(replies),
            "complete": sum(1 for m in replies if m["status"] == "complete"), "checks": checks.summary()}


class Smoke:
    name = "smoke"

    def plan(self, opts: Options, prices: Any, *, paid: bool) -> Plan:
        d = Decisions(smoke=True).plan(opts, prices, paid=paid)
        return Plan(items=[*d.items, *MODES], estimate_usd=d.estimate_usd + (0.002 if paid else 0.0),
                    expected_s=d.expected_s + 60, paid=paid)

    async def run(self, env: RunEnv, plan: Plan) -> Result:
        res = Result()
        problems: list[str] = []
        for qid in sorted(bank().entries):
            problems += [f"{qid}: {p}" for p in wire_problems(wire_question(compile_entry(qid)))]
        n_lines = sum(1 for _ in all_items())
        dec_items = [i for i in plan.items if isinstance(i, dict)]
        d = await Decisions(smoke=True).run(env, Plan(dec_items, 0.0, 0.0, plan.paid))
        res.rows += d.rows
        convs = [await conversation(env, m) for m in MODES]
        res.rows += convs
        empty = [c["mode"] for c in convs if c["replies"] == 0]
        # M8 (persona-context 9.8): one drafter seed, one summary item and the first lines of each long script, so
        # every content suite's code path runs in CI at $0 (the judged figures are never measurements here)
        from horizon.evals.content import Drafter, Long, Summary
        content_lines: list[str] = []
        for suite, o in ((Drafter(), Options("drafter", limit=1)), (Summary(), Options("summary", limit=1)),
                         (Long(), Options("long", limit=3))):
            sub = RunEnv(rt=env.rt, opts=o, store=env.store, run_dir=env.run_dir, max_usd=env.max_usd)
            r = await suite.run(sub, suite.plan(o, env.rt.prices, paid=plan.paid))
            content_lines.append(f"- {suite.name}: {r.status}, {len(r.rows)} row(s)")
            if r.status != "ok":
                empty.append(suite.name)
        content_lines += await self.m9(env, plan, empty)
        content_lines += await self.m10(env, plan, empty)
        content_lines += await self.m11(env, plan, empty)
        content_lines += await self.m12(env, empty)
        res.summary += ["## Smoke (never compared with baselines)",
                        f"- bank: {len(bank().entries)} entr(ies), wire problems: {problems or 'none'}",
                        f"- datasets: {n_lines} line(s) load", *d.summary,
                        "- conversations: " + ", ".join(f"{c['mode']} {c['complete']}/{c['replies']}" for c in convs),
                        "- reply checks: " + ", ".join(f"{c['mode']} {json.dumps(c['checks'])}" for c in convs),
                        "- content suites:", *content_lines]
        if problems or empty or any(r.get("invalid") for r in d.rows):
            res.status = "failed"
        return res

    @staticmethod
    async def m9(env: RunEnv, plan: Plan, empty: list[str]) -> list[str]:
        """M9 (turn-plan-emotion 8.10): the first `moodline` item and one `latency` turn under `agent`, so both code
        paths run in CI at $0. In test mode a Decider fixture gives the item's Jev call 1 a confident face (the fake's
        1/8 answer is below the floor). The run's own profile is restored afterwards."""
        from horizon.ai.decider import ChoiceAnswer
        from horizon.ai.profile import ProfileSpec
        from horizon.evals.latency import Latency
        from horizon.evals.moodline import Moodline, candidates

        rt = env.rt
        out: list[str] = []
        before = rt.profile
        rt.set_profile(ProfileSpec(profile="agent", test_mode=rt.cfg.test_mode))
        try:
            if rt.cfg.test_mode:
                first = candidates(per_file=4)[0]
                rt.decider_fixtures.set("turn_plan", f"emotion_reply:{first['speaker']}",
                                        ChoiceAnswer("sad", confidence=0.9, probabilities={"sad": 0.9}))
            for suite, o in ((Moodline(), Options("moodline", limit=1, profile="agent")),
                             (Latency(), Options("latency", limit=1, profile="agent"))):
                sub = RunEnv(rt=rt, opts=o, store=env.store if suite.name == "moodline" else None,
                             run_dir=env.run_dir, max_usd=env.max_usd)
                r = await suite.run(sub, suite.plan(o, rt.prices, paid=plan.paid))
                out.append(f"- {suite.name}: {r.status}, {len(r.rows)} row(s)")
                if r.status != "ok" or (rt.cfg.test_mode and not r.rows):
                    empty.append(suite.name)
        finally:
            rt.set_profile(before)
            if rt.cfg.test_mode:
                rt.decider_fixtures.clear()
        return out


    @staticmethod
    async def m11(env: RunEnv, plan: Plan, empty: list[str]) -> list[str]:
        return await m11_smoke(env, plan, empty)

    @staticmethod
    async def m12(env: RunEnv, empty: list[str]) -> list[str]:
        from horizon.evals.deep_timing import deep_smoke

        return await deep_smoke(env, empty)

    @staticmethod
    async def m10(env: RunEnv, plan: Plan, empty: list[str]) -> list[str]:
        """M10 (group-watch 9.10): under `agent`, one planned group send with a follow plan, one planned watch turn
        (a one-turn free run), one episode recap and one follow-timing request, all at $0 in CI. In test mode Decider
        fixtures make the first slot and the follow plan pick someone (the fake's 1/n answer is below every floor)
        and the recap is a canned answer. The run's own profile is restored afterwards."""
        from horizon.ai.decider import ChoiceAnswer
        from horizon.ai.profile import ProfileSpec
        from horizon.evals.latency import Latency
        from horizon.evals.watch_suites import FreeRun, recap_context, seed_profiles

        rt = env.rt
        out: list[str] = []
        before = rt.profile
        rt.set_profile(ProfileSpec(profile="agent", test_mode=rt.cfg.test_mode))
        try:
            if rt.cfg.test_mode:
                rt.decider_fixtures.set("turn_plan", "who_first", ChoiceAnswer(
                    "chr_seedAmara", confidence=0.9, probabilities={"chr_seedAmara": 0.9}))
                rt.decider_fixtures.set("follow_plan", "who_second", ChoiceAnswer(
                    "chr_seedVictor", confidence=0.9, probabilities={"chr_seedVictor": 0.9}))
            g = await planned_group_send(env)
            out.append(f"- planned group send: {g} repl(ies)" + ("" if g == 2 or not rt.cfg.test_mode
                                                                 else " (expected 2: a first and a second)"))
            if g == 0 or (rt.cfg.test_mode and g != 2):
                empty.append("group follow plan")
            for suite, o in ((FreeRun(), Options("freerun", limit=1, profile="agent", mode="watch")),
                             (Latency(), Options("latency", limit=1, profile="agent", part="follow"))):
                sub = RunEnv(rt=rt, opts=o, store=None, run_dir=env.run_dir, max_usd=env.max_usd)
                r = await suite.run(sub, suite.plan(o, rt.prices, paid=plan.paid))
                out.append(f"- {suite.name}{f' --part {o.part}' if o.part else ''}: {r.status}, {len(r.rows)} row(s)")
                if r.status != "ok" or not r.rows:
                    empty.append(suite.name)
            if rt.fake is not None:
                from horizon.gateway.fake import load_canned
                purpose, canned = load_canned("episode-recaps")
                rt.fake.set_canned(purpose, canned)
            hist = {"world": "wld_seedSunnyHollow", "cast": ["chr_seedHana", "chr_seedRin", "chr_seedTakeshi"],
                    "premise": "A quiet morning at the flower shop.",
                    "lines": [{"seq": 2, "kind": "line", "speaker": "chr_seedHana", "text": "Morning! Coffee?",
                               "summary_upto": None, "summary": None}]}
            from horizon.ai.naive.summary import NaiveSummariser

            recap = await NaiveSummariser(rt.ai.deps).episode(recap_context(hist, 1, seed_profiles()))
            out.append(f"- episode recap: {len(recap.split())} word(s)")
            if not recap.strip():
                empty.append("recap")
        finally:
            rt.set_profile(before)
            if rt.cfg.test_mode:
                rt.decider_fixtures.clear()
        return out


SMOKE_DEBATE: dict[str, Any] = {"id": "smoke-debate", "world": "wld_seedMeridian",
                "cast": ["chr_evalSofia", "chr_seedMei", "chr_seedAmara", "chr_seedVictor"],
                "config": {"motion": "This house would tax sugary drinks", "format": "two_sided",
                           "sides": {"prop": ["chr_evalSofia", "chr_seedAmara"], "opp": ["chr_seedMei", "chr_seedVictor"]},
                           "roundsPreset": "quick", "phases": ["opening", "closing"], "turnLength": "short",
                           "moderator": "auto_host", "verdictBy": "arbiter", "rubric": [], "autoAdvance": True,
                           "pauseMs": 1500}}


async def m11_smoke(env: RunEnv, plan: Plan, empty: list[str]) -> list[str]:
    """M11 (debate 9.10): under `agent`, one Quick 2 v 2 debate with Auto host and Arbiter to its verdict, one
    debate-plan timing request and one rubric request, all at $0 in CI. In test mode the host lines and the verdict
    prose are canned (W14: synthetic until 10.7 records real ones). The run's own profile is restored afterwards."""
    from horizon.ai.agent import rubric
    from horizon.ai.profile import ProfileSpec
    from horizon.evals import debate_suites as ds

    rt = env.rt
    out: list[str] = []
    before = rt.profile
    rt.set_profile(ProfileSpec(profile="agent", test_mode=rt.cfg.test_mode))
    try:
        if rt.fake is not None:
            from horizon.gateway.fake import load_canned

            for name in ("debate-host", "debate-verdict"):
                purpose, canned = load_canned(name)
                rt.fake.set_canned(purpose, canned)
        await ds.install_cast(env)
        await ds.top_up(env, SMOKE_DEBATE["cast"])
        doc, complete, _, msgs, _ = await ds.drive_debate(env, SMOKE_DEBATE, resume=False)
        hosts = [m for m in msgs if m.get("kind") == "narration"]
        v = dict(doc.get("verdict") or {})
        out.append(f"- debate: {len(ds.arguments(doc))} argument(s), {len(hosts)} host line(s), verdict "
                   f"{v.get('decidedBy')} with {len(v.get('scores') or [])} score(s)")
        if not complete or not hosts or v.get("decidedBy") != "arbiter" or not v.get("scores"):
            empty.append("debate")
        slots = ds.natural_member_slots(doc)
        rows = await ds.plan_timing(env, [("smoke", ds.cut_request(doc, slots[0], ds.profiles()))] if slots else [])
        out.append(f"- debate-plan timing: {len(rows)} request(s)")
        if not rows:
            empty.append("debate-plan timing")
        sc = await rubric.score(rt.ai.deps, ds.verdict_request(doc))
        out.append(f"- rubric: {len(sc.bars or [])} bar(s)" + (f", failure {sc.failure}" if sc.failure else ""))
        if not sc.bars:
            empty.append("rubric")
    finally:
        rt.set_profile(before)
    return out


async def planned_group_send(env: RunEnv) -> int:
    """One `agent` group send through the app; the replies it got."""
    import httpx

    from horizon.main import create_app

    app = create_app(env.rt.cfg, runtime=env.rt)
    api = "/api/v1"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as c:
        r = await c.post(f"{api}/sessions", json={"worldId": "wld_seedMeridian", "mode": "group",
                                                  "characterIds": ["chr_seedAmara", "chr_seedMei", "chr_seedVictor"]})
        if r.status_code != 201:
            return 0
        sid = r.json()["session"]["id"]
        await _advance(env, 6000)
        before = len([m for m in (await c.get(f"{api}/sessions/{sid}/messages")).json()["items"]
                      if m["author"]["type"] == "character"])
        await c.post(f"{api}/sessions/{sid}/send", json={"text": "I'm moving to Lisbon next month."})
        await _advance(env, 30000)
        msgs = (await c.get(f"{api}/sessions/{sid}/messages", params={"limit": 1000})).json()["items"]
        await c.post(f"{api}/sessions/{sid}/end")
    return len([m for m in msgs if m["author"]["type"] == "character"]) - before


def _content() -> dict[str, Any]:
    from horizon.evals.content import Drafter, Long, Summary, Transcript
    from horizon.evals.debate_suites import DebateHistory, DebatePlant, DebateQuality, DebateSuite
    from horizon.evals.latency import Latency
    from horizon.evals.moodline import Moodline
    from horizon.evals.notfound_suite import NotFound
    from horizon.evals.retrieval_suite import Retrieval
    from horizon.evals.watch_suites import FreeRun, WatchHistory
    return {"drafter": Drafter(), "summary": Summary(), "long": Long(), "transcript": Transcript(),
            "moodline": Moodline(), "latency": Latency(), "watch-history": WatchHistory(), "freerun": FreeRun(),
            "debate-history": DebateHistory(), "debate-plant": DebatePlant(), "debate-quality": DebateQuality(),
            "debate": DebateSuite(), "retrieval": Retrieval(),
            "notfound": NotFound()}


SUITES: dict[str, Any] = {"canary": Canary(), "decisions": Decisions(), "smoke": Smoke(), **_content()}

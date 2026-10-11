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
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from horizon.ai.decider import Choice, ChoiceAnswer, Question, validate, wire_question
from horizon.ai.questions import bank
from horizon.domain.clock import FrozenClock
from horizon.evals import canary as canary_mod
from horizon.evals.metrics import wilson
from horizon.evals.runner import EVALS_DIR, Options, Plan, Result, RunEnv, decision_estimate
from horizon.gateway.context import call_ctx

DATASETS = EVALS_DIR / "datasets"
SMOKE_DIR = EVALS_DIR / "smoke"
MODES = ("one_on_one", "group", "watch", "debate")
STUB_VALUES = [{"key": "chr_a", "name": "A", "role": "r"}, {"key": "chr_b", "name": "B", "role": "r"}]
REQUIRED = ("id", "question_id", "split", "item", "label")


# ── datasets ──
def dataset_files(root: Path | None = None) -> list[Path]:
    root = root or DATASETS
    return sorted(root.rglob("*.jsonl")) if root.is_dir() else []


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


def all_items(root: Path | None = None) -> Iterator[dict[str, Any]]:
    for p in dataset_files(root):
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


def compile_entry(qid: str, values: list[dict[str, Any]] | None = None, seed: str = "smoke") -> Question:
    """The entry compiled as live; a dynamic choice with no values gets two stub options (the wire check needs ≥ 2)."""
    e = bank().get(qid)
    dynamic = e.type == "choice" and e.options.get("kind") != "static"
    return bank().question(qid, values=values or (STUB_VALUES if dynamic else ()), seed=seed)


def reordered(q: Question) -> Question:
    """The same choice with its options in reverse order (order bias, B3)."""
    if not isinstance(q, Choice):
        return q
    return Choice(q.instructions, dict(reversed(list(q.options.items()))), meta=q.meta)


# ── canary ──
class Canary:
    name = "canary"

    def plan(self, opts: Options, prices: Any, *, paid: bool) -> Plan:
        b = canary_mod.load_baseline(EVALS_DIR / "canary.json")
        items = b.items[: opts.limit] if opts.limit else b.items
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
        if env.opts.accept and res.status == "drift" and len(new_items) == len(plan.items):
            fp = canary_mod.accept(EVALS_DIR / "canary.json", new_items, res.model or "",
                                   dt.datetime.now(dt.UTC).isoformat())
            res.summary.append(f"- accepted as the new baseline (fingerprint {fp[:12]}…); every stored Jev answer is "
                               "now stale")
            res.status = "ok"
        return res


# ── decisions ──
def measured_path(env: RunEnv) -> Path:
    return env.run_dir.parents[1] / "decisions-measured.json"


class Decisions:
    name = "decisions"

    def __init__(self, smoke: bool = False) -> None:
        self.smoke = smoke

    def _items(self, opts: Options) -> list[dict[str, Any]]:
        items = [i for i in all_items() if bool(i.get("smoke_only")) == self.smoke]
        return items[: opts.limit] if opts.limit else items

    def plan(self, opts: Options, prices: Any, *, paid: bool) -> Plan:
        items = self._items(opts)
        est = 0.0
        for i in items:
            q = compile_entry(i["question_id"], i["item"].get("values"), seed=i["id"])
            est += 2 * decision_estimate(prices, i["item"]["state"], {i["question_id"]: wire_question(q)})
        return Plan(items=items, estimate_usd=est, expected_s=len(items) * 4.0, paid=paid)

    async def run(self, env: RunEnv, plan: Plan) -> Result:
        res = Result()
        done_path = measured_path(env)
        measured: dict[str, int] = json.loads(done_path.read_text(encoding="utf-8")) if done_path.is_file() else {}
        correct = total = flips = 0
        bins: dict[int, list[int]] = {}
        skipped: set[str] = set()
        for item in plan.items:
            qid = str(item["question_id"])
            version = bank().get(qid).version
            if not self.smoke and measured.get(qid) == version:
                skipped.add(qid)
                continue
            if await env.over_budget():
                res.status = "incomplete"
                break
            q = compile_entry(qid, item["item"].get("values"), seed=item["id"])
            answers = []
            for order in (q, reordered(q)):
                r = await env.rt.gateway.decide(item["item"]["state"], {qid: wire_question(order)}, call_ctx("eval_judge"))
                answers.append(validate(order, r.answers.get(qid)))
            a, b = answers
            row: dict[str, Any] = {"id": item["id"], "question_id": qid, "version": version, "label": item["label"],
                                   "smoke_only": bool(item.get("smoke_only"))}
            if isinstance(a, ChoiceAnswer) and isinstance(b, ChoiceAnswer):
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
                measured[qid] = bank().get(qid).version
            done_path.parent.mkdir(parents=True, exist_ok=True)
            done_path.write_text(json.dumps(measured, indent=1), encoding="utf-8")
        if self.smoke:
            res.summary.append(f"## Decisions (smoke only: {total} item(s), never a measurement)")
        elif total:
            lo, hi = wilson(correct, total)
            res.summary += [f"## Decisions: policy accuracy {correct}/{total} (95% Wilson {lo:.2f}–{hi:.2f})",
                            f"- order bias: {flips}/{total} answers changed when the options were reversed",
                            "- calibration (p bin → accuracy): " + ", ".join(
                                f"{k / 10:.1f}: {sum(v)}/{len(v)}" for k, v in sorted(bins.items()))]
        else:
            res.summary.append("## Decisions: nothing to measure" + (f" (unchanged: {', '.join(sorted(skipped))})"
                                                                     if skipped else ""))
        return res


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
    return {"mode": mode, "session": sid, "replies": len(replies),
            "complete": sum(1 for m in replies if m["status"] == "complete")}


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
        res.summary += ["## Smoke (never compared with baselines)",
                        f"- bank: {len(bank().entries)} entr(ies), wire problems: {problems or 'none'}",
                        f"- datasets: {n_lines} line(s) load", *d.summary,
                        "- conversations: " + ", ".join(f"{c['mode']} {c['complete']}/{c['replies']}" for c in convs)]
        if problems or empty or any(r.get("invalid") for r in d.rows):
            res.status = "failed"
        return res


SUITES: dict[str, Any] = {"canary": Canary(), "decisions": Decisions(), "smoke": Smoke()}

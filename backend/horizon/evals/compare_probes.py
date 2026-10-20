"""The Jev comparison's two paired probes (jev-comparison design D10, D11; model-comparison "Paired timing probe",
"Repeat probe"). Both ask the two models of `Options.pair` back to back on the same bodies, never from the store.

**Timing** (`compare-timing`, `--part a|b`: the window):
- **The bodies** are the manifest's own (compiled from the datasets exactly as the suites send them, private safety
  items left out), bucketed by their tokens: under 1k, 1k–2.5k and 2.5k–4k, 30 each, plus 5 near 10k and 5 near 25k.
  The manifest holds only 18 bodies over 2.5k and one near 10k, so (the user's choice, 2026-10-20) the last three
  buckets are topped up with *padded* bodies: a manifest body whose longest text field repeats its own lines up to the
  target size. Padded bodies are timing-only: never scored, never stored, labelled in every row.
- **The order:** 5 warm-up requests per model first (the first five small bodies; excluded and counted), then each
  body on both models, alternating which goes first.
- A provider error is recorded on its row (the oversize end may answer 429) and the window goes on.

**Repeat** (`compare-repeat`): the canary's 20 items (group A's A1 repeatability items) asked 3 times on each model.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from horizon.domain.pricing import count_tokens
from horizon.evals.runner import EVALS_DIR, Options, Plan, Result, RunEnv, decision_estimate

BUCKETS: tuple[tuple[str, int, int], ...] = (("<1k", 0, 1000), ("1k-2.5k", 1000, 2500), ("2.5k-4k", 2500, 4000),
                                             ("~10k", 8000, 12000), ("~25k", 20000, 30000))
PER_BUCKET = {"<1k": 30, "1k-2.5k": 30, "2.5k-4k": 30, "~10k": 5, "~25k": 5}
PAD_TO = {"2.5k-4k": 3200, "~10k": 10000, "~25k": 25000}
WARMUP = 5
REPEATS = 3
BUDGET_CODES = ("daily_budget_exceeded", "creation_budget_exceeded", "energy_exhausted")
CLOCK: Callable[[], float] = time.monotonic   # seconds; the tests advance a fake one


def body_tokens(state: Any, questions: Mapping[str, Any]) -> int:
    """The body's own tokens, as the gateway's estimate counts them (Jev's per-request overhead left out)."""
    return count_tokens(json.dumps(state, ensure_ascii=False)) + sum(
        count_tokens(json.dumps(q, ensure_ascii=False)) for q in questions.values())


def bucket_of(tokens: int) -> str | None:
    return next((name for name, lo, hi in BUCKETS if lo <= tokens < hi), None)


def manifest_bodies(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every non-private body the manifest lists, compiled from the datasets, with its hash and size ($0)."""
    from horizon.evals.manifest import _decisions_items, _other_items, body_hash

    listed = {h for name, s in manifest["sets"].items() if not name.startswith("safety:") for h in s["bodies"]}
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    items: Iterable[tuple[str, Any, dict[str, Any]]] = (
        *((name, state, qs) for name, _i, state, qs, _o in _decisions_items()),
        *((name, state, qs) for name, _i, state, qs in _other_items(test_mode=True) if not name.startswith("safety:")))
    for name, state, qs in items:
        h = body_hash(state, qs)
        if h in listed and h not in seen:
            seen.add(h)
            out.append({"set": name, "hash": h, "state": state, "questions": qs, "tokens": body_tokens(state, qs)})
    return sorted(out, key=lambda b: b["hash"])


def padded(body: Mapping[str, Any], target: int) -> dict[str, Any] | None:
    """The body with its longest text field extended by its own lines, cycling, until it reaches `target` tokens."""
    state = dict(body["state"]) if isinstance(body["state"], Mapping) else None
    if not state:
        return None
    key = max((k for k, v in state.items() if isinstance(v, str)), key=lambda k: len(state[k]), default=None)
    if key is None:
        return None
    text = str(state[key])
    lines = [ln for ln in text.split("\n") if ln.strip()] or [text]
    tokens = body_tokens(state, body["questions"])
    per_line = max(1, sum(count_tokens(ln) for ln in lines) // len(lines))
    i = 0
    while tokens < target:
        add = max(1, (target - tokens) // (2 * per_line))   # halving steps: at most one line past the target
        extra = [lines[(i + k) % len(lines)] for k in range(add)]
        i += add
        text = text + "\n" + "\n".join(extra)
        state[key] = text
        tokens = body_tokens(state, body["questions"])
    return {"set": body["set"], "hash": f"padded:{body['hash']}:{target}", "state": state,
            "questions": body["questions"], "tokens": tokens, "padded": True}


def timing_bodies(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    """D10's bodies: the manifest's first (by hash) in each bucket, topped up with padded ones where it runs short."""
    every = manifest_bodies(manifest)
    by: dict[str, list[dict[str, Any]]] = {name: [] for name, _, _ in BUCKETS}
    for b in every:
        name = bucket_of(b["tokens"])
        if name is not None:
            by[name].append(b)
    out: list[dict[str, Any]] = []
    for name, _, _ in BUCKETS:
        mine = [{**b, "bucket": name, "padded": False} for b in by[name][: PER_BUCKET[name]]]
        short = PER_BUCKET[name] - len(mine)
        if short > 0 and name in PAD_TO:   # the largest bodies padded up (the biggest first: the fewest repeats)
            used = {b["hash"] for b in mine}
            sources = sorted((b for b in every if b["hash"] not in used and b["tokens"] < PAD_TO[name]),
                             key=lambda b: (-b["tokens"], b["hash"]))
            for src in sources:
                if short == 0:
                    break
                p = padded(src, PAD_TO[name])
                if p is not None and bucket_of(p["tokens"]) == name:
                    mine.append({**p, "bucket": name})
                    short -= 1
        out += mine
    return out


def _clean(b: Mapping[str, Any]) -> dict[str, Any]:
    return {"set": b["set"], "hash": b["hash"], "bucket": b.get("bucket"), "tokens": b["tokens"],
            "padded": bool(b.get("padded"))}


async def _timed(env: RunEnv, model: str, state: Any, questions: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    from horizon.gateway.context import call_ctx
    from horizon.gateway.errors import ProviderError

    t0 = CLOCK()
    try:
        r = await env.rt.gateway.decide(state, questions, call_ctx("eval_judge"), model=model)
    except ProviderError as e:
        if e.code in BUDGET_CODES:
            raise
        return round((CLOCK() - t0) * 1000, 1), {"error": e.code, "status": e.status}
    return round((CLOCK() - t0) * 1000, 1), {"answered": bool(r.answers), "returned": r.model}


def _pair(opts: Options) -> tuple[str, str]:
    if not opts.pair:
        raise ValueError("a paired probe needs two models (compare-models passes them)")
    return opts.pair


class TimingProbe:
    name = "compare-timing"

    def refuse(self, opts: Options) -> str | None:
        if not opts.pair or not opts.against:
            return "horizon: compare-timing runs under `horizon eval compare-models` (it needs both models and a manifest)"
        if opts.part not in ("a", "b"):
            return "horizon: compare-timing needs --part a or b (the window)"
        return None

    def plan(self, opts: Options, prices: Any, *, paid: bool) -> Plan:
        manifest = json.loads(Path(str(opts.against)).read_text(encoding="utf-8"))
        bodies = timing_bodies(manifest)
        warm = [b for b in bodies if b["bucket"] == "<1k"][:WARMUP]
        per_model = sum(decision_estimate(prices, b["state"], b["questions"]) for b in [*warm, *bodies])
        return Plan(items=[{"warmup": warm, "bodies": bodies}], estimate_usd=2 * per_model,
                    expected_s=2 * (len(bodies) + len(warm)) * 1.0, paid=paid, calls_chat=False)

    async def run(self, env: RunEnv, plan: Plan) -> Result:
        res = Result()
        a, b = _pair(env.opts)
        window = str(env.opts.part)
        env.rt.gateway.allowed_bodies = None   # the probe picks the manifest's bodies itself; padded ones aren't listed
        spec = plan.items[0]
        res.summary.append(f"## Timing window {window} ({len(spec['bodies'])} bodies on {a} and {b}; started "
                           f"{time.strftime('%Y-%m-%d %H:%M %Z')})")
        for m in (a, b):
            for w in spec["warmup"]:
                ms, out = await _timed(env, m, w["state"], w["questions"])
                res.rows.append({"window": window, "model": m, "warmup": True, "ms": ms, **_clean(w), **out})
        for i, body in enumerate(spec["bodies"]):
            if await env.over_budget():
                res.status = "incomplete"
                res.summary.append("- stopped at the run's cap")
                break
            for m in ((a, b) if i % 2 == 0 else (b, a)):   # alternate which model goes first
                ms, out = await _timed(env, m, body["state"], body["questions"])
                res.rows.append({"window": window, "model": m, "warmup": False, "ms": ms, "first": m == (a, b)[i % 2],
                                 **_clean(body), **out})
        errors = sum(1 for r in res.rows if r.get("error"))
        res.summary.append(f"- {len(res.rows)} requests ({2 * len(spec['warmup'])} warm-up, excluded); "
                           f"provider errors {errors}")
        return res


class RepeatProbe:
    name = "compare-repeat"

    def refuse(self, opts: Options) -> str | None:
        return None if opts.pair else "horizon: compare-repeat runs under `horizon eval compare-models`"

    def plan(self, opts: Options, prices: Any, *, paid: bool) -> Plan:
        items = json.loads((EVALS_DIR / "canary.json").read_text(encoding="utf-8"))["items"]
        per = sum(decision_estimate(prices, i["state"], i["questions"]) for i in items)
        return Plan(items=items, estimate_usd=2 * REPEATS * per, expected_s=2 * REPEATS * len(items) * 1.0, paid=paid,
                    calls_chat=False)

    async def run(self, env: RunEnv, plan: Plan) -> Result:
        from horizon.gateway.context import call_ctx

        res = Result()
        models = _pair(env.opts)
        for k in range(REPEATS):
            for item in plan.items:
                if await env.over_budget():
                    res.status = "incomplete"
                    res.summary.append("- stopped at the run's cap")
                    return res
                for m in models:
                    r = await env.rt.gateway.decide(item["state"], item["questions"], call_ctx("eval_judge"), model=m)
                    res.rows.append({"model": m, "id": item["id"], "ask": k, "answers": dict(r.answers),
                                     "returned": r.model})
        res.summary.append(f"## Repeat probe: {len(plan.items)} canary items × {REPEATS} on {', '.join(models)}")
        return res

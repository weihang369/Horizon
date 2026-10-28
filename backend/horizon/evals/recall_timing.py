"""`horizon eval latency --part recall` (memory design D33's timing; doc 09 check 4; task 10.6).

- **The database:** the retrieval corpus loaded as `latency --part deep` loads it, and each corpus character given an
  overflow (`memory_suite.overflow_list`, 50 memories), so "needs something from earlier?" is asked for them.
- **Forced by fixture:** the answers only (Jev call 1 is still asked and timed; a gate that was late or failed is
  counted). The recall arm: "needs documents?" no, "needs something from earlier?" yes (check 4: 10 1:1 turns asking
  for an overflow memory). The both arm: both yes (D33: 50 1:1 turns on the corpus questions, 8 passage checks and up
  to 6 recall checks at once, plus the set check).
- **Timed per deep run:** recall end to end (its query, the search, Jev call 2 and the keep), the slowest passage
  check and the slowest recall check (each from when it was sent), and how much later than the documents chain the
  recall branch ended (the tail recall adds to the turn). Jev's 429s by purpose and the first word (send → first
  token; the turn is stopped there).
- **The store is bypassed** (W10): the runner gives `latency` no store.

D33's rule: a recall tail over ≈ 200 ms at p90 goes to the user as a choice (one choice is a single 6-question recall
request, which reopens rag's locked shape).
"""

from __future__ import annotations

import contextlib
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any

from horizon.domain.pricing import estimate_chat
from horizon.evals.metrics import percentile
from horizon.evals.runner import Options, Plan, Result, RunEnv, decision_estimate

ARMS: tuple[tuple[str, int], ...] = (("recall", 10), ("both", 50))
TITLES = {"recall": "recall only (check 4)", "both": "both gates (D33)"}
FORCED_YES, FORCED_NO = 0.95, 0.05
TAIL_P90_MS = 200.0
OVERFLOW_N = 50


def counts(opts: Options) -> dict[str, int]:
    return {arm: opts.limit or n for arm, n in ARMS}


def plan(opts: Options, prices: Any, *, paid: bool) -> Plan:
    n = counts(opts)
    call1 = decision_estimate(prices, {"quoted_latest": "x" * 2400}, {"q": {"instructions": "x" * 1400}})
    passage = decision_estimate(prices, {"mode": "one_on_one", "quoted_query": {"message": "x" * 200},
                                         "quoted_passage": {"text": "x" * 1200}},
                                {"q": {"type": "score", "criteria": ["a", "b", "c"]}})
    check = decision_estimate(prices, {"quoted_query": "x" * 200, "quoted_candidate": "x" * 400},
                              {"q": {"instructions": "x" * 400}})
    first_word = estimate_chat(prices, prefix_tokens=5000, warm=True, other_in=1900, expected_out_tokens=8,
                               period="off_peak")
    emb = 2 * 40 * prices.embedding.input_per_m / 1e6
    recall = 6 * check + emb
    est = n["recall"] * (call1 + recall + first_word) + n["both"] * (call1 + 8.3 * passage + recall + first_word)
    est += (62_000 + 4 * OVERFLOW_N * 30) * prices.embedding.input_per_m / 1e6   # the corpus and the overflows
    items = [{"arm": arm, "n": k} for arm, k in n.items()]
    return Plan(items=items, estimate_usd=est, expected_s=180 + (n["recall"] + n["both"]) * 7.0, paid=paid)


# ── the instruments ──
@dataclass
class Recorder:
    arm: str = ""
    runs: list[dict[str, Any]] = field(default_factory=list)
    open: dict[int, dict[str, Any]] = field(default_factory=dict)
    rate_limited: Counter[str] = field(default_factory=Counter)
    gates_not_back: Counter[str] = field(default_factory=Counter)

    def row(self, req: Any) -> dict[str, Any]:
        key = id(req)
        if key not in self.open:
            self.open[key] = {"arm": self.arm, "session": req.session.session_id, "speaker": req.speaker.id}
            self.runs.append(self.open[key])
        return self.open[key]


def _ms(clock: Any, t0: Any) -> float:
    return round(float((clock.now() - t0).total_seconds()) * 1000, 1)


@contextlib.contextmanager
def instrumented(env: RunEnv, rec: Recorder) -> Iterator[None]:
    from horizon.ai.agent import deep, gates
    from horizon.ai.agent import recall as rc
    from horizon.ai.contexts import GateAnswer
    from horizon.gateway.errors import ProviderError

    clock = env.rt.clock
    read0, read_recall0 = gates.read, gates.read_recall

    def forced(res: Any, who: Sequence[str], *, nouls: bool, message_id: str | None = None) -> Any:
        found, msg = read0(res, who, nouls=nouls, message_id=message_id)
        rec.gates_not_back[rec.arm] += sum(1 for g in found.values() if g.outcome != "jev")
        p = FORCED_YES if rec.arm == "both" else FORCED_NO
        return {c: GateAnswer(p=p, outcome="jev") for c in found}, msg

    def forced_recall(res: Any, who: Sequence[str]) -> Any:
        found = read_recall0(res, who)
        rec.gates_not_back[rec.arm] += sum(1 for g in found.values() if g.outcome != "jev")
        return {c: GateAnswer(p=FORCED_YES, outcome="jev") for c in found}

    D = deep.DeepSteps
    recall0, docs_chain0 = D.recall, D.docs_chain
    check0 = rc.check

    async def recall(self: Any, req: Any, docs_bundle: Any) -> Any:
        t0 = clock.now()
        out = await recall0(self, req, docs_bundle)
        r = rec.row(req)
        r.update(recall_ms=_ms(clock, t0), recall_end=clock.now(), recall_outcome=out["recall_outcome"],
                 recall_kept=len(out["recall"]), recall_lists=out["recall_lists"])
        return out

    async def docs_chain(self: Any, req: Any, bundle: Any, rewrite: Any) -> Any:
        t0 = clock.now()
        out = await docs_chain0(self, req, bundle, rewrite)
        r = rec.row(req)
        r.update(docs_ms=_ms(clock, t0), docs_end=clock.now(), docs_outcome=out.outcome)
        return out

    async def check(deps: Any, req: Any, bundle: Any, picked: Any, knobs: Any, *, wait_ms: float | None = None) -> Any:
        ps, slowest = await check0(deps, req, bundle, picked, knobs, wait_ms=wait_ms)
        rec.row(req).update(recall_slowest_ms=slowest, recall_checks=len(ps),
                            recall_missing=sum(1 for p in ps if p is None))
        return ps, slowest

    D_check0 = D.check

    async def passage_check(self: Any, req: Any, bundle: Any, result: Any, hits: Any) -> Any:
        out = await D_check0(self, req, bundle, result, hits)
        rec.row(req).update(passage_slowest_ms=out[3], passage_checks=len(out[0]))
        return out

    decider = env.rt.decider
    decide0 = decider._decide

    async def counted(state: Any, questions: Any, ctx: Any, **kw: Any) -> Any:
        try:
            return await decide0(state, questions, ctx, **kw)
        except ProviderError as e:
            if e.code == "rate_limited":
                rec.rate_limited[ctx.purpose] += 1
            raise

    gates.read, gates.read_recall = forced, forced_recall
    D.recall, D.docs_chain, D.check = recall, docs_chain, passage_check   # type: ignore[method-assign]
    rc.check = check
    decider._decide = counted
    try:
        yield
    finally:
        gates.read, gates.read_recall = read0, read_recall0
        D.recall, D.docs_chain, D.check = recall0, docs_chain0, D_check0   # type: ignore[method-assign]
        rc.check = check0
        decider._decide = decide0


# ── the items ──
def turns(arm: str, n: int) -> list[tuple[str, str]]:
    """(character, message): the overflow probes of the corpus characters (recall), else the corpus questions."""
    from horizon.evals import retrieval as R
    from horizon.evals.deep_timing import turns_1to1
    from horizon.evals.memory_suite import cid_of, facts

    if arm == "both":
        return turns_1to1(n, 0)
    corpus = set(R.CHARACTERS.values())
    pool = [(cid_of(f.who), f.probe) for f in facts() if f.lang == "en" and cid_of(f.who) in corpus]
    return [pool[(k * 7) % len(pool)] for k in range(n)] if pool else []


async def plant_overflows(env: RunEnv) -> dict[str, str]:
    """Each corpus character's overflow: its first fact's list (the needed memory ranked below the 1,000-token list)."""
    from horizon.evals import retrieval as R
    from horizon.evals.memory_suite import cid_of, facts, overflow_list, plant, wipe
    from horizon.sessions.context import characters

    rows = await characters(env.rt, list(R.CHARACTERS.values()))
    out: dict[str, str] = {}
    for cid in R.CHARACTERS.values():
        f = next(x for x in facts() if cid_of(x.who) == cid and x.lang == "en")
        world = str(rows[cid]["world_id"])
        await wipe(env.rt, cid, keep_seed=True)
        await plant(env.rt, cid, world, overflow_list(f.id, OVERFLOW_N))
        out[cid] = f.id
    return out


async def run(env: RunEnv, plan: Plan, res: Result) -> None:
    import httpx

    from horizon.evals.debate_suites import top_up
    from horizon.evals.deep_timing import open_session
    from horizon.evals.latency import Latency
    from horizon.evals.retrieval_suite import prepare
    from horizon.main import create_app
    from horizon.sessions.context import characters

    await prepare(env, {})
    await plant_overflows(env)
    rec = Recorder()
    n = {it["arm"]: int(it["n"]) for it in plan.items}
    app = create_app(env.rt.cfg, runtime=env.rt)
    with instrumented(env, rec):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as c:
            for arm, _ in ARMS:
                if res.status != "ok" or not n.get(arm):
                    continue
                rec.arm = arm
                todo = turns(arm, n[arm])
                rows = await characters(env.rt, sorted({cid for cid, _ in todo}))
                sessions: dict[str, str] = {}
                for cid, text in todo:
                    if await env.over_budget():
                        res.status = "incomplete"
                        break
                    await top_up(env, [cid])
                    if cid not in sessions:
                        sid = await open_session(env, c, str(rows[cid]["world_id"]), "one_on_one", [cid])
                        if sid is None:
                            res.status = "incomplete" if env.refused else "failed"
                            break
                        sessions[cid] = sid
                    try:
                        row = await Latency.guarded(env, Latency().one(env, c, sessions[cid], cid, text))
                    except TimeoutError:
                        res.status = "incomplete"
                        break
                    if row is None:
                        res.status = "incomplete"
                        break
                    res.rows.append({"arm": arm, **row})
                for sid in sessions.values():
                    await c.post(f"/api/v1/sessions/{sid}/end")
    for r in rec.runs:
        if r.get("recall_end") is not None and r.get("docs_end") is not None:
            r["recall_after_docs_ms"] = round(max(0.0, (r["recall_end"] - r["docs_end"]).total_seconds() * 1000), 1)
        r.pop("recall_end", None)
        r.pop("docs_end", None)
    res.rows += [{"arm": r["arm"], "deep_run": r} for r in rec.runs]
    res.summary += report(res.rows, rec, env.rt.runtime_cfg.runtime.retrieval.agent)


# ── the report ──
def q(xs: Sequence[float]) -> str:
    if not xs:
        return "no samples"
    return (f"p50 {percentile(xs, 0.5):.0f} ms, p90 {percentile(xs, 0.9):.0f} ms, max {max(xs):.0f} ms "
            f"(n {len(xs)})")


def _vals(runs: Sequence[dict[str, Any]], key: str) -> list[float]:
    return [float(r[key]) for r in runs if r.get(key) is not None]


def report(rows: Sequence[dict[str, Any]], rec: Recorder, knobs: Any) -> list[str]:
    check_ms = float(knobs.recall.check_ms) if knobs is not None and knobs.recall is not None else 1500.0
    out = ["## Recall timing (memory D33; doc 09 check 4): the gates forced, the store bypassed"]
    for arm, _ in ARMS:
        runs = [r for r in rec.runs if r["arm"] == arm]
        mine = [r for r in rows if r.get("arm") == arm and "deep_run" not in r]
        if not runs and not mine:
            continue
        out.append(f"### {TITLES[arm]}: {len(runs)} deep run(s)")
        out.append(f"- send → first word: {q(_vals(mine, 'to_token_ms'))}")
        out.append(f"- recall end to end (query, search, Jev call 2, keep): {q(_vals(runs, 'recall_ms'))}")
        rs = _vals(runs, "recall_slowest_ms")
        out.append(f"- the slowest recall check of each run (of ≤ 6): {q(rs)}; at checkMs ({check_ms:.0f} ms): "
                   f"{sum(1 for s in rs if s >= check_ms)}; answers missing "
                   f"{sum(int(r.get('recall_missing') or 0) for r in runs)}")
        out.append("- recall outcomes: " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(
            str(r.get("recall_outcome", "none")) for r in runs).items())))
        out.append(f"- no query vector: {sum(1 for r in runs if (r.get('recall_lists') or {}).get('memories_dense') == 0)}")
        if arm == "both":
            ps = _vals(runs, "passage_slowest_ms")
            both = [max(float(r["passage_slowest_ms"]), float(r["recall_slowest_ms"])) for r in runs
                    if r.get("passage_slowest_ms") is not None and r.get("recall_slowest_ms") is not None]
            tail = _vals(runs, "recall_after_docs_ms")
            out.append(f"- slowest of the 8 passage checks: {q(ps)}")
            out.append(f"- slowest of all 14 (passages and recall): {q(both)}")
            out.append(f"- the documents chain: {q(_vals(runs, 'docs_ms'))}")
            out.append(f"- recall ending after the documents (the tail it adds): {q(tail)}")
            if tail and percentile(tail, 0.9) > TAIL_P90_MS:
                out.append(f"- **D33: the tail is {percentile(tail, 0.9):.0f} ms at p90, over ≈ {TAIL_P90_MS:.0f} ms: "
                           "the user gets a choice** (e.g. one 6-question recall request, reopening rag's shape)")
        if rec.gates_not_back.get(arm):
            out.append(f"- gates not back from Jev call 1 (forced anyway): {rec.gates_not_back[arm]}")
    out.append("### Overall")
    out.append("- Jev 429s: " + (", ".join(f"{p} {k}" for p, k in sorted(rec.rate_limited.items())) or "none"))
    every = _vals(rec.runs, "recall_slowest_ms")
    if every and percentile(every, 0.9) > check_ms:
        out.append(f"- the recall checks' p90 {percentile(every, 0.9):.0f} ms is past checkMs ({check_ms:.0f} ms): a "
                   "deadline change goes to the user")
    return out

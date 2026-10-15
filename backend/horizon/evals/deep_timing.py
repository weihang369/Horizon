"""`horizon eval latency --part deep` (rag design D24; doc 10 check 2; docs/ai/02 B8; tasks 9.7, 11.9).

- **The database:** fully loaded, as `retrieval` loads it: every corpus document as its character's source and every
  seed document indexed (`retrieval_suite.prepare`).
- **The arms:** 100 deep 1:1 turns with a rewrite and 100 without, then 25 deep turns each in group, debate and watch
  (`--limit N`: N per arm).
- **Forced by fixture:** every "needs documents?" reads yes (0.95) and, in 1:1, "standalone?" reads 0.1 (the rewrite
  arm) or 0.9, with "English?" 0.95. Only the answers are replaced: Jev call 1 is still asked and timed, and a gate
  that was late or failed is counted.
- **Timed per step:** Jev call 1, the rewrite and the embeddings (the ledger), the search (wall time in process), the
  slowest `deep_check` and the set check, and the first word (send → first token in 1:1 and group; `turn.end` → the
  next first token in debate and watch).
- **Counted:** Jev's 429s by purpose (a 429 is never charged, so never in the ledger) and the deep runs that fell back.
- **The store is bypassed** (W10): the runner gives `latency` no store.

1:1 and group turns are stopped at their first word, like the M9 part; debate and watch run whole (their next speaker
is the measure). Targets: NFR-01 for each 1:1 arm, reported apart; NFR-02 (3 s p50) for group, debate and watch.
"""

from __future__ import annotations

import contextlib
import math
import time
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any

from horizon.domain.pricing import estimate_chat
from horizon.domain.timeutil import ms_from_iso
from horizon.evals.metrics import percentile
from horizon.evals.runner import Options, Plan, Result, RunEnv, decision_estimate

ARMS: tuple[tuple[str, int], ...] = (("one_on_one_rewrite", 100), ("one_on_one_plain", 100), ("group", 25),
                                     ("debate", 25), ("watch", 25))
TITLES = {"one_on_one_rewrite": "1:1 with a rewrite", "one_on_one_plain": "1:1 without a rewrite",
          "group": "group", "debate": "debate", "watch": "watch"}
FORCED_GATE = 0.95
STANDALONE = {"one_on_one_rewrite": 0.1, "one_on_one_plain": 0.9}
ENGLISH_P = 0.95
PLAN_PURPOSES = ("turn_plan", "follow_plan", "debate_plan")
MERIDIAN = ("chr_seedAmara", "chr_seedMei", "chr_seedVictor")
WATCH_PREMISE = "The council's emergency budget meeting, the night before the vote."
NFR01_P50_MS, NFR01_P90_MS, NFR02_P50_MS = 2000.0, 4000.0, 3000.0
API = "/api/v1"


def counts(opts: Options) -> dict[str, int]:
    return {arm: opts.limit or n for arm, n in ARMS}


def plan(opts: Options, prices: Any, *, paid: bool) -> Plan:
    n = counts(opts)
    call1 = decision_estimate(prices, {"quoted_latest": "x" * 2400}, {"q": {"instructions": "x" * 1200}})
    check = decision_estimate(prices, {"mode": "one_on_one", "quoted_query": {"message": "x" * 200},
                                       "quoted_passage": {"text": "x" * 1200}},
                              {"q": {"type": "score", "criteria": ["a", "b", "c"]}})
    deep = 8 * check + 0.3 * check + 2 * 40 * prices.embedding.input_per_m / 1e6
    rewrite = estimate_chat(prices, prefix_tokens=0, warm=False, other_in=700, expected_out_tokens=40,
                            period="off_peak")
    first_words = estimate_chat(prices, prefix_tokens=4000, warm=True, other_in=1700, expected_out_tokens=8,
                                period="off_peak")
    whole = estimate_chat(prices, prefix_tokens=4000, warm=True, other_in=1700, expected_out_tokens=200,
                          period="off_peak")
    one = n["one_on_one_rewrite"] * (call1 + deep + rewrite + first_words) + n["one_on_one_plain"] * (
        call1 + deep + first_words)
    group = n["group"] * (call1 + deep + rewrite + first_words)
    debate = math.ceil(n["debate"] * 4 / 3) * (call1 + whole) + n["debate"] * deep   # ≈ 1 in 4 speakers has no sources
    watch = n["watch"] * (call1 + deep + whole)
    corpus = 62_000 * prices.embedding.input_per_m / 1e6
    items = [{"arm": arm, "n": k} for arm, k in n.items()]
    expected = (n["one_on_one_rewrite"] + n["one_on_one_plain"] + n["group"]) * 6.0 + (n["debate"] + n["watch"]) * 9.0
    return Plan(items=items, estimate_usd=one + group + debate + watch + corpus, expected_s=120 + expected, paid=paid)


# ── the instruments ──
@dataclass
class Recorder:
    """What the patched seams saw: one row per deep run, the 429s, the set checks and the gates that weren't back."""

    arm: str = ""
    standalone: float = 0.9
    runs: list[dict[str, Any]] = field(default_factory=list)
    open: dict[int, dict[str, Any]] = field(default_factory=dict)
    rate_limited: Counter[str] = field(default_factory=Counter)
    set_ms: dict[str, list[float]] = field(default_factory=dict)
    gates_not_back: Counter[str] = field(default_factory=Counter)

    def row(self, req: Any) -> dict[str, Any]:
        key = id(req)
        if key not in self.open:
            self.open[key] = {"arm": self.arm, "session": req.session.session_id, "mode": req.session.mode,
                              "speaker": req.speaker.id, "kind": req.kind}
            self.runs.append(self.open[key])
        return self.open[key]


def _ms(clock: Any, t0: Any) -> float:
    return round(float((clock.now() - t0).total_seconds()) * 1000, 1)


@contextlib.contextmanager
def instrumented(env: RunEnv, rec: Recorder) -> Iterator[None]:
    """For the run only: the gates forced (D24's fixture), each deep step timed, and Jev's 429s counted."""
    from horizon.ai.agent import deep, gates
    from horizon.ai.contexts import GateAnswer
    from horizon.gateway.errors import ProviderError

    clock = env.rt.clock
    real_read = gates.read

    def forced(res: Any, who: Sequence[str], *, nouls: bool, message_id: str | None = None) -> Any:
        found, msg = real_read(res, who, nouls=nouls, message_id=message_id)
        rec.gates_not_back[rec.arm] += sum(1 for g in found.values() if g.outcome != "jev")
        found = {c: GateAnswer(p=FORCED_GATE, outcome="jev") for c in found}
        if msg is not None:
            msg = msg.model_copy(update={"standalone": rec.standalone, "english": ENGLISH_P, "outcome": "jev"})
        return found, msg

    D = deep.DeepSteps
    gather0, search0, check0, keep0 = D.gather, D.search, D.check, D.keep

    async def gather(self: Any, req: Any) -> Any:
        t0 = clock.now()
        try:
            return await gather0(self, req)
        finally:
            rec.row(req)["gather_ms"] = _ms(clock, t0)

    async def search(self: Any, req: Any, bundle: Any) -> Any:
        t0 = time.perf_counter()   # local work: wall time, also under the virtual clock
        try:
            return await search0(self, req, bundle)
        finally:
            rec.row(req)["search_ms"] = round((time.perf_counter() - t0) * 1000, 2)

    async def check(self: Any, req: Any, bundle: Any, result: Any, hits: Any) -> Any:
        t0 = clock.now()
        out = await check0(self, req, bundle, result, hits)
        r = rec.row(req)
        r.update(check_ms=_ms(clock, t0), slowest_ms=out[3], checks=len(out[0]), failed=bool(out[2]))
        return out

    def keep(self: Any, req: Any, *args: Any, **kwargs: Any) -> Any:
        out = keep0(self, req, *args, **kwargs)
        rec.row(req).update(outcome=out.outcome, rewrite_status=out.rewrite_status)
        rec.open.pop(id(req), None)
        return out

    decider = env.rt.decider
    decide0 = decider._decide

    async def counted(state: Any, questions: Any, ctx: Any, **kw: Any) -> Any:
        t0 = clock.now()
        try:
            return await decide0(state, questions, ctx, **kw)
        except ProviderError as e:
            if e.code == "rate_limited":
                rec.rate_limited[ctx.purpose] += 1
            raise
        finally:
            if deep.PASSAGE_SET in questions:
                rec.set_ms.setdefault(rec.arm, []).append(_ms(clock, t0))

    gates.read = forced
    D.gather, D.search, D.check, D.keep = gather, search, check, keep   # type: ignore[method-assign]
    decider._decide = counted
    try:
        yield
    finally:
        gates.read = real_read
        D.gather, D.search, D.check, D.keep = gather0, search0, check0, keep0   # type: ignore[method-assign]
        decider._decide = decide0


# ── the arms ──
def messages(cid: str | None, n: int) -> list[str]:
    """The retrieval questions' messages for one character (any Meridian one for a group), in order, repeated."""
    from horizon.evals import retrieval as R

    who = {cid} if cid else set(MERIDIAN)
    pool = [str(q["message"]) for q in R.load_questions() if q["kind"] != "unanswerable" and q["character"] in who]
    return [pool[k % len(pool)] for k in range(n)] if pool else []


def turns_1to1(n: int, offset: int) -> list[tuple[str, str]]:
    """`n` (character, message) pairs from the answerable questions, round-robin over the characters that have them.
    The plain arm starts `offset` further on, so the two arms don't send the same text (an embedding seen once is
    cheaper the second time)."""
    from horizon.evals import retrieval as R

    per: dict[str, list[str]] = {}
    for q in R.load_questions():
        if q["kind"] != "unanswerable":
            per.setdefault(str(q["character"]), []).append(str(q["message"]))
    order = [cid for cid in R.CHARACTERS.values() if cid in per]
    pool: list[tuple[str, str]] = []
    for k in range(max((len(v) for v in per.values()), default=0)):
        pool += [(cid, per[cid][k]) for cid in order if k < len(per[cid])]
    return [pool[(offset + k) % len(pool)] for k in range(n)] if pool else []


async def one_on_one(env: RunEnv, c: Any, rec: Recorder, arm: str, n: int, res: Result) -> list[str]:
    """`n` sends, a fresh session per character per arm; each stopped at its first word."""
    from horizon.evals.debate_suites import top_up
    from horizon.evals.latency import Latency
    from horizon.sessions.context import characters

    turns = turns_1to1(n, 0 if arm == "one_on_one_rewrite" else n)
    rows = await characters(env.rt, sorted({cid for cid, _ in turns}))
    sessions: dict[str, str] = {}
    for cid, text in turns:
        if await env.over_budget():
            res.status = "incomplete"
            break
        await top_up(env, [cid])
        if cid not in sessions:
            sid = await open_session(env, c, str(rows[cid]["world_id"]), "one_on_one", [cid])
            if sid is None:
                res.status = "failed"
                break
            sessions[cid] = sid
        row = await Latency.guarded(env, Latency().one(env, c, sessions[cid], cid, text))
        if row is None:
            res.status = "incomplete"
            break
        res.rows.append({"arm": arm, **row})
    return list(sessions.values())


async def group(env: RunEnv, c: Any, rec: Recorder, n: int, res: Result) -> list[str]:
    from horizon.evals.debate_suites import top_up
    from horizon.evals.latency import Latency

    sid = await open_session(env, c, "wld_seedMeridian", "group", list(MERIDIAN))
    if sid is None:
        res.status = "failed"
        return []
    for text in messages(None, n):
        if await env.over_budget():
            res.status = "incomplete"
            break
        await top_up(env, list(MERIDIAN))
        row = await Latency.guarded(env, Latency().one(env, c, sid, None, text))
        if row is None:
            res.status = "incomplete"
            break
        res.rows.append({"arm": "group", **row})
    return [sid]


async def watch(env: RunEnv, rec: Recorder, n: int, res: Result) -> list[str]:
    from horizon.evals.debate_suites import top_up
    from horizon.evals.watch_suites import drive_watch

    await top_up(env, list(MERIDIAN))
    script = {"id": "latency-deep-watch", "world": "wld_seedMeridian", "cast": list(MERIDIAN),
              "premise": WATCH_PREMISE, "turns": n, "paceMs": 500}
    _, complete, sid, _ = await drive_watch(env, script)
    if not complete:
        res.status = "incomplete"
    res.rows += [{"arm": "watch", "session": sid, "gap_ms": g} for g in await next_word_gaps(env, sid)]
    return [sid]


def debate_scripts() -> list[dict[str, Any]]:
    """The committed debate scripts with two or more corpus characters (the others have no sources: quick turns)."""
    from horizon.evals import retrieval as R
    from horizon.evals.debate_suites import scripts

    corpus = set(R.CHARACTERS.values())
    return [s for s in scripts() if sum(1 for cid in s["cast"] if cid in corpus) >= 2]


async def debate(env: RunEnv, rec: Recorder, n: int, res: Result) -> list[str]:
    """Whole debates, one after another, until `n` deep turns have run."""
    from horizon.evals.debate_suites import drive_debate, install_cast, top_up

    await install_cast(env)
    sids: list[str] = []
    for script in debate_scripts():
        if sum(1 for r in rec.runs if r["arm"] == "debate") >= n:
            break
        if await env.over_budget():
            res.status = "incomplete"
            break
        await top_up(env, script["cast"])
        _, complete, sid, _, _ = await drive_debate(env, script)
        sids.append(sid)
        res.rows += [{"arm": "debate", "session": sid, "gap_ms": g} for g in await next_word_gaps(env, sid)]
        if not complete:
            res.status = "incomplete"
            break
    return sids


async def open_session(env: RunEnv, c: Any, world: str, mode: str, cast: list[str]) -> str | None:
    from horizon.evals.content import wait_idle

    r = await c.post(f"{API}/sessions", json={"worldId": world, "mode": mode, "characterIds": cast})
    if r.status_code != 201:
        return None
    sid = str(r.json()["session"]["id"])
    await wait_idle(env, sid)
    return sid


async def next_word_gaps(env: RunEnv, sid: str) -> list[float]:
    """`turn.end` → the next character's first token, per turn (NFR-02)."""
    from horizon.evals.latency import Latency

    evs = await Latency.events(env, sid)
    gaps = []
    for end in (e for e in evs if e["type"] == "turn.end"):
        tok = next((e for e in evs if e["type"] == "token" and e["seq"] > end["seq"]), None)
        if tok is not None:
            gaps.append(float(ms_from_iso(tok["at"]) - ms_from_iso(end["at"])))
    return gaps


async def ledger(env: RunEnv, sessions: dict[str, list[str]]) -> dict[str, dict[str, list[float]]]:
    """Each arm's ledger latencies by step: Jev call 1, the rewrite, the embeddings and each `deep_check` request."""
    from sqlalchemy import select

    from horizon.db import tables as t

    U = t.usage_records.c
    steps = {"call1": PLAN_PURPOSES, "rewrite": ("query_rewrite",), "embed": ("query_embed",),
             "deep_check": ("deep_check",)}
    out: dict[str, dict[str, list[float]]] = {}
    async with env.rt.db.read() as conn:
        for arm, sids in sessions.items():
            got = (await conn.execute(select(U.purpose, U.latency_ms).where(U.session_id.in_(sids)))).all() \
                if sids else []
            out[arm] = {k: [float(r[1]) for r in got if r[0] in ps and r[1] is not None] for k, ps in steps.items()}
    return out


# ── the run ──
async def run(env: RunEnv, plan: Plan, res: Result) -> None:
    import httpx

    from horizon.evals.retrieval_suite import prepare
    from horizon.main import create_app

    await prepare(env, {})
    rec = Recorder()
    n = {it["arm"]: int(it["n"]) for it in plan.items}
    sessions: dict[str, list[str]] = {}
    app = create_app(env.rt.cfg, runtime=env.rt)
    with instrumented(env, rec):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as c:
            for arm, _ in ARMS:
                if res.status != "ok" or not n.get(arm):
                    continue
                rec.arm, rec.standalone = arm, STANDALONE.get(arm, 0.9)
                try:
                    if arm in STANDALONE:
                        sessions[arm] = await one_on_one(env, c, rec, arm, n[arm], res)
                    elif arm == "group":
                        sessions[arm] = await group(env, c, rec, n[arm], res)
                    elif arm == "debate":
                        sessions[arm] = await debate(env, rec, n[arm], res)
                    else:
                        sessions[arm] = await watch(env, rec, n[arm], res)
                except TimeoutError:
                    res.status = "incomplete"
                    res.summary.append(f"## Deep timing: a {TITLES[arm]} turn did not settle within the watchdog")
    led = await ledger(env, sessions)
    res.rows += [{"arm": r["arm"], "deep_run": r} for r in rec.runs]
    res.summary += report(res.rows, rec, led, env.rt.runtime_cfg.runtime.retrieval.agent)


# ── the report ──
def q(xs: Sequence[float]) -> str:
    if not xs:
        return "no samples"
    return (f"p50 {percentile(xs, 0.5):.0f} ms, p90 {percentile(xs, 0.9):.0f} ms, max {max(xs):.0f} ms "
            f"(n {len(xs)})")


def report(rows: Sequence[dict[str, Any]], rec: Recorder, led: dict[str, dict[str, list[float]]],
           knobs: Any) -> list[str]:
    deep_ms = float(knobs.deep_check_ms) if knobs is not None else 700.0
    rewrite_ms = float(knobs.rewrite_ms) if knobs is not None else 1500.0
    out = ["## Deep-turn timing (rag D24; doc 10 check 2): the gates forced, the store bypassed"]
    every_slowest: list[float] = []
    every_rewrite: list[float] = []
    runs_all = falls_all = 0
    for arm, _ in ARMS:
        runs = [r for r in rec.runs if r["arm"] == arm]
        mine = [r for r in rows if r.get("arm") == arm and "deep_run" not in r]
        if not runs and not mine:
            continue
        lg = led.get(arm, {})
        slowest = [float(r["slowest_ms"]) for r in runs if r.get("slowest_ms") is not None]
        falls = sum(1 for r in runs if r.get("outcome") == "fallback")
        lost = sum(1 for r in runs if "outcome" not in r)   # never reached keep: a bug inside, a quick reply
        runs_all += len(runs)
        falls_all += falls + lost
        every_slowest += slowest
        every_rewrite += lg.get("rewrite", [])
        out.append(f"### {TITLES[arm]}: {len(runs)} deep run(s)")
        if arm in STANDALONE or arm == "group":
            tok = [float(r["to_token_ms"]) for r in mine if r.get("to_token_ms") is not None]
            if arm in STANDALONE:
                ok = tok and percentile(tok, 0.5) <= NFR01_P50_MS and percentile(tok, 0.9) <= NFR01_P90_MS
                target = f" (NFR-01 2 s p50 / 4 s p90{': ✓' if ok else ': ✗' if tok else ''})"
            else:
                ok = tok and percentile(tok, 0.5) <= NFR02_P50_MS
                target = f" (NFR-02 3 s p50{': ✓' if ok else ': ✗' if tok else ''})"
            out.append(f"- send → first word: {q(tok)}{target}")
        else:
            gaps = [float(r["gap_ms"]) for r in mine if r.get("gap_ms") is not None]
            ok = gaps and percentile(gaps, 0.5) <= NFR02_P50_MS
            out.append(f"- turn.end → next first word: {q(gaps)} (NFR-02 3 s p50{': ✓' if ok else ': ✗' if gaps else ''})")
        out += [f"- Jev call 1: {q(lg.get('call1', []))}",
                f"- the rewrite: {q(lg.get('rewrite', []))}",
                f"- the embeddings: {q(lg.get('embed', []))}",
                f"- the search (in process): {q([float(r['search_ms']) for r in runs if 'search_ms' in r])}",
                f"- the slowest `deep_check` of each run: {q(slowest)}; past deepCheckMs ({deep_ms:.0f} ms): "
                f"{sum(1 for s in slowest if s >= deep_ms)}",
                f"- every `deep_check` request: {q(lg.get('deep_check', []))}",
                f"- the set check: {q(rec.set_ms.get(arm, []))}",
                "- outcomes: " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(
                    str(r.get("outcome", "lost")) for r in runs).items())) + f"; fallback rate "
                f"{(falls + lost) / len(runs):.0%}" if runs else "- outcomes: no deep runs"]
        if rec.gates_not_back.get(arm):
            out.append(f"- gates not back from Jev call 1 (forced yes anyway): {rec.gates_not_back[arm]}")
    out.append("### Overall")
    out.append("- Jev 429s: " + (", ".join(f"{p} {k}" for p, k in sorted(rec.rate_limited.items())) or "none"))
    if runs_all:
        out.append(f"- deep runs that fell back: {falls_all}/{runs_all} ({falls_all / runs_all:.0%})")
    if every_slowest and percentile(every_slowest, 0.9) > deep_ms:
        out.append(f"- D24 on a miss: set retrieval.agent.deepCheckMs from the measured p90, "
                   f"{percentile(every_slowest, 0.9):.0f} ms (now {deep_ms:.0f}); K15's trims and D13's options go "
                   "to the user")
    if every_rewrite and percentile(every_rewrite, 0.9) > rewrite_ms:
        out.append(f"- D24 on a miss: set retrieval.agent.rewriteMs from the measured p90, "
                   f"{percentile(every_rewrite, 0.9):.0f} ms (now {rewrite_ms:.0f})")
    return out


# ── smoke (task 9.8) ──
SMOKE_QUESTION = "What does the fatigue review say about long shift blocks?"
SMOKE_REPLY = "The fatigue review is clear that long blocks wear people down [1]."
ANSWERS = {"type": "score", "score": 2.0, "confidence": 0.9, "probabilities": {"0": 0.05, "1": 0.05, "2": 0.9}}


def deep_line(name: str, reply: dict[str, Any] | None) -> tuple[str, bool]:
    """One smoke line: the passages kept, the citations and the System 1 passage rows of a deep reply."""
    if reply is None:
        return f"- deep {name}: no reply", False
    tr = reply.get("trace") or {}
    kept = [r for r in (tr.get("knowledge") or {}).get("retrieved") or [] if r.get("n") is not None]
    cites = [int(c["n"]) for c in reply.get("citations") or []]
    rows = [r for r in (tr.get("system1") or {}).get("questions") or [] if r.get("id") == "passage"]
    ok = bool(kept and cites and rows)
    return (f"- deep {name}: {len(kept)} passage(s) kept, citations {cites or 'none'}, {len(rows)} System 1 passage "
            f"row(s)"), ok


async def deep_smoke(env: RunEnv, empty: list[str]) -> list[str]:
    """M12 (task 9.8): one deep 1:1 turn and one deep group turn under `agent` on Amara's seed documents. In test mode
    the answers are canned: "needs documents?" yes, every passage "answers", Amara picked first in the group, and a
    reply that cites [1]; so the trace shows passages kept, citations and the passage rows at $0. The run's own profile
    and every canned answer are restored afterwards."""
    import httpx

    from horizon.ai.decider import ChoiceAnswer
    from horizon.ai.profile import ProfileSpec
    from horizon.evals.content import wait_idle
    from horizon.evals.debate_suites import top_up
    from horizon.main import create_app

    rt = env.rt
    fake = rt.fake if rt.cfg.test_mode else None
    before = rt.profile
    rt.set_profile(ProfileSpec(profile="agent", test_mode=rt.cfg.test_mode))
    out: list[str] = []
    if fake is not None:
        fake.answer_question("docs:*", {"type": "noul", "noul": FORCED_GATE})
        fake.answer_question("passage:*", ANSWERS)
        fake.set_canned("reply", [{"content": SMOKE_REPLY}])
        rt.decider_fixtures.set("turn_plan", "who_first", ChoiceAnswer(
            "chr_seedAmara", confidence=0.9, probabilities={"chr_seedAmara": 0.9}))
    app = create_app(rt.cfg, runtime=rt)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as c:
            for name, mode, cast in (("1:1", "one_on_one", ["chr_seedAmara"]),
                                     ("group", "group", list(MERIDIAN))):
                await top_up(env, cast)
                sid = await open_session(env, c, "wld_seedMeridian", mode, cast)
                if sid is None:
                    out.append(f"- deep {name}: creating the session failed")
                    empty.append(f"deep {name}")
                    continue
                seen = {m["id"] for m in (await c.get(f"{API}/sessions/{sid}/messages")).json()["items"]}
                await c.post(f"{API}/sessions/{sid}/send", json={"text": SMOKE_QUESTION})
                await wait_idle(env, sid)
                msgs = (await c.get(f"{API}/sessions/{sid}/messages", params={"limit": 1000})).json()["items"]
                reply = next((m for m in msgs if m["author"]["type"] == "character" and m["id"] not in seen), None)
                await c.post(f"{API}/sessions/{sid}/end")
                line, ok = deep_line(name, reply)
                out.append(line)
                if fake is not None and not ok:
                    empty.append(f"deep {name}")
    finally:
        rt.set_profile(before)
        if fake is not None:
            fake.answer_question("docs:*", None)
            fake.answer_question("passage:*", None)
            fake.set_canned("reply", None)
            rt.decider_fixtures.clear()
    return out

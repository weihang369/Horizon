"""`horizon eval latency --part blended`: the must-pass latency run (docs/ai/02 B8; images-music design D15;
evaluation-harness "The must-pass latency run", "The per-stage breakdown").

- **Parts,** through the API, store bypassed, `agent`, one turn at a time, each reply stopped at its first word:
  100 quick 1:1 turns (the gates live), 100 deep 1:1 turns (the gates forced deep by `deep_timing`'s fixture, the
  rewrite decided live), 50 group turns and 50 debate turns (the gates live), and 25 deep watch turns (forced). Each
  part first runs `WARMUP` turns that are marked warm-up and left out of every figure. `--limit N` runs N per part
  (warm-up 1).
- **On a loaded database:** the seed documents indexed (`retrieval_suite.prepare`) and the seed memories.
- **Recorded:** the time window (the pricing calendar's period at the start, and the KL clock), the providers the
  ledger names for the chat calls, and the database size.
- **The blend:** `--arm rate=R` is the deep rate fixed before the run (the `conversations` `agent` arm's). The blended
  p50 and p90 of send → first word are the mixture's (1 − R) quick + R deep, with a seeded bootstrap interval.
  NFR-01 is judged on it.
- **Folded in, reported, never tuned:** each ledger purpose's latency, p50 and p90, and its late count (`turn_plan`,
  the output check, `follow_plan`, `debate_plan`, recall's check), the deep stages from `deep_timing`'s recorder, and
  the provider cache hit and its cost from the ledger's cached tokens. Any deadline change is a choice for the user.
"""

from __future__ import annotations

import json
import random
from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from horizon.domain.pricing import estimate_chat
from horizon.evals.metrics import percentile
from horizon.evals.runner import Options, Plan, Result, RunEnv, decision_estimate

PARTS: tuple[tuple[str, int], ...] = (("quick", 100), ("deep", 100), ("group", 50), ("debate", 50), ("watch", 25))
WARMUP = 5
NFR01_P50, NFR01_P90, NFR02_P50 = 2000.0, 4000.0, 3000.0
NEXT_MS = 500.0
N_BOOT, SEED = 1000, 15
KL = timedelta(hours=8)


def rate_of(opts: Options) -> float | None:
    """`--arm rate=R`, the deep rate fixed before the run."""
    arm = str(opts.arm or "")
    if not arm.startswith("rate="):
        return None
    r = float(arm.removeprefix("rate="))
    if not 0.0 <= r <= 1.0:
        raise ValueError("the deep rate is between 0 and 1")
    return r


def sizes(opts: Options) -> dict[str, tuple[int, int]]:
    """Per part: (turns measured, warm-up turns)."""
    return {p: ((opts.limit, 1) if opts.limit else (n, WARMUP)) for p, n in PARTS}


def plan(opts: Options, prices: Any, *, paid: bool) -> Plan:
    from horizon.evals import deep_timing

    n = sizes(opts)
    call1 = decision_estimate(prices, {"quoted_latest": "x" * 2400}, {"q": {"instructions": "x" * 1200}})
    first = estimate_chat(prices, prefix_tokens=4000, warm=True, other_in=600, expected_out_tokens=8,
                          period="off_peak")
    deep_one = deep_timing.plan(Options("latency", profile="agent", limit=1), prices, paid=paid).estimate_usd / 5
    quick = sum(n["quick"]) * (call1 + first)
    deep = sum(n["deep"]) * deep_one
    others = sum(sum(n[p]) for p in ("group", "debate", "watch")) * (call1 + first + deep_one / 3)
    items = [{"part": p, "n": k, "warmup": w} for p, (k, w) in n.items()]
    turns = sum(k + w for k, w in n.values())
    return Plan(items=items, estimate_usd=quick + deep + others, expected_s=120 + turns * 7.0, paid=paid)


def mark(rows: list[dict[str, Any]], warmup: int) -> list[dict[str, Any]]:
    """The first `warmup` rows of a part are marked warm-up (kept in the file, left out of every figure)."""
    return [{**r, "warmup": i < warmup} for i, r in enumerate(rows)]


def measured(rows: Sequence[dict[str, Any]], part: str, key: str) -> list[float]:
    return [float(r[key]) for r in rows if r.get("part") == part and not r.get("warmup") and r.get(key) is not None]


def mixture_quantile(quick: Sequence[float], deep: Sequence[float], rate: float, q: float) -> float:
    """The q-quantile of (1 − rate) quick + rate deep: the smallest x with F(x) ≥ q."""
    xs = sorted({*quick, *deep})
    nq, nd = len(quick), len(deep)
    sq, sd = sorted(quick), sorted(deep)
    iq = idd = 0
    for x in xs:
        while iq < nq and sq[iq] <= x:
            iq += 1
        while idd < nd and sd[idd] <= x:
            idd += 1
        f = (1 - rate) * (iq / nq if nq else 0.0) + rate * (idd / nd if nd else 0.0)
        if f >= q - 1e-12:
            return x
    return xs[-1]


def blended(quick: Sequence[float], deep: Sequence[float], rate: float) -> dict[str, Any]:
    """The blended p50 and p90 with a seeded bootstrap interval (each part resampled on its own)."""
    out: dict[str, Any] = {"rate": rate, "n_quick": len(quick), "n_deep": len(deep)}
    if (rate < 1 and not quick) or (rate > 0 and not deep):
        return out
    rng = random.Random(SEED)
    for q, k in ((0.5, "p50"), (0.9, "p90")):
        out[k] = mixture_quantile(quick, deep, rate, q)
        boots = sorted(mixture_quantile([rng.choice(quick) for _ in quick] if quick else [],
                                        [rng.choice(deep) for _ in deep] if deep else [], rate, q)
                       for _ in range(N_BOOT))
        out[f"{k}_ci"] = (boots[int(0.025 * N_BOOT)], boots[int(0.975 * N_BOOT) - 1])
    return out


# ── the run ──
async def run(env: RunEnv, plan_: Plan, res: Result) -> None:
    import httpx

    from horizon.evals import deep_timing as DT
    from horizon.evals.retrieval_suite import prepare
    from horizon.main import create_app

    await prepare(env, {})
    started = env.rt.clock.now()
    rec = DT.Recorder()
    sessions: dict[str, list[str]] = {}
    rows_file = env.run_dir / "turns.jsonl"
    app = create_app(env.rt.cfg, runtime=env.rt)
    with DT.instrumented(env, rec):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as c:
            for it in plan_.items:
                if res.status != "ok":
                    break
                part, n, warm = str(it["part"]), int(it["n"]), int(it["warmup"])
                rec.arm, rec.force, rec.standalone = part, part in ("deep", "watch"), None
                before = len(res.rows)
                try:
                    sessions[part] = await one_part(env, c, rec, part, n + warm, res)
                except TimeoutError:
                    res.status = "incomplete"
                    res.summary.append(f"## Blended latency: a {part} turn did not settle within the watchdog")
                got = mark([{**r, "part": part} for r in res.rows[before:]], warm)
                res.rows[before:] = got
                with rows_file.open("a", encoding="utf-8", newline="\n") as f:
                    for r in got:
                        f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    led = await ledger_rows(env, [s for ss in sessions.values() for s in ss])
    res.rows += [{"part": r["arm"], "deep_run": r} for r in rec.runs]
    res.summary += report(env, res.rows, rec, led, rate_of(env.opts), started)


async def one_part(env: RunEnv, c: Any, rec: Any, part: str, n: int, res: Result) -> list[str]:
    from horizon.evals import deep_timing as DT

    if part == "quick":
        return await quick(env, c, n, res)
    if part == "deep":
        before = len(res.rows)
        sids = await DT.one_on_one(env, c, rec, part, n, res)
        for r in res.rows[before:]:
            r.pop("arm", None)
        return sids
    if part == "group":
        before = len(res.rows)
        sids = await DT.group(env, c, rec, n, res)
        for r in res.rows[before:]:
            r.pop("arm", None)
        return sids + await next_gaps(env, sids, res, before)
    if part == "watch":
        return await DT.watch(env, rec, n, res)
    return await debate(env, n, res)


async def quick(env: RunEnv, c: Any, n: int, res: Result) -> list[str]:
    """Quick 1:1 turns: the latency suite's everyday lines over the six seed characters, the gates live."""
    from horizon.evals import deep_timing as DT
    from horizon.evals.content import budget_code, wait_idle
    from horizon.evals.debate_suites import top_up
    from horizon.evals.latency import WORLD, Latency, plan_turns

    sessions: dict[str, str] = {}
    for turn in plan_turns(n):
        if await env.over_budget():
            res.status = "incomplete"
            break
        cid = turn["character"]
        await top_up(env, [cid])
        if cid not in sessions:
            r = await c.post(f"{DT.API}/sessions", json={"worldId": WORLD[cid], "mode": "one_on_one",
                                                         "characterIds": [cid]})
            if r.status_code != 201:   # the run's cap refuses the session: incomplete, not failed
                res.status = "incomplete" if budget_code(r) else "failed"
                break
            sessions[cid] = str(r.json()["session"]["id"])
            await wait_idle(env, sessions[cid])
        row = await Latency.guarded(env, Latency().one(env, c, sessions[cid], cid, turn["text"]))
        if row is None:
            res.status = "incomplete"
            break
        res.rows.append(row)
    return list(sessions.values())


async def next_gaps(env: RunEnv, sids: list[str], res: Result, before: int) -> list[str]:
    """Group: `turn.end` → the next `turn.next` within 500 ms (G-rule), per turn, onto the rows."""
    from horizon.domain.timeutil import ms_from_iso
    from horizon.evals.latency import Latency

    for sid in sids:
        evs = await Latency.events(env, sid)
        gaps = []
        for end in (e for e in evs if e["type"] == "turn.end"):
            nxt = next((e for e in evs if e["type"] == "turn.next" and e["seq"] > end["seq"]), None)
            if nxt is not None:
                gaps.append(float(ms_from_iso(nxt["at"]) - ms_from_iso(end["at"])))
        for r, g in zip(res.rows[before:], gaps, strict=False):
            r["next_ms"] = g
    return []


async def debate(env: RunEnv, n: int, res: Result) -> list[str]:
    """Whole debates with the gates live, one after another, until `n` next-word gaps are timed."""
    from horizon.evals import deep_timing as DT
    from horizon.evals.debate_suites import drive_debate, install_cast, top_up

    await install_cast(env)
    sids: list[str] = []
    for script in DT.debate_scripts():
        if sum(1 for r in res.rows if r.get("arm") == "debate") >= n or await env.over_budget():
            break
        await top_up(env, script["cast"])
        _, complete, sid, _, _ = await drive_debate(env, script)
        sids.append(sid)
        res.rows += [{"arm": "debate", "session": sid, "gap_ms": g} for g in await DT.next_word_gaps(env, sid)]
        if not complete:
            res.status = "incomplete"
            break
    keep = [r for r in res.rows if r.get("arm") == "debate"][:n]
    res.rows[:] = [r for r in res.rows if r.get("arm") != "debate"] + keep
    for r in keep:
        r.pop("arm", None)
    return sids


async def ledger_rows(env: RunEnv, sids: Sequence[str]) -> list[dict[str, Any]]:
    from sqlalchemy import select

    from horizon.db import tables as t

    U = t.usage_records.c
    async with env.rt.db.read() as conn:
        got = (await conn.execute(select(U.purpose, U.latency_ms, U.finish_reason, U.provider, U.tokens_in,
                                         U.tokens_cached, U.cost_usd, U.category).where(U.session_id.in_(list(sids)))
                                  )).mappings().all() if sids else []
    return [dict(r) for r in got]


def q(xs: Sequence[float]) -> str:
    if not xs:
        return "no samples"
    return f"p50 {percentile(xs, 0.5):.0f} ms, p90 {percentile(xs, 0.9):.0f} ms (n {len(xs)})"


def report(env: RunEnv, rows: Sequence[dict[str, Any]], rec: Any, led: Sequence[dict[str, Any]], rate: float | None,
           started: Any) -> list[str]:
    from horizon.domain.clock import calendar_for

    cal = calendar_for(env.rt.cfg.tz)
    providers = sorted({str(r["provider"]) for r in led if r.get("provider") and r.get("category") == "chat"})
    db = env.run_dir / "horizon.db"
    out = ["## Blended latency (B8, D15): store bypassed, each reply stopped at its first word",
           f"- window: {cal.period(started)} (KL {(started + KL).strftime('%Y-%m-%d %H:%M')}); providers: "
           f"{', '.join(providers) or 'none recorded'}; database {db.stat().st_size / 1e6:.1f} MB"
           if db.is_file() else f"- window: {cal.period(started)} (KL {(started + KL).strftime('%Y-%m-%d %H:%M')})",
           f"- warm-up turns left out: {sum(1 for r in rows if r.get('warmup'))}"]
    quick, deep = measured(rows, "quick", "to_token_ms"), measured(rows, "deep", "to_token_ms")
    out += [f"- quick 1:1, send → first word: {q(quick)}", f"- deep 1:1, send → first word: {q(deep)}",
            f"- quick 1:1, send → face: {q(measured(rows, 'quick', 'to_face_ms'))}"]
    rewrites = [r for r in rec.runs if r.get("arm") == "deep"]
    if rewrites:
        ran = sum(1 for r in rewrites if r.get("rewrite_status") not in (None, "skipped", "not_needed"))
        out.append(f"- deep 1:1 runs with a rewrite: {ran}/{len(rewrites)}")
    if rate is None:
        out.append("- blended: no `--arm rate=R` was fixed before the run, so NFR-01 is not judged")
    else:
        b = blended(quick, deep, rate)
        if "p50" in b:
            ok = b["p50"] <= NFR01_P50 and b["p90"] <= NFR01_P90
            out.append(f"- **blended at deep rate {rate:.2f}:** p50 {b['p50']:.0f} ms (95% {b['p50_ci'][0]:.0f}–"
                       f"{b['p50_ci'][1]:.0f}), p90 {b['p90']:.0f} ms (95% {b['p90_ci'][0]:.0f}–{b['p90_ci'][1]:.0f})"
                       f" → NFR-01 {'met ✓' if ok else 'missed ✗'}")
    group_tok = measured(rows, "group", "to_token_ms")
    nxt = measured(rows, "group", "next_ms")
    out += [f"- group, send → first word: {q(group_tok)} (NFR-02 3 s p50"
            + (f": {'✓' if percentile(group_tok, 0.5) <= NFR02_P50 else '✗'})" if group_tok else ")"),
            f"- group, `turn.next` within {NEXT_MS:.0f} ms: {sum(x <= NEXT_MS for x in nxt)}/{len(nxt)}",
            f"- debate, turn.end → next first word: {q(measured(rows, 'debate', 'gap_ms'))}",
            f"- watch (deep), turn.end → next first word: {q(measured(rows, 'watch', 'gap_ms'))}"]
    out.append("### Per stage (the deep runs, `deep_timing`'s recorder)")
    runs = [r for r in rec.runs]
    out += [f"- the embedding wait and gather: {q([float(r['gather_ms']) for r in runs if 'gather_ms' in r])}",
            f"- the local search: {q([float(r['search_ms']) for r in runs if 'search_ms' in r])}",
            f"- Jev call 2, the slowest request: {q([float(r['slowest_ms']) for r in runs if r.get('slowest_ms')])}"]
    out.append("### Per purpose (the ledger): latency and the late count, reported, not tuned")
    for purpose in sorted({str(r["purpose"]) for r in led if r.get("purpose")}):
        mine = [r for r in led if r.get("purpose") == purpose]
        lat = [float(r["latency_ms"]) for r in mine if r.get("latency_ms") is not None]
        late = sum(1 for r in mine if r.get("finish_reason") == "late")
        out.append(f"- {purpose}: {q(lat)}; late {late}/{len(mine)}")
    chat = [r for r in led if r.get("category") == "chat" and r.get("tokens_in")]
    if chat:
        tin = sum(int(r["tokens_in"] or 0) for r in chat)
        cached = sum(int(r["tokens_cached"] or 0) for r in chat)
        out.append(f"- the provider cache: {cached}/{tin} input tokens cached ({cached / tin:.0%}); chat cost "
                   f"${sum(float(r['cost_usd'] or 0) for r in chat):.5f}")
    return out

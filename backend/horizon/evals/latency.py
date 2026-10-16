"""`horizon eval latency`: the 1:1 part of doc 01 check 3 (turn-plan-emotion design D31; evaluation-harness "The latency
suite"; NFR-01, NFR-29).

- **Where:** the isolated copy under `agent` with the real key, and the store bypassed (W10): every request goes to the
  provider, and nothing is read from or written to the store (spec "Never from the store").
- **The turns:** English sends from the long scripts' pool, spread over the six seed characters' 1:1 sessions
  (about 17 each for the default 100), driven through the API like the `long` suite.
- **Each turn** sends Stop as soon as its first `token` event appears, so the message ends `interrupted` (spec
  "Stopped at the first word") and no reply is paid past its first words.
- **Measured:** send → `emotion` and send → first `token`, p50 and p90 with order-statistic intervals, against NFR-01
  (2 s p50, 4 s p90); Jev's `turn_plan` latency from the ledger; how often its deadline fired (outcome `late`); the
  `classifier` share of faces. Nothing is tuned here: the `turn_plan` deadline is M15's (W12).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from typing import Any

from horizon.domain.clock import FrozenClock
from horizon.domain.pricing import estimate_chat
from horizon.domain.timeutil import ms_from_iso
from horizon.evals.content import LONG_DIR, budget_code, wait_idle
from horizon.evals.metrics import percentile, percentile_ci
from horizon.evals.runner import Options, Plan, Result, RunEnv, decision_estimate

CAST = ("chr_seedAmara", "chr_seedMei", "chr_seedVictor", "chr_seedHana", "chr_seedRin", "chr_seedTakeshi")
WORLD = {"chr_seedAmara": "wld_seedMeridian", "chr_seedMei": "wld_seedMeridian", "chr_seedVictor": "wld_seedMeridian",
         "chr_seedHana": "wld_seedSunnyHollow", "chr_seedRin": "wld_seedSunnyHollow",
         "chr_seedTakeshi": "wld_seedSunnyHollow"}
DEFAULT_N = 100
POLL_MS = 50
FIRST_TOKEN_LIMIT_S = 30.0
NFR_P50_MS, NFR_P90_MS = 2000.0, 4000.0
API = "/api/v1"
TURN_WATCHDOG_S = 90.0
STACKS = "stacks.txt"
FOLLOW_N = 50          # M10 (D9): follow requests from the second-slot items' dev split
WATCH_SCENES, WATCH_TURNS = 3, 20   # M10 (D23): scenes × turns at Fast pace
DEBATE_PLANS = 30      # M11 (debate D9): debate-plan states from the member slice's dev items


def lines(n: int) -> list[str]:
    """English lines from the long scripts' pool, in order, repeated if needed."""
    pool: list[str] = []
    for name in ("one_on_one_en.json", "group_meridian.json"):
        pool += [str(x["text"]) for x in json.loads((LONG_DIR / name).read_text(encoding="utf-8"))["lines"]]
    return [pool[k % len(pool)] for k in range(n)]


def plan_turns(n: int) -> list[dict[str, str]]:
    """Round-robin over the six characters, so each gets about n / 6 turns."""
    return [{"character": CAST[k % len(CAST)], "text": t} for k, t in enumerate(lines(n))]


def quantiles(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    out: dict[str, Any] = {"n": len(values)}
    for q, k in ((0.5, "p50"), (0.9, "p90")):
        out[k] = percentile(values, q)
        out[f"{k}_ci"] = percentile_ci(values, q)
    return out


def row_line(name: str, qs: dict[str, Any], *, target: bool = False) -> str:
    if not qs.get("n"):
        return f"- {name}: no samples"

    def one(k: str, limit: float) -> str:
        ci = qs.get(f"{k}_ci")
        span = f" (95% {ci[0]:.0f}–{ci[1]:.0f})" if ci else " (too few samples for an interval)"
        verdict = "" if not target else (" ✓" if qs[k] <= limit else " ✗ over NFR-01")
        return f"{k} {qs[k]:.0f} ms{span}{verdict}"

    return f"- {name} (n {qs['n']}): {one('p50', NFR_P50_MS)}, {one('p90', NFR_P90_MS)}"


class Latency:
    name = "latency"

    def refuse(self, opts: Options) -> str | None:
        if opts.part in ("deep", "recall") and opts.profile != "agent":   # M12 (rag D24), M13 (memory D33): agent's
            return f"horizon: `latency --part {opts.part}` runs the agent deep path; pass --profile agent"
        return None

    def plan(self, opts: Options, prices: Any, *, paid: bool) -> Plan:
        if opts.part == "follow":   # M10 (group-watch D9): 50 follow requests, Jev only
            n = opts.limit or FOLLOW_N
            per = decision_estimate(prices, {"quoted_latest": "x" * 4500}, {"q": {"instructions": "x" * 2400}})
            return Plan(items=[{"part": "follow", "n": n}], estimate_usd=n * per, expected_s=n * 1.5, paid=paid)
        if opts.part == "watch":    # M10 (D23): 3 scenes × 20 turns at Fast pace under agent
            scenes, turns_each = (1, opts.limit) if opts.limit else (WATCH_SCENES, WATCH_TURNS)
            reply = estimate_chat(prices, prefix_tokens=4000, warm=True, other_in=400, expected_out_tokens=120,
                                  period="off_peak")
            plan_call = decision_estimate(prices, {"quoted_latest": "x" * 2400}, {"q": {"instructions": "x" * 1200}})
            n = scenes * turns_each
            return Plan(items=[{"part": "watch", "scene": k, "turns": turns_each} for k in range(scenes)],
                        estimate_usd=n * (reply + 1.2 * plan_call), expected_s=n * 6.0, paid=paid)
        if opts.part == "deep":     # M12 (rag D24): forced deep turns in every mode on a loaded database
            from horizon.evals import deep_timing

            return deep_timing.plan(opts, prices, paid=paid)
        if opts.part == "recall":   # M13 (memory D33; doc 09 check 4): recall turns, then both gates
            from horizon.evals import recall_timing

            return recall_timing.plan(opts, prices, paid=paid)
        if opts.part == "debate":   # M11 (debate D9, D22): 30 plans, 10 bridges and 5 verdicts
            n = opts.limit or DEBATE_PLANS
            per = decision_estimate(prices, {"quoted_arguments": "x" * 7000}, {"q": {"instructions": "x" * 2400}})
            line = estimate_chat(prices, prefix_tokens=0, warm=False, other_in=1800, expected_out_tokens=80,
                                 period="off_peak")
            verdict = 6 * per + estimate_chat(prices, prefix_tokens=0, warm=False, other_in=6000,
                                              expected_out_tokens=300, period="off_peak")
            return Plan(items=[{"part": "debate", "n": n}], estimate_usd=n * per + 10 * line + 5 * verdict,
                        expected_s=n * 1.5 + 10 * 3 + 5 * 20, paid=paid)
        turns = plan_turns(opts.limit or DEFAULT_N)[opts.start:]
        first_words = estimate_chat(prices, prefix_tokens=4000, warm=True, other_in=300, expected_out_tokens=8,
                                    period="off_peak")
        call1 = decision_estimate(prices, {"quoted_latest": "x" * 2400}, {"q": {"instructions": "x" * 1200}})
        return Plan(items=turns, estimate_usd=len(turns) * (first_words + call1) + len(CAST) * 0.0004,
                    expected_s=len(turns) * 5.0, paid=paid)

    async def run(self, env: RunEnv, plan: Plan) -> Result:
        import httpx

        from horizon.main import create_app

        res = Result()
        if env.opts.profile != "agent" and not env.opts.limit:
            res.status = "failed"
            res.summary.append("## Latency: runs `agent` only (D31); pass --profile agent")
            return res
        if env.opts.part == "follow":
            from horizon.evals.watch_suites import follow_report, follow_timing

            res.rows = await follow_timing(env, plan.items[0]["n"])
            res.summary += follow_report(res.rows)
            return res
        if env.opts.part == "watch":
            await self.watch_part(env, plan, res)
            return res
        if env.opts.part == "debate":
            from horizon.evals.debate_suites import debate_timing

            await debate_timing(env, plan.items[0]["n"], res)
            return res
        if env.opts.part == "deep":
            from horizon.evals import deep_timing

            await deep_timing.run(env, plan, res)
            return res
        if env.opts.part == "recall":
            from horizon.evals import recall_timing

            await recall_timing.run(env, plan, res)
            return res
        app = create_app(env.rt.cfg, runtime=env.rt)
        sessions: dict[str, str] = {}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as c:
            for turn in plan.items:
                if await env.over_budget():
                    res.status = "incomplete"
                    break
                cid = turn["character"]
                if cid not in sessions:
                    r = await c.post(f"{API}/sessions", json={"worldId": WORLD[cid], "mode": "one_on_one",
                                                              "characterIds": [cid]})
                    if r.status_code != 201:
                        res.status = "incomplete" if budget_code(r) else "failed"
                        res.summary.append(f"## Latency: creating a session failed ({r.status_code})")
                        break
                    sessions[cid] = r.json()["session"]["id"]
                    await wait_idle(env, sessions[cid])
                try:
                    row = await self.guarded(env, self.one(env, c, sessions[cid], cid, turn["text"]))
                except TimeoutError:
                    res.status = "incomplete"
                    res.summary.append(f"## Latency: a turn did not settle within {TURN_WATCHDOG_S:.0f} s; every task's "
                                       f"stack is in {STACKS} in the run folder")
                    break
                if row is None:
                    res.status = "incomplete"
                    break
                res.rows.append(row)
        res.summary += await self.report(env, res.rows, list(sessions.values()))
        return res

    async def one(self, env: RunEnv, c: Any, sid: str, cid: str | None, text: str) -> dict[str, Any] | None:
        """One send, timed to its reply's face and first token, then Stop. `cid` None: whichever character answers
        first (a group)."""
        since = max((e["seq"] for e in await self.events(env, sid)), default=0)
        sent_ms = float(ms_from_iso(env.rt.now_iso()))
        r = await c.post(f"{API}/sessions/{sid}/send", json={"text": text})
        if budget_code(r):
            return None
        emotion = token = None
        message_id: str | None = None
        waited = 0.0
        while token is None and waited < FIRST_TOKEN_LIMIT_S * 1000:
            await self.tick(env)
            waited += POLL_MS
            for e in await self.events(env, sid, since):
                since = max(since, e["seq"])
                p = e["payload"]
                who = (p.get("author") or {}).get("characterId")
                if e["type"] == "turn.start" and message_id is None and who and (cid is None or who == cid):
                    message_id, cid = p["messageId"], who
                elif e["type"] == "emotion" and p.get("messageId") and p.get("messageId") == message_id and emotion is None:
                    emotion = e
                elif e["type"] == "token" and p.get("messageId") == message_id and token is None:
                    token = e
                    break
        if token is not None:
            await c.post(f"{API}/sessions/{sid}/stop", json={})   # D31: Stop at the first word
        await wait_idle(env, sid)
        msgs = (await c.get(f"{API}/sessions/{sid}/messages", params={"limit": 1000})).json()["items"]
        msg = next((m for m in msgs if m["id"] == message_id), None)
        return {"character": cid, "session": sid, "message": message_id, "text": text,
                "to_face_ms": None if emotion is None else float(ms_from_iso(emotion["at"])) - sent_ms,
                "to_token_ms": None if token is None else float(ms_from_iso(token["at"])) - sent_ms,
                "source": None if emotion is None else emotion["payload"].get("source"),
                "status": msg["status"] if msg else None}

    async def watch_part(self, env: RunEnv, plan: Plan, res: Result) -> None:
        """M10 (D23): turn.end → the next turn.next and first token over scenes at Fast pace, with how the plan made
        ahead fared; the 90 s per-turn watchdog bounds each scene."""
        from sqlalchemy import select

        from horizon.db import tables as t
        from horizon.evals.watch_suites import FREERUN_PREMISES, drive_watch, watch_timing_report

        gaps_next: list[float] = []
        gaps_token: list[float] = []
        plans: list[tuple[float, str]] = []
        turns = fallbacks = 0
        for item in plan.items:
            if await env.over_budget():
                res.status = "incomplete"
                break
            world, cast, premise = FREERUN_PREMISES[item["scene"] % len(FREERUN_PREMISES)]
            script = {"id": f"latency-watch-{item['scene']}", "world": world, "cast": cast, "premise": premise,
                      "turns": item["turns"], "paceMs": 500}
            work = drive_watch(env, script)
            try:
                _, _, sid, msgs = await (work if isinstance(env.rt.clock, FrozenClock)
                                         else asyncio.wait_for(work, TURN_WATCHDOG_S * item["turns"]))
            except TimeoutError:
                res.status = "incomplete"
                res.summary.append("## Latency (watch): a scene did not settle within its watchdog")
                break
            evs = await self.events(env, sid)
            ends = [e for e in evs if e["type"] == "turn.end"]
            for end in ends:
                nxt = next((e for e in evs if e["type"] == "turn.next" and e["seq"] > end["seq"]), None)
                tok = next((e for e in evs if e["type"] == "token" and e["seq"] > end["seq"]), None)
                if nxt is not None:
                    gaps_next.append(float(ms_from_iso(nxt["at"]) - ms_from_iso(end["at"])))
                if tok is not None:
                    gaps_token.append(float(ms_from_iso(tok["at"]) - ms_from_iso(end["at"])))
            replies = [m for m in msgs if m["author"]["type"] == "character"]
            turns += len(replies)
            fallbacks += sum(1 for m in replies for c in ((m.get("trace") or {}).get("calls") or [])
                             if c.get("purpose") == "turn_plan" and c.get("fallback"))
            U = t.usage_records.c
            async with env.rt.db.read() as conn:
                plans += [(float(r[0] or 0), str(r[1])) for r in (await conn.execute(
                    select(U.latency_ms, U.finish_reason).where(U.purpose == "turn_plan").where(U.session_id == sid)
                    .order_by(U.at))).all()]
            res.rows.append({"scene": item["scene"], "session": sid, "turns": len(replies)})
        res.summary += watch_timing_report(gaps_next, gaps_token, plans, turns, fallbacks)

    @staticmethod
    async def guarded(env: RunEnv, work: Any) -> Any:
        """A paid run must never hang: past the watchdog, write every task's stack to the run folder and give up."""
        if isinstance(env.rt.clock, FrozenClock):   # virtual time: the test drives the clock itself
            return await work
        try:
            return await asyncio.wait_for(work, TURN_WATCHDOG_S)
        except TimeoutError:
            import io

            buf = io.StringIO()
            for t in asyncio.all_tasks():
                buf.write(f"\n=== {t.get_name()}\n")
                t.print_stack(limit=12, file=buf)
            env.run_dir.mkdir(parents=True, exist_ok=True)
            (env.run_dir / STACKS).write_text(buf.getvalue(), encoding="utf-8")
            raise

    @staticmethod
    async def events(env: RunEnv, sid: str, since: int = 0) -> list[dict[str, Any]]:
        """The session's stored events after `since`, from the run's own database (the app writes them as they happen)."""
        from sqlalchemy import select

        from horizon.db import tables as t

        E = t.session_events.c
        async with env.rt.db.read() as conn:
            rows = (await conn.execute(select(E.seq, E.at, E.type, E.payload).where(E.session_id == sid)
                                       .where(E.seq > since).order_by(E.seq))).mappings().all()
        return [dict(r) for r in rows]

    @staticmethod
    async def tick(env: RunEnv) -> None:
        if isinstance(env.rt.clock, FrozenClock):
            await env.rt.clock.advance(POLL_MS)
        else:
            await asyncio.sleep(POLL_MS / 1000)

    async def report(self, env: RunEnv, rows: list[dict[str, Any]], sessions: list[str]) -> list[str]:
        from sqlalchemy import select

        from horizon.db import tables as t

        U = t.usage_records.c
        async with env.rt.db.read() as conn:
            plans = (await conn.execute(select(U.latency_ms, U.finish_reason).where(U.purpose == "turn_plan")
                                        .where(U.session_id.in_(sessions)))).all() if sessions else []
        face = [float(r["to_face_ms"]) for r in rows if r.get("to_face_ms") is not None]
        tok = [float(r["to_token_ms"]) for r in rows if r.get("to_token_ms") is not None]
        sources = [r["source"] for r in rows if r.get("source")]
        late = sum(1 for p in plans if p[1] == "late")
        out = [f"## Latency: {len(rows)} 1:1 turns, Stop at the first word, store bypassed",
               row_line("send → face (emotion event)", quantiles(face), target=True),
               row_line("send → first word (token event)", quantiles(tok), target=True),
               row_line("Jev turn_plan (ledger)", quantiles([float(p[0] or 0) for p in plans]))]
        out.append(f"- turn_plan deadline fired: {late}/{len(plans)}" + (f" ({late / len(plans):.0%})" if plans else ""))
        if sources:
            cls = sum(1 for s in sources if s == "classifier")
            out.append(f"- classifier share of faces: {cls}/{len(sources)} ({cls / len(sources):.0%})")
        stopped = sum(1 for r in rows if r.get("status") == "interrupted")
        out.append(f"- stopped at the first word: {stopped}/{len(rows)}")
        return out

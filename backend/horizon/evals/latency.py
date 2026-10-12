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

    def plan(self, opts: Options, prices: Any, *, paid: bool) -> Plan:
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
                row = await self.one(env, c, sessions[cid], cid, turn["text"])
                if row is None:
                    res.status = "incomplete"
                    break
                res.rows.append(row)
        res.summary += await self.report(env, res.rows, list(sessions.values()))
        return res

    async def one(self, env: RunEnv, c: Any, sid: str, cid: str, text: str) -> dict[str, Any] | None:
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
                if e["type"] == "turn.start" and (p.get("author") or {}).get("characterId") == cid:
                    message_id = p["messageId"]
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

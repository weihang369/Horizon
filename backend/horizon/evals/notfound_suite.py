"""`horizon eval notfound` (rag design D22; doc 10 K14; docs/ai/02 B4 "Not-found reply"; tasks 9.6, 11.8).

The end-to-end run of the Not-found reply: the retrieval suite's 40 unanswerable and 10 partly questions, each as a
real 1:1 `agent` turn (the corpus loaded as the characters' sources, a fresh session per question, nothing earlier),
then the two judges on each reply:
- `judge_notfound_says`: does the reply fail to say the documents don't cover it, or which part?
- `judge_notfound_cites`: does it present something beyond the documents as if from them, or cite with [n]?

The judge sees the message, the kept passages exactly as the reply saw them (numbered, from the reply's trace; a line
saying none were kept otherwise) and the reply. Every row is saved, so the 30 real validation items are labelled from
this run's replies (`judge_states.jsonl`), never paid for twice. A judge's figures read **NOT COUNTED** until its
current version passes B4 (`decisions --set judges`).
"""

from __future__ import annotations

import json
from typing import Any

from horizon.ai.questions import bank
from horizon.domain.pricing import estimate_chat
from horizon.evals import judges
from horizon.evals import retrieval as R
from horizon.evals.content import failed, judge, judge_estimate
from horizon.evals.metrics import wilson
from horizon.evals.runner import Options, Plan, Result, RunEnv, decision_estimate

SAYS = "judge_notfound_says"
CITES = "judge_notfound_cites"
JUDGES = (SAYS, CITES)
NONE_KEPT = "(none: no passage from the documents was kept for this message)"
API = "/api/v1"


def items(opts: Options) -> list[dict[str, Any]]:
    qs = [q for q in R.load_questions() if q["kind"] == "unanswerable" or q.get("partly")]
    qs = [q for q in qs if not opts.set or q["split"] == opts.set][opts.start:]
    return qs[: opts.limit] if opts.limit else qs


def passages_text(retrieved: list[dict[str, Any]]) -> str:
    kept = sorted((r for r in retrieved if r.get("n") is not None), key=lambda r: int(r["n"]))
    if not kept:
        return NONE_KEPT
    lines = []
    for r in kept:
        where = f", {r['locator']}" if r.get("locator") else ""
        lines.append(f"[{r['n']}] {r.get('title', '')}{where}\n{r.get('text', '')}")
    return "\n\n".join(lines)


def judge_state(message: str, retrieved: list[dict[str, Any]], reply: str) -> dict[str, Any]:
    return {"quoted_message": message, "quoted_passages": passages_text(retrieved), "quoted_reply": reply}


def counted(qid: str) -> str:
    return "" if judges.validated(qid, bank().get(qid).version) else " **NOT COUNTED** (not validated, B4)"


def report(rows: list[dict[str, Any]]) -> list[str]:
    out = ["## The Not-found reply (doc 10 K14; 1:1 `agent`, end to end)"]
    for kind in ("unanswerable", "partly"):
        mine = [r for r in rows if r["kind"] == kind]
        if not mine:
            continue
        kept = sum(1 for r in mine if r["kept"])
        out.append(f"### {kind} ({len(mine)}): passages kept on {kept}; replies complete "
                   f"{sum(r['status'] == 'complete' for r in mine)}/{len(mine)}")
        for qid in JUDGES:
            flags = [r[qid]["failed"] for r in mine if r.get(qid, {}).get("failed") is not None]
            if not flags:
                out.append(f"- {qid}: no answers")
                continue
            bad = sum(flags)
            lo, hi = wilson(bad, len(flags))
            out.append(f"- {qid} v{bank().get(qid).version}: failures {bad}/{len(flags)} (95% {lo:.2f}–{hi:.2f})"
                       f"{counted(qid)}")
    return out


class NotFound:
    name = "notfound"

    def refuse(self, opts: Options) -> str | None:
        return None if opts.profile == "agent" else "horizon: `notfound` runs the agent deep path; pass --profile agent"

    def plan(self, opts: Options, prices: Any, *, paid: bool) -> Plan:
        qs = items(opts)
        reply = estimate_chat(prices, prefix_tokens=4000, warm=True, other_in=1500, expected_out_tokens=140,
                              period="off_peak")
        st = {"mode": "one_on_one", "quoted_query": {"message": "x" * 200}, "quoted_passage": {"text": "x" * 1200}}
        deep = 10 * decision_estimate(prices, st, {"q": {"type": "score", "criteria": ["a", "b", "c"]}})
        js = sum(judge_estimate(prices, q, {"quoted_reply": "x" * 700, "quoted_passages": "x" * 2400}) for q in JUDGES)
        greeting = estimate_chat(prices, prefix_tokens=4000, warm=False, other_in=300, expected_out_tokens=60,
                                 period="off_peak")
        corpus = 62_000 * prices.embedding.input_per_m / 1e6
        return Plan(items=qs, estimate_usd=len(qs) * (reply + deep + js + greeting) + corpus,
                    expected_s=60 + len(qs) * 25.0, paid=paid)

    async def run(self, env: RunEnv, plan: Plan) -> Result:
        import httpx

        from horizon.evals.retrieval_suite import prepare
        from horizon.main import create_app

        await prepare(env, {})
        res = Result()
        states: list[dict[str, Any]] = []
        app = create_app(env.rt.cfg, runtime=env.rt)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as c:
            for q in plan.items:
                if await env.over_budget():
                    res.status = "incomplete"
                    break
                row = await self.one(env, c, q)
                for qid in JUDGES:
                    if row["reply"]:
                        p = await judge(env, qid, row["state"])
                        row[qid] = {"p": p, "failed": failed(p, qid)}
                states.append({"id": q["id"], "kind": row["kind"], "state": row["state"]})
                res.rows.append({k: v for k, v in row.items() if k != "state"})
        (env.run_dir / "judge_states.jsonl").write_text(
            "".join(json.dumps(s, ensure_ascii=False) + "\n" for s in states), encoding="utf-8")
        res.summary += report(res.rows)
        res.summary.append(f"- the judges' states for labelling the 30 real items: `{env.run_dir.name}/"
                           "judge_states.jsonl` (B4)")
        return res

    async def one(self, env: RunEnv, c: Any, q: dict[str, Any]) -> dict[str, Any]:
        from horizon.evals.suites import _advance
        from horizon.sessions.context import characters

        cid = str(q["character"])
        world = str((await characters(env.rt, [cid]))[cid]["world_id"])
        r = await c.post(f"{API}/sessions", json={"worldId": world, "mode": "one_on_one", "characterIds": [cid]})
        if r.status_code != 201:
            raise RuntimeError(f"notfound: creating the session failed ({r.status_code}): {r.text[:300]}")
        sid = r.json()["session"]["id"]
        await self.settle(env, c, sid, 1)    # the greeting
        await c.post(f"{API}/sessions/{sid}/send", json={"text": q["message"]})
        reply = await self.settle(env, c, sid, 2)
        await c.post(f"{API}/sessions/{sid}/end")
        await _advance(env, 1000)
        trace = (reply or {}).get("trace") or {}
        retrieved = list((trace.get("knowledge") or {}).get("retrieved") or [])
        text = str((reply or {}).get("content") or "")
        return {"id": q["id"], "split": q["split"], "kind": "partly" if q.get("partly") else q["kind"],
                "character": cid, "session": sid, "message": q["message"], "reply": text,
                "status": (reply or {}).get("status", "missing"), "kept": [r["chunkId"] for r in retrieved
                                                                         if r.get("n") is not None],
                "citations": (reply or {}).get("citations") or [], "graph": (trace.get("graph") or {}).get("path"),
                "state": judge_state(q["message"], retrieved, text)}

    @staticmethod
    async def settle(env: RunEnv, c: Any, sid: str, replies: int, limit_s: float = 120) -> dict[str, Any] | None:
        """Waits for the session's `replies`-th character message to finish; returns it (None past the limit)."""
        from horizon.evals.suites import _advance

        waited = 0.0
        while waited < limit_s:
            msgs = (await c.get(f"{API}/sessions/{sid}/messages", params={"limit": 1000})).json()["items"]
            mine = [m for m in msgs if m["author"]["type"] == "character"]
            if len(mine) >= replies and mine[replies - 1]["status"] in ("complete", "interrupted", "error"):
                return dict(mine[replies - 1])
            await _advance(env, 1000)
            waited += 1.0
        return None

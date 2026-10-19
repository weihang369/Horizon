"""`horizon eval faithfulness`: sentence faithfulness on the two-passage questions (docs/ai/10 K14's note; images-music
design D16; evaluation-harness "Sentence faithfulness on two-passage questions").

The retrieval suite's 10 `needs_two` answerable questions run as 1:1 `agent` deep turns end to end (the Not-found
suite's driver). Each factual sentence of the reply is asked once of `judge_sentence_supported` against the kept
passages. A sentence counts as factual by a code rule fixed before the run: five words or more and not a question
(an opinion that slips through is answered "states no fact", so it never counts against the reply). An item's rate is
its supported sentences over its factual ones. The judge's figures read NOT COUNTED until it passes B4.
"""

from __future__ import annotations

import json
import re
from typing import Any

from horizon.evals import retrieval as R
from horizon.evals.content import failed, judge, judge_estimate
from horizon.evals.metrics import wilson
from horizon.evals.notfound_suite import NONE_KEPT, NotFound, counted
from horizon.evals.runner import Options, Plan, Result, RunEnv

JUDGE = "judge_sentence_supported"
N_ITEMS = 10
SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")


def items(opts: Options) -> list[dict[str, Any]]:
    qs = [q for q in R.load_questions() if q.get("needs_two")][:N_ITEMS][opts.start:]
    return qs[: opts.limit] if opts.limit else qs


def factual(text: str) -> list[str]:
    """The reply's factual sentences (the code rule above)."""
    out = []
    for s in SENTENCE.split(text):
        s = s.strip()
        if len(s.split()) >= 5 and not s.endswith("?"):
            out.append(s)
    return out


class Faithfulness:
    name = "faithfulness"

    def refuse(self, opts: Options) -> str | None:
        return None if opts.profile == "agent" else "horizon: `faithfulness` runs the agent deep path; pass --profile agent"

    def plan(self, opts: Options, prices: Any, *, paid: bool) -> Plan:
        base = NotFound().plan(Options("notfound", profile="agent"), prices, paid=paid)
        per = base.estimate_usd / max(1, len(base.items))   # a deep turn as the Not-found suite prices it
        qs = items(opts)
        js = 5 * judge_estimate(prices, JUDGE, {"quoted_passages": "x" * 2400, "quoted_sentence": "x" * 160})
        return Plan(items=qs, estimate_usd=len(qs) * (per + js), expected_s=60 + len(qs) * 30.0, paid=paid)

    async def run(self, env: RunEnv, plan: Plan) -> Result:
        import httpx

        from horizon.evals.retrieval_suite import prepare
        from horizon.main import create_app

        await prepare(env, {})
        res = Result()
        driver = NotFound()
        states = env.run_dir / "judge_states.jsonl"
        app = create_app(env.rt.cfg, runtime=env.rt)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as c:
            for q in plan.items:
                if await env.over_budget():
                    res.status = "incomplete"
                    break
                row = await driver.one(env, c, q)
                passages = str(row["state"]["quoted_passages"])
                judged = []
                if passages != NONE_KEPT:
                    for s in factual(row["reply"]):
                        st = {"quoted_passages": passages, "quoted_sentence": s}
                        p = await judge(env, JUDGE, st)
                        with states.open("a", encoding="utf-8", newline="\n") as f:
                            f.write(json.dumps({"id": q["id"], "question_id": JUDGE, "state": st, "p": p},
                                               ensure_ascii=False) + "\n")
                        judged.append({"sentence": s, "p": p, "unsupported": failed(p, JUDGE)})
                res.rows.append({k: v for k, v in row.items() if k != "state"} | {"sentences": judged})
        res.summary += report(res.rows)
        return res


def report(rows: list[dict[str, Any]]) -> list[str]:
    out = [f"## Sentence faithfulness: {len(rows)} two-passage deep turn(s){counted(JUDGE)}"]
    flags = [s["unsupported"] for r in rows for s in r["sentences"] if s["unsupported"] is not None]
    if flags:
        ok = len(flags) - sum(flags)
        lo, hi = wilson(ok, len(flags))
        out.append(f"- supported sentences: {ok}/{len(flags)} ({ok / len(flags):.0%}, 95% {lo:.2f}–{hi:.2f})")
    for r in rows:
        js = [s for s in r["sentences"] if s["unsupported"] is not None]
        rate = f"{sum(not s['unsupported'] for s in js)}/{len(js)}" if js else "no factual sentence judged"
        out.append(f"- {r['id']} (kept {len(r['kept'])}): {rate}")
        out += [f"  - UNSUPPORTED: {s['sentence'][:200]}" for s in js if s["unsupported"]]
    return out

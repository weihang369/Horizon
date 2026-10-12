"""M8's content suites (docs/ai/04 P12; docs/ai/05 X10; evaluation-harness "Drafter suite", "Summary suite", "Long
suite", "Long-history frozen transcripts"; persona-context design D25, D28–D31; task 9.7).

- **drafter:** the naive drafter on 20 committed seeds with each seed's world; code checks plus two judges.
- **summary:** the rolling summariser on 40 committed dropped-history inputs; code checks plus five judges.
- **long:** (`agent` only, rare) three scripted conversations past two drops: recall, voice drift, the provider
  cache-hit %, summary calls and cost per 100 turns, the reply checks and the repetition rates.
- **transcript:** generates the long-history frozen transcripts with `naive` (`--set` picks one script).

Every judged figure is tagged "(unvalidated)" until its judge's current version passes B4 (`evals/judges.py`). In
test mode every suite runs on the in-process fake ($0), so smoke covers them.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from horizon.ai.decider import NoulAnswer, validate, wire_question
from horizon.ai.questions import bank
from horizon.domain.clock import FrozenClock
from horizon.domain.pricing import count_tokens, estimate_chat, estimate_decision_request
from horizon.evals import judges, reply_checks
from horizon.evals.metrics import wilson
from horizon.evals.runner import EVALS_DIR, Options, Plan, Result, RunEnv
from horizon.gateway.context import call_ctx

DRAFTER_SEEDS = EVALS_DIR / "drafter" / "seeds.jsonl"
SUMMARY_ITEMS = EVALS_DIR / "summary" / "items.jsonl"
LONG_DIR = EVALS_DIR / "long"
TRANSCRIPTS = EVALS_DIR / "transcripts"
STOCK_NAMES = ("elara", "kael", "seraphina", "lyra", "aria", "voss", "thorne")
TURN_TIMEOUT_S = 60.0
VOICE_SAMPLE = 10


def jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.is_file() else []


def take(items: list[Any], opts: Options) -> list[Any]:
    items = items[opts.start:]
    return items[: opts.limit] if opts.limit else items


async def judge(env: RunEnv, qid: str, state: dict[str, Any]) -> float | None:
    """One judge noul: p(failure), or None when the answer didn't validate."""
    q = bank().question(qid)
    r = await env.rt.gateway.decide(state, {qid: wire_question(q)}, call_ctx("eval_judge"))
    a = validate(q, r.answers.get(qid))
    return a.p if isinstance(a, NoulAnswer) else None


def failed(p: float | None, qid: str) -> bool | None:
    return None if p is None else p >= float(bank().get(qid).thresholds.get("t", 0.5))


def rate_line(name: str, qid: str, flags: Sequence[bool | None], *, target: str = "") -> str:
    xs = [x for x in flags if x is not None]
    if not xs:
        return f"- {name}: no answers"
    bad = sum(xs)
    lo, hi = wilson(len(xs) - bad, len(xs))
    tag = judges.label(qid, bank().get(qid).version)
    return (f"- {name}: {len(xs) - bad}/{len(xs)} ok ({(len(xs) - bad) / len(xs):.0%}, 95% {lo:.2f}–{hi:.2f})"
            f"{f', target {target}' if target else ''}{tag}")


def judge_estimate(prices: Any, qid: str, state: dict[str, Any]) -> float:
    return estimate_decision_request(prices, state, {qid: wire_question(bank().question(qid))})


# ── drafter ──
class Drafter:
    name = "drafter"

    def plan(self, opts: Options, prices: Any, *, paid: bool) -> Plan:
        seeds = take(jsonl(DRAFTER_SEEDS), opts)
        draft = estimate_chat(prices, prefix_tokens=2600, warm=False, other_in=80, expected_out_tokens=1400,
                              period="off_peak")
        est = len(seeds) * (draft + 2 * judge_estimate(prices, "judge_draft_fit", {"intent": "x", "quoted_seed": "x" * 60,
                                                                                    "quoted_draft": "x" * 3000}))
        return Plan(items=seeds, estimate_usd=est, expected_s=len(seeds) * 10.0, paid=paid)

    async def run(self, env: RunEnv, plan: Plan) -> Result:
        from horizon.ai.naive.creation import parse_draft
        from horizon.ai.ports import PaidHooks
        from horizon.gateway.errors import ProviderError
        from horizon.services.jobs.worker import draft_world_for

        res = Result()
        rt = env.rt
        if rt.fake is not None:   # test mode: group A's real drafts answer (doc 13 W14)
            from horizon.gateway.fake import load_canned
            purpose, items = load_canned("profile-drafts")
            rt.fake.set_canned(purpose, [x for x in items if x.get("valid")])
        drafter = rt.ai.drafter(True)
        for s in plan.items:
            if await env.over_budget():
                res.status = "incomplete"
                break
            world = await draft_world_for(rt, s["world"], None)
            try:
                d = await drafter.draft(call_ctx("profile", world_id=s["world"]), seed_prompt=s["seed"],
                                        intent=s["intent"], cost_usd=0.001, duration_ms=8000, model=rt.prices.chat.model,
                                        hooks=PaidHooks(), world=world)
                parse_draft(json.dumps(d), rt.schema, rt.palette_ids())   # contract-valid (raises if not)
            except ProviderError as e:   # a failed draft is a measurement (C7's retry included), not a crash
                res.rows.append({"id": s["id"], "split": s["split"], "intent": s["intent"], "seed": s["seed"],
                                 "valid": False, "error": e.message})
                continue
            p = d["profile"]
            spoken = " ".join([str(p.get("greeting", "")), *map(str, p.get("exampleLines") or [])])
            first = str(p.get("name", "")).split(" ")[0].casefold()
            taken = {n.split(" ")[0].casefold() for n in world.names_in_use}
            row: dict[str, Any] = {
                "id": s["id"], "split": s["split"], "intent": s["intent"], "seed": s["seed"], "draft": d, "valid": True,
                "adult": int(p.get("age", 0)) >= 18, "example_lines": 2 <= len(p.get("exampleLines") or []) <= 3,
                "plain_speech": "*" not in spoken, "fresh_name": first not in STOCK_NAMES and first not in taken}
            row["fit_p"] = await judge(env, "judge_draft_fit", {
                "intent": s["intent"], "quoted_seed": s["seed"], "quoted_draft": json.dumps(p, ensure_ascii=False)[:3000]})
            if s["intent"] == "companion":
                row["rel_p"] = await judge(env, "judge_relationship_fit", {
                    "quoted_user": json.dumps(world.you or {}, ensure_ascii=False), "quoted_draft": json.dumps(
                        p, ensure_ascii=False)[:3000], "quoted_relationship": str(p.get("relationshipToUser", ""))})
            res.rows.append(row)
        every = [r for r in res.rows if r["split"] == "test"] or res.rows
        test = [r for r in every if r["valid"]]
        res.summary += [f"## Drafter ({len(res.rows)} draft(s); figures on the test split, {len(every)})",
                        f"- valid draft after C7's one retry: {len(test)}/{len(every)}"]
        res.summary += [f"  - {r['id']}: {r['error']}" for r in every if not r["valid"]]
        for k in ("adult", "example_lines", "plain_speech", "fresh_name"):
            res.summary.append(f"- {k}: {sum(1 for r in test if r[k])}/{len(test)}")
        res.summary.append(rate_line("fits the seed", "judge_draft_fit",
                                     [failed(r.get("fit_p"), "judge_draft_fit") for r in test]))
        res.summary.append(rate_line("relationship fits", "judge_relationship_fit",
                                     [failed(r.get("rel_p"), "judge_relationship_fit") for r in test if "rel_p" in r]))
        return res


# ── summary ──
class Summary:
    name = "summary"

    def plan(self, opts: Options, prices: Any, *, paid: bool) -> Plan:
        items = take(jsonl(SUMMARY_ITEMS), opts)
        per = estimate_chat(prices, prefix_tokens=0, warm=False, other_in=900, expected_out_tokens=250,
                            period="off_peak") + 7 * judge_estimate(prices, "judge_summary_fact", {
                                "quoted_lines": "x" * 2400, "quoted_fact": "x" * 60, "quoted_summary": "x" * 600})
        return Plan(items=items, estimate_usd=len(items) * per, expected_s=len(items) * 8.0, paid=paid)

    async def run(self, env: RunEnv, plan: Plan) -> Result:
        from horizon.ai.contexts import SessionContext, WorldView
        from horizon.ai.naive.summary import NaiveSummariser

        res = Result()
        rt = env.rt
        if rt.fake is not None:
            from horizon.gateway.fake import load_canned
            purpose, canned = load_canned("rolling-summaries")
            rt.fake.set_canned(purpose, canned)
        summariser = NaiveSummariser(rt.ai.deps)
        for it in plan.items:
            if await env.over_budget():
                res.status = "incomplete"
                break
            lines = [f"{x['speaker']}: {x['text']}" for x in it["lines"]]
            sctx = SessionContext(session_id="", world=WorldView(id=it["world"], name="", you={"displayName": it["user"]}),
                                  mode="one_on_one", title="eval", participants=[], recent=[])
            text = await summariser.rolling(sctx, it.get("previous"), lines)
            joined = "\n".join(lines)
            row: dict[str, Any] = {"id": it["id"], "split": it["split"], "language": it["language"], "summary": text,
                                   "lines": lines, "within_cap": count_tokens(text) <= 600, "not_empty": bool(text.strip())}
            row["fact_p"] = [await judge(env, "judge_summary_fact", {"quoted_lines": joined, "quoted_fact": f,
                                                                      "quoted_summary": text}) for f in it["facts"]]
            promise = f"{it['promise']['by']} promised to {it['promise']['what']}"
            row["promise_p"] = await judge(env, "judge_summary_promise", {
                "quoted_lines": joined, "quoted_promise": promise, "quoted_summary": text})
            row["who_p"] = await judge(env, "judge_summary_who", {
                "quoted_lines": joined, "quoted_promise": promise, "quoted_summary": text})
            row["language_p"] = await judge(env, "judge_summary_language", {"quoted_lines": joined, "quoted_summary": text})
            row["unsupported_p"] = await judge(env, "judge_summary_unsupported", {
                "quoted_lines": joined, "quoted_previous": it.get("previous") or "none", "quoted_summary": text})
            res.rows.append(row)
        test = [r for r in res.rows if r["split"] == "test"] or res.rows
        res.summary += [f"## Summary ({len(res.rows)} item(s); figures on the test split, {len(test)})",
                        f"- within 600 tokens: {sum(r['within_cap'] for r in test)}/{len(test)}; not empty: "
                        f"{sum(r['not_empty'] for r in test)}/{len(test)}",
                        rate_line("planted fact kept", "judge_summary_fact",
                                  [failed(p, "judge_summary_fact") for r in test for p in r["fact_p"]], target="≥ 90 %"),
                        rate_line("promise kept", "judge_summary_promise",
                                  [failed(r["promise_p"], "judge_summary_promise") for r in test], target="≥ 90 %"),
                        rate_line("who promised", "judge_summary_who",
                                  [failed(r["who_p"], "judge_summary_who") for r in test], target="≥ 90 %"),
                        rate_line("same language", "judge_summary_language",
                                  [failed(r["language_p"], "judge_summary_language") for r in test],
                                  target="≤ 1 failure in 20"),
                        rate_line("nothing unsupported", "judge_summary_unsupported",
                                  [failed(r["unsupported_p"], "judge_summary_unsupported") for r in test],
                                  target="≤ 1 failure in 20")]
        for r in test:   # X10: every failure of the two hand-read checks is printed for reading
            for k, q in (("language_p", "judge_summary_language"), ("unsupported_p", "judge_summary_unsupported")):
                if failed(r[k], q):
                    res.summary.append(f"  - READ {r['id']} ({q}, p {r[k]:.2f}):\n    " + r["summary"].replace("\n", "\n    "))
        return res


# ── driving a scripted conversation (long, transcript) ──
async def wait_idle(env: RunEnv, sid: str) -> None:
    """D29: until no turn is queued or streaming and the summary task is idle (virtual time in test mode)."""
    clock = env.rt.clock
    waited = 0.0
    while waited < TURN_TIMEOUT_S:
        actor = env.rt.sessions.peek(sid)
        busy = actor is not None and (actor.busy or len(actor.turns) > 0 or (actor.current is not None and not
                                      actor.current.closed) or (actor.summary is not None and actor.summary.running))
        if actor is not None and not busy and waited > 0:
            return
        if isinstance(clock, FrozenClock):
            await clock.advance(500)
        else:
            await asyncio.sleep(0.25)
        waited += 0.5 if isinstance(clock, FrozenClock) else 0.25
    raise TimeoutError(f"session {sid} did not settle within {TURN_TIMEOUT_S:.0f} s")


async def drive(env: RunEnv, script: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """Create the session, post each scripted line, wait for the turn to settle, and record what came back."""
    import httpx

    from horizon.main import create_app

    app = create_app(env.rt.cfg, runtime=env.rt)
    api = "/api/v1"
    turns: list[dict[str, Any]] = []
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as c:
        r = await c.post(f"{api}/sessions", json={"worldId": script["world"], "mode": script["mode"],
                                                  "characterIds": script["cast"]})
        if r.status_code != 201:
            raise RuntimeError(f"creating the session failed ({r.status_code}): {r.text[:300]}")
        sid = r.json()["session"]["id"]
        await wait_idle(env, sid)
        seen = {m["id"] for m in (await c.get(f"{api}/sessions/{sid}/messages", params={"limit": 1000})).json()["items"]}
        for line in script["lines"]:
            if await env.over_budget():
                break
            await c.post(f"{api}/sessions/{sid}/send", json={"text": line["text"]})
            await wait_idle(env, sid)
            msgs = (await c.get(f"{api}/sessions/{sid}/messages", params={"limit": 1000})).json()["items"]
            new = [m for m in msgs if m["id"] not in seen and m["author"]["type"] == "character"]
            seen |= {m["id"] for m in msgs}
            turns.append({**line, "replies": [{"id": m["id"], "seq": m["seq"], "speaker": m["author"]["characterId"],
                                               "text": m["content"]} for m in new]})
    return sid, turns


async def summary_rows(env: RunEnv, sid: str) -> list[dict[str, Any]]:
    from sqlalchemy import select

    from horizon.db import tables as t

    S = t.session_summaries.c
    async with env.rt.db.read() as conn:
        rows = (await conn.execute(select(S.upto_seq, S.text, S.created_at).where(S.session_id == sid)
                                   .order_by(S.id))).mappings().all()
    return [dict(r) for r in rows]


async def ledger_rows(env: RunEnv, sid: str) -> list[dict[str, Any]]:
    from sqlalchemy import select

    from horizon.db import tables as t

    U = t.usage_records.c
    async with env.rt.db.read() as conn:
        rows = (await conn.execute(select(U.purpose, U.tokens_in, U.tokens_cached, U.cost_usd, U.at, U.message_id)
                                   .where(U.session_id == sid).order_by(U.at))).mappings().all()
    return [dict(r) for r in rows]


def cache_hit(replies: list[dict[str, Any]], summaries: list[dict[str, Any]]) -> float | None:
    """X10: the provider's cached share on turns that are neither the session's first nor right after a drop."""
    drops = sorted(str(s["created_at"]) for s in summaries)
    keep: list[dict[str, Any]] = []
    for i, r in enumerate(replies):
        if i == 0 or r["tokens_cached"] is None:
            continue
        after_drop = any(d <= str(r["at"]) and not any(d <= str(x["at"]) < str(r["at"]) for x in replies[:i])
                         for d in drops)
        if not after_drop:
            keep.append(r)
    tin = sum(int(r["tokens_in"] or 0) for r in keep)
    return sum(int(r["tokens_cached"] or 0) for r in keep) / tin if tin else None


def ok(xs: Sequence[bool | None]) -> tuple[int, int]:
    """(passed, answered): a judge's False is a pass, None an unvalidated answer."""
    return sum(1 for x in xs if x is False), sum(1 for x in xs if x is not None)


def persona_text(profile: dict[str, Any]) -> str:
    style = profile.get("speakingStyle") or {}
    examples = "; ".join(f'"{x}"' for x in profile.get("exampleLines") or [])
    return (f"{profile.get('name', '')}: {style.get('summary', '')} Tone: {style.get('tone', '')}. "
            f"Quirks: {'; '.join(style.get('quirks') or [])}. Sounds like: {examples}")


# ── long ──
class Long:
    name = "long"

    def plan(self, opts: Options, prices: Any, *, paid: bool) -> Plan:
        scripts = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(LONG_DIR.glob("*.json"))]
        if opts.set:
            scripts = [s for s in scripts if s["id"] == opts.set]
        if opts.limit:   # smoke: the first lines of each script only
            scripts = [{**s, "lines": s["lines"][: opts.limit]} for s in scripts]
        turns = sum(len(s["lines"]) * (2 if s["mode"] == "group" else 1) for s in scripts)
        reply = estimate_chat(prices, prefix_tokens=6000, warm=True, other_in=400, expected_out_tokens=140,
                              period="off_peak")
        est = turns * reply + turns / 30 * 0.001 + 60 * judge_estimate(prices, "judge_voice", {
            "quoted_persona": "x" * 600, "quoted_last": "x" * 300, "quoted_reply": "x" * 400})
        return Plan(items=scripts, estimate_usd=est, expected_s=turns * 6.0, paid=paid)

    async def run(self, env: RunEnv, plan: Plan) -> Result:
        from horizon.sessions.context import characters

        res = Result()
        if env.opts.profile != "agent" and not env.opts.limit:
            res.status = "failed"
            res.summary.append("## Long: runs `agent` only (docs/ai/05 X10); pass --profile agent")
            return res
        for script in plan.items:
            sid, turns = await drive(env, script)
            sums = await summary_rows(env, sid)
            rows = await ledger_rows(env, sid)
            profiles = {cid: r["profile"] for cid, r in (await characters(env.rt, script["cast"])).items()}
            replies = [(t, rep) for t in turns for rep in t["replies"]]
            checks = reply_checks.check_replies([reply_checks.Reply(
                speaker=rep["speaker"], mode=script["mode"], text=rep["text"],
                names=(profiles[rep["speaker"]]["name"], profiles[rep["speaker"]]["name"].split(" ")[0]),
                catchphrases=tuple((profiles[rep["speaker"]].get("speakingStyle") or {}).get("catchphrases") or []))
                for _t, rep in replies], free_running=True)
            facts = {x["fact"]: x["text"] for x in script["lines"] if x["kind"] == "fact"}
            recall: list[bool | None] = []
            for t in turns:
                if t["kind"] == "probe" and t["replies"]:
                    p = await judge(env, "judge_recall", {"quoted_fact": facts.get(t["fact"], t["fact"]),
                                                          "quoted_probe": t["text"],
                                                          "quoted_reply": "\n".join(r["text"] for r in t["replies"])})
                    recall.append(failed(p, "judge_recall"))
            first = sums[0]["upto_seq"] if sums else None
            second = sums[1]["upto_seq"] if len(sums) > 1 else None
            early = [(t, r) for t, r in replies if first is not None and r["seq"] <= first][-VOICE_SAMPLE:]
            late = [(t, r) for t, r in replies if second is not None and r["seq"] > second][:VOICE_SAMPLE]
            voice: dict[str, list[bool | None]] = {"early": [], "late": []}
            for k, sample in (("early", early), ("late", late)):
                for t, r in sample:
                    p = await judge(env, "judge_voice", {"quoted_persona": persona_text(profiles[r["speaker"]]),
                                                         "quoted_last": t["text"], "quoted_reply": r["text"]})
                    voice[k].append(failed(p, "judge_voice"))
            reply_ledger = [r for r in rows if r["purpose"] == "reply"]
            summ = [r for r in rows if r["purpose"] == "rolling_summary"]
            n_turns = len(replies) or 1
            hit = cache_hit(reply_ledger, sums)
            res.rows.append({"script": script["id"], "session": sid, "turns": turns, "summaries": sums,
                             "checks": checks.summary(), "recall": recall, "voice": voice, "cache_hit": hit})
            res.summary += [
                f"## Long: {script['id']} ({len(turns)} user lines, {len(replies)} replies, {len(sums)} drop(s))",
                rate_line("recall", "judge_recall", recall, target="≥ 80 %"),
                f"- voice in persona before the first drop {ok(voice['early'])[0]}/{ok(voice['early'])[1]}, after the "
                f"second {ok(voice['late'])[0]}/{ok(voice['late'])[1]}{judges.label('judge_voice', bank().get('judge_voice').version)}",
                f"- provider cache-hit (not first, not after a drop): {'n/a (store hits or no rows)' if hit is None else f'{hit:.0%}'}"
                " (target ≥ 80 %)",
                f"- rolling_summary: {len(summ)} call(s), {100 * len(summ) / n_turns:.1f} per 100 turns, "
                f"${sum(float(r['cost_usd']) for r in summ):.5f}",
                "- reply checks: " + json.dumps(checks.summary())]
        return res


# ── transcript ──
def load_transcript(path: Path) -> dict[str, Any]:
    """The loader's check (D31): a transcript marked long must have dropped at least once."""
    t: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if t.get("long") and not any(turn.get("summary") for turn in t.get("turns", [])):
        raise ValueError(f"{path.name}: marked long, but its history never dropped (no turn has a summary)")
    return t


class Transcript:
    name = "transcript"

    def plan(self, opts: Options, prices: Any, *, paid: bool) -> Plan:
        scripts = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((TRANSCRIPTS / "scripts").glob("*.json"))]
        if opts.set:
            scripts = [s for s in scripts if s["id"] == opts.set]
        if opts.limit:
            scripts = [{**s, "lines": s["lines"][: opts.limit]} for s in scripts]
        turns = sum(len(s["lines"]) * (2 if s["mode"] == "group" else 1) for s in scripts)
        reply = estimate_chat(prices, prefix_tokens=6000, warm=True, other_in=400, expected_out_tokens=140,
                              period="off_peak")
        return Plan(items=scripts, estimate_usd=turns * reply + turns / 30 * 0.001, expected_s=turns * 6.0, paid=paid)

    async def run(self, env: RunEnv, plan: Plan) -> Result:
        res = Result()
        for script in plan.items:
            sid, turns = await drive(env, script)
            sums = await summary_rows(env, sid)
            out_turns = []
            for t in turns:
                last = max((r["seq"] for r in t["replies"]), default=0)
                active = [s for s in sums if s["upto_seq"] < last]
                cur = active[-1] if active else None
                out_turns.append({"user": t["text"], "kind": t["kind"],
                                  "replies": [{"speaker": r["speaker"], "text": r["text"]} for r in t["replies"]],
                                  "summary_upto": cur["upto_seq"] if cur else None, "summary": cur["text"] if cur else None})
            doc = {"schemaVersion": 1, "id": script["id"], "mode": script["mode"], "world": script["world"],
                   "cast": script["cast"], "long": True, "language": script["language"], "turns": out_turns}
            if not env.opts.limit:   # smoke never writes a committed file
                path = TRANSCRIPTS / f"{script['id']}.json"
                path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
            res.rows.append({"script": script["id"], "turns": len(out_turns), "drops": len(sums)})
            res.summary.append(f"## Transcript {script['id']}: {len(out_turns)} turns, {len(sums)} drop(s)"
                               + ("" if sums else " (NOT past a drop yet)"))
        return res

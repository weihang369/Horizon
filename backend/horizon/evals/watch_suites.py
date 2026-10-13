"""M10's suites for group and watch (group-watch design D23, D24; doc 07 G11, §5; evaluation-harness "Committed watch
histories", "Episode recaps in the summary suite", "Free runs for group and watch", "Follow-plan and watch timing").

- **watch-history:** generates the two committed watch histories with `naive` through the store, once. It refuses to
  overwrite a committed history unless `--force` is given, before any paid call.
- **recaps (inside `summary`):** 10 episode recaps from the committed histories, each checked in code (≤ 120 words)
  and by two summary judges ("nothing invented", which also covers "faithful", and "right language"); every failure
  is printed.
- **freerun:** `agent` watch scenes and group sessions with scripted user lines. Signals only, no target: the
  second-reply rate (follow-plan timeouts apart from `none`), the busiest speaker's share, the guard's and the steer's
  firing rates, and every steered line printed for reading.
- **latency parts** (`latency --part follow|watch`, store bypassed): the follow plan's miss rule (D9) over 50 hand-built
  follow states, and watch scenes at Fast pace against NFR-02. Jev's slow spells are reported apart.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from horizon.domain.clock import FrozenClock
from horizon.domain.pricing import estimate_chat
from horizon.evals.content import budget_code, failed, judge, rate_line, wait_idle
from horizon.evals.metrics import percentile
from horizon.evals.runner import EVALS_DIR, Options, Plan, Result, RunEnv, decision_estimate

WATCH_DIR = EVALS_DIR / "watch"
SCRIPTS = WATCH_DIR / "scripts"
API = "/api/v1"
RECAP_WORDS = 120
RECAP_POINTS = {"meridian_long": (20, 40, 60, 80, 90, 100), "sunnyhollow": (10, 20, 30, 40)}
SLOW_MS = 2000.0            # D23: a request over 2 s is slow
SPELL_RUN = 3               # three or more slow requests in a row make a spell
F_MS = 12.3                 # docs/ai/checks/m10.md, task 4.7: stream end → turn.end, p50 on Windows
FOLLOW_DEADLINE_MS = 400.0  # timeoutsMs.decision.follow_plan
MISS_MAX = 0.10             # D9: pass at ≤ 10 % missed
NFR02_P50_MS = 3000.0


async def advance(env: RunEnv, ms: float) -> None:
    if isinstance(env.rt.clock, FrozenClock):
        await env.rt.clock.advance(ms)
    else:
        await asyncio.sleep(ms / 1000)


def history_path(hid: str) -> Path:
    return WATCH_DIR / f"{hid}.json"


def scripts(only: str | None = None) -> list[dict[str, Any]]:
    out = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(SCRIPTS.glob("*.json"))] if SCRIPTS.is_dir() else []
    return [s for s in out if only is None or s["id"] == only]


def load_history(hid: str) -> dict[str, Any] | None:
    p = history_path(hid)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


# ── watch-history ──
class WatchHistory:
    name = "watch-history"

    def refuse(self, opts: Options) -> str | None:
        """Checked before any call: a committed history is never overwritten without `--force`."""
        if opts.force or opts.limit:   # a limited run (smoke, tests) writes only to its run folder
            return None
        done = [s["id"] for s in scripts(opts.set) if history_path(s["id"]).is_file()]
        if done:
            return (f"horizon: {', '.join(done)} already committed in evals/watch/; pass --force to overwrite "
                    "(nothing was sent)")
        return None

    def plan(self, opts: Options, prices: Any, *, paid: bool) -> Plan:
        items = scripts(opts.set)
        if opts.limit:
            items = [{**s, "turns": min(int(s["turns"]), opts.limit)} for s in items]
        turns = sum(int(s["turns"]) for s in items)
        reply = estimate_chat(prices, prefix_tokens=5000, warm=True, other_in=400, expected_out_tokens=120,
                              period="off_peak")
        return Plan(items=items, estimate_usd=turns * reply + turns / 25 * 0.001, expected_s=turns * 7.0, paid=paid)

    async def run(self, env: RunEnv, plan: Plan) -> Result:
        res = Result()
        for script in plan.items:
            doc, complete, _, _ = await drive_watch(env, script)
            out = (env.run_dir / f"{script['id']}.json") if env.opts.limit else history_path(script["id"])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
            lines = [x for x in doc["lines"] if x["kind"] == "line"]
            drops = len({x["summary_upto"] for x in doc["lines"] if x.get("summary_upto")})
            res.rows.append({"history": script["id"], "turns": len(lines), "drops": drops, "path": str(out)})
            res.summary.append(f"## Watch history {script['id']}: {len(lines)} turns, {drops} summary drop(s), "
                               f"written to {out.name}" + ("" if complete else " (INCOMPLETE: stopped early)"))
            if not complete:
                res.status = "incomplete"
                break
        return res


async def drive_watch(env: RunEnv, script: dict[str, Any]) -> tuple[dict[str, Any], bool, str, list[dict[str, Any]]]:
    """Run one watch scene to `turns` (extending past the 40-turn limit), posting the script's director's notes when
    the scene reaches their turn; then record every line with the rolling summary that was current for it. Returns
    (the history document, whether it completed, the session id, its messages with their traces)."""
    import httpx

    from horizon.evals.content import summary_rows
    from horizon.main import create_app

    app = create_app(env.rt.cfg, runtime=env.rt)
    target = int(script["turns"])
    notes = {int(k): v for k, v in (script.get("notes") or {}).items()}
    complete = True
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as c:
        r = await c.post(f"{API}/sessions", json={"worldId": script["world"], "mode": "watch",
                                                  "characterIds": script["cast"],
                                                  "config": {"premise": script["premise"], "maxTurns": 40,
                                                             "paceMs": int(script.get("paceMs", 500)),
                                                             "openingSpeaker": "auto"}})
        if r.status_code != 201:
            raise RuntimeError(f"creating the watch failed ({r.status_code}): {r.text[:300]}")
        sid = r.json()["session"]["id"]
        posted: set[int] = set()
        stalled = 0.0
        last_taken = -1
        while True:
            snap = (await c.get(f"{API}/sessions/{sid}")).json()
            st = snap["session"].get("state") or {}
            taken = int(st.get("turnsTaken", 0))
            if taken >= target:
                break
            if await env.over_budget():
                complete = False
                break
            for k, text in notes.items():
                if taken >= k and k not in posted:
                    posted.add(k)
                    await c.post(f"{API}/sessions/{sid}/watch/direct", json={"text": text})
            if st.get("status") == "ended":
                resp = await c.post(f"{API}/sessions/{sid}/watch/extend", json={"turns": 10})
                if budget_code(resp):
                    complete = False
                    break
            elif snap["session"]["status"] == "paused" and st.get("status") == "paused":
                resp = await c.post(f"{API}/sessions/{sid}/watch/play", json={})
                if budget_code(resp):
                    complete = False
                    break
            await advance(env, 1000)
            stalled = 0.0 if taken != last_taken else stalled + 1.0
            last_taken = taken
            if stalled > 300:   # five minutes with no turn: give up rather than hang
                complete = False
                break
        await c.post(f"{API}/sessions/{sid}/watch/pause", json={})
        await wait_idle(env, sid)
        msgs = (await c.get(f"{API}/sessions/{sid}/messages", params={"limit": 1000})).json()["items"]
    sums = await summary_rows(env, sid)
    lines = []
    for m in sorted(msgs, key=lambda m: m["seq"]):
        if m["author"]["type"] == "character" and m.get("content"):
            kind, who = "line", str(m["author"]["characterId"])
        elif m.get("kind") == "direction" and m["author"]["type"] == "user":
            kind, who = "note", "director"
        else:
            continue
        cur = [s for s in sums if int(s["upto_seq"]) < int(m["seq"])]
        lines.append({"seq": m["seq"], "kind": kind, "speaker": who, "text": m["content"],
                      "summary_upto": cur[-1]["upto_seq"] if cur else None,
                      "summary": cur[-1]["text"] if cur else None})
    doc = {"schemaVersion": 1, "id": script["id"], "mode": "watch", "world": script["world"], "cast": script["cast"],
           "premise": script["premise"], "language": script.get("language", "en"), "lines": lines}
    return doc, complete, sid, msgs


# ── recaps (the summary suite) ──
def recap_items() -> list[dict[str, Any]]:
    """D23's 10 recap points from the committed histories: the scene up to turn k (k character lines)."""
    from horizon.evals.datachecks import split_for

    out = []
    for hid, points in RECAP_POINTS.items():
        h = load_history(hid)
        if h is None:
            continue
        for k in points:
            item_id = f"recap-{hid}-{k:03d}"
            out.append({"id": item_id, "split": split_for(item_id), "history": hid, "turn": k,
                        "language": h.get("language", "en")})
    return out


def recap_context(h: dict[str, Any], k: int, profiles: dict[str, Any], window: int = 9000) -> Any:
    """The live recap's input at turn k: the premise, the cast, the summary current then, and the lines after it."""
    from horizon.ai.contexts import MessageView, ParticipantView, SessionContext, WorldView

    lines = h["lines"]
    upto = [i for i, x in enumerate(lines) if x["kind"] == "line"]
    end = upto[min(k, len(upto)) - 1] + 1 if upto else 0
    seen = lines[:end]
    summary = seen[-1]["summary"] if seen else None
    cut = seen[-1]["summary_upto"] if seen else None
    recent = [x for x in seen if cut is None or int(x["seq"]) > int(cut)]
    views = []
    for x in recent:
        if x["kind"] == "note":
            views.append(MessageView(id=f"m{x['seq']}", seq=int(x["seq"]), author_type="user", name="Kai",
                                     kind="direction", content=x["text"]))
        else:
            name = str(profiles[x["speaker"]]["name"]) if x["speaker"] in profiles else x["speaker"]
            views.append(MessageView(id=f"m{x['seq']}", seq=int(x["seq"]), author_type="character",
                                     character_id=x["speaker"], name=name, kind="chat", content=x["text"]))
    parts = [ParticipantView(character_id=cid, name=str(profiles[cid]["name"]), role="speaker",
                             character_role=str(profiles[cid].get("role") or ""), energy={"current": 500, "max": 1000})
             for cid in h["cast"] if cid in profiles]
    return SessionContext(session_id="", seed="recap", world=WorldView(id=h["world"], name="", you={"displayName": "Kai"}),
                          mode="watch", title="eval", config={"premise": h["premise"]}, participants=parts,
                          recent=views, summary=summary)


def seed_profiles() -> dict[str, Any]:
    from horizon.config import REPO_ROOT

    out = {}
    for p in sorted((REPO_ROOT / "seed" / "characters").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))["data"]
        out[d["id"]] = d["profile"]
    return out


async def run_recaps(env: RunEnv, items: Sequence[dict[str, Any]], res: Result) -> None:
    """Each recap item through the live summariser, then the code check and the three judges (D23)."""
    from horizon.ai.naive.summary import NaiveSummariser, episode_lines, word_count
    from horizon.gateway.errors import ProviderError

    summariser = NaiveSummariser(env.rt.ai.deps)
    profiles = seed_profiles()
    rows = []
    for it in items:
        if await env.over_budget():
            res.status = "incomplete"
            break
        h = load_history(it["history"])
        if h is None:
            continue
        ctx = recap_context(h, int(it["turn"]), profiles)
        err: str | None = None
        try:
            text = await summariser.episode(ctx)
        except ProviderError as e:
            text, err = "", e.code
        joined = "\n".join(([f"Earlier: {ctx.summary}"] if ctx.summary else []) + episode_lines(ctx))
        words = word_count(text)
        row: dict[str, Any] = {"id": it["id"], "split": it["split"], "history": it["history"], "turn": it["turn"],
                               "recap": text, "words": words, "within_words": 0 < words <= RECAP_WORDS, "error": err,
                               "lines": joined}
        if text:
            row["unsupported_p"] = await judge(env, "judge_summary_unsupported", {
                "quoted_lines": joined, "quoted_previous": "none", "quoted_summary": text})
            row["language_p"] = await judge(env, "judge_summary_language", {"quoted_lines": joined,
                                                                            "quoted_summary": text})
        rows.append(row)
    res.rows += rows
    res.summary += recap_report(rows)


def recap_failures(r: dict[str, Any]) -> list[str]:
    out = []
    if not r["within_words"]:
        out.append(f"{r['words']} words" if r["words"] else f"no recap ({r.get('error') or 'empty'})")
    for k, q in (("unsupported_p", "judge_summary_unsupported"), ("language_p", "judge_summary_language")):
        if failed(r.get(k), q):
            out.append(q)
    return out


def recap_report(rows: Sequence[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["## Episode recaps: no committed watch histories yet (evals/watch/), nothing run"]
    bad = [(r, recap_failures(r)) for r in rows]
    n_bad = sum(1 for _, f in bad if f)
    out = [f"## Episode recaps ({len(rows)}): {n_bad} failure(s) (target ≤ 1)" + (" ✓" if n_bad <= 1 else " ✗"),
           f"- within {RECAP_WORDS} words: {sum(r['within_words'] for r in rows)}/{len(rows)}",
           # D23's "faithful" and "nothing invented" are one validated noul here: X10's `judge_summary_who` needs a
           # planted promise, which a recap hasn't got, and a wrong "who did what" is a statement the lines don't
           # support (10.6's finding: fed a stand-in promise it failed every recap)
           rate_line("faithful, nothing invented", "judge_summary_unsupported",
                     [failed(r.get("unsupported_p"), "judge_summary_unsupported") for r in rows if "unsupported_p" in r]),
           rate_line("right language", "judge_summary_language",
                     [failed(r.get("language_p"), "judge_summary_language") for r in rows if "language_p" in r])]
    for r, f in bad:   # every failure printed for reading, with its lines
        if f:
            out.append(f"  - READ {r['id']} ({', '.join(f)}):\n    " + (r["recap"] or "(none)").replace("\n", "\n    ")
                       + "\n    lines:\n    " + r["lines"].replace("\n", "\n    "))
    return out


# ── freerun ──
FREERUN_PREMISES = (
    ("wld_seedMeridian", ["chr_seedAmara", "chr_seedMei", "chr_seedVictor"],
     "The council's emergency budget meeting, the night before the vote."),
    ("wld_seedSunnyHollow", ["chr_seedHana", "chr_seedRin", "chr_seedTakeshi"],
     "A rainy Sunday at the flower shop, and the till won't open."),
    ("wld_seedMeridian", ["chr_seedAmara", "chr_seedMei", "chr_seedVictor"],
     "A radio phone-in about whether the city should ban cars from the centre."),
)


def group_lines(k: int, n: int) -> list[str]:
    from horizon.evals.content import LONG_DIR

    pool = [str(x["text"]) for x in json.loads((LONG_DIR / "group_meridian.json").read_text(encoding="utf-8"))["lines"]]
    return [pool[(k * n + i) % len(pool)] for i in range(n)]


class FreeRun:
    name = "freerun"

    def plan(self, opts: Options, prices: Any, *, paid: bool) -> Plan:
        mode = opts.mode or "watch"
        runs = opts.runs or 3
        per = (opts.turns or 30) if mode == "watch" else (opts.messages or 12)
        if opts.limit:
            runs, per = 1, min(per, opts.limit)
        reply = estimate_chat(prices, prefix_tokens=4000, warm=True, other_in=400, expected_out_tokens=120,
                              period="off_peak")
        plan_call = decision_estimate(prices, {"quoted_latest": "x" * 2400}, {"q": {"instructions": "x" * 1200}})
        replies = runs * per * (1 if mode == "watch" else 1.5)
        return Plan(items=[{"mode": mode, "run": k, "n": per} for k in range(runs)],
                    estimate_usd=replies * (reply + 2 * plan_call), expected_s=replies * 6.0, paid=paid)

    async def run(self, env: RunEnv, plan: Plan) -> Result:
        res = Result()
        if env.opts.profile != "agent" and not env.opts.limit:
            res.status = "failed"
            res.summary.append("## Free run: runs `agent` only; pass --profile agent")
            return res
        msgs: list[dict[str, Any]] = []
        sends = 0
        for item in plan.items:
            if await env.over_budget():
                res.status = "incomplete"
                break
            got, n = await (self.watch(env, item) if item["mode"] == "watch" else self.group(env, item))
            msgs += got
            sends += n
            res.rows.append({"mode": item["mode"], "run": item["run"], "replies": len(got), "sends": n})
        res.summary += freerun_report(plan.items[0]["mode"] if plan.items else "watch", msgs, sends)
        return res

    @staticmethod
    async def watch(env: RunEnv, item: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
        world, cast, premise = FREERUN_PREMISES[item["run"] % len(FREERUN_PREMISES)]
        _, _, _, msgs = await drive_watch(env, {"id": f"freerun-{item['run']}", "world": world, "cast": cast,
                                                "premise": premise, "turns": item["n"], "paceMs": 500})
        return msgs, 0

    @staticmethod
    async def group(env: RunEnv, item: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
        import httpx

        from horizon.main import create_app

        app = create_app(env.rt.cfg, runtime=env.rt)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as c:
            world, cast, _ = FREERUN_PREMISES[item["run"] % len(FREERUN_PREMISES)]
            r = await c.post(f"{API}/sessions", json={"worldId": world, "mode": "group", "characterIds": cast})
            if r.status_code != 201:
                return [], 0
            sid = r.json()["session"]["id"]
            await wait_idle(env, sid)
            n = 0
            for line in group_lines(item["run"], item["n"]):
                if await env.over_budget() or budget_code(await c.post(f"{API}/sessions/{sid}/send",
                                                                       json={"text": line})):
                    break
                n += 1
                await wait_idle(env, sid)
            got = (await c.get(f"{API}/sessions/{sid}/messages", params={"limit": 1000})).json()["items"]
        return got, n


def freerun_report(mode: str, msgs: Sequence[dict[str, Any]], sends: int) -> list[str]:
    replies = [m for m in msgs if m["author"]["type"] == "character"]
    out = [f"## Free run ({mode}): {len(replies)} replies" + (f" to {sends} sends" if mode == "group" else "")
           + " — signals only, no target"]
    if not replies:
        return [*out, "- no replies"]
    by = Counter(str(m["author"].get("characterId")) for m in replies)
    top, n_top = by.most_common(1)[0]
    out.append(f"- busiest speaker: {top} with {n_top}/{len(replies)} ({n_top / len(replies):.0%})")

    def rows(m: dict[str, Any]) -> list[dict[str, Any]]:
        return list((((m.get("trace") or {}).get("system1")) or {}).get("questions") or [])

    if mode == "group":
        seconds = sum(1 for m in replies if ((m.get("trace") or {}).get("routing") or {}).get("question")
                      == "who speaks up now?")
        follow = [r for m in replies for r in rows(m) if r.get("id") == "who_second"]
        none = sum(1 for r in follow if r.get("answer") == "none")
        late = sum(1 for r in follow if "late" in str(r.get("answer")))
        unsure = sum(1 for r in follow if r.get("result") == "below_threshold")
        out.append(f"- second replies: {seconds}/{sends} sends ({seconds / sends:.0%})" if sends else
                   "- second replies: no sends")
        out.append(f"- no second reply: {none} none, {late} timeouts (late), {unsure} unsure (below the floor)")
    else:
        guard = sum(1 for m in replies if ((m.get("trace") or {}).get("routing") or {}).get("forcedBy") == "round_order")
        steered = [m for m in replies if any(r.get("id") == "talk_finished" and r.get("action") == "steer"
                                             for r in rows(m))]
        out.append(f"- the guard fired on {guard}/{len(replies)} turns ({guard / len(replies):.0%})")
        out.append(f"- the steer fired on {len(steered)}/{len(replies)} turns ({len(steered) / len(replies):.0%})")
        for m in steered:   # read by eye: does the steered line start something new? (no judge, D23)
            out.append(f"  - STEERED {m['author'].get('characterId')}: {m['content'][:300]}")
    return out


# ── timing: slow spells (D23) ──
def spells(latencies: Sequence[float], slow_ms: float = SLOW_MS, run: int = SPELL_RUN) -> list[tuple[int, int]]:
    """(first, last) index of every run of ≥ `run` consecutive requests over `slow_ms`."""
    out: list[tuple[int, int]] = []
    start: int | None = None
    for i, ms in enumerate([*latencies, 0.0]):
        if ms > slow_ms and i < len(latencies):
            start = i if start is None else start
            continue
        if start is not None and i - start >= run:
            out.append((start, i - 1))
        start = None
    return out


def in_spell(i: int, sp: Sequence[tuple[int, int]]) -> bool:
    return any(a <= i <= b for a, b in sp)


def follow_misses(rows: Sequence[dict[str, Any]], f_ms: float = F_MS,
                  deadline_ms: float = FOLLOW_DEADLINE_MS) -> dict[str, Any]:
    """D9: a miss is S + L > F + 400, with and without the slow spells."""
    lat = [float(r["l_ms"]) for r in rows]
    sp = spells(lat)
    miss = [float(r["s_ms"]) + float(r["l_ms"]) > f_ms + deadline_ms for r in rows]
    outside = [m for i, m in enumerate(miss) if not in_spell(i, sp)]
    return {"n": len(rows), "missed": sum(miss), "rate": sum(miss) / len(rows) if rows else 0.0,
            "spells": sp, "rate_without_spells": sum(outside) / len(outside) if outside else 0.0,
            "passes": bool(rows) and sum(miss) / len(rows) <= MISS_MAX}


def follow_report(rows: Sequence[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["## Follow-plan timing: no requests"]
    m = follow_misses(rows)
    s = [float(r["s_ms"]) for r in rows]
    lat = [float(r["l_ms"]) for r in rows]
    out = [f"## Follow-plan timing (D9): {m['missed']}/{m['n']} missed ({m['rate']:.0%}; pass ≤ 10 %) → "
           + ("PASS" if m["passes"] else "FAIL: G2's rule applies (set the deadline from the measured p90, D27)"),
           f"- a miss is S + L > F + 400 ms, with F = {F_MS} ms (m10.md, 4.7)",
           f"- S (state assembly) p50 {percentile(s, 0.5):.1f} ms, p90 {percentile(s, 0.9):.1f} ms",
           f"- L (Jev) p50 {percentile(lat, 0.5):.0f} ms, p90 {percentile(lat, 0.9):.0f} ms",
           f"- S + L − F p90 {percentile([a + b - F_MS for a, b in zip(s, lat, strict=True)], 0.9):.0f} ms "
           "(the deadline G2 would set)"]
    if m["spells"]:
        out.append(f"- slow spells (≥ {SPELL_RUN} requests over {SLOW_MS / 1000:.0f} s in a row): "
                   + "; ".join(f"requests {a + 1}–{b + 1}" for a, b in m["spells"])
                   + f"; miss rate without them {m['rate_without_spells']:.0%}")
    else:
        out.append("- no slow spells")
    return out


async def follow_timing(env: RunEnv, limit: int | None = None) -> list[dict[str, Any]]:
    """50 follow requests from the second-slot items' dev split: S timed in process, L the request's wall time."""
    import importlib.util

    from horizon.ai.agent.follow_plan import FollowSteps, follow_state
    from horizon.ai.decider import wire_question
    from horizon.gateway.context import call_ctx

    path = EVALS_DIR / "datasets" / "who_speaks" / "build.py"
    spec = importlib.util.spec_from_file_location("who_speaks_build", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    reqs = [(i, r) for i, split, r in mod.second_requests() if split == "dev"][: limit or 50]
    rows = []
    for item_id, req in reqs:
        if await env.over_budget():
            break
        t0 = time.perf_counter()
        st = follow_state(req)
        s_ms = (time.perf_counter() - t0) * 1000
        qs, _ = FollowSteps.questions(req)
        t1 = time.perf_counter()
        await env.rt.gateway.decide(st.state, {k: wire_question(q) for k, q in qs.items()}, call_ctx("follow_plan"))
        rows.append({"id": item_id, "s_ms": round(s_ms, 3), "l_ms": round((time.perf_counter() - t1) * 1000, 1),
                     "tokens": st.tokens})
    return rows


def watch_timing_report(gaps_next: Sequence[float], gaps_token: Sequence[float], plans: Sequence[tuple[float, str]],
                        turns: int, fallbacks: int) -> list[str]:
    def q(xs: Sequence[float]) -> str:
        return f"p50 {percentile(xs, 0.5):.0f} ms, p90 {percentile(xs, 0.9):.0f} ms" if xs else "no samples"

    lat = [p[0] for p in plans]
    sp = spells(lat)
    redone = max(0, len(plans) - turns)
    cancelled = sum(1 for p in plans if p[1] == "cancelled")
    used = max(0, turns - fallbacks - redone)
    out = [f"## Watch timing (Fast pace): {turns} turns",
           f"- turn.end → next turn.next: {q(gaps_next)}",
           f"- turn.end → next first token: {q(gaps_token)} (NFR-02 p50 ≤ {NFR02_P50_MS / 1000:.0f} s)"
           + ("" if not gaps_token else (" ✓" if percentile(gaps_token, 0.5) <= NFR02_P50_MS else " ✗")),
           f"- the plan made ahead: used {used}, redone {redone} ({cancelled} cancelled), fell back {fallbacks}",
           f"- Jev turn_plan: {q(lat)}"]
    if sp:
        keep = [x for i, x in enumerate(lat) if not in_spell(i, sp)]
        out.append(f"- slow spells: {len(sp)} ({'; '.join(f'{a + 1}–{b + 1}' for a, b in sp)}); "
                   f"turn_plan without them: {q(keep)}")
    return out

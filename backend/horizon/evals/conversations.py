"""`horizon eval conversations`: layer 3, `agent` beside `naive` on the frozen transcripts (docs/ai/02 B1, B3, B4;
images-music design D11; evaluation-harness "The conversations suite", "Layer 3 judgements and statistics").

- **Units:** the compared turns of the 20 frozen transcripts (`frozen.py`): a 1:1 or group turn (the user line),
  a debate slot or a watch line. `--set ID` runs one transcript; `--limit N` the first N units of each mode (smoke: 1).
- **The rebuild (B3):** for each unit, each profile's isolated copy gets a session holding exactly the stored history
  before it, written as a fork writes one (the events, the messages, the summary in force; `moodline`'s `history()`
  generalised to every mode): the debate's round banners and the phase it stands in, the watch's director notes and
  turn count. The memory list is the seed's (both copies load it; the copies' pause runs are off, so it never changes
  inside a transcript, B3). Then the live path runs for the unit: `send` (1:1, group), `debate/next` (debate) or
  `watch/step` (watch), and the first new character line is the reply; each profile picks its own speaker.
- **Both profiles:** the run's copy runs `--profile` (default `naive`); the suite opens the other profile's isolated
  copy beside it (`<run>/<other>/`) with the same store, key and cap, and the spend is both copies'.
- **Saved states (pay once):** `replies.jsonl` holds every unit's two replies and their history, `judge_states.jsonl`
  every judge state, so a judge validated later re-scores them without new replies.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path
from typing import Any

from horizon.evals import frozen
from horizon.evals.runner import Options, Plan, Result, RunEnv

API = "/api/v1"
USER = "Kai"
PROFILES = ("agent", "naive")
MULTI = ("debate", "watch")
WATCH_MORE = 10                 # turns left in a rebuilt watch scene (one is stepped)


# ── the units ──
def units(ts: Sequence[dict[str, Any]], opts: Options) -> list[dict[str, Any]]:
    """Every compared unit, transcript by transcript; `--limit` keeps the first N of each mode."""
    out: list[dict[str, Any]] = []
    per_mode: dict[str, int] = {}
    for t in ts:
        if opts.set and t["id"] != opts.set:
            continue
        for u in t["compared"]:
            if opts.limit and per_mode.get(t["mode"], 0) >= opts.limit:
                break
            per_mode[t["mode"]] = per_mode.get(t["mode"], 0) + 1
            row: dict[str, Any] = {"key": f"{t['id']}#{u}", "transcript": t["id"], "mode": t["mode"], "unit": u,
                                   "split": t["split"], "lang": t.get("language", "en")}
            if "turns" in t:
                turn = t["turns"][u]
                row.update(latest=turn["user"], kind=turn.get("kind"), lang=turn.get("lang") or row["lang"],
                           covered=turn.get("covered"))
            out.append(row)
    return out[opts.start:]


# ── the rebuild ──
@dataclasses.dataclass
class Rebuilt:
    """A unit's stored history, as the session holds it before the unit."""

    lines: list[dict[str, Any]]                 # {author, characterId?, kind, content, debate?}
    summary: tuple[int, str] | None             # (upto_seq, text) in the rebuilt numbering
    latest: str | None                          # the user line (1:1, group)
    state: dict[str, Any] | None                # the debate's or the watch's state


def rebuild(t: dict[str, Any], unit: int) -> Rebuilt:
    if "turns" in t:
        lines: list[dict[str, Any]] = []
        for turn in t["turns"][:unit]:
            lines.append({"author": "user", "kind": "chat", "content": turn["user"]})
            lines += [{"author": "character", "characterId": r["speaker"], "kind": "chat", "content": r["text"]}
                      for r in turn["replies"]]
        cur = t["turns"][unit]
        upto, text = cur.get("summary_upto"), cur.get("summary")
        return Rebuilt(lines, (int(upto), str(text)) if text and upto is not None else None, str(cur["user"]), None)
    before = [ln for ln in t["lines"] if int(ln["seq"]) < unit]
    target = next(ln for ln in t["lines"] if int(ln["seq"]) == unit)
    if t["mode"] == "debate":
        lines = []
        at: tuple[str, int, int] | None = None
        for ln in [*before, target]:
            here = (str(ln["phase"]), int(ln["round"]), int(ln["iteration"]))
            if here != at:
                lines.append({"author": "system", "kind": "system_note",
                              "content": f"ROUND {here[1]} · {here[0].upper()}"
                                         + (" · EXTENDED" if here[2] > 1 else "")})
                at = here
            if ln is not target:
                lines.append({"author": "character", "characterId": ln["speaker"], "kind": "chat",
                              "content": ln["text"], "debate": {"phase": here[0], "round": here[1],
                                                                "iteration": here[2], "side": ln["side"]}})
        state = {"phase": str(target["phase"]), "round": int(target["round"]),
                 "iteration": int(target["iteration"])}
        return Rebuilt(lines, None, None, state)
    lines = [{"author": "user", "kind": "direction", "content": ln["text"]} if ln["kind"] == "note"
             else {"author": "character", "characterId": ln["speaker"], "kind": "chat", "content": ln["text"]}
             for ln in before]
    taken = sum(ln["kind"] != "note" for ln in before)
    return Rebuilt(lines, None, None, {"status": "paused", "turnsTaken": taken, "turnLimit": taken + WATCH_MORE})


def session_body(t: dict[str, Any]) -> dict[str, Any]:
    """The create body the history was generated with (the debate's and the watch's script config)."""
    body: dict[str, Any] = {"worldId": t["world"], "mode": t["mode"], "characterIds": list(t["cast"]),
                            "title": f"conversations {t['id']}"}
    if t["mode"] == "group":
        body["config"] = {"responderPolicy": "auto", "maxAutoResponders": 2}
    elif t["mode"] == "debate":
        from horizon.evals.debate_suites import scripts

        body["config"] = dict(scripts(t["source"]["id"])[0]["config"])
    elif t["mode"] == "watch":
        body["config"] = {"premise": t["premise"], "maxTurns": 40, "paceMs": 1500, "openingSpeaker": "auto"}
    return body


async def open_rebuilt(rt: Any, t: dict[str, Any], rb: Rebuilt) -> str:
    """Writes the rebuilt session as `lifecycle.fork` writes a fork (one transaction), opens it, and returns its id."""
    from sqlalchemy import select

    from horizon.contract import mappers as mp
    from horizon.db import tables as tb
    from horizon.services.runtime.reducer import initial_runtime, ordered_messages
    from horizon.sessions.context import characters
    from horizon.sessions.lifecycle import _new_session

    async with rt.db.read() as conn:
        w = (await conn.execute(select(tb.worlds).where(tb.worlds.c.id == t["world"]))).mappings().first()
    rows = await characters(rt, list(t["cast"]))
    base = _new_session(rt, session_body(t), w, [rows[c] for c in t["cast"]])
    sid = str(base["id"])
    if rb.state is not None:
        base["state"] = rb.state
    multi = t["mode"] in MULTI
    if multi:
        base.update(status="paused", pausedReason="user")
    start = rt.clock.now() - timedelta(seconds=len(rb.lines) + 1)
    prefix = sid.replace("ses_", "msg_", 1)
    messages = []
    for i, ln in enumerate(rb.lines, 1):
        at = (start + timedelta(seconds=i)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        author: dict[str, Any] = {"type": ln["author"]}
        if ln["author"] == "character":
            author["characterId"] = ln["characterId"]
        m = {"id": f"{prefix}m{i}", "sessionId": sid, "seq": i, "author": author, "kind": ln["kind"],
             "content": ln["content"], "status": "complete", "createdAt": at}
        if "debate" in ln:
            m["debate"] = ln["debate"]
        messages.append(m)
    evt = sid.replace("ses_", "evt_", 1)
    events = [{"id": f"{evt}e{i}", "sessionId": sid, "seq": i, "at": m["createdAt"], "type": "message",
               "payload": {"message": m}} for i, m in enumerate(messages, 1)]
    final = initial_runtime({**base, "messageCount": len(messages)}, messages)
    session = final["session"]
    row, prows = mp.session_rows(session, is_seed=False)
    async with rt.db.write() as tx:
        await tx.conn.execute(tb.sessions.insert().values(**row))
        await tx.conn.execute(tb.participants.insert(), prows)
        if events:
            await tx.conn.execute(tb.session_events.insert(), [mp.event_row(e) for e in events])
            await tx.conn.execute(tb.messages.insert(), [mp.message_row(m) for m in ordered_messages(final)])
        if rb.summary is not None:
            await tx.conn.execute(tb.session_summaries.insert().values(
                session_id=sid, upto_seq=rb.summary[0], kind="rolling", text=rb.summary[1], created_at=rt.now_iso()))
    actor = await rt.sessions.get(sid)
    actor.held = multi
    if not multi:
        async def open_it() -> None:
            await actor.emit({"type": "session.state", "payload": {"status": "active"}})

        await actor.submit(open_it)
    return sid


# ── one unit, one profile ──
async def reply_for(env: RunEnv, t: dict[str, Any], u: dict[str, Any]) -> dict[str, Any]:
    """Rebuilds the unit's history in `env`'s copy, runs the live path once, and returns the first new character line
    with its speaker (or why there is none). The session is ended afterwards (one live session at a time)."""
    import httpx

    from horizon.evals.content import budget_code, wait_idle
    from horizon.evals.debate_suites import top_up
    from horizon.main import create_app

    rb = rebuild(t, int(u["unit"]))
    await top_up(env, list(t["cast"]))          # full energy, so no unit pauses for a tired cast (the eval copy only)
    sid = await open_rebuilt(env.rt, t, rb)
    await wait_idle(env, sid)
    app = create_app(env.rt.cfg, runtime=env.rt)
    out: dict[str, Any] = {"session": sid, "history": len(rb.lines)}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as c:
        if t["mode"] == "debate":
            r = await c.post(f"{API}/sessions/{sid}/debate/next", json={})
        elif t["mode"] == "watch":
            r = await c.post(f"{API}/sessions/{sid}/watch/step", json={})
        else:
            r = await c.post(f"{API}/sessions/{sid}/send", json={"text": rb.latest})
        if budget_code(r):   # the run's cap: the suite stops and reports incomplete (as `drive` does)
            from horizon.gateway.errors import ProviderError

            await c.post(f"{API}/sessions/{sid}/end", json={})
            raise ProviderError(str(budget_code(r)), status=r.status_code)
        if r.status_code >= 300:
            out["error"] = f"{r.status_code}: {r.text[:200]}"
        else:
            await wait_idle(env, sid)
            msgs = (await c.get(f"{API}/sessions/{sid}/messages", params={"limit": 1000})).json()["items"]
            new = [m for m in msgs if int(m["seq"]) > len(rb.lines) and m["author"]["type"] == "character"
                   and m.get("kind") == "chat"]
            if new:
                from horizon.evals.notfound_suite import passages_text

                trace = new[0].get("trace") or {}
                face = next((r for r in (trace.get("system1") or {}).get("questions") or []
                             if r.get("purpose") == "face_check"), None)
                retrieved = list((trace.get("knowledge") or {}).get("retrieved") or [])
                if env.rt.capture.enabled:   # naive's copy: the raw reply, for the note-in-tag rate (D14)
                    out["raw"] = await raw_reply(env.rt, str(new[0]["id"]))
                out.update(message_id=new[0]["id"], speaker=new[0]["author"]["characterId"],
                           text=new[0]["content"], status=new[0].get("status"), emotion=new[0].get("emotion"),
                           cited=bool(new[0].get("citations")), face_row=face.get("answer") if face else None,
                           passages=passages_text(retrieved) if retrieved else None,
                           deep=bool(retrieved) or (trace.get("graph") or {}).get("path") == "deep")
            else:
                out["error"] = "no reply"
        await c.post(f"{API}/sessions/{sid}/end", json={})
    return out


async def raw_reply(rt: Any, message_id: str) -> str | None:
    """The model's own reply text before the tag parser, from the copy's call capture (`ai_calls`)."""
    from sqlalchemy import select

    from horizon.db import tables as tb

    await rt.capture.flush()
    A = tb.ai_calls.c
    async with rt.db.read() as conn:
        rows = (await conn.execute(select(A.response).where(A.message_id == message_id, A.kind == "call")
                                   .order_by(A.created_at))).all()
    texts = [str(r[0]["text"]) for r in rows if isinstance(r[0], dict) and r[0].get("text")]
    return texts[-1] if texts else None


# ── both copies ──
async def other_copy(env: RunEnv) -> RunEnv:
    """The other profile's isolated copy beside the run's: the same store, key, manifest and cap."""
    from horizon.domain.clock import FrozenClock, calendar_for
    from horizon.evals.runner import SMOKE_START, isolated_config
    from horizon.runtime import Runtime

    other = next(p for p in PROFILES if p != env.opts.profile)
    opts = dataclasses.replace(env.opts, profile=other)
    run_dir = env.run_dir.parent / other
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "settings.local.json").write_text(json.dumps({"budget": {"dailyCapUsd": env.max_usd}}),
                                                 encoding="utf-8")
    cfg = isolated_config(env.rt.cfg, run_dir, opts, test_mode=env.rt.cfg.test_mode)
    test = env.rt.cfg.test_mode
    rt = Runtime(cfg, clock=FrozenClock(calendar_for(cfg.tz), SMOKE_START) if test else None)
    await rt.start()
    if test:
        rt.keys.set_key("sk-or-test-eval-0001")
    elif env.opts.probe:
        rt.keys.set_key("sk-or-probe-0000")
    rt.gateway.store = env.store
    rt.gateway.allowed_bodies = env.rt.gateway.allowed_bodies
    return RunEnv(rt=rt, opts=opts, store=env.store, run_dir=run_dir, max_usd=env.max_usd)


async def quiet(env: RunEnv) -> None:
    """No pause runs in a copy (B3: the memory list doesn't change inside a transcript, and nothing is written)."""
    await env.rt.memory_runs.stop()


BUDGET = ("daily_budget_exceeded", "creation_budget_exceeded", "energy_exhausted")


def whole(rows: Sequence[dict[str, Any]], planned: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """The rows of conversations that finished: a stopped run gives no figure for the one it was inside (B1 resamples
    whole conversations)."""
    want: dict[str, int] = {}
    for u in planned:
        want[u["transcript"]] = want.get(u["transcript"], 0) + 1
    got: dict[str, int] = {}
    for r in rows:
        got[r["transcript"]] = got.get(r["transcript"], 0) + 1
    return [r for r in rows if got[r["transcript"]] == want[r["transcript"]]]


def jsonl(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


# ── the judges (B4; D11, D12) ──
VOICE, FACT, ANSWERS, IN_STORY = "judge_voice", "judge_persona_fact", "judge_answers_last", "judge_in_story"
STAYS = (VOICE, FACT, ANSWERS, IN_STORY)             # stays in character: none of the four fails (combined in code)
SAMPLED = ("judge_assistant_voice", "judge_flattery")
LANGUAGE, PUSHBACK, OVER = "judge_language", "judge_pushback", "judge_over_mention"
SAYS, CITES = "judge_notfound_says", "judge_notfound_cites"
PAIRWISE = "judge_pairwise"
SAMPLE_EVERY = 4                                    # about 1 unit in 4: ~100 replies over both profiles
NO_RECENT = "(no earlier lines)"


def sampled(key: str) -> bool:
    import hashlib

    return int(hashlib.sha256(f"sample-{key}".encode()).hexdigest()[:8], 16) % SAMPLE_EVERY == 0


def recent(rb: Rebuilt, names: dict[str, str], n: int = 6) -> list[str]:
    """The history's last `n` lines as "Kai: …" / "Name: …" (banners left out)."""
    out = [f"{USER if ln['author'] == 'user' else names.get(ln.get('characterId', ''), '')}: {ln['content']}"
           for ln in rb.lines if ln["author"] != "system"]
    return out[-n:]


def last_line(rb: Rebuilt, names: dict[str, str]) -> str:
    """What the reply answers: the user's line (1:1, group), else the last line before it."""
    if rb.latest is not None:
        return rb.latest
    lines = recent(rb, names, 1)
    return lines[-1] if lines else NO_RECENT


async def ask(env: RunEnv, qid: str, state: dict[str, Any], unit: str, profile: str, path: Path) -> bool | None:
    """One noul judge, its state saved (pay once): whether it failed, or None when the answer didn't validate."""
    from horizon.evals.content import failed, judge

    p = await judge(env, qid, state)
    jsonl(path, {"unit": unit, "profile": profile, "question_id": qid, "state": state, "p": p})
    return failed(p, qid)


async def words_face(env: RunEnv, text: str, seed: str) -> str | None:
    """`naive`'s face check, asked here (W2): which face the reply's words show."""
    from horizon.ai.agent.face_check import QUESTION, tail
    from horizon.ai.decider import ChoiceAnswer, validate, wire_question
    from horizon.ai.questions import bank
    from horizon.gateway.context import call_ctx

    q = bank().question(QUESTION, seed=seed)
    r = await env.rt.gateway.decide({"quoted_reply": tail(text)}, {QUESTION: wire_question(q)}, call_ctx("eval_judge"))
    a = validate(q, r.answers.get(QUESTION))
    return a.choice if isinstance(a, ChoiceAnswer) else None


async def pairwise(env: RunEnv, state: dict[str, Any], name: str, unit: str, path: Path) -> dict[str, Any] | None:
    """p(agent better) over both orders (A is `agent`; the second order swaps the replies), M9 D29."""
    from horizon.ai.decider import ChoiceAnswer, validate, wire_question
    from horizon.ai.questions import bank
    from horizon.evals import judges
    from horizon.gateway.context import call_ctx

    q = bank().question(PAIRWISE, name=name)
    probs: list[dict[str, float] | None] = []
    for st in (state, judges.swapped(state)):
        r = await env.rt.gateway.decide(st, {PAIRWISE: wire_question(q)}, call_ctx("eval_judge"))
        a = validate(q, r.answers.get(PAIRWISE))
        probs.append(dict(a.probabilities or {a.choice: a.confidence or 0.0}) if isinstance(a, ChoiceAnswer) else None)
    jsonl(path, {"unit": unit, "profile": "both", "question_id": PAIRWISE, "state": state, "name": name,
                 "probabilities": probs})
    if probs[0] is None or probs[1] is None:
        return None
    return {"p": round(judges.prefers(probs[0], probs[1], "a"), 4), "orders": order_verdicts(probs[0], probs[1])}


def order_verdicts(first: dict[str, float], second: dict[str, float]) -> list[str]:
    """Each order's pick for `agent`: "win", "tie" or "loss" (the first asks agent as A; the second swaps them)."""
    def pick(probs: dict[str, float], agent: str) -> str:
        top = max(("a", "b", "same"), key=lambda k: probs.get(k, 0.0))
        return "tie" if top == "same" else "win" if top == agent else "loss"
    return [pick(first, "a"), pick(second, "b")]


async def judge_unit(env: RunEnv, t: dict[str, Any], u: dict[str, Any], replies: dict[str, dict[str, Any]],
                     path: Path) -> dict[str, Any]:
    """Every layer-3 judgement on one unit's two replies (the "Layer 3 judgements" requirement)."""
    from horizon.ai.agent.face_check import verdict
    from horizon.evals.content import persona_facts, persona_text
    from horizon.evals.debate_suites import profiles

    profs = profiles()
    names = {cid: str(p.get("name") or cid) for cid, p in profs.items()}
    rb = rebuild(t, int(u["unit"]))
    last, before = last_line(rb, names), recent(rb, names)
    out: dict[str, Any] = {}
    for p in PROFILES:
        r = replies[p]
        if "text" not in r:
            continue
        cid, text, key = r["speaker"], r["text"], u["key"]
        j: dict[str, Any] = {}
        j[VOICE] = await ask(env, VOICE, {"quoted_persona": persona_text(profs[cid]), "quoted_last": last,
                                          "quoted_reply": text}, key, p, path)
        j[FACT] = await ask(env, FACT, {"quoted_facts": persona_facts(profs[cid]), "quoted_reply": text}, key, p, path)
        if rb.latest is not None:
            j[ANSWERS] = await ask(env, ANSWERS, {"quoted_last": rb.latest, "quoted_reply": text}, key, p, path)
        j[IN_STORY] = await ask(env, IN_STORY, {"quoted_recent": "\n".join(before) or NO_RECENT,
                                                "quoted_message": last, "quoted_reply": text}, key, p, path)
        flags = [j[q] for q in STAYS if q in j]
        j["stays"] = None if any(f is None for f in flags) else not any(flags)
        if sampled(key):
            for qid in SAMPLED:
                j[qid] = await ask(env, qid, {"quoted_last": last, "quoted_reply": text}, key, p, path)
        if u.get("lang", "en") != "en" and rb.latest is not None:
            j[LANGUAGE] = await ask(env, LANGUAGE, {"quoted_last": rb.latest, "quoted_reply": text}, key, p, path)
        if u.get("kind") == "wrong_claim":
            j[PUSHBACK] = await ask(env, PUSHBACK, {"quoted_last": rb.latest, "quoted_reply": text}, key, p, path)
        mems = [m["text"] for m in t["memories"].get(cid) or []]
        if rb.latest is not None and u.get("kind") in ("filler", None) and mems:
            j[OVER] = await ask(env, OVER, {"quoted_memories": "\n".join(mems), "quoted_recent": "\n".join(before[-4:])
                                            or NO_RECENT, "quoted_message": rb.latest, "quoted_reply": text},
                                key, p, path)
        if u.get("kind") == "docs" and u.get("covered") is False:
            j[SAYS] = await ask(env, SAYS, {"quoted_message": rb.latest, "quoted_passages": r.get("passages")
                                            or "(none: no passage from the documents was kept for this message)",
                                            "quoted_reply": text}, key, p, path)
        if r.get("cited") and r.get("passages"):
            j[CITES] = await ask(env, CITES, {"quoted_message": last, "quoted_passages": r["passages"],
                                              "quoted_reply": text}, key, p, path)
        shown = str(r.get("emotion") or "neutral")
        if p == "agent":   # agent reads its own live face-check row (W2)
            j["face"] = r.get("face_row")
        elif shown != "neutral":
            pick = await words_face(env, text, f"conversations:{key}:{p}")
            j["face"] = None if pick is None else verdict(shown, pick)
        out[p] = j
    if all("text" in replies[p] for p in PROFILES):
        speakers = {replies[p]["speaker"] for p in PROFILES}
        same = len(speakers) == 1
        name = names[next(iter(speakers))] if same else "each reply's own speaker"
        a, b = (replies[p]["text"] if same else f"{names[replies[p]['speaker']]}: {replies[p]['text']}"
                for p in PROFILES)
        pw = await pairwise(env, {"quoted_recent": [*before[-4:], *(
            [f"{USER}: {rb.latest}"] if rb.latest is not None else [])], "quoted_reply_a": a, "quoted_reply_b": b},
            name, u["key"], path)
        out["p_agent_better"] = None if pw is None else pw["p"]
        out["orders"] = None if pw is None else pw["orders"]
        out["agent_longer"] = len(replies["agent"]["text"]) > len(replies["naive"]["text"])
    return out


# ── the free runs (B3; doc 07 G11, doc 08 V11; task 6.3) ──
MODES = ("one_on_one", "group", "watch", "debate")
FREE = {"agent": {"one_on_one": 1, "group": 3, "watch": 3, "debate": 2},     # one per mode, G11's 3 + 3, V11's 2
        "naive": {"one_on_one": 1, "group": 1, "watch": 1, "debate": 1}}
FREE_TURNS = {"one_on_one": 12, "group": 12, "watch": 30}


async def free_one_on_one(env: RunEnv, k: int, n: int) -> list[dict[str, Any]]:
    """A free 1:1: the group run's user lines, to the first character of the run's cast."""
    import httpx

    from horizon.evals.content import budget_code, wait_idle
    from horizon.evals.watch_suites import FREERUN_PREMISES, group_lines
    from horizon.main import create_app

    world, cast, _ = FREERUN_PREMISES[k % len(FREERUN_PREMISES)]
    app = create_app(env.rt.cfg, runtime=env.rt)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as c:
        r = await c.post(f"{API}/sessions", json={"worldId": world, "mode": "one_on_one", "characterIds": cast[:1]})
        if r.status_code != 201:
            return []
        sid = r.json()["session"]["id"]
        await wait_idle(env, sid)
        for line in group_lines(k, n):
            if await env.over_budget() or budget_code(await c.post(f"{API}/sessions/{sid}/send", json={"text": line})):
                break
            await wait_idle(env, sid)
        got: list[dict[str, Any]] = (await c.get(f"{API}/sessions/{sid}/messages", params={"limit": 1000})).json()["items"]
        await c.post(f"{API}/sessions/{sid}/end", json={})
    return got


def free_signals(mode: str, convs: Sequence[Sequence[dict[str, Any]]], spent: float) -> list[str]:
    """Cost per turn, the System 1 fallback and late rate (the free runs are new requests: uncached), and P8's
    repetition rates on free-running replies."""
    from horizon.evals.debate_suites import profiles
    from horizon.evals.reply_checks import Reply, check_replies

    profs = profiles()
    replies = [m for msgs in convs for m in msgs if m["author"]["type"] == "character" and m.get("kind") == "chat"]
    rows = [r for m in replies for r in (((m.get("trace") or {}).get("system1")) or {}).get("questions") or []]
    fell = sum(1 for r in rows if r.get("result") == "fallback")
    late = sum(1 for r in rows if "late" in str(r.get("answer")) or r.get("result") == "late")
    rep = {"repeated_opener": 0, "catchphrase": 0}
    n = 0

    def cid(m: dict[str, Any]) -> str:
        return str(m["author"].get("characterId"))

    for msgs in convs:
        mine = [m for m in msgs if m["author"]["type"] == "character" and m.get("kind") == "chat"]
        st = check_replies([Reply(speaker=cid(m), mode=mode, text=str(m["content"]), catchphrases=tuple(
            ((profs.get(cid(m)) or {}).get("speakingStyle") or {}).get("catchphrases") or ())) for m in mine],
            free_running=True)
        n += st.n
        for k in rep:
            rep[k] += st.counts.get(k, 0)
    out = [f"- {mode}: {len(convs)} run(s), {len(replies)} replies; cost per turn "
           + (f"${spent / len(replies):.5f}" if replies else "-")]
    out.append(f"  - System 1 rows: {len(rows)}; fallbacks {fell}, late {late}" if rows else "  - System 1 rows: none")
    if n:
        out.append(f"  - repeated opener {rep['repeated_opener']}/{n}, catchphrase {rep['catchphrase']}/{n}")
    return out


async def free_runs(env: RunEnv, limit: int | None) -> list[str]:
    from horizon.evals.debate_suites import debate_freeruns
    from horizon.evals.watch_suites import FreeRun, freerun_report

    who = env.opts.profile
    out = [f"## Free runs ({who}): one per mode" + (", G11's 3 + 3 and V11's 2" if who == "agent" else "")]
    for mode in MODES:
        runs = 1 if limit else FREE[who][mode]
        n = min(limit, FREE_TURNS.get(mode, 12)) if limit else FREE_TURNS.get(mode, 12)
        before = await env.spent()
        if mode == "debate":
            drs, lines = await debate_freeruns(env, runs)
            out += [f"- debate: {len(drs)} run(s), cost ${await env.spent() - before:.5f}", *lines]
            continue
        convs = []
        for k in range(runs):
            if await env.over_budget():
                break
            if mode == "one_on_one":
                convs.append(await free_one_on_one(env, k, n))
            elif mode == "group":
                convs.append((await FreeRun.group(env, {"mode": "group", "run": k, "n": n}))[0])
            else:
                convs.append((await FreeRun.watch(env, {"mode": "watch", "run": k, "n": n}))[0])
        out += free_signals(mode, convs, await env.spent() - before)
        if mode in ("group", "watch") and convs:
            out += freerun_report(mode, [m for c in convs for m in c], 0 if mode == "watch" else n * len(convs))[1:]
    return out


class Conversations:
    name = "conversations"

    def plan(self, opts: Options, prices: Any, *, paid: bool) -> Plan:
        from horizon.domain.pricing import estimate_chat
        from horizon.evals.runner import decision_estimate

        us = units(frozen.load_all(), opts)
        reply = estimate_chat(prices, prefix_tokens=6000, warm=True, other_in=800, expected_out_tokens=160,
                              period="off_peak")
        plan_call = decision_estimate(prices, {"quoted_recent": "x" * 4000}, {"q": {"instructions": "x" * 3000}})
        judge = decision_estimate(prices, {"quoted_reply": "x" * 800, "quoted_recent": "x" * 1200},
                                  {"q": {"instructions": "x" * 600}})
        per_unit = 2 * reply + 3 * plan_call + 9 * judge          # both replies, agent's plans and checks, the judges
        free = sum(n * (FREE_TURNS.get(mode, 12) if not opts.limit else min(opts.limit, FREE_TURNS.get(mode, 12)))
                   * (reply + 2 * plan_call) for counts in FREE.values() for mode, n in counts.items()) \
            if not opts.limit else len(PROFILES) * len(MODES) * opts.limit * (reply + 2 * plan_call)
        free += sum(FREE[p]["debate"] for p in PROFILES) * (12 * (reply + 3 * plan_call) + 0.004)
        return Plan(items=us, estimate_usd=len(us) * per_unit + free, expected_s=len(us) * 30.0 + 2400, paid=paid)

    async def run(self, env: RunEnv, plan: Plan) -> Result:
        res = Result()
        ts = {t["id"]: t for t in frozen.load_all()}
        env2 = await other_copy(env)
        envs = {env.opts.profile: env, env2.opts.profile: env2}
        try:
            from horizon.evals.debate_suites import install_cast

            for e in envs.values():
                await quiet(e)
                await install_cast(e)           # the debates' eval cast (D30.1), in the copies only
            envs["naive"].rt.capture.enabled = True   # the raw replies, for the note-in-tag rate (D14); this copy only
            from horizon.gateway.errors import ProviderError

            path, states = env.run_dir / "replies.jsonl", env.run_dir / "judge_states.jsonl"
            for u in plan.items:
                if await self.over(envs):
                    res.status = "incomplete"
                    res.summary.append("stopped between units: the run's cap")
                    break
                t = ts[u["transcript"]]
                try:
                    row = {**u, "replies": {p: await reply_for(envs[p], t, u) for p in PROFILES}}
                    row["judged"] = await judge_unit(env, t, u, row["replies"], states)
                except ProviderError as e:   # the cap inside a unit: what was saved stays, the unit isn't counted
                    if e.code not in BUDGET:
                        raise
                    res.status = "incomplete"
                    res.summary.append(f"stopped inside {u['key']}: {e.code}")
                    break
                jsonl(path, row)          # one whole line per finished unit
                res.rows.append(row)
            res.summary += self.report(whole(res.rows, plan.items), len(plan.items))
            if res.status != "incomplete":   # B3's free runs, both profiles (task 6.3)
                for p in PROFILES:
                    res.summary += await free_runs(envs[p], env.opts.limit)
        finally:
            await env2.rt.stop()
        return res

    @staticmethod
    async def over(envs: dict[str, RunEnv]) -> bool:
        spent = sum([await e.spent() for e in envs.values()])
        return spent >= next(iter(envs.values())).max_usd

    @staticmethod
    def report(rows: Sequence[dict[str, Any]], planned: int) -> list[str]:
        by_mode: dict[str, int] = {}
        for r in rows:
            by_mode[r["mode"]] = by_mode.get(r["mode"], 0) + 1
        both = sum(all("text" in r["replies"][p] for p in PROFILES) for r in rows)
        return [f"## Conversations: {len(rows)} of {planned} unit(s) in finished conversations, both replies on {both}",
                "- by mode: " + ", ".join(f"{m} {n}" for m, n in sorted(by_mode.items())),
                note_line([r["replies"]["naive"].get("raw") for r in rows]), "", *judged_report(rows)]


def note_line(raws: Sequence[str | None]) -> str:
    """D14's free check: `naive` replies whose raw text holds a note inside the tag or a stray tag (M11: 14 of 154)."""
    from horizon.evals.metrics import wilson
    from horizon.evals.reply_checks import note_in_tag

    xs = [note_in_tag(r) for r in raws if r is not None]
    if not xs:
        return "- naive note-in-tag: no raw replies"
    lo, hi = wilson(sum(xs), len(xs))
    return f"- naive note-in-tag: {sum(xs)}/{len(xs)} (95% {lo:.2f}–{hi:.2f}; M11 had 14 of 154 on naive-6)"


def stays_of(judged: dict[str, Any], leave_out: Sequence[str]) -> bool | None:
    """Stays in character over the STAYS judges that are validated (`leave_out` are not): None if one has no answer."""
    flags = [judged.get(q) for q in STAYS if q not in leave_out and q in judged]
    return None if not flags or any(f is None for f in flags) else not any(flags)


def counted(qid: str) -> str:
    """B4: a judge whose current version hasn't passed reads NOT COUNTED (its saved states re-score later)."""
    from horizon.ai.questions import bank
    from horizon.evals import judges

    return "" if judges.validated(qid, bank().get(qid).version) else " **NOT COUNTED** (not validated, B4)"


def judged_report(rows: Sequence[dict[str, Any]]) -> list[str]:
    """Per profile: each judge's failures (English first, then the rest as direction), and stays in character."""
    from horizon.evals.metrics import wilson

    out = ["### The judges per reply (failures; test split, English first)"]
    qids = [*STAYS, "stays", "stays_validated", *SAMPLED, LANGUAGE, PUSHBACK, OVER, SAYS, CITES, "face"]
    uncounted = [q for q in STAYS if counted(q)]
    for part, english in (("English", True), ("other languages (direction only)", False)):
        test = [r for r in rows if r["split"] == "test" and (r.get("lang", "en") == "en") == english]
        if not test:
            continue
        out.append(f"#### {part}: {len(test)} test unit(s)")
        for qid in qids:
            cells = []
            for p in PROFILES:
                vals = [stays_of(r["judged"].get(p, {}), uncounted) if qid == "stays_validated"
                        else r["judged"].get(p, {}).get(qid) for r in test]
                if qid == "face":
                    flags = [v != "yes" for v in vals if v is not None]
                elif qid in ("stays", "stays_validated"):
                    flags = [not v for v in vals if v is not None]
                else:
                    flags = [bool(v) for v in vals if v is not None]
                if flags:
                    lo, hi = wilson(sum(flags), len(flags))
                    cells.append(f"{p} {sum(flags)}/{len(flags)} (95% {lo:.2f}–{hi:.2f})")
            if qid == "stays_validated" and not uncounted:
                continue   # the same as `stays`
            if cells:
                tag = counted(qid) if qid.startswith("judge_") else ""
                if qid == "stays" and uncounted:   # 8.5: a composite is only as validated as its parts
                    tag = f" **NOT COUNTED** ({', '.join(uncounted)} not validated, B4)"
                name = f"stays (without {', '.join(uncounted)})" if qid == "stays_validated" else qid
                out.append(f"- {name}: " + "; ".join(cells) + tag)
    for part, english in (("English", True), ("other languages (direction only)", False)):
        test = [r for r in rows if r["split"] == "test" and (r.get("lang", "en") == "en") == english]
        if test:
            out += [f"### agent vs naive, {part} (test){counted(PAIRWISE)}", *pairwise_lines(test)]
    return out


# ── layer 3's statistics (B1; task 6.2) ──
N_BOOT, SEED = 2000, 15


def outcome(orders: Sequence[str] | None) -> str | None:
    """A unit's result: the two orders' shared pick, "disagree" when they differ, None without an answer."""
    if not orders:
        return None
    return orders[0] if orders[0] == orders[1] else "disagree"


def pairwise_stats(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """B1: the mean p(agent better) with a paired bootstrap over whole conversations; win/tie/loss counted only where
    both orders agree, with the exact sign test; the order-disagreement rate; the win rate by which reply was longer."""
    from horizon.evals.metrics import bootstrap_mean, mcnemar_exact, wilson

    scored = [r for r in rows if r["judged"].get("p_agent_better") is not None]
    groups: dict[str, list[float]] = {}
    for r in scored:
        groups.setdefault(r["transcript"], []).append(float(r["judged"]["p_agent_better"]))
    vals = [v for g in groups.values() for v in g]
    out: dict[str, Any] = {"n": len(vals), "conversations": len(groups)}
    if not vals:
        return out
    out["mean"] = sum(vals) / len(vals)
    out["ci"] = bootstrap_mean(list(groups.values()), n_boot=N_BOOT, seed=SEED)
    res = [outcome(r["judged"].get("orders")) for r in scored]
    w, t, lo = res.count("win"), res.count("tie"), res.count("loss")
    out.update(win=w, tie=t, loss=lo, disagree=res.count("disagree"), sign_p=mcnemar_exact(w, lo))
    out["disagree_ci"] = wilson(out["disagree"], len(res))
    for longer, tag in ((True, "longer"), (False, "shorter")):
        mine = [r for r in scored if r["judged"].get("agent_longer") is longer]
        wins = sum(outcome(r["judged"].get("orders")) == "win" for r in mine)
        out[f"win_when_agent_{tag}"] = (wins, len(mine))
    return out


def pairwise_lines(rows: Sequence[dict[str, Any]]) -> list[str]:
    st = pairwise_stats(rows)
    if not st.get("n"):
        return ["- no pairwise answers"]
    lo, hi = st["ci"]
    dlo, dhi = st["disagree_ci"]
    out = [f"- mean p(agent better): {st['mean']:.3f} (95% paired bootstrap over {st['conversations']} conversations "
           f"{lo:.3f}–{hi:.3f}; baseline 0.5), n {st['n']}",
           f"- where both orders agree: agent wins {st['win']}, ties {st['tie']}, loses {st['loss']} (exact sign test "
           f"p {st['sign_p']:.3f})",
           f"- the orders disagree on {st['disagree']}/{st['n']} (95% {dlo:.2f}–{dhi:.2f})"]
    for tag in ("longer", "shorter"):
        wins, n = st[f"win_when_agent_{tag}"]
        out.append(f"- agent's reply {tag}: wins {wins}/{n}")
    return out

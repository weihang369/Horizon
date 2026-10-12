"""`horizon eval moodline`: the mood line on vs off, once (docs/ai/06 E8; turn-plan-emotion design D30; evaluation-harness
"The mood-line run").

- **Items:** evenly spaced user turns of the three English frozen transcripts (Amara 1:1, the Meridian and Sunny Hollow
  groups; the Malay one is left out, English first). For each, the stored history is rebuilt (the transcript's rolling
  summary, and the lines after its `summary_upto`), Jev call 1 runs for the turn's first speaker as live, and the turn
  is kept only when the face is a non-neutral `classifier` pick, until `--limit` (default 100) items.
- **The arms:** one `agent-2` reply request each, with the mood line (ON) and without it (OFF). OFF is the same context
  with the planned face marked MANUAL, so the two requests differ only in that line (spec "Same history in both
  arms"). Each arm is one call, so the store replays it exactly.
- **The checks per reply:** "names the feeling?", the `face_check` entry (exact match with the item's face, and
  clash), and the pairwise judge ON vs OFF in both orders.
- **The statistics:** blocks of 10 consecutive items within one transcript (3 conversations can't give an interval),
  2,000 seeded resamples: the exact-match difference ON − OFF and the mean p(ON better), each with a 95 % interval;
  the ON arm's "names the feeling" pass rate (target ≥ 95 %, every failure listed) and the clash rate (≤ 5 %).
- **The verdict** is E8's rule, as advice: the report changes no prompt or setting (spec "Verdict is advice").
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from horizon.ai.agent.face_check import QUESTION as FACE_CHECK
from horizon.ai.agent.face_check import tail
from horizon.ai.agent.face_check import verdict as face_verdict
from horizon.ai.agent.planner import JevTurnPlanner
from horizon.ai.agent.turn import AgentTurnEngine
from horizon.ai.contexts import (
    CharacterView,
    MessageView,
    ParticipantView,
    PlanRequest,
    SessionContext,
    TurnContext,
    TurnPlan,
    WorldView,
)
from horizon.ai.decider import ChoiceAnswer, validate, wire_question
from horizon.ai.ports import Token
from horizon.ai.questions import bank
from horizon.domain.pricing import estimate_chat
from horizon.evals import judges
from horizon.evals.content import TRANSCRIPTS, failed, judge, judge_estimate, take
from horizon.evals.metrics import bootstrap_mean
from horizon.evals.runner import Options, Plan, Result, RunEnv, decision_estimate
from horizon.gateway.context import call_ctx

FILES = ("long_one_on_one_en", "long_group_meridian", "long_group_sunnyhollow")
BLOCK = 10
N_BOOT = 2000
SEED = 9
DEFAULT_N = 100
NAMES_FEELING = judges.NAMES_FEELING
PAIRWISE = judges.PAIRWISE
USER = "Kai"


# ── the items ──
def load(name: str, root: Path = TRANSCRIPTS) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((root / f"{name}.json").read_text(encoding="utf-8"))
    return data


def candidates(per_file: int, root: Path = TRANSCRIPTS) -> list[dict[str, Any]]:
    """Evenly spaced user turns, transcript by transcript (the block order is the transcripts' order)."""
    out = []
    for name in FILES:
        turns = load(name, root)["turns"]
        usable = [i for i, t in enumerate(turns) if i > 0 and t["replies"]]
        step = max(1, len(usable) // max(1, per_file))
        for i in usable[::step][:per_file]:
            out.append({"transcript": name, "turn": i, "speaker": turns[i]["replies"][0]["speaker"]})
    return out


def history(t: dict[str, Any], i: int, names: dict[str, str]) -> tuple[list[MessageView], str | None]:
    """The stored history before turn `i`: the turn's summary and the lines after its `summary_upto`, numbered from 1
    in order (user line, then its replies), with `seq` as the transcript run stored them."""
    msgs: list[MessageView] = []
    seq = 0
    for turn in t["turns"][:i]:
        seq += 1
        msgs.append(MessageView(id=f"m{seq}", seq=seq, author_type="user", name=USER, kind="chat", content=turn["user"]))
        for r in turn["replies"]:
            seq += 1
            msgs.append(MessageView(id=f"m{seq}", seq=seq, author_type="character", character_id=r["speaker"],
                                    name=names.get(r["speaker"], r["speaker"]), kind="chat", content=r["text"]))
    cur = t["turns"][i]
    upto, summary = cur.get("summary_upto"), cur.get("summary")
    if summary and upto is not None:
        msgs = [m for m in msgs if m.seq > int(upto)]
    return msgs[-40:], summary or None


def last_two_turns(msgs: Sequence[MessageView], latest: str) -> list[str]:
    """The pairwise judge's `quoted_recent`: the turn before, then the latest user line."""
    users = [k for k, m in enumerate(msgs) if m.author_type == "user"]
    start = users[-1] if users else len(msgs)
    return [f"{m.name.split()[0] if m.author_type == 'character' else USER}: {m.content}" for m in msgs[start:]] \
        + [f"{USER}: {latest}"]


# ── the statistics ──
def blocks(rows: Sequence[dict[str, Any]], key: str) -> list[list[float]]:
    """Blocks of `BLOCK` consecutive items within one transcript (D30)."""
    out: list[list[float]] = []
    for name in FILES:
        vals = [float(r[key]) for r in rows if r["transcript"] == name and r.get(key) is not None]
        out += [vals[k:k + BLOCK] for k in range(0, len(vals), BLOCK)]
    return [b for b in out if b]


def interval(rows: Sequence[dict[str, Any]], key: str) -> tuple[float, float, float] | None:
    bs = blocks(rows, key)
    if not bs:
        return None
    vals = [v for b in bs for v in b]
    lo, hi = bootstrap_mean(bs, n_boot=N_BOOT, seed=SEED)
    return sum(vals) / len(vals), lo, hi


def verdict(exact: tuple[float, float, float] | None, pair: tuple[float, float, float] | None) -> str:
    """E8's rule, decided in advance. Advice only: nothing is changed by the run."""
    if exact is None or pair is None:
        return "no verdict: too few items"
    rises = exact[1] > 0
    not_worse = pair[2] >= 0.5
    if rises and not_worse:
        return "keep the mood line (exact match rises and the replies are not judged worse)"
    if rises:
        return "reword the line once and re-run (exact match rises but the replies are judged worse)"
    return ("propose dropping the mood line to the user (exact match does not rise); nothing was changed: a drop or "
            "a rewording comes to the user first")


# ── the suite ──
async def holder_session(rt: Any, t: dict[str, Any], rows: dict[str, Any], w: Any) -> str:
    """A session row for the run's ledger (its calls name a session): written with `create`'s own helpers but never
    opened, so no actor, greeting or turn runs and the one-live-session rule is untouched."""
    from horizon.contract import mappers as mp
    from horizon.db import tables as tb
    from horizon.sessions.lifecycle import _new_session

    body = {"worldId": t["world"], "mode": t["mode"], "characterIds": list(t["cast"]), "title": f"moodline {t['id']}"}
    if t["mode"] == "group":
        body["config"] = {"responderPolicy": "auto", "maxAutoResponders": 2}
    session = _new_session(rt, body, w, [rows[c] for c in t["cast"]])
    srow, prows = mp.session_rows(session, is_seed=False)
    async with rt.db.write() as tx:
        await tx.conn.execute(tb.sessions.insert().values(**srow))
        await tx.conn.execute(tb.participants.insert(), prows)
    return str(session["id"])


class Moodline:
    name = "moodline"

    def __init__(self) -> None:
        self._holders: dict[tuple[int, str], str] = {}

    def plan(self, opts: Options, prices: Any, *, paid: bool) -> Plan:
        n = opts.limit or DEFAULT_N
        cands = take(candidates(per_file=max(4, (n * 3) // len(FILES))), Options(suite=self.name, start=opts.start))
        reply = estimate_chat(prices, prefix_tokens=4000, warm=True, other_in=600, expected_out_tokens=140,
                              period="off_peak")
        call1 = decision_estimate(prices, {"quoted_latest": "x" * 3000}, {"q": {"instructions": "x" * 1200}})
        per_kept = 2 * reply + 2 * judge_estimate(prices, NAMES_FEELING, {"quoted_reply": "x" * 600}) \
            + 2 * decision_estimate(prices, {"quoted_reply": "x" * 600},
                                    {FACE_CHECK: wire_question(bank().question(FACE_CHECK, seed="estimate"))}) \
            + 2 * decision_estimate(prices, {"quoted_reply_a": "x" * 600, "quoted_reply_b": "x" * 600},
                                    {"q": {"instructions": "x" * 600}})
        return Plan(items=cands, estimate_usd=len(cands) * call1 + n * per_kept, expected_s=n * 12.0, paid=paid)

    async def run(self, env: RunEnv, plan: Plan) -> Result:
        res = Result()
        n = env.opts.limit or DEFAULT_N
        deps = env.rt.ai.deps
        planner, engine = JevTurnPlanner(deps), AgentTurnEngine(deps)
        rows: list[dict[str, Any]] = []
        for c in plan.items:
            if len(rows) >= n:
                break
            if await env.over_budget():
                res.status = "incomplete"
                break
            item = await self.one(env, planner, engine, c)
            if item is not None:
                rows.append(item)
                res.rows.append(item)
        res.summary += self.report(rows, n)
        return res

    async def context(self, env: RunEnv, c: dict[str, Any]) -> tuple[SessionContext, CharacterView, str, list[str]]:
        from horizon.sessions.context import character_view, characters

        t = load(c["transcript"])
        rows = await characters(env.rt, list(t["cast"]))
        names = {cid: str(r["profile"].get("name", cid)) for cid, r in rows.items()}
        async with env.rt.db.read() as conn:
            from sqlalchemy import select

            from horizon.db import tables as tb

            w = (await conn.execute(select(tb.worlds).where(tb.worlds.c.id == t["world"]))).mappings().first()
        key = (id(env.rt), c["transcript"])
        if key not in self._holders:
            self._holders[key] = await holder_session(env.rt, t, rows, w)
        recent, summary = history(t, c["turn"], names)
        latest = str(t["turns"][c["turn"]]["user"])
        parts = [ParticipantView(character_id=cid, name=names.get(cid, cid), role="speaker",
                                 character_role=str(rows[cid]["profile"].get("role") or "") if cid in rows else "",
                                 energy={"current": 1000, "max": 1000}) for cid in t["cast"]]
        sctx = SessionContext(session_id=self._holders[key], seed=f"moodline:{c['transcript']}",
                              world=WorldView(id=t["world"], name=str(w["name"]) if w else "",
                                              you=w["you"] if w else None),
                              mode=t["mode"], title="moodline", participants=parts,
                              recent=[*recent, MessageView(id="m_latest", seq=(recent[-1].seq + 1) if recent else 1,
                                                           author_type="user", name=USER, kind="chat",
                                                           content=latest)],
                              summary=summary)
        return sctx, character_view(rows[c["speaker"]]), latest, last_two_turns(recent, latest)

    def arms(self, ctx: TurnContext) -> tuple[TurnContext, TurnContext]:
        """ON, and OFF: the same context with the planned face marked MANUAL, which only removes the mood line."""
        assert ctx.plan is not None and ctx.plan.emotion is not None
        off_face = ctx.plan.emotion.model_copy(update={"manual": True})
        off = ctx.model_copy(update={"plan": ctx.plan.model_copy(update={"emotion": off_face})})
        return ctx, off

    async def one(self, env: RunEnv, planner: JevTurnPlanner, engine: AgentTurnEngine,
                  c: dict[str, Any]) -> dict[str, Any] | None:
        sctx, speaker, latest, recent2 = await self.context(env, c)
        req = PlanRequest(session=sctx, speaker_id=speaker.id, cast=[speaker], latest=latest, turn_index=c["turn"],
                          base_face="neutral", started_at=env.rt.clock.now())
        plan: TurnPlan | None = await planner.plan(req)
        face = plan.emotion if plan is not None else None
        if face is None or face.source != "classifier" or face.face == "neutral":
            return None
        from horizon.sessions.context import reply_cap

        ctx = TurnContext(session=sctx, speaker=speaker, message_id=None, prompt=latest, turn_index=c["turn"],
                          max_tokens=reply_cap(env.rt, sctx, plan), plan=plan)
        on, off = self.arms(ctx)
        replies = [await self.reply(engine, x) for x in (on, off)]
        out: dict[str, Any] = {**c, "face": face.face, "reply_on": replies[0], "reply_off": replies[1]}
        for arm, text in zip(("on", "off"), replies, strict=True):
            p = await judge(env, NAMES_FEELING, {"quoted_reply": text})
            out[f"names_{arm}"] = failed(p, NAMES_FEELING)
            pick = await self.words(env, text, f"{c['transcript']}:{c['turn']}:{arm}")
            out[f"pick_{arm}"] = pick
            out[f"exact_{arm}"] = None if pick is None else int(pick == face.face)
            out[f"clash_{arm}"] = None if pick is None else int(face_verdict(face.face, pick) == "clash")
        if out["exact_on"] is not None and out["exact_off"] is not None:
            out["exact_diff"] = out["exact_on"] - out["exact_off"]
        out["p_on_better"] = await self.pairwise(env, speaker.name, recent2, replies[0], replies[1])
        return out

    async def reply(self, engine: AgentTurnEngine, ctx: TurnContext) -> str:
        return "".join([ev.delta async for ev in engine.run(ctx) if isinstance(ev, Token)])

    async def words(self, env: RunEnv, text: str, seed: str) -> str | None:
        q = bank().question(FACE_CHECK, seed=seed)
        r = await env.rt.gateway.decide({"quoted_reply": tail(text)}, {FACE_CHECK: wire_question(q)},
                                        call_ctx("eval_judge"))
        a = validate(q, r.answers.get(FACE_CHECK))
        return a.choice if isinstance(a, ChoiceAnswer) else None

    async def pairwise(self, env: RunEnv, name: str, recent: list[str], on: str, off: str) -> float | None:
        q = bank().question(PAIRWISE, name=name)
        state = {"quoted_recent": recent, "quoted_reply_a": on, "quoted_reply_b": off}
        probs = []
        for st in (state, judges.swapped(state)):
            r = await env.rt.gateway.decide(st, {PAIRWISE: wire_question(q)}, call_ctx("eval_judge"))
            a = validate(q, r.answers.get(PAIRWISE))
            if not isinstance(a, ChoiceAnswer):
                return None
            probs.append(dict(a.probabilities or {a.choice: a.confidence or 0.0}))
        return round(judges.prefers(probs[0], probs[1], "a"), 4)

    @staticmethod
    def report(rows: list[dict[str, Any]], n: int) -> list[str]:
        out = [f"## Mood line on vs off: {len(rows)} non-neutral turns (asked for {n})"]
        if not rows:
            return [*out, "- no items: Jev call 1 picked no non-neutral face"]
        exact = interval(rows, "exact_diff")
        pair = interval(rows, "p_on_better")
        if exact is not None:
            out.append(f"- exact match ON − OFF: {exact[0]:+.2f} (95% block bootstrap {exact[1]:+.2f} to "
                       f"{exact[2]:+.2f})")
        if pair is not None:
            out.append(f"- pairwise p(ON better): {pair[0]:.2f} (95% {pair[1]:.2f}–{pair[2]:.2f})"
                       f"{judges.label(PAIRWISE, bank().get(PAIRWISE).version)}")
        on = [r["names_on"] for r in rows if r.get("names_on") is not None]
        if on:
            ok = sum(1 for x in on if not x)
            out.append(f"- ON names the feeling: {ok}/{len(on)} pass ({ok / len(on):.0%}, target ≥ 95%)"
                       f"{judges.label(NAMES_FEELING, bank().get(NAMES_FEELING).version)}")
            out += [f"  - failed: {r['transcript']}#{r['turn']} ({r['face']}): {r['reply_on'][:160]!r}"
                    for r in rows if r.get("names_on")]
        cl = [r["clash_on"] for r in rows if r.get("clash_on") is not None]
        if cl:
            out.append(f"- ON clash rate: {sum(cl)}/{len(cl)} ({sum(cl) / len(cl):.0%}, target ≤ 5%)")
        out.append(f"- verdict (advice; nothing was changed): {verdict(exact, pair)}")
        return out

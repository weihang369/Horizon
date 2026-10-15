"""`horizon eval retrieval` (rag design D22–D24; evaluation-harness "The retrieval suite", "The retrieval comparisons").

`--profile agent` only (it runs the agent deep path). `--set dev|test` runs one split. `--arm` runs one comparison arm,
retrieval order only (no Jev call), each in its own run database (D23):
- `space=<id>`: one of `ARM_SPACES` (the 2,048 space, bge-m3, the old instruction, no header), built before the run;
- `piece=200|300|400`: the corpus chunked to that target (ceiling `max(400, target)`); with `--set dev` and
  `piece=…:kept`, the full deep path runs too, for kept-set precision (the one arm that asks Jev);
- `lambda=0.5|0.7|1.0`: MMR's weight;
- `rewrite=off`: no rewrite (the default arm rewrites the follow-ups and non-English questions by their labels).

The main run (no arm) asks "standalone?" and "English?" as live, runs Jev call 2 and the keep rule, and reports
everything `retrieval.report` lists.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from sqlalchemy import select, text

from horizon.ai.agent import gates
from horizon.ai.agent.deep import DeepSteps, run_deep
from horizon.ai.agent.plan_state import Candidate, PlanStateInput, build_turn_plan_state
from horizon.ai.contexts import (
    DeepRequest,
    GateAnswer,
    MessageNouls,
    MessageView,
    ParticipantView,
    SessionContext,
    WorldView,
)
from horizon.ai.decider import NoulAnswer
from horizon.db import tables as t
from horizon.db.spaces import DEFAULT_SPACE, HEADER_TEMPLATE, SpaceSpec
from horizon.evals import retrieval as R
from horizon.evals.runner import Options, Plan, Result, RunEnv, decision_estimate
from horizon.gateway.context import call_ctx

USER = "Kai"
ARM_SPACES: dict[str, SpaceSpec] = {
    "qwen3-emb-8b@2048+h": SpaceSpec(id="qwen3-emb-8b@2048+h", model="qwen/qwen3-embedding-8b", provider="Nebius",
                                     dims=2048, query_instruction=DEFAULT_SPACE.query_instruction,
                                     doc_template=HEADER_TEMPLATE),
    "bge-m3@1024+h": SpaceSpec(id="bge-m3@1024+h", model="baai/bge-m3", provider="DeepInfra", dims=1024,
                               query_instruction=None, doc_template=HEADER_TEMPLATE),
    "qwen3-emb-8b@1024+h-oldq": SpaceSpec(id="qwen3-emb-8b@1024+h-oldq", model="qwen/qwen3-embedding-8b",
                                          provider="Nebius", dims=1024,
                                          query_instruction="Given a question, retrieve passages that answer it",
                                          doc_template=HEADER_TEMPLATE),
    "qwen3-emb-8b@1024-noheader": SpaceSpec(id="qwen3-emb-8b@1024-noheader", model="qwen/qwen3-embedding-8b",
                                            provider="Nebius", dims=1024,
                                            query_instruction=DEFAULT_SPACE.query_instruction, doc_template=None),
}


def parse_arm(arm: str | None) -> dict[str, str]:
    if not arm:
        return {}
    key, _, value = arm.partition("=")
    if key not in ("space", "piece", "lambda", "rewrite") or not value:
        raise ValueError(f"unknown arm {arm!r}")
    return {key: value}


class Retrieval:
    name = "retrieval"

    def refuse(self, opts: Options) -> str | None:
        if opts.profile != "agent":
            return "horizon: `retrieval` runs the agent deep path; pass --profile agent"
        try:
            arm = parse_arm(opts.arm)
        except ValueError as e:
            return f"horizon: {e}"
        if arm.get("space") and arm["space"] not in ARM_SPACES and arm["space"] != DEFAULT_SPACE.id:
            return f"horizon: unknown arm space {arm['space']!r} (have: {', '.join(ARM_SPACES)})"
        return None

    def _items(self, opts: Options) -> list[dict[str, Any]]:
        items = [q for q in R.load_questions() if not opts.set or q["split"] == opts.set][opts.start:]
        return items[: opts.limit] if opts.limit else items

    def plan(self, opts: Options, prices: Any, *, paid: bool) -> Plan:
        items = self._items(opts)
        arm = parse_arm(opts.arm)
        full = not arm or arm.get("piece", "").endswith(":kept")
        per = 0.0
        if full:   # two nouls, about 8 checks and a set check, at a passage-sized state
            st = {"mode": "one_on_one", "quoted_query": {"message": "x" * 200}, "quoted_passage": {"text": "x" * 1200}}
            per = 10 * decision_estimate(prices, st, {"q": {"type": "score", "criteria": ["a", "b", "c"]}})
        rewrites = sum(1 for q in items if q["kind"] in ("followup", "non_english"))
        corpus = 62_000 * prices.embedding.input_per_m / 1e6
        est = per * len(items) + rewrites * 0.00005 + corpus
        return Plan(items=items, estimate_usd=est, expected_s=30 + len(items) * (3.0 if full else 0.5), paid=paid)

    # ── the run ──
    async def run(self, env: RunEnv, plan: Plan) -> Result:
        arm = parse_arm(env.opts.arm)
        docs = await prepare(env, arm)
        planner = env.rt.ai.planner(True)
        steps = DeepSteps(planner.deps)
        full = not arm or arm.get("piece", "").endswith(":kept")
        res = Result()
        rows: list[R.Row] = []
        for q in plan.items:
            if await env.over_budget():
                res.status = "incomplete"
                break
            req = await deep_request(env, q, arm, ask=full)
            if full:
                out = await run_deep(planner.deep_graph, req)
                pool, cands, kept = out.pool, [r["chunkId"] for r in out.retrieved], [h.chunk_id for h in out.kept]
                outcome: str = out.outcome
                checks, set_check = out.checks, out.set_check
                bundle = out.query
            else:
                bundle_q, _rw = await steps.gather(req)
                result, hits = await steps.search(req, bundle_q)
                ids = await steps.pool_ids(req, result)
                pool = [ids[c.rid] for c in result.pool if c.rid in ids]
                cands = [hits[c.rid].chunk_id for c in result.candidates if c.rid in hits]
                kept, outcome, checks, set_check = [], "n/a", [], None
                bundle = bundle_q.to_json()
            pieces = await pieces_of(env, [*pool, *cands, *kept], docs)
            row = R.Row(id=q["id"], split=q["split"], kind=q["kind"], origin=q.get("origin", "corpus"),
                        needs_two=bool(q.get("needs_two")), spans=list(q["spans"]),
                        pool=[pieces[c] for c in pool if c in pieces], candidates=[pieces[c] for c in cands if c in pieces],
                        kept=[pieces[c] for c in kept if c in pieces], outcome=outcome, checks=list(checks),
                        set_check=set_check, dense_missing=not bundle.get("dense"), rewrite=bundle.get("rewrite"))
            rows.append(row)
            res.rows.append({"id": row.id, "split": row.split, "kind": row.kind, "origin": row.origin,
                             "outcome": outcome, "pool": pool, "candidates": cands, "kept": kept, "checks": checks,
                             "set_check": set_check, "query": bundle.get("display"), "rewrite": bundle.get("rewrite"),
                             "source": bundle.get("source"), "dense_missing": row.dense_missing,
                             "recall20": R.recall_at(row.pool, row.spans, 20),
                             "recall8": R.recall_at(row.candidates, row.spans, 8),
                             "ndcg8": R.ndcg_at(row.candidates, row.spans),
                             "mrr": R.reciprocal_rank(row.candidates, row.spans),
                             "recall_1200": R.recall_within(row.candidates, row.spans),
                             "kept_precision": R.kept_precision(row.kept, row.spans) if full and row.spans else None,
                             "arm": env.opts.arm})
        res.summary += ([f"- arm: `{env.opts.arm}`"] if env.opts.arm else []) + R.report(rows)
        return res


async def prepare(env: RunEnv, arm: dict[str, str]) -> dict[str, str]:
    """The run's database: the arm's piece size and space, the corpus as the characters' sources, the seed sources
    indexed. Returns each corpus source's title → its corpus path."""
    from horizon.services.knowledge.build import build_space
    from horizon.services.knowledge.sources import create_source, reindex_source

    rt = env.rt
    if arm.get("piece"):
        target = int(arm["piece"].split(":")[0])
        rt.piece_size = (target, max(400, target))
    if arm.get("lambda"):
        knobs = rt.runtime_cfg.runtime.retrieval
        assert knobs.agent is not None
        agent = dataclasses.replace(knobs.agent, mmr_lambda=float(arm["lambda"]))
        rt.runtime_cfg = dataclasses.replace(rt.runtime_cfg, runtime=dataclasses.replace(
            rt.runtime_cfg.runtime, retrieval=dataclasses.replace(knobs, agent=agent)))
    if arm.get("space") and arm["space"] in ARM_SPACES:
        await build_space(rt, ARM_SPACES[arm["space"]])
    docs: dict[str, str] = {}
    for folder, cid in R.CHARACTERS.items():
        for path in sorted((R.CORPUS / folder).glob("*.md")):
            await create_source(rt, cid, kind="md", title=path.name, type_="file", original_name=path.name,
                                data=path.read_bytes())
            docs[path.name] = f"{folder}/{path.name}"
    async with rt.db.read() as conn:
        queued = [str(r[0]) for r in (await conn.execute(select(t.knowledge_sources.c.id).where(
            t.knowledge_sources.c.status == "queued"))).all()]
        seeds = [str(r[0]) for r in (await conn.execute(select(t.knowledge_sources.c.id).where(
            t.knowledge_sources.c.is_seed.is_(True), t.knowledge_sources.c.status == "keyword_only"))).all()]
    for sid in queued:
        rt.ingest.submit(sid)
    for sid in seeds:   # the seed's documents searched by meaning too (a paid embedding through the seed view)
        await reindex_source(rt, sid)
    await settle_ingest(env)
    return docs


async def settle_ingest(env: RunEnv, limit_s: float = 900) -> None:
    from horizon.evals.suites import _advance

    waited = 0.0
    while waited < limit_s:
        async with env.rt.db.read() as conn:
            busy = (await conn.execute(text("SELECT count(*) FROM knowledge_sources WHERE status IN "
                                            "('queued', 'extracting', 'chunking', 'embedding')"))).scalar_one()
        if not busy:
            return
        await _advance(env, 1000)
        waited += 1.0
    raise RuntimeError("indexing the corpus did not finish")


_HOLDERS: dict[tuple[int, str], str] = {}


async def holder(env: RunEnv, cid: str, row: Any) -> str:
    """One 1:1 session row per character in the run's database, so the ledger's rows name a real session (moodline's
    holder: written, never opened)."""
    from horizon.evals.moodline import holder_session

    key = (id(env.rt), cid)
    if key not in _HOLDERS:
        world = str(row["world_id"])
        async with env.rt.db.read() as conn:
            w = (await conn.execute(select(t.worlds).where(t.worlds.c.id == world))).mappings().first()
        _HOLDERS[key] = await holder_session(env.rt, {"world": world, "mode": "one_on_one", "cast": [cid],
                                                      "id": f"retrieval {cid}"}, {cid: row}, w)
    return _HOLDERS[key]


async def deep_request(env: RunEnv, q: dict[str, Any], arm: dict[str, str], *, ask: bool) -> DeepRequest:
    from horizon.sessions.context import character_view, characters

    rt = env.rt
    cid = str(q["character"])
    row = (await characters(rt, [cid]))[cid]
    view = character_view(row)
    world = str(row["world_id"])
    session_id = await holder(env, cid, row)
    recent: list[MessageView] = []
    for i, line in enumerate(q.get("earlier") or []):
        who, _, said = line.partition(": ")
        mine = who != USER
        recent.append(MessageView(id=f"msg_e{i}", seq=i + 1, author_type="character" if mine else "user",
                                  character_id=cid if mine else None, name=who, kind="chat", content=said))
    recent.append(MessageView(id="msg_q", seq=len(recent) + 1, author_type="user", name=USER, kind="chat",
                              content=q["message"]))
    sctx = SessionContext(session_id=session_id, world=WorldView(id=world, name=world,
                                                                             you={"displayName": USER}),
                          mode="one_on_one", title="eval", participants=[ParticipantView(
                              character_id=cid, name=view.name, role="speaker", energy={"current": 100, "max": 100})],
                          recent=recent)
    nouls: MessageNouls | None
    if arm.get("rewrite") == "off":
        nouls = None
    elif ask:
        nouls = await ask_nouls(env, sctx, view.name, cid, q)
    else:   # the comparisons ask no Jev: the labels say which questions a rewrite is for
        nouls = MessageNouls(standalone=0.0 if q["kind"] == "followup" else 1.0,
                             english=0.0 if q["kind"] == "non_english" else 1.0)
    previous = next((line.partition(": ")[2] for line in reversed(q.get("earlier") or [])
                     if line.startswith(f"{USER}: ")), "")
    return DeepRequest(session=sctx, speaker=view, kind="reply", message=q["message"], message_id=None,
                       earlier=list(q.get("earlier") or [])[-2:], previous_user=previous, gate=GateAnswer(p=0.9),
                       abstain_ok=True, nouls=nouls, k=3, started_at=rt.clock.now())


async def ask_nouls(env: RunEnv, sctx: SessionContext, name: str, cid: str, q: dict[str, Any]) -> MessageNouls:
    """"standalone?" and "English?" as live, on the 1:1 plan's state."""
    inp = PlanStateInput(mode="one_on_one", user_name=USER, candidates=[Candidate(id=cid, name=name)],
                         latest=q["message"], recent=[{"speaker": m.partition(": ")[0], "text": m.partition(": ")[2]}
                                                      for m in q.get("earlier") or []])
    state = build_turn_plan_state(inp).state
    qs = {k: v for k, v in gates.questions({cid: name}, [cid], nouls=True).items() if not k.startswith("docs:")}
    call = env.rt.decider.start(state, qs, call_ctx("turn_plan", world_id=sctx.world.id), purpose="turn_plan")
    got = await call.final()
    s, e = got.answers.get(gates.STANDALONE), got.answers.get(gates.ENGLISH)
    return MessageNouls(standalone=s.p if isinstance(s, NoulAnswer) else None,
                        english=e.p if isinstance(e, NoulAnswer) else None)


async def pieces_of(env: RunEnv, chunk_ids: list[str], docs: dict[str, str]) -> dict[str, R.Piece]:
    if not chunk_ids:
        return {}
    C, S = t.knowledge_chunks.c, t.knowledge_sources.c
    async with env.rt.db.read() as conn:
        rows = (await conn.execute(select(C.id, C.source_id, C.char_start, C.char_end, S.title, S.is_seed,
                                          C.token_count)
                                   .join(t.knowledge_sources, S.id == C.source_id)
                                   .where(C.id.in_(sorted(set(chunk_ids)))))).all()
    out: dict[str, R.Piece] = {}
    for cid, sid, a, b, title, seed, tokens in rows:
        doc = f"seed:{sid}" if seed else docs.get(str(title), str(title))
        out[str(cid)] = R.Piece(chunk_id=str(cid), doc=doc, start=int(a or 0), end=int(b or 0),
                                tokens=int(tokens or 0))
    return out

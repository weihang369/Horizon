"""`horizon eval memory` (memory design D39, D40; docs/ai/09 M12; evaluation-harness "The memory suite").

`--profile agent` only. Synthetic inputs only (W10): `evals/memory/{rewrite,probes,layer3}.jsonl`, built by
`evals/memory/build.py`, and the labelled facts. `--part` runs one part (default: rewrite, recall and layer3); `--set
dev|test` one split; `--limit N` the first N items of each part.

- **rewrite** (24 stretches, 6 secrets, 6 small-talk): each item's present characters get exactly its planted lists,
  then the `agent` writer's graph runs on the stretch as a pause run would (memory-1, Jev's importance and guard, the
  duplicate check). Nothing is applied: the run's changes and ops are read. Targets (doc 09 M12): expected changes
  covered ≥ 80 % (`judge_memory_missed`; a confirm is covered when its line stays current), written lines supported
  ≥ 95 % (`judge_memory_unsupported`), changed facts rewritten rather than duplicated ≥ 80 %, still-true facts lost
  after the guard ≤ 5 % (`judge_memory_lost`, per supersede), untouched lines left alone ≥ 90 %, secrets stored 0,
  small talk ≤ 1 line per character.
- **recall** (60 in-session, 40 overflow): the four frozen transcripts are written to the run's database and their
  lines up to the last summary's bound indexed (`index_drop`: FTS and one embedding); an overflow probe's character
  gets 40–60 memories with the needed one ranked below its list. Recall's own steps run (`recall_bundle`, `find`,
  `check`, `keep`), the query's vector awaited in full (order, not timing: check 4 times the live path). Reported per
  kind: hit@3 of the search order, Recall@6 (in the checked set) and the kept hit (after Jev call 2), with Wilson
  intervals. `--latency` (store-bypassed) reads every check to the end and reports the slowest landing per probe,
  for `recall.checkMs`.
- **layer3** (20 pairs): session 1 plants two facts among small talk and ends; its pause run writes; session 2 asks
  both probes and two unrelated things. Probe use (`judge_recall`, doc 05's noul) ≥ 80 % and over-mention
  (`judge_over_mention`) ≤ 10 %, with intervals; duplicates left in the tab are counted.
- **dup** (`--part dup`): the `dupCosine` sweep on planted pairs: a fact and its rewording (the same fact) against the
  fact and its extension, its changed value, and another fact of the same character. Dev picks the lowest cosine with
  ≥ 95 % precision on "same fact"; test confirms it.

**The recall arms** (`--part recall --arm …`, retrieval order only, no Jev call; D40's comparisons, D39's instruction):
`search=bm25`, `search=dense`, `mmr=off`, `lambda=0.5|0.7|1.0`, `space=<id>` (one of the retrieval suite's arm spaces,
built after the lines are indexed; overflow memories are planted in it).
"""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import math
import re
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select, text

from horizon.ai.agent import recall as rc
from horizon.ai.contexts import DeepRequest, GateAnswer, ParticipantView, SessionContext, WorldView
from horizon.db import spaces
from horizon.db import tables as t
from horizon.domain.pricing import estimate_chat
from horizon.evals import judges
from horizon.evals.content import failed, judge, judge_estimate
from horizon.evals.metrics import wilson
from horizon.evals.runner import EVALS_DIR, Options, Plan, Result, RunEnv, decision_estimate
from horizon.gateway.context import call_ctx

MEM_DIR = EVALS_DIR / "memory"
TRANSCRIPTS = EVALS_DIR / "transcripts"
FACTS_PY = EVALS_DIR / "datasets" / "earlier" / "facts.py"
USER = "Kai"
PARTS = ("rewrite", "recall", "layer3")
ALL_PARTS = (*PARTS, "dup")
TARGETS = {"covered": 0.80, "supported": 0.95, "rewritten": 0.80, "lost": 0.05, "untouched": 0.90, "probe": 0.80,
           "over": 0.10, "hit3": 0.80}
DUP_PRECISION = 0.95
DUP_GRID = tuple(round(0.80 + 0.01 * i, 2) for i in range(20))
LATENCY_CHECK_MS = 10_000.0
MEMORY_WAIT_S = 300.0


# ── the inputs ──
def load(name: str, root: Path = MEM_DIR) -> list[dict[str, Any]]:
    path = root / f"{name}.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def facts() -> list[Any]:
    """The labelled facts (`evals/datasets/earlier/facts.py`), loaded by path."""
    mod = sys.modules.get("m13_facts")
    if mod is None:
        spec = importlib.util.spec_from_file_location("m13_facts", FACTS_PY)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        sys.modules["m13_facts"] = mod
        spec.loader.exec_module(mod)
    return list(mod.FACTS)


def small_talk() -> list[tuple[str, str, int, str]]:
    facts()
    return list(sys.modules["m13_facts"].SMALL_TALK)


def cid_of(who: str) -> str:
    return f"chr_seed{who.capitalize()}"


def parse_arm(arm: str | None) -> dict[str, str]:
    if not arm:
        return {}
    key, _, value = arm.partition("=")
    ok = {"search": ("bm25", "dense"), "mmr": ("off",), "lambda": None, "space": None}
    if key not in ok or not value or (ok[key] is not None and value not in (ok[key] or ())):
        raise ValueError(f"unknown arm {arm!r}")
    if key == "lambda":
        float(value)
    return {key: value}


def parts_of(opts: Options) -> tuple[str, ...]:
    return (opts.part,) if opts.part else PARTS


def _take(rows: list[dict[str, Any]], opts: Options) -> list[dict[str, Any]]:
    rows = [r for r in rows if not opts.set or r["split"] == opts.set][opts.start:]
    return rows[: opts.limit] if opts.limit else rows


# ── the overflow probes' lists (deterministic) ──
def overflow_list(fact_id: str, n: int) -> list[dict[str, Any]]:
    """`n` memories for the fact's character: the needed one (low importance, four months old) and `n − 1` others
    (the other facts' extended lines first, then small talk), recent and more important, so the needed one ranks
    below the 1,000-token list."""
    fs = facts()
    needed = next(f for f in fs if f.id == fact_id)
    others = [f.extend for f in fs if f.id != fact_id]
    others += [f"{USER} said: {line}" for _w, line, _lvl, lang in small_talk() if lang == "en"]
    rows = [{"id": f"mem_ovf{fact_id}x00", "text": needed.memory, "importance": 0.3, "days": 120}]
    for i, line in enumerate(others[: n - 1]):   # ids are contract-valid: a planted memory can reach a trace
        rows.append({"id": f"mem_ovf{fact_id}x{i + 1:02d}", "text": line, "importance": round(0.5 + 0.1 * (i % 5), 2),
                     "days": i % 20})
    return rows


# ── the dupCosine pairs ──
def dup_pairs(rewrite_rows: Sequence[Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Same fact: a memory and its rewording. Not the same: its extension (a new detail the check would drop), a
    changed value (from the rewrite suite's planted changes), another fact of the same character."""
    from horizon.evals.datachecks import split_for

    fs = facts()
    out: list[dict[str, Any]] = []

    def add(a: str, b: str, same: bool, why: str) -> None:
        pid = f"dup-{len(out) + 1:03d}"
        out.append({"id": pid, "split": split_for(pid), "a": a, "b": b, "same": same, "why": why})

    for f in fs:
        if f.reword:   # 22 of the 40 facts carry a rewording (the same fact); the rest only their other pairs
            add(f.memory, f.reword, True, f"{f.id} reworded")
        add(f.memory, f.extend, False, f"{f.id} extended")
        nxt = next((g for g in fs[fs.index(f) + 1:] + fs if g.who == f.who and g.id != f.id), None)
        if nxt is not None:
            add(f.memory, nxt.memory, False, f"{f.id} vs {nxt.id}")
    seen: set[str] = set()
    for row in rewrite_rows if rewrite_rows is not None else load("rewrite"):
        for e in row.get("expected") or []:
            if e["op"] != "rewrite":
                continue
            old = next(x["text"] for x in row["lists"][e["for"]] if x["label"] == e["target"])
            if old not in seen:
                seen.add(old)
                add(old, e["text"], False, f"{row['id']} changed")
    return out


# ── the recall comparisons (D39, D40; K3's rule, as `retrieval-compare`) ──
ARM_FOCUS = {"space": "recall6", "lambda": "hit3", "mmr": "hit3", "search": "hit3"}   # D39: Recall@6 for the instruction


def compare_report(base_dev: Path, arm_dev: Path) -> list[str]:
    """A recall arm against the default run, per probe kind: dev decides, the same runs' test rows confirm. Nothing is
    changed: a win goes to the user (D39)."""
    from horizon.evals import retrieval as R

    _, bd = R.load_results(base_dev)
    name, ad = R.load_results(arm_dev)
    if not name:
        raise ValueError(f"{arm_dev}: not an arm run (the default run comes first)")
    bd, ad = ([r for r in rows if r.get("part") == "recall" and not r.get("listed")] for rows in (bd, ad))
    metric = ARM_FOCUS[name.partition("=")[0]]
    out = [f"## Comparison: `{name}` against the default (K3's rule: >= {R.WIN_GAIN * 100:.0f} points of {metric} on "
           "dev with a paired bootstrap interval above 0, then test >= 0)"]
    for kind in ("in_session", "overflow"):
        dev = R.paired(bd, ad, metric, (kind,), "dev")
        test = R.paired(bd, ad, metric, (kind,), "test") or None
        v, gain, lo, hi = R.verdict(dev, test)
        out.append(f"- {kind.replace('_', '-')}: dev gain {gain * 100:+.1f} points (95% {lo * 100:+.1f} to "
                   f"{hi * 100:+.1f}; {len(dev)} paired)"
                   + (f", test {sum(test) / len(test) * 100:+.1f} points" if test else "") + f"; **{v}**")
    return out


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    na, nb = math.sqrt(math.sumprod(a, a)), math.sqrt(math.sumprod(b, b))
    return math.sumprod(a, b) / (na * nb) if na and nb else 0.0


def dup_sweep(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Per threshold: precision and recall of "same fact" at cosine ≥ t."""
    out = []
    for th in DUP_GRID:
        called = [r for r in rows if float(r["cosine"]) >= th]
        tp = sum(1 for r in called if r["same"])
        pos = sum(1 for r in rows if r["same"])
        out.append({"t": th, "called": len(called), "precision": tp / len(called) if called else 1.0,
                    "recall": tp / pos if pos else 0.0})
    return out


def choose_dup(rows: Sequence[Mapping[str, Any]]) -> float | None:
    """D39: the lowest cosine with ≥ 95 % precision on "same fact" (precision is read where it is defined)."""
    for s in dup_sweep(rows):
        if s["called"] and s["precision"] >= DUP_PRECISION:
            return float(s["t"])
    return None


def dup_report(rows: Sequence[Mapping[str, Any]], live: float) -> list[str]:
    dev = [r for r in rows if r["split"] == "dev"]
    test = [r for r in rows if r["split"] == "test"]
    t_ = choose_dup(dev)
    out = ["## dupCosine (D39)", f"- pairs: {len(rows)} ({sum(r['same'] for r in rows)} same fact); live {live}"]
    out.append("| t | dev called | dev precision | dev recall |")
    out.append("|---|---|---|---|")
    for s in dup_sweep(dev):
        out.append(f"| {s['t']:.2f} | {s['called']} | {s['precision']:.0%} | {s['recall']:.0%} |")
    if t_ is None:
        out.append("- **no threshold reaches 95 % precision on dev**: keep the live value; this goes to the user")
        return out
    on_test = next(s for s in dup_sweep(test) if s["t"] == t_)
    out.append(f"- **chosen on dev: {t_:.2f}**; on test: precision {on_test['precision']:.0%}, recall "
               f"{on_test['recall']:.0%} ({on_test['called']} called)")
    if t_ != live:
        out.append(f"- differs from the live {live}: a change goes to the user as a choice")
    return out


# ── reporting ──
def rate(name: str, flags: Sequence[bool | None], *, target: float, upper: bool = False, qid: str | None = None) -> str:
    """A pass-rate line with its Wilson interval. `upper`: the target is a ceiling on the failure rate."""
    xs = [x for x in flags if x is not None]
    if not xs:
        return f"- {name}: no answers"
    bad = sum(xs)
    tag = counted(qid) if qid else ""
    if tag:   # an unvalidated judge's figure is reported, never held against a target
        return f"- {name}: failures {bad}/{len(xs)}{tag}"
    if upper:
        lo, hi = wilson(bad, len(xs))
        return (f"- {name}: {bad}/{len(xs)} ({bad / len(xs):.0%}, 95% {lo:.2f}–{hi:.2f}), target ≤ {target:.0%}"
                f"{' **miss**' if bad / len(xs) > target else ''}{tag}")
    ok = len(xs) - bad
    lo, hi = wilson(ok, len(xs))
    return (f"- {name}: {ok}/{len(xs)} ({ok / len(xs):.0%}, 95% {lo:.2f}–{hi:.2f}), target ≥ {target:.0%}"
            f"{' **miss**' if ok / len(xs) < target else ''}{tag}")


def counted(qid: str) -> str:
    from horizon.ai.questions import bank

    return "" if judges.validated(qid, bank().get(qid).version) else " **NOT COUNTED** (not validated, B4)"


def _pct(xs: Sequence[float], q: float) -> float:
    s = sorted(xs)
    return s[min(len(s) - 1, max(0, math.ceil(q * len(s)) - 1))]


def rewrite_report(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    def flat(key: str) -> list[bool | None]:
        return [x for r in rows for x in r.get(key) or []]

    out = ["## Rewrite (doc 09 M12)", f"- items: {len(rows)} ({sum(r['kind'] == 'stretch' for r in rows)} stretches, "
           f"{sum(r['kind'] == 'secret' for r in rows)} secrets, {sum(r['kind'] == 'small_talk' for r in rows)} "
           f"small talk); failed calls {sum(1 for r in rows if r.get('failed'))}"]
    out.append(rate("expected changes covered", flat("missed"), target=TARGETS["covered"], qid="judge_memory_missed"))
    out.append(rate("written lines supported", flat("unsupported"), target=TARGETS["supported"],
                    qid="judge_memory_unsupported"))
    out.append(rate("changed facts rewritten, not duplicated", flat("duplicated"), target=TARGETS["rewritten"]))
    out.append(rate("still-true facts lost after the guard", flat("lost"), target=TARGETS["lost"], upper=True,
                    qid="judge_memory_lost"))
    out.append(rate("untouched lines left alone", flat("touched"), target=TARGETS["untouched"]))
    secrets = [r for r in rows if r["kind"] == "secret"]
    stored = sum(1 for r in secrets if r.get("secret_stored"))
    out.append(f"- secrets stored: {stored}/{len(secrets)}, target 0{' **miss**' if stored else ''}")
    talk = [r for r in rows if r["kind"] == "small_talk"]
    over = sum(1 for r in talk if any(n > 1 for n in (r.get("written_per") or {}).values()))
    out.append(f"- small-talk stretches over 1 line per character: {over}/{len(talk)}, target 0"
               f"{' **miss**' if over else ''}")
    guard = [x for r in rows for x in r.get("log") or [] if x.get("step") == "guard"]
    out.append(f"- guard kept beside: {len(guard)}; duplicates reinforced: "
               f"{sum(1 for r in rows for x in r.get('log') or [] if x.get('step') == 'duplicate')}")
    timed = [float(r["run_ms"]) for r in rows if r.get("latency") and r.get("run_ms") is not None]
    if timed:   # doc 09 check 2: expectations only, nothing waits on a run
        out.append(f"### Check 2: pause-run time, store-bypassed ({len(timed)} runs)")
        out.append(f"- p50 {_pct(timed, 0.5):.0f} ms, p90 {_pct(timed, 0.9):.0f} ms, max {max(timed):.0f} ms "
                   "(memory-1, Jev's importance and guard, the duplicate check's embedding; the commit is one local "
                   "transaction)")
    fails = [f"- `{r['id']}` {f}" for r in rows for f in r.get("failures") or []]
    if fails:
        out += ["### Failures to read", *fails]
    return out


def recall_report(rows: Sequence[Mapping[str, Any]], arm: str | None) -> list[str]:
    out = [f"## Recall{f' (arm `{arm}`)' if arm else ''}"]
    for kind in ("in_session", "overflow"):
        rs = [r for r in rows if r["kind"] == kind and not r.get("listed")]
        if not rs:
            continue
        out.append(f"### {kind.replace('_', '-')} ({len(rs)} probes)")
        out.append(rate("hit@3 (search order)", [not r["hit3"] for r in rs], target=TARGETS["hit3"]))
        out.append(rate("Recall@6 (in the checked set)", [not r["recall6"] for r in rs], target=TARGETS["hit3"]))
        if not arm:
            out.append(rate("kept (after Jev call 2)", [not r["kept_hit"] for r in rs], target=TARGETS["hit3"]))
            outcomes: dict[str, int] = {}
            for r in rs:
                outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1
            out.append(f"- outcomes: {', '.join(f'{k} {v}' for k, v in sorted(outcomes.items()))}")
        out.append(f"- no query vector: {sum(1 for r in rs if r['dense_missing'])}")
        listed = [r for r in rows if r["kind"] == kind and r.get("listed")]
        if listed:
            out.append(f"- not counted, the needed memory made the list: {len(listed)}")
    slow = [float(r["slowest_ms"]) for r in rows if r.get("slowest_ms") is not None]
    if slow and any(r.get("latency") for r in rows):
        p99 = _pct(slow, 0.99)
        out.append(f"### Jev call 2's slowest landing per probe (store-bypassed, {len(slow)})")
        out.append(f"- p50 {_pct(slow, 0.5):.0f} ms, p90 {_pct(slow, 0.9):.0f} ms, p99 {p99:.0f} ms; "
                   f"`recall.checkMs` from the tail: {int(math.ceil(p99 / 100.0) * 100)} ms")
    miss = [f"- `{r['id']}` ({r['kind']}) {r['probe']!r}: searched {r['picked'][:3]}" for r in rows
            if not r["hit3"] and not r.get("listed")]
    if miss:
        out += ["### Misses to read", *miss]
    return out


def layer3_report(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    out = ["## Layer 3, two sessions (agent writer and recall)", f"- pairs: {len(rows)}"]
    out.append(rate("probe replies use the fact", [x for r in rows for x in r["probe_fail"]], target=TARGETS["probe"],
                    qid="judge_recall"))
    out.append(rate("over-mention on unrelated turns", [x for r in rows for x in r["over"]], target=TARGETS["over"],
                    upper=True, qid="judge_over_mention"))
    out.append(f"- memories written by session 1: {sum(len(r['written']) for r in rows)}; duplicates left in the tab: "
               f"{sum(r['duplicates'] for r in rows)}")
    return out


# ── the database ──
async def wipe(rt: Any, cid: str, *, keep_seed: bool = False) -> None:
    """Remove a character's memories (and their vectors in every space) from the run's database."""
    M = t.memory_items.c
    async with rt.db.write() as tx:
        q = select(M.rid).where(M.character_id == cid)
        if keep_seed:
            q = q.where(M.is_seed.is_(False))
        rids = [int(r) for r in (await tx.conn.execute(q)).scalars()]
        for space in await spaces.non_retired(tx.conn):
            mem, _ = spaces.vec_tables(space.id)
            for rid in rids:
                await tx.conn.execute(text(f"DELETE FROM {mem} WHERE rid = :r"), {"r": rid})
        if rids:
            await tx.conn.execute(delete(t.memory_items).where(M.rid.in_(rids)))


async def plant(rt: Any, cid: str, world: str, rows: Sequence[Mapping[str, Any]], *, mode: str = "one_on_one") -> None:
    """Write `rows` (id, text, importance, optional `days` old, optional `kind`) as current memories, embedded in the
    active space when there is a key."""
    import sqlite_vec

    now = rt.clock.now()
    async with rt.db.write() as tx:
        for r in rows:
            at = (now - timedelta(days=float(r.get("days") or 0))).isoformat().replace("+00:00", "Z")
            await tx.conn.execute(t.memory_items.insert().values(
                id=r["id"], character_id=cid, world_id=world, kind=r.get("kind") or "fact", text=r["text"],
                importance=float(r["importance"]), source_session_id=None, source_message_id=None,
                source_variant_id=None, source_mode=mode, about_character_id=None, created_at=at, last_recalled_at=None,
                recall_count=0, superseded_by=None, is_seed=False))
    if rt.keys.status() != "set" or not rows:
        return
    async with rt.db.read() as conn:
        space = await spaces.active(conn)
        rid_of = {str(i): int(r) for i, r in (await conn.execute(select(t.memory_items.c.id, t.memory_items.c.rid).where(
            t.memory_items.c.id.in_([r["id"] for r in rows])))).all()}
    got = await rt.ai.embedder(True).embed([r["text"] for r in rows], kind="document", space=space,
                                           ctx=call_ctx("embed_doc", world_id=world, pauses_sessions=False))
    mem, _ = spaces.vec_tables(space.id)
    async with rt.db.write() as tx:
        for r, vec in zip(rows, got.vectors, strict=True):
            await tx.conn.execute(text(f"INSERT INTO {mem}(rid, character_id, embedding) VALUES (:r, :c, :e)"),
                                  {"r": rid_of[r["id"]], "c": cid, "e": sqlite_vec.serialize_float32(list(vec))})


async def character_rows(rt: Any, cids: Sequence[str]) -> dict[str, Any]:
    from horizon.sessions.context import characters

    return dict(await characters(rt, list(cids)))


async def holder(rt: Any, world: str, cast: Sequence[str], label: str) -> str:
    """A session row naming the run's calls (moodline's holder: written, never opened)."""
    from horizon.evals.moodline import holder_session

    rows = await character_rows(rt, cast)
    async with rt.db.read() as conn:
        w = (await conn.execute(select(t.worlds).where(t.worlds.c.id == world))).mappings().first()
    mode = "one_on_one" if len(cast) == 1 else "group"
    return await holder_session(rt, {"world": world, "mode": mode, "cast": list(cast), "id": label},
                                {c: rows[c] for c in cast}, w)


# ── the judges ──
async def ask(env: RunEnv, qid: str, state: dict[str, Any], item_id: str) -> bool | None:
    """One judge noul, its state kept for B4's 30 real validation items (`judge_states.jsonl`, never paid twice)."""
    p = await judge(env, qid, state)
    with (env.run_dir / "judge_states.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"id": item_id, "question_id": qid, "state": state, "p": p}, ensure_ascii=False) + "\n")
    return failed(p, qid)


# ── the rewrite part ──
def _norm(s: str) -> str:
    return re.sub(r"[\s\-]", "", s).casefold()


async def rewrite_item(env: RunEnv, item: Mapping[str, Any]) -> dict[str, Any]:
    from horizon.services.memory.block import ListedMemory
    from horizon.services.memory.runs import RunContext, RunIO
    from horizon.services.memory.stretch import Present, Stretch, StretchLine

    rt = env.rt
    world = str(item["world"])
    present = [str(c) for c in item["present"]]
    lists: dict[str, list[dict[str, Any]]] = {str(k): list(v) for k, v in item["lists"].items()}
    for cid in present:
        await wipe(rt, cid)
        if cid in lists:
            await plant(rt, cid, world, lists[cid], mode=str(item["mode"]))
    rows = await character_rows(rt, present)
    names = {c: str(rows[c]["profile"].get("name") or c) for c in present}
    sid = await holder(rt, world, present, f"memory {item['id']}")
    async with rt.db.read() as conn:
        wname = (await conn.execute(select(t.worlds.c.name).where(t.worlds.c.id == world))).scalar() or world
    lines: list[StretchLine] = []
    for i, ln in enumerate(item["lines"]):
        you = ln["speaker"] == "you"
        who = None if you else cid_of(str(ln["speaker"]))
        lines.append(StretchLine(n=i + 1, message_id=f"msg_{str(item['id']).replace('-', '')}x{i + 1:02d}",
                                 variant_id=None, seq=i + 1,
                                 speaker=USER if you else names.get(who or "", who or ""), text=str(ln["text"]),
                                 author="user" if you else "character", character_id=who))
    pres = [Present(n=k + 1, character_id=c, name=names[c], role=str(rows[c]["profile"].get("role") or ""),
                    memories=[ListedMemory(label=m["label"], id=m["id"], kind=m.get("kind") or "fact", text=m["text"],
                                           importance=float(m["importance"])) for m in lists.get(c, [])],
                    about=str((rows[c]["profile"].get("personality") or {}).get("summary") or ""))
            for k, c in enumerate(present)]
    stretch = Stretch(session_id=sid, world_id=world, world_name=str(wname), user_name=USER, mode=str(item["mode"]),
                      header=str(item.get("header") or ""), context=[], lines=lines, present=pres, from_seq=0,
                      upto_seq=len(lines), reread_ids=[])
    ctx = RunContext(world_id=world, session_id=sid, now=rt.clock.now, knobs=rt.runtime_cfg.runtime.memory,
                     io=RunIO(rt, world))
    writer = rt.ai.memory_writer(True)
    started = time.perf_counter()   # check 2: the run's own time (memory-1, Jev, the embedding); the commit is local
    out = await writer.graph.ainvoke({"stretch": stretch, "ctx": ctx, "path": []}, config={"recursion_limit": 10})
    run_ms = round((time.perf_counter() - started) * 1000, 1)
    row = await score_rewrite(env, item, out["rewrite"], out["result"])
    return {**row, "run_ms": run_ms, "latency": bool(env.opts.latency), "calls": out["rewrite"].calls,
            "session": sid, "present": len(present), "in_tokens": stretch_tokens(stretch)}


def transcript_text(item: Mapping[str, Any]) -> str:
    return "\n".join(f"{USER if ln['speaker'] == 'you' else str(ln['speaker']).capitalize()}: {ln['text']}"
                     for ln in item["lines"])


async def score_rewrite(env: RunEnv, item: Mapping[str, Any], call: Any, result: Any) -> dict[str, Any]:
    from horizon.ai.ports import Insert, Reinforce, Supersede

    lists: dict[str, list[dict[str, Any]]] = {str(k): list(v) for k, v in item["lists"].items()}
    by_label = {cid: {m["label"]: m for m in ls} for cid, ls in lists.items()}
    by_id = {m["id"]: m for ls in lists.values() for m in ls}
    said = transcript_text(item)
    written: dict[str, list[str]] = {}
    superseded: dict[str, set[str]] = {}
    reinforced: dict[str, set[str]] = {}
    replaced: list[tuple[str, str, str]] = []   # (character, old text, new text)
    for cid, ops in (result.ops or {}).items():
        for op in ops:
            if isinstance(op, Insert | Supersede):
                written.setdefault(cid, []).append(op.draft.text)
            if isinstance(op, Supersede):
                for old in op.old_ids:
                    superseded.setdefault(cid, set()).add(old)
                    replaced.append((cid, str(by_id.get(old, {}).get("text") or old), op.draft.text))
            elif isinstance(op, Reinforce):
                reinforced.setdefault(cid, set()).add(op.id)
    rewrote: dict[str, set[str]] = {}
    for c in getattr(call, "changes", None) or []:
        if c.op == "rewrite" and c.target is not None:
            rewrote.setdefault(c.character_id, set()).add(c.target.id)
    row: dict[str, Any] = {"id": item["id"], "split": item["split"], "kind": item["kind"], "mode": item["mode"],
                           "lang": item.get("lang"), "failed": bool(result.failed), "written": written,
                           "written_per": {c: len(v) for c, v in written.items()},
                           "superseded": {c: sorted(v) for c, v in superseded.items()},
                           "reinforced": {c: sorted(v) for c, v in reinforced.items()},
                           "changes": [{"for": c.character_id, "op": c.op, "target": c.target.id if c.target else None,
                                        "text": c.text} for c in getattr(call, "changes", None) or []],
                           "log": list(result.log or []), "missed": [], "unsupported": [], "duplicated": [],
                           "lost": [], "touched": [], "failures": []}
    fails: list[str] = row["failures"]
    for e in item.get("expected") or []:
        cid = str(e["for"])
        target = by_label.get(cid, {}).get(e["target"]) if e.get("target") else None
        if e["op"] == "confirm":
            tid = str(target["id"]) if target else ""
            ok = tid in reinforced.get(cid, set()) or (tid not in superseded.get(cid, set())
                                                       and tid not in rewrote.get(cid, set()))
            row["missed"].append(not ok)
            if not ok:
                fails.append(f"confirm lost its line for {cid}: {e['text']!r}")
            continue
        miss = await ask(env, "judge_memory_missed", {"quoted_expected": f"{e['op']}: {e['text']}",
                                                      "quoted_written": "\n".join(written.get(cid, [])) or "(nothing)"},
                         str(item["id"]))
        row["missed"].append(miss)
        if miss:
            fails.append(f"missed for {cid} ({e['op']}): {e['text']!r}")
        if e["op"] == "rewrite" and target is not None:
            dup = str(target["id"]) not in rewrote.get(cid, set())
            row["duplicated"].append(dup)
            if dup:
                fails.append(f"not rewritten for {cid}: {target['text']!r} (the call's changes: "
                             f"{[c for c in row['changes'] if c['for'] == cid]})")
    old_lines = {cid: "\n".join(m["text"] for m in ls) or "(nothing yet)" for cid, ls in lists.items()}
    for cid, texts in written.items():
        for line in texts:
            bad = await ask(env, "judge_memory_unsupported", {"quoted_line": line, "quoted_messages": said,
                                                              "quoted_memories": old_lines.get(cid, "(nothing yet)")},
                            str(item["id"]))
            row["unsupported"].append(bad)
            if bad:
                fails.append(f"unsupported for {cid}: {line!r}")
    for cid, old, new in replaced:
        bad = await ask(env, "judge_memory_lost", {"quoted_old": old, "quoted_new": new, "quoted_messages": said},
                        str(item["id"]))
        row["lost"].append(bad)
        if bad:
            fails.append(f"lost a fact for {cid}: {old!r} → {new!r}")
    for cid, labels in (item.get("untouched") or {}).items():
        for lb in labels:
            m = by_label.get(cid, {}).get(lb)
            if m is None:
                continue
            hit = m["id"] in superseded.get(cid, set()) or m["id"] in rewrote.get(cid, set())
            row["touched"].append(hit)
            if hit:
                fails.append(f"rewrote an untouched line for {cid}: {m['text']!r}")
    if item["kind"] == "secret":
        key = _norm(str(item.get("secret") or ""))
        row["secret_stored"] = bool(key) and any(key in _norm(x) for xs in written.values() for x in xs)
        if row["secret_stored"]:
            fails.append(f"stored the secret {item.get('secret')!r}")
    if item["kind"] == "small_talk" and any(n > 1 for n in row["written_per"].values()):
        fails.append(f"small talk wrote {row['written_per']}")
    return row


# ── doc 09 check 1: the rewrite calls' shape and size ──
LONG_TRANSCRIPT = "long_one_on_one_en"
LONG_TOKENS = 8000


def long_piece_item(tokens: int = LONG_TOKENS) -> dict[str, Any]:
    """An 8,000-token piece (`memory.pieceTokens`) of the long 1:1 transcript, Amara holding the first stretch's
    planted list: check 1's longest call. It has no expected changes; the call's validity and size are read."""
    from horizon.domain.pricing import count_tokens

    d = json.loads((TRANSCRIPTS / f"{LONG_TRANSCRIPT}.json").read_text(encoding="utf-8"))
    cid = str(d["cast"][0])
    lines: list[dict[str, str]] = []
    used = 0
    for turn in d["turns"]:
        for who, said in [("you", str(turn["user"])), *[("amara", str(r["text"])) for r in turn["replies"]]]:
            cost = count_tokens(f"{who}: {said}") + 2
            if used + cost > tokens:
                break
            lines.append({"speaker": who, "text": said})
            used += cost
        else:
            continue
        break
    first = load("rewrite")[0]
    return {"id": "mrw-long", "split": "dev", "kind": "long", "mode": "one_on_one", "lang": "en",
            "world": str(d["world"]), "present": [cid], "lists": {cid: first["lists"][cid]}, "header": "",
            "lines": lines, "expected": [], "untouched": {}, "source": f"check 1: {tokens} tokens of {LONG_TRANSCRIPT}"}


def stretch_tokens(stretch: Any) -> int:
    from horizon.ai.memory import rewrite as mem1
    from horizon.domain.pricing import count_tokens

    return int(count_tokens(mem1.SYSTEM) + count_tokens(mem1.user_message(stretch)))


async def add_calls(env: RunEnv, rows: list[dict[str, Any]]) -> None:
    """Each item's `memory` calls from the ledger: tokens out, the finish reason, and the cap they ran under."""
    from horizon.ai.memory import rewrite as mem1

    U = t.usage_records.c
    sids = [str(r["session"]) for r in rows if r.get("session")]
    if not sids:
        return
    async with env.rt.db.read() as conn:
        got = (await conn.execute(select(U.session_id, U.tokens_in, U.tokens_out, U.finish_reason, U.latency_ms)
                                  .where(U.purpose == "memory", U.session_id.in_(sids)).order_by(U.at))).all()
    for r in rows:
        r["memory_calls"] = [{"in": a, "out": b, "finish": f, "ms": ms, "cap": mem1.max_tokens(int(r["present"]))}
                             for s, a, b, f, ms in got if s == r.get("session")]


def check1_report(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    calls = [c for r in rows for c in r.get("memory_calls") or []]
    if not calls:
        return []
    outs = [float(c["out"]) for c in calls if c.get("out") is not None]
    share = [float(c["out"]) / float(c["cap"]) for c in calls if c.get("out") is not None and c.get("cap")]
    failed_ = [r["id"] for r in rows if r.get("failed")]
    parse = sum(1 for r in rows for x in r.get("log") or [] if "parse" in str(x.get("why", "")).lower())
    out = [f"### Check 1: the `memory-1` calls ({len(calls)} across {len(rows)} items)",
           f"- valid answers: {len(rows) - len(failed_)}/{len(rows)} items"
           + (f" (failed: {', '.join(failed_)})" if failed_ else "") + f"; parse retries logged: {parse}",
           f"- finish `length`: {sum(1 for c in calls if c.get('finish') == 'length')}",
           f"- output tokens: p50 {_pct(outs, 0.5):.0f}, max {max(outs):.0f}; share of the cap: p50 "
           f"{_pct(share, 0.5):.0%}, max {max(share):.0%} (pass: well under)" if outs and share else
           "- output tokens: not in the ledger"]
    for r in rows:
        if r["kind"] == "long":
            c = (r.get("memory_calls") or [{}])[0]
            out.append(f"- the {LONG_TOKENS}-token piece (`{r['id']}`): ≈ {r.get('in_tokens')} tokens in, "
                       f"{c.get('out')} out of a {c.get('cap')} cap, finish {c.get('finish')}, written "
                       f"{sum(len(v) for v in (r.get('written') or {}).values())} line(s)")
    return out


# ── the recall part ──
@dataclasses.dataclass
class Scene:
    session_id: str
    world: str
    mode: str
    cast: list[str]
    upto: int
    seq_of_turn: dict[int, str]
    earlier: list[str]


async def load_transcript(env: RunEnv, name: str) -> Scene:
    """The frozen transcript as a session's messages, its lines up to the last summary's bound indexed."""
    from horizon.services.memory.index import index_drop, line_text
    from horizon.services.memory.stretch import Msg, label

    rt = env.rt
    d = json.loads((TRANSCRIPTS / f"{name}.json").read_text(encoding="utf-8"))
    cast = [str(c) for c in d["cast"]]
    sid = await holder(rt, str(d["world"]), cast, f"memory {name}")
    rows = await character_rows(rt, cast)
    names = {c: str(rows[c]["profile"].get("name") or c) for c in cast}
    now = rt.now_iso()
    msgs: list[Msg] = []
    seq_of_turn: dict[int, str] = {}
    for i, turn in enumerate(d["turns"]):
        mid = f"msg_{name.replace('_', '')}{len(msgs) + 1:04d}"
        seq_of_turn[i] = mid
        msgs.append(Msg(id=mid, seq=len(msgs) + 1, author_type="user", character_id=None, kind="chat",
                        content=str(turn["user"]), status="complete", variant_id=None))
        for r in turn["replies"]:
            msgs.append(Msg(id=f"msg_{name.replace('_', '')}{len(msgs) + 1:04d}", seq=len(msgs) + 1,
                            author_type="character",
                            character_id=str(r["speaker"]), kind="chat", content=str(r["text"]), status="complete",
                            variant_id=None))
    async with rt.db.write() as tx:
        await tx.conn.execute(t.messages.insert(), [
            {"id": m.id, "session_id": sid, "seq": m.seq, "author_type": m.author_type,
             "author_character_id": m.character_id, "kind": m.kind, "content": m.content, "status": m.status,
             "created_at": now} for m in msgs])
    upto = max((int(x["summary_upto"]) for x in d["turns"] if x.get("summary_upto") is not None), default=len(msgs))
    mode = str(d["mode"])
    lines = [(m.id, m.seq, m.author_type, line_text(label(m, names, USER, mode), m.content)) for m in msgs
             if m.seq <= upto]
    await index_drop(rt, sid, str(d["world"]), lines)
    earlier = [line_text(label(m, names, USER, mode), m.content) for m in msgs[-2:]]
    return Scene(session_id=sid, world=str(d["world"]), mode=mode, cast=cast, upto=upto, seq_of_turn=seq_of_turn,
                 earlier=earlier)


_DenseOnly = rc.DenseOnly   # the `search=dense` arm switches both corpora's keyword search off


class _ArmIO:
    def __init__(self, io: Any, dense_only: bool) -> None:
        self.io = io
        self.dense_only = dense_only

    def active_space(self) -> str:
        return str(self.io.active_space())

    def lines(self, *a: Any) -> Any:
        c = self.io.lines(*a)
        return _DenseOnly(c) if self.dense_only else c

    def overflow(self, *a: Any) -> Any:
        c = self.io.overflow(*a)
        return _DenseOnly(c) if self.dense_only else c


def recall_request(env: RunEnv, scene_session: str, world: str, mode: str, view: Any, probe: str,
                   earlier: list[str], *, upto: int, block_ids: list[str], has_overflow: bool) -> DeepRequest:
    sctx = SessionContext(session_id=scene_session, world=WorldView(id=world, name=world, you={"displayName": USER}),
                          mode=mode, title="eval", participants=[ParticipantView(
                              character_id=view.id, name=view.name, role="speaker",
                              energy={"current": 100, "max": 100})], recent=[])
    return DeepRequest(session=sctx, speaker=view, kind="reply", message=probe, message_id=None, earlier=earlier,
                       previous_user="", gate=GateAnswer(p=0.9), abstain_ok=True, nouls=None, k=3,
                       started_at=env.rt.clock.now(), docs=False, recall=True, upto_seq=upto, block_ids=block_ids,
                       has_overflow=has_overflow)


async def run_recall(env: RunEnv, req: DeepRequest, needed: str, arm: dict[str, str]) -> dict[str, Any]:
    deps = env.rt.ai.planner(True).deps
    io = deps.deep_io()
    knobs = deps.retrieval().agent.recall
    if arm.get("mmr") == "off":
        knobs = dataclasses.replace(knobs, mmr_lambda=1.0)
    if arm.get("lambda"):
        knobs = dataclasses.replace(knobs, mmr_lambda=float(arm["lambda"]))
    if env.opts.latency:   # read every check to its end: the tail is what `checkMs` is chosen from
        knobs = dataclasses.replace(knobs, check_ms=LATENCY_CHECK_MS)
    space_id = io.active_space()
    dense: dict[int, list[float]] = {}
    if arm.get("search") != "bm25" and io.key_set():
        space = await io.space(space_id)
        if space is not None:   # awaited in full: order, not timing (check 4 times the live wait)
            try:
                got = await io.embedder().embed([req.message], kind="query", space=space, ctx=call_ctx(
                    "query_embed", world_id=req.session.world.id, session_id=req.session.session_id))
                dense = {0: list(got.vectors[0])}
            except Exception:
                dense = {}
    bundle = rc.recall_bundle(req, None, dense, space_id)
    found = await rc.find(_ArmIO(io, arm.get("search") == "dense"), req, bundle, knobs, deps.memory_knobs(),
                          deps.clock().now())
    picked = [it.hit.id for it in found.picked]
    row: dict[str, Any] = {"picked": picked, "hit3": needed in picked[:3], "recall6": needed in picked,
                           "dense_missing": not dense, "lists": found.lists}
    if arm:
        return row
    started = time.perf_counter()
    ps, slowest = await rc.check(deps, req, bundle, found.picked, knobs)
    kept, outcome = rc.keep(found.picked, found.merged, ps, knobs)
    row.update(ps=ps, kept=[h.id for h in kept], kept_hit=needed in [h.id for h in kept], outcome=outcome,
               slowest_ms=slowest, wall_ms=round((time.perf_counter() - started) * 1000, 1),
               latency=bool(env.opts.latency))
    return row


async def recall_part(env: RunEnv, items: list[dict[str, Any]], arm: dict[str, str], res: Result) -> list[dict[str, Any]]:
    from horizon.services.memory.block import memory_list
    from horizon.sessions.context import character_view

    rt = env.rt
    scenes: dict[str, Scene] = {}
    for name in dict.fromkeys(str(p["transcript"]) for p in items if p["kind"] == "in_session"):
        scenes[name] = await load_transcript(env, name)
    if arm.get("space"):
        from horizon.evals.retrieval_suite import ARM_SPACES
        from horizon.services.knowledge.build import build_space

        await build_space(rt, ARM_SPACES[arm["space"]])
    holders: dict[str, str] = {}
    out: list[dict[str, Any]] = []
    for p in items:
        if await env.over_budget():
            res.status = "incomplete"
            break
        cid = str(p["speaker"])
        view = character_view((await character_rows(rt, [cid]))[cid])
        base = {"id": p["id"], "split": p["split"], "kind": p["kind"], "probe": p["probe"], "speaker": cid,
                "arm": env.opts.arm}
        if p["kind"] == "in_session":
            sc = scenes[str(p["transcript"])]
            needed = sc.seq_of_turn[int(p["turn"])]
            req = recall_request(env, sc.session_id, sc.world, sc.mode, view, str(p["probe"]), sc.earlier,
                                 upto=sc.upto, block_ids=[], has_overflow=False)
        else:
            world = str(p["world"])
            plants = overflow_list(str(p["fact_id"]), int(p["memories"]))
            await wipe(rt, cid)
            await plant(rt, cid, world, plants)
            async with rt.db.read() as conn:
                listed, overflow = await memory_list(conn, cid, world, rt.clock.now(), rt.runtime_cfg.runtime.memory)
            needed = plants[0]["id"]
            block = [m.id for m in listed]
            if needed in block:   # the needed memory made the list: not an overflow probe on this database
                out.append({**base, "needed": needed, "listed": True, "picked": [], "hit3": False, "recall6": False,
                            "dense_missing": False})
                continue
            if cid not in holders:
                holders[cid] = await holder(rt, world, [cid], f"memory overflow {cid}")
            req = recall_request(env, holders[cid], world, "one_on_one", view, str(p["probe"]), [], upto=0,
                                 block_ids=block, has_overflow=overflow)
        got = await run_recall(env, req, needed, arm)
        out.append({**base, "needed": needed, **got})
    return out


# ── layer 3 ──
async def end_session(env: RunEnv, sid: str) -> None:
    import httpx

    from horizon.main import create_app

    app = create_app(env.rt.cfg, runtime=env.rt)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as c:
        await c.post(f"/api/v1/sessions/{sid}/end")


async def wait_written(env: RunEnv, sid: str) -> bool:
    """Run the session's pause run now and wait until its checkpoint reaches the last message."""
    from horizon.evals.suites import _advance

    rt = env.rt
    rt.memory_runs.request(sid, high=True, reason="eval")
    waited = 0.0
    while waited < MEMORY_WAIT_S:
        await rt.memory_runs.drain()
        async with rt.db.read() as conn:
            seq = (await conn.execute(select(t.sessions.c.memory_seq).where(t.sessions.c.id == sid))).scalar() or 0
            top = (await conn.execute(select(func.max(t.messages.c.seq)).where(t.messages.c.session_id == sid))
                   ).scalar() or 0
        if int(seq) >= int(top) and not rt.memory_runs.busy(sid):
            return True
        await _advance(env, 1000)
        waited += 1.0
    return False


async def current_texts(rt: Any, cid: str, world: str) -> list[tuple[str, str, bool]]:
    M = t.memory_items.c
    async with rt.db.read() as conn:
        rows = (await conn.execute(select(M.id, M.text, M.is_seed).where(
            M.character_id == cid, M.world_id == world, M.superseded_by.is_(None)))).all()
    return [(str(r[0]), str(r[1]), bool(r[2])) for r in rows]


def duplicates(texts: Sequence[str]) -> int:
    """Pairs left in the tab that say the same thing: case-folded equal, or ≥ 80 % of their words shared."""
    from horizon.ai.retrieval import jaccard

    n = 0
    for i, a in enumerate(texts):
        for b in texts[i + 1:]:
            if a.casefold() == b.casefold() or jaccard(a, b) >= 0.8:
                n += 1
    return n


RECENT_LINES = 4
NO_RECENT = "(no earlier lines)"


def recent_before(turns: Sequence[Mapping[str, Any]], index: int, name: str, n: int = RECENT_LINES) -> str:
    """The session's last `n` lines before turn `index` ("Kai: …", "Name: …"), as judge_over_mention v2 sees them."""
    lines: list[str] = []
    for tn in turns[:index]:
        lines.append(f"{USER}: {tn['text']}")
        lines += [f"{name}: {r['text']}" for r in tn.get("replies") or []]
    return "\n".join(lines[-n:]) or NO_RECENT


async def layer3_pair(env: RunEnv, pair: Mapping[str, Any]) -> dict[str, Any]:
    from horizon.evals.content import drive

    rt = env.rt
    cid, world = str(pair["speaker"]), str(pair["world"])
    await wipe(rt, cid, keep_seed=True)
    s1, _ = await drive(env, {"world": world, "mode": "one_on_one", "cast": [cid],
                              "lines": [{"text": x, "kind": "plant"} for x in pair["session1"]]})
    await end_session(env, s1)
    settled = await wait_written(env, s1)
    mems = await current_texts(rt, cid, world)
    written = [x for _i, x, seed in mems if not seed]
    lines = []
    for k in range(2):
        lines.append({"text": pair["probes"][k]["probe"], "kind": "probe", "fact": pair["probes"][k]["fact"]})
        lines.append({"text": pair["unrelated"][k], "kind": "unrelated"})
    s2, turns = await drive(env, {"world": world, "mode": "one_on_one", "cast": [cid], "lines": lines})
    await end_session(env, s2)
    memories = "\n".join(x for _i, x, _s in mems) or "(nothing)"
    probe_fail: list[bool | None] = []
    over: list[bool | None] = []
    name = str((await character_rows(rt, [cid]))[cid]["profile"].get("name") or cid)
    for k, tn in enumerate(turns):
        reply = "\n".join(r["text"] for r in tn["replies"])
        if not reply:
            continue
        if tn["kind"] == "probe":
            probe_fail.append(await ask(env, "judge_recall", {"quoted_fact": tn["fact"], "quoted_probe": tn["text"],
                                                              "quoted_reply": reply}, str(pair["id"])))
        else:
            over.append(await ask(env, "judge_over_mention", {"quoted_memories": memories,
                                                              "quoted_recent": recent_before(turns, k, name),
                                                              "quoted_message": tn["text"], "quoted_reply": reply},
                                  str(pair["id"])))
    after = [x for _i, x, _s in await current_texts(rt, cid, world)]
    return {"id": pair["id"], "split": pair["split"], "speaker": cid, "session1": s1, "session2": s2,
            "written_settled": settled, "written": written, "turns": turns, "probe_fail": probe_fail, "over": over,
            "duplicates": duplicates(after)}


# ── the suite ──
class Memory:
    name = "memory"

    def refuse(self, opts: Options) -> str | None:
        if opts.profile != "agent":
            return "horizon: `memory` runs the agent writer and recall; pass --profile agent"
        if opts.part and opts.part not in ALL_PARTS:
            return f"horizon: unknown part {opts.part!r} (have: {', '.join(ALL_PARTS)})"
        try:
            arm = parse_arm(opts.arm)
        except ValueError as e:
            return f"horizon: {e}"
        if arm and opts.part != "recall":
            return "horizon: the arms compare recall's order; pass --part recall"
        if arm.get("space"):
            from horizon.evals.retrieval_suite import ARM_SPACES

            if arm["space"] not in ARM_SPACES:
                return f"horizon: unknown arm space {arm['space']!r} (have: {', '.join(ARM_SPACES)})"
        return None

    def _items(self, opts: Options) -> list[tuple[str, dict[str, Any]]]:
        out: list[tuple[str, dict[str, Any]]] = []
        for part in parts_of(opts):
            if part == "dup":
                out += [("dup", r) for r in _take(dup_pairs(), Options(suite=self.name, start=opts.start))]
                continue
            rows = load({"recall": "probes"}.get(part, part))
            if part == "rewrite":
                rows = [*rows, long_piece_item()]   # doc 09 check 1's 8,000-token piece, last
            out += [(part, r) for r in _take(rows, opts)]
        return out

    def plan(self, opts: Options, prices: Any, *, paid: bool) -> Plan:
        items = self._items(opts)
        arm = parse_arm(opts.arm)
        mem1 = estimate_chat(prices, prefix_tokens=1500, warm=False, other_in=5500, expected_out_tokens=600,
                             period="off_peak")
        jev = decision_estimate(prices, {"quoted_line": "x" * 300, "quoted_about": "x" * 300}, {"q": {"instructions": "x" * 400}})
        judge_ = judge_estimate(prices, "judge_memory_unsupported", {"quoted_line": "x" * 200, "quoted_messages": "x" * 1600,
                                                                     "quoted_memories": "x" * 1500})
        check = decision_estimate(prices, {"quoted_query": "x" * 200, "quoted_candidate": "x" * 600},
                                  {"q": {"instructions": "x" * 400}})
        reply = estimate_chat(prices, prefix_tokens=6000, warm=True, other_in=600, expected_out_tokens=140,
                              period="off_peak")
        emb = 200 * prices.embedding.input_per_m / 1e6
        est, secs = 0.0, 0.0
        for part, _row in items:
            if part == "rewrite":
                est += mem1 + 4 * jev + 8 * judge_ + 40 * emb
                secs += 15
            elif part == "recall":
                est += (0 if arm else 6 * check) + 40 * emb
                secs += 1 if arm else 3
            elif part == "layer3":
                est += 14 * reply + 2 * (mem1 + 4 * jev) + 4 * judge_
                secs += 120
            else:
                est += 2 * emb
                secs += 0.2
        if any(p == "recall" for p, _ in items):   # the transcripts' lines, embedded once
            est += 60_000 * prices.embedding.input_per_m / 1e6
        return Plan(items=items, estimate_usd=est, expected_s=30 + secs, paid=paid)

    async def run(self, env: RunEnv, plan: Plan) -> Result:
        res = Result()
        arm = parse_arm(env.opts.arm)
        (env.run_dir / "judge_states.jsonl").unlink(missing_ok=True)
        by_part: dict[str, list[dict[str, Any]]] = {}
        for part, row in plan.items:
            by_part.setdefault(part, []).append(row)
        if "rewrite" in by_part:
            rows = []
            for item in by_part["rewrite"]:
                if await env.over_budget():
                    res.status = "incomplete"
                    break
                rows.append(await rewrite_item(env, item))
            await add_calls(env, rows)
            res.rows += [{"part": "rewrite", **r} for r in rows]
            res.summary += rewrite_report([r for r in rows if r["kind"] != "long"]) + check1_report(rows)
        if "recall" in by_part and res.status != "incomplete":
            rows = await recall_part(env, by_part["recall"], arm, res)
            res.rows += [{"part": "recall", **r} for r in rows]
            res.summary += recall_report(rows, env.opts.arm)
        if "layer3" in by_part and res.status != "incomplete":
            rows = []
            for pair in by_part["layer3"]:
                if await env.over_budget():
                    res.status = "incomplete"
                    break
                rows.append(await layer3_pair(env, pair))
            res.rows += [{"part": "layer3", **r} for r in rows]
            res.summary += layer3_report(rows)
        if "dup" in by_part and res.status != "incomplete":
            rows = await dup_part(env, by_part["dup"])
            res.rows += [{"part": "dup", **r} for r in rows]
            res.summary += dup_report(rows, float(env.rt.runtime_cfg.runtime.memory.dup_cosine))
        if (env.run_dir / "judge_states.jsonl").is_file():
            res.summary.append(f"- the judges' states for labelling the 30 real items: `{env.run_dir.name}/"
                               "judge_states.jsonl` (B4)")
        return res


# ── U3: the embedding provider probe ──
PROBE_PER_PROVIDER = 10


class EmbedProbe:
    """`horizon eval embed-probe --set ProviderA,ProviderB` (memory D39, U3): 10 query embeddings per OpenRouter
    provider of the active space's model, one at a time, timed; store-bypassed (the runner never gives it a store).
    A faster provider gets its own space only after the user's OK."""

    name = "embed-probe"

    def refuse(self, opts: Options) -> str | None:
        if not opts.set:
            return "horizon: name the providers to compare: --set Nebius,OtherProvider"
        return None

    def plan(self, opts: Options, prices: Any, *, paid: bool) -> Plan:
        providers = [p.strip() for p in (opts.set or "").split(",") if p.strip()]
        probes = [str(p["probe"]) for p in load("probes")]
        items = [{"provider": pv, "text": probes[(k * PROBE_PER_PROVIDER + i) % len(probes)]}
                 for k, pv in enumerate(providers) for i in range(PROBE_PER_PROVIDER)]
        est = len(items) * 40 * prices.embedding.input_per_m / 1e6
        return Plan(items=items, estimate_usd=est, expected_s=10 + 2.0 * len(items), paid=paid)

    async def run(self, env: RunEnv, plan: Plan) -> Result:
        rt = env.rt
        res = Result()
        async with rt.db.read() as conn:
            active = await spaces.active(conn)
        for it in plan.items:
            space = dataclasses.replace(active, id=f"{active.id}~{it['provider']}", provider=it["provider"])
            started = time.perf_counter()
            try:
                await rt.ai.embedder(True).embed([it["text"]], kind="query", space=space,
                                                 ctx=call_ctx("query_embed", pauses_sessions=False))
                ok, err = True, None
            except Exception as e:   # a provider that refuses the model: recorded, not fatal
                ok, err = False, getattr(e, "code", type(e).__name__)
            res.rows.append({"provider": it["provider"], "text": it["text"], "ok": ok, "error": err,
                             "wall_ms": round((time.perf_counter() - started) * 1000, 1)})
        res.summary += probe_report(res.rows, active)
        return res


def probe_report(rows: Sequence[Mapping[str, Any]], active: Any) -> list[str]:
    out = [f"## Embedding provider probe (U3): `{active.model}`, query embeddings one at a time, store-bypassed",
           f"- active space `{active.id}` (provider {active.provider})"]
    for pv in dict.fromkeys(str(r["provider"]) for r in rows):
        mine = [r for r in rows if r["provider"] == pv]
        ms = [float(r["wall_ms"]) for r in mine if r["ok"]]
        bad = [str(r["error"]) for r in mine if not r["ok"]]
        out.append(f"- {pv}: {len(ms)}/{len(mine)} ok" + (f", p50 {_pct(ms, 0.5):.0f} ms, p90 {_pct(ms, 0.9):.0f} ms, "
                                                         f"max {max(ms):.0f} ms" if ms else "")
                   + (f"; errors {sorted(set(bad))}" if bad else ""))
    out.append("- a faster provider gets its own space and a `horizon space build` only after the user's OK")
    return out


async def dup_part(env: RunEnv, pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rt = env.rt
    if rt.keys.status() != "set":
        return []
    async with rt.db.read() as conn:
        space = await spaces.active(conn)
    texts = list(dict.fromkeys([p["a"] for p in pairs] + [p["b"] for p in pairs]))
    got = await rt.ai.embedder(True).embed(texts, kind="document", space=space,
                                           ctx=call_ctx("embed_doc", pauses_sessions=False))
    vec: dict[str, Sequence[float]] = dict(zip(texts, got.vectors, strict=True))
    return [{**p, "cosine": round(cosine(vec[p["a"]], vec[p["b"]]), 4)} for p in pairs]


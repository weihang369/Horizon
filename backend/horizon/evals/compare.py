"""`horizon eval compare-models`: a candidate Jev against the pinned one on Horizon's own Jev requests (jev-comparison
design D7–D11, D20; model-comparison spec).

**The steps** (`--step`, in this order; with no `--step`, every step not yet done, stopping where one can't run yet).
Each step is one or more ordinary `Runner` runs, with their own folder, estimate, cap (max(1.5 × estimate, $0.01)) and
ledger. The run ids go to `data/evals/compare-<base>-vs-<new>.json`, so a step resumes or re-runs alone: a finished
run is skipped, an unfinished one re-runs, and the store serves every answer it already paid for.
1. `canary`: the base model's canary (a 1.13 drift stops the comparison: the user decides), then the candidate's
   first canary, which writes its own baseline (D5).
2. `probe`: `--probe` of every set step on both models: the exact misses and what they would cost. Sends nothing.
3. `sets`: on each model, against the manifest: `decisions`, `decisions --set judges`, `deep-check` and
   `safety --part input,care,output,motion,image,song`.
4. `repeat`: the repeat probe (D11). 5. `timing-a`, `timing-b`: the timing probe's two windows, ≥ 3 h apart (D10).
6. `report`: from the saved rows only ($0, re-runnable; `--report-only [RUN…]` names the runs instead).

**The report** pairs each item's rows on the two models (set, item id; both option orders are in one row) and scores
them two ways (D8): *drop-in*, every rule at its live value (the bank's floors and thresholds, safety's knobs); and
*re-tuned*, the candidate's value re-chosen on its dev rows by the set's own chooser, written down, then read on test
once (safety has no split: its own leave-one-out rule). The base model is always read at its live values: that is
what ships. English rows are scored (the English-first rule). Each comparison gives the counts, Wilson intervals,
the discordant counts (b: only the base right; c: only the candidate right) and the exact McNemar p.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from horizon.ai.questions import bank
from horizon.config import REPO_ROOT
from horizon.evals import m12_sets, m13_sets, policies, who_policies
from horizon.evals.metrics import mcnemar_exact, percentile, percentile_ci, wilson
from horizon.evals.runner import Options, Runner

SEED = REPO_ROOT / "seed"   # the prices, deadlines and runtime the report reads (the repo's own seed)

STEPS = ("canary", "probe", "sets", "repeat", "timing-a", "timing-b", "report")
WINDOW_GAP_H = 3.0
LIVE_LATENCY_RUN = "20261019T233533-latency-4096b9"   # M15 8.12: the must-pass latency run's ledger (per-turn tokens)
TURN_PURPOSES = ("turn_plan", "guardrail", "face_check", "reaction")   # D9: a 1:1 reply's Jev requests
GROUP_A_REPEAT = "group A A1 (jev-1.13, 2026-10): 0 of 20 choices changed; p within ±0.06"
Row = Mapping[str, Any]


# ── where things live ──
def slug(model: str) -> str:
    return model.replace("/", "__")


def state_path(data_dir: Path, base: str, new: str) -> Path:
    return data_dir / "evals" / f"compare-{slug(base)}-vs-{slug(new)}.json"


def out_dir(data_dir: Path, base: str, new: str) -> Path:
    return data_dir / "evals" / f"compare-{slug(base)}-vs-{slug(new)}"


def load_state(path: Path, base: str, new: str, manifest: str) -> dict[str, Any]:
    if path.is_file():
        return dict(json.loads(path.read_text(encoding="utf-8")))
    return {"base": base, "new": new, "manifest": manifest, "runs": {}, "probe": {}}


def save_state(path: Path, state: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=1) + "\n", encoding="utf-8")


def run_folder(data_dir: Path, run_id: str) -> Path | None:
    """A run's profile folder (`data/evals/<run>/<profile>/`): the one with `run.json`, or for a run from before it
    (M15's latency run), the one with a ledger."""
    root = data_dir / "evals" / run_id
    if not root.is_dir():
        return None
    folders = [p for p in sorted(root.iterdir()) if p.is_dir()]
    return next((p for p in folders if (p / "run.json").is_file()),
                next((p for p in folders if (p / "horizon.db").is_file()), None))


def run_meta(data_dir: Path, run_id: str) -> dict[str, Any]:
    f = run_folder(data_dir, run_id)
    return dict(json.loads((f / "run.json").read_text(encoding="utf-8"))) if f is not None else {}


def run_rows(data_dir: Path, run_id: str) -> list[dict[str, Any]]:
    f = run_folder(data_dir, run_id)
    if f is None or not (f / "results.jsonl").is_file():
        return []
    return [json.loads(ln) for ln in (f / "results.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]


def ledger(data_dir: Path, run_id: str) -> list[dict[str, Any]]:
    """The run's paid Jev rows (read-only): cost, tokens in, latency."""
    f = run_folder(data_dir, run_id)
    if f is None or not (f / "horizon.db").is_file():
        return []
    con = sqlite3.connect(f"file:{(f / 'horizon.db').as_posix()}?mode=ro", uri=True)
    try:
        cur = con.execute("SELECT purpose, model, cost_usd, tokens_in, latency_ms FROM usage_records "
                          "WHERE category = 'decision' AND is_seed = 0")
        return [{"purpose": p, "model": m, "usd": float(c or 0.0), "tokens_in": t, "ms": ms} for p, m, c, t, ms in cur]
    finally:
        con.close()


# ── the steps: the runner options each one runs ──
SAFETY_JEV = "input,care,output,motion,image,song"


def set_options(model: str, manifest: str, *, probe: bool = False, yes: bool = False) -> list[Options]:
    common: dict[str, Any] = {"decision_model": model, "against": manifest, "probe": probe, "yes": yes}
    return [Options("decisions", **common), Options("decisions", set="judges", **common),
            Options("deep-check", **common), Options("safety", part=SAFETY_JEV, **common)]


def cap_for(opts: Options, prices: Any) -> float:
    """The user's rule for a paid run: max(1.5 × estimate, $0.01)."""
    from horizon.evals import suites

    est = suites.SUITES[opts.suite].plan(opts, prices, paid=True).estimate_usd
    return round(max(1.5 * float(est), 0.01), 6)


@dataclass
class Comparison:
    """One comparison: two models, a manifest, the runs so far. `runner_for` builds each step's runner (tests pass
    one on the fake)."""
    data_dir: Path
    base: str
    new: str
    manifest: str
    runner_for: Callable[[], Runner]
    out: Callable[[str], None] = print
    yes: bool = False
    now: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.UTC)

    def __post_init__(self) -> None:
        self.path = state_path(self.data_dir, self.base, self.new)
        self.state = load_state(self.path, self.base, self.new, self.manifest)

    def _done(self, run_id: str | None, *, drift_done: bool = True) -> bool:
        return bool(run_id) and run_meta(self.data_dir, str(run_id)).get("status") in (
            ("ok", "drift") if drift_done else ("ok",))

    async def _run(self, key: str, opts: Options, *, prices: Any) -> tuple[int, str | None]:
        """One runner run, recorded under `key`; skipped when its recorded run finished. A drifted base canary is
        never "finished": the comparison stopped on it, so once the user has dealt with the drift it runs again."""
        runs = self.state["runs"]
        if self._done(runs.get(key), drift_done=key != "canary:base"):
            self.out(f"{key}: done ({runs[key]}), skipped")
            return 0, runs[key]
        r = self.runner_for()
        if not opts.probe and opts.max_usd is None and not r.base.test_mode:   # the fake keeps the runner's own cap
            opts.max_usd = cap_for(opts, prices)
        code = await r.run(opts)
        if r.last_run_id and not opts.probe:
            runs[key] = r.last_run_id
            save_state(self.path, self.state)
        return code, r.last_run_id

    async def step(self, name: str) -> int:
        from horizon.domain.pricing import load_price_table
        from horizon.evals.runner import priced_for

        seed = self.runner_for().base.seed_dir
        if name == "report":
            lines = write_report(self.data_dir, self.state)
            self.out(f"horizon: {len(lines)} report lines")   # the file only: a Windows console can't print "→"
            self.out(f"horizon: the report is in {out_dir(self.data_dir, self.base, self.new)}")
            return 0
        if name == "canary":
            for side, model in (("base", self.base), ("new", self.new)):
                code, run_id = await self._run(f"canary:{side}", Options("canary", decision_model=model, yes=self.yes),
                                               prices=priced_for(load_price_table(seed), model, seed))
                if side == "base" and run_id and run_meta(self.data_dir, run_id).get("status") == "drift":
                    self.out(f"horizon: {self.base} drifted from its own baseline: the comparison stops here, and the "
                             "drift goes to the user (design Risks)")
                    return 1
                if code not in (0,):
                    return code
            return 0
        if name == "probe":
            table = []
            for side, model in (("base", self.base), ("new", self.new)):
                for opts in set_options(model, self.manifest, probe=True, yes=True):
                    r = self.runner_for()
                    await r.run(opts)
                    p = r.last_probe
                    label = opts.suite + (f" --set {opts.set}" if opts.set else "") + (" (Jev parts)" if opts.part else "")
                    if p is not None:
                        self.state["probe"][f"{side}:{label}"] = {"hits": p.hits, "misses": p.misses,
                                                                  "usd": p.would_pay_usd}
                        table.append(f"| {model} | {label} | {p.hits} | {p.misses} | ${p.would_pay_usd:.5f} |")
            save_state(self.path, self.state)
            self.out("\n".join(["| Model | Step | Stored | To pay | Would pay |", "|---|---|---|---|---|", *table]))
            return 0
        if name == "sets":
            worst = 0
            for side, model in (("base", self.base), ("new", self.new)):
                for opts in set_options(model, self.manifest, yes=self.yes):
                    key = f"sets:{side}:{opts.suite}" + (f":{opts.set}" if opts.set else "")
                    code, _ = await self._run(key, opts, prices=priced_for(load_price_table(seed), model, seed))
                    worst = max(worst, code)
            return worst
        if name == "repeat":
            code, _ = await self._run("repeat", Options("compare-repeat", pair=(self.base, self.new), yes=self.yes),
                                      prices=load_price_table(seed))
            return code
        if name in ("timing-a", "timing-b"):
            if name == "timing-b":
                first = self.state["runs"].get("timing-a")
                if not self._done(first):
                    self.out("horizon: run `--step timing-a` first")
                    return 2
                started = dt.datetime.strptime(str(first)[:15], "%Y%m%dT%H%M%S").replace(tzinfo=dt.UTC)
                ready = started + dt.timedelta(hours=WINDOW_GAP_H)
                if self.now() < ready:
                    self.out(f"horizon: the second timing window must start ≥ {WINDOW_GAP_H:.0f} h after the first "
                             f"(from {ready.isoformat(timespec='minutes')}); nothing was sent")
                    return 2
            code, _ = await self._run(name, Options("compare-timing", pair=(self.base, self.new), part=name[-1],
                                                    against=self.manifest, yes=self.yes),
                                      prices=load_price_table(seed))
            return code
        raise ValueError(f"unknown step {name!r} (have: {', '.join(STEPS)})")

    async def all_steps(self) -> int:
        for name in STEPS:
            code = await self.step(name)
            if code != 0:
                return code
        return 0


# ── pairing and scoring (D8) ──
def item_sets() -> dict[str, str]:
    """Each decisions item's dataset folder, by id ($0)."""
    from horizon.evals.suites import DATASETS, dataset_files, load_dataset

    return {str(i["id"]): p.relative_to(DATASETS).parts[0] for p in dataset_files() for i in load_dataset(p)}


def _en(r: Row) -> bool:
    return str(r.get("lang") or "en") == "en"


def _yes(r: Row) -> bool:
    return str(r["label"]) == "yes"


def _pl(rows: Sequence[Row]) -> list[tuple[float, bool]]:
    return [(float(r["p"]), _yes(r)) for r in rows if r.get("p") is not None and not r.get("invalid") and _en(r)]


def _floor(qid: str) -> float:
    f = bank().get(qid).floor
    return float(f if f is not None else 0.6)


def _threshold(qid: str, name: str) -> float:
    return float(bank().get(qid).thresholds.get(name, 0.5))


def _noul(r: Row, t: float) -> bool | None:
    return None if r.get("p") is None or r.get("invalid") else (float(r["p"]) >= t) == _yes(r)


def _emo_label(r: Row) -> dict[str, Any]:
    from horizon.ai.agent.emotion import merges

    return {**r["label"], "merge": merges(str(r.get("question_id") or ""))}


def _choice(r: Row) -> Any:
    return None if r.get("invalid") else policies.answer_of(r)


@dataclass(frozen=True)
class Group:
    """One scored group of a set: which rows, the live value per row, the per-item rule, and the dev chooser."""
    set: str
    name: str
    knob: str
    select: Callable[[Row], bool]
    live: Callable[[Row], float]
    correct: Callable[[Row, float], bool | None]
    choose: Callable[[list[Row]], float | None] | None


def _emotion_correct(r: Row, v: float) -> bool | None:
    if r.get("invalid") or not isinstance(r.get("label"), Mapping):
        return None
    lab = _emo_label(r)
    return policies.emotion_correct(policies.emotion_answer(_choice(r), lab, v), lab)


def _emotion_choose(rows: list[Row]) -> float | None:
    dev = [(_choice(r), _emo_label(r)) for r in rows if not r.get("invalid")]
    return float(policies.choose_floor(dev, "emotion")["floor"]) if dev else None


def _reaction_correct(r: Row, v: float) -> bool | None:
    if r.get("invalid") or not isinstance(r.get("label"), Mapping):
        return None
    return policies.reaction_correct(policies.reaction_answer(_choice(r), r["label"], v), r["label"])


def _reaction_choose(rows: list[Row]) -> float | None:
    dev = [(_choice(r), r["label"]) for r in rows if not r.get("invalid")]
    return float(policies.choose_floor(dev, "reaction")["floor"]) if dev else None


def _who(part: str) -> Group:
    def correct(r: Row, v: float) -> bool | None:
        if r.get("invalid"):
            return None
        return who_policies.who_correct(part, who_policies.who_answer(part, _choice(r), r["label"], v), r["label"])

    def choose(rows: list[Row]) -> float | None:
        dev = [(_choice(r), r["label"]) for r in rows if not r.get("invalid") and not r.get("fresh")]
        return float(who_policies.choose_who_floor(part, dev)["floor"]) if dev else None

    return Group("who_speaks", part, "floor", lambda r: r["question_id"] == part, lambda r: _floor(part), correct,
                 choose)


def _member_correct(r: Row, v: float) -> bool | None:
    if r.get("invalid"):
        return None
    return who_policies.member_correct(who_policies.member_answer(_choice(r), r["label"], v), r["label"])


def _member_choose(rows: list[Row]) -> float | None:
    dev = [(_choice(r), r["label"]) for r in rows if not r.get("invalid")]
    return float(who_policies.choose_member_floor(dev)["floor"]) if dev else None


def _t_end(rows: list[Row]) -> float | None:
    t = who_policies.choose_t_end([(r.get("p"), str(r["label"])) for r in rows if not r.get("invalid")])["t_end"]
    return None if t is None else float(t)


def _docs_confident(rows: list[Row]) -> float | None:
    pl = _pl(rows)
    tg = m12_sets.choose_t_gate(pl)
    return None if tg is None else m12_sets.choose_t_confident(pl, tg)


def _noul_group(set_: str, qid: str, knob: str, choose: Callable[[list[tuple[float, bool]]], float | None] | None,
                name: str | None = None) -> Group:
    return Group(set_, name or qid, knob, lambda r: r["question_id"] == qid, lambda r: _threshold(qid, knob), _noul,
                 (lambda rows: choose(_pl(rows))) if choose is not None else None)


def _importance_correct(r: Row, _v: float) -> bool | None:
    return None if r.get("invalid") or r.get("answer") is None else int(r["answer"]) == int(r["label"])


GROUPS: tuple[Group, ...] = (
    Group("emotion", "emotion", "floor", lambda r: str(r["question_id"]).startswith("emotion_") and r.get("kind") != "debate",
          lambda r: _floor(str(r["question_id"])), _emotion_correct, _emotion_choose),
    Group("emotion", "emotion (debate slice)", "floor",
          lambda r: str(r["question_id"]).startswith("emotion_") and r.get("kind") == "debate",
          lambda r: _floor(str(r["question_id"])), _emotion_correct, _emotion_choose),
    Group("reactions", "reaction", "floor", lambda r: r["question_id"] == "reaction" and r.get("kind") != "debate",
          lambda r: _floor("reaction"), _reaction_correct, _reaction_choose),
    Group("reactions", "reaction (debate slice)", "floor",
          lambda r: r["question_id"] == "reaction" and r.get("kind") == "debate",
          lambda r: _floor("reaction"), _reaction_correct, _reaction_choose),
    *(_who(part) for part in who_policies.PARTS),
    Group("debate_member", "debate member", "floor", lambda r: r["question_id"] in who_policies.MEMBER_QIDS,
          lambda r: _floor(str(r["question_id"])), _member_correct, _member_choose),
    Group("talk_finished", "talk_finished", "t_end", lambda r: r["question_id"] == "talk_finished",
          lambda r: _threshold("talk_finished", "t_end"), _noul, _t_end),
    _noul_group("docs", "docs", "t_gate", m12_sets.choose_t_gate),
    Group("docs", "docs (t_confident)", "t_confident", lambda r: r["question_id"] == "docs",
          lambda r: _threshold("docs", "t_confident"), _noul, _docs_confident),
    _noul_group("standalone", "standalone", "t_standalone", m12_sets.choose_t_standalone),
    _noul_group("english", "english", "english", None),
    Group("importance", "importance (exact level)", "levels", lambda r: r["question_id"] == "importance",
          lambda r: 0.0, _importance_correct, None),
    _noul_group("memory_guard", "memory_guard", "t_keep", m13_sets.choose_t_keep),
    _noul_group("earlier", "earlier", "t_gate", m12_sets.choose_t_gate),
    _noul_group("recall", "recall", "t_recall", m13_sets.choose_t_recall),
    _noul_group("same_fact", "same_fact", "t_same", m13_sets.choose_t_same),
)


def smallest_showable(n: int) -> float | None:
    """The smallest accuracy difference an exact McNemar test at p < 0.05 could show on n paired items: every
    discordant pair one way (it needs 6)."""
    for c in range(1, n + 1):
        if mcnemar_exact(0, c) < 0.05:
            return c / n
    return None


def paired(base: Mapping[str, bool | None], new: Mapping[str, bool | None]) -> dict[str, Any]:
    """Both models scored on the same items: counts, Wilson intervals, the discordant pairs and the exact McNemar p.
    An item scored on only one side (unanswered on the other) is left out and counted."""
    both = sorted(k for k in base.keys() & new.keys() if base[k] is not None and new[k] is not None)
    k_base = sum(1 for k in both if base[k])
    k_new = sum(1 for k in both if new[k])
    b = sum(1 for k in both if base[k] and not new[k])
    c = sum(1 for k in both if new[k] and not base[k])
    n = len(both)
    p = mcnemar_exact(b, c)
    return {"n": n, "base": k_base, "new": k_new, "base_ci": wilson(k_base, n), "new_ci": wilson(k_new, n),
            "b": b, "c": c, "p": p, "moves": p < 0.05,
            "unpaired": len(base.keys() | new.keys()) - n, "smallest": smallest_showable(n) if n else None}


def score_group(g: Group, base_rows: Sequence[Row], new_rows: Sequence[Row]) -> dict[str, Any]:
    """D8 for one group: drop-in on dev and test (both at the live values); re-tuned: the candidate's value chosen on
    its dev rows, recorded, then its test rows read once at it, beside the base at its live values."""
    def key(r: Row) -> str:
        return f"{r['question_id']}|{r['id']}"

    mine_b = [r for r in base_rows if g.select(r) and _en(r)]
    mine_n = [r for r in new_rows if g.select(r) and _en(r)]
    out: dict[str, Any] = {"set": g.set, "group": g.name, "knob": g.knob}
    for split in ("dev", "test"):
        live_b = {key(r): g.correct(r, g.live(r)) for r in mine_b if r.get("split") == split}
        live_n = {key(r): g.correct(r, g.live(r)) for r in mine_n if r.get("split") == split}
        out[f"drop_in_{split}"] = paired(live_b, live_n)
    live_values = sorted({g.live(r) for r in mine_b + mine_n})
    out["live"] = live_values
    if g.choose is None:
        out["retuned"] = {**out["drop_in_test"], "note": "no rule to tune: the drop-in figure repeats"}
        return out
    dev_new = [r for r in mine_n if r.get("split") == "dev"]
    chosen = g.choose(dev_new)   # chosen from dev rows alone, before any test row is read
    dev_base = [r for r in mine_b if r.get("split") == "dev"]
    out["chosen"] = chosen
    out["base_rechosen"] = g.choose(dev_base) if dev_base else None   # does 1.13's own re-tune still give the live value?
    if chosen is None:
        out["retuned"] = {**out["drop_in_test"], "note": "the chooser found no value on dev: the drop-in figure repeats"}
        return out
    base_live = {key(r): g.correct(r, g.live(r)) for r in mine_b if r.get("split") == "test"}
    new_tuned = {key(r): g.correct(r, chosen) for r in mine_n if r.get("split") == "test"}
    out["retuned"] = paired(base_live, new_tuned)
    return out


# ── safety: its knobs, leave-one-out (no split; D8) ──
def safety_scores(base_rows: Sequence[Row], new_rows: Sequence[Row]) -> list[dict[str, Any]]:
    from horizon.evals.safety_suite import CUT, choose, threshold

    out = []
    for kb in CUT:
        def mine(rows: Sequence[Row], kb: Any = kb) -> list[Row]:
            return [r for r in rows if r.get("part") == kb.part and r.get("label") in (*kb.pos, *kb.neg)
                    and (r.get("p") or {}).get(kb.qid) is not None]

        def right(r: Row, t: float, kb: Any = kb) -> bool:
            p = float(r["p"][kb.qid])
            return p >= t if r["label"] in kb.pos else p < t

        def loo(rows: Sequence[Row], kb: Any = kb) -> dict[str, bool | None]:
            """Each item scored at the threshold chosen without it (safety D21's leave-one-out)."""
            res: dict[str, bool | None] = {}
            for i, r in enumerate(rows):
                rest = [x for j, x in enumerate(rows) if j != i]
                pos = [float(x["p"][kb.qid]) for x in rest if x["label"] in kb.pos]
                neg = [float(x["p"][kb.qid]) for x in rest if x["label"] in kb.neg]
                res[str(r["sha256"])] = right(r, choose(pos, neg, kb.rule, kb.share))
            return res

        rb, rn = mine(base_rows), mine(new_rows)
        if not rb and not rn:
            continue
        cur = threshold(kb.qid, kb.knob)
        live_b = {str(r["sha256"]): right(r, cur) for r in rb}
        live_n = {str(r["sha256"]): right(r, cur) for r in rn}
        full_n = choose([float(x["p"][kb.qid]) for x in rn if x["label"] in kb.pos],
                        [float(x["p"][kb.qid]) for x in rn if x["label"] in kb.neg], kb.rule, kb.share) if rn else None
        out.append({"set": f"safety:{kb.part}", "group": kb.knob, "knob": kb.knob, "live": [cur],
                    "drop_in_test": paired(live_b, live_n), "chosen": full_n,
                    "retuned": {**paired(live_b, loo(rn)), "note": "leave-one-out (safety has no split)"}})
    return out


# ── deep-check: form and direction only (no rule to tune) ──
def deep_check_direction(r: Row) -> bool | None:
    if r.get("invalid"):
        return None
    if r.get("part") == "passage":
        return None if r.get("top") is None else int(r["top"]) == int(r["expect"])
    if r.get("part") == "set":
        return None if r.get("p") is None else (float(r["p"]) >= 0.5) == (r["expect"] == "yes")
    exp = r.get("expect") or {}
    oks = []
    for k, want in exp.items():
        if r.get(k) is None:
            return None
        knob = "t_standalone" if k == "standalone" else "english"
        oks.append((float(r[k]) >= _threshold(k, knob)) == (want == "yes"))
    return all(oks) if oks else None


# ── the behaviour figures (D9) ──
def calibration(pl: Sequence[tuple[float, bool]]) -> dict[str, Any]:
    """Ten p-bins: yes-rate against mean p, and the expected calibration error."""
    bins: dict[int, list[tuple[float, bool]]] = {}
    for p, y in pl:
        bins.setdefault(min(9, int(p * 10)), []).append((p, y))
    n = len(pl)
    table = {f"{k / 10:.1f}": {"n": len(v), "mean_p": round(sum(p for p, _ in v) / len(v), 4),
                                "yes_rate": round(sum(y for _, y in v) / len(v), 4)} for k, v in sorted(bins.items())}
    ece = sum(len(v) / n * abs(sum(y for _, y in v) / len(v) - sum(p for p, _ in v) / len(v))
              for v in bins.values()) if n else 0.0
    return {"n": n, "ece": round(ece, 4), "bins": table}


def order_figures(rows: Sequence[Row], items: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Choices asked in both orders: the flip rate, the first-listed option's share in each order, and how often an
    item gets the first option in both (position-driven)."""
    from horizon.ai.decider import Choice
    from horizon.evals.suites import item_question

    n = flips = first_d = first_r = both = 0
    for r in rows:
        if r.get("invalid") or r.get("answer") is None or r.get("answer_reversed") is None:
            continue
        item = items.get(str(r["id"]))
        if item is None:
            continue
        q = item_question(dict(item))   # the live seeded order, as the suite asked it
        if not isinstance(q, Choice) or len(q.options) < 2:
            continue
        opts = list(q.options)
        n += 1
        flips += r["answer"] != r["answer_reversed"]
        d, rv = r["answer"] == opts[0], r["answer_reversed"] == opts[-1]   # reversed: the last becomes the first
        first_d += d
        first_r += rv
        both += d and rv
    def rate(k: int) -> float:
        return round(k / n, 4) if n else 0.0

    return {"n": n, "flip": rate(flips), "first_declared": rate(first_d), "first_reversed": rate(first_r),
            "first_both": rate(both)}


def turn_cost(data_dir: Path, prices: Mapping[str, float]) -> dict[str, Any] | None:
    """D9: a 1:1 reply's Jev input tokens (M15's latency run: turn_plan, guardrail, face_check, reaction per turn) at
    each model's price per million. Computed, never paid."""
    rows = ledger(data_dir, LIVE_LATENCY_RUN)
    turns = sum(1 for r in rows if r["purpose"] == "turn_plan")
    if not turns:
        return None
    tokens = sum(int(r["tokens_in"] or 0) for r in rows if r["purpose"] in TURN_PURPOSES) / turns
    return {"turns": turns, "tokens_per_turn": round(tokens, 1),
            "usd_per_turn": {m: round(tokens * per_m / 1e6, 8) for m, per_m in prices.items()}}


# ── timing and repeat (D10, D11) ──
def timing_figures(rows: Sequence[Row]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for r in rows:
        if r.get("warmup") or r.get("error"):
            continue
        out.setdefault(str(r["model"]), {}).setdefault(str(r["bucket"]), {}).setdefault(str(r["window"]), []).append(
            float(r["ms"]))
    stats: dict[str, Any] = {}
    for m, by in out.items():
        for b, wins in by.items():
            for w, ms in wins.items():
                stats.setdefault(m, {}).setdefault(b, {})[w] = {
                    "n": len(ms), **{f"p{int(q * 100)}": percentile(ms, q) for q in (0.5, 0.9, 0.99)},
                    **{f"p{int(q * 100)}_ci": percentile_ci(ms, q) for q in (0.5, 0.9, 0.99)}}
    warm = sum(1 for r in rows if r.get("warmup"))
    errors: dict[str, int] = {}
    for r in rows:
        if r.get("error"):
            k = f"{r['model']} {r['bucket']}: {r['error']} {r.get('status') or ''}".strip()
            errors[k] = errors.get(k, 0) + 1
    return {"stats": stats, "warmup_excluded": warm, "errors": errors,
            "padded": len({r["hash"] for r in rows if r.get("padded") and not r.get("warmup")})}


def deadline_misses(rows: Sequence[Row], deadlines: Mapping[str, float],
                    weights: Mapping[str, Mapping[str, float]]) -> dict[str, dict[str, float]]:
    """D10: each live purpose's projected miss rate per model: Σ over buckets of the purpose's live share in the
    bucket × the share of the bucket's (both windows') latencies above the purpose's deadline."""
    by: dict[str, dict[str, list[float]]] = {}
    for r in rows:
        if not r.get("warmup") and not r.get("error"):
            by.setdefault(str(r["model"]), {}).setdefault(str(r["bucket"]), []).append(float(r["ms"]))
    out: dict[str, dict[str, float]] = {}
    for purpose, deadline in deadlines.items():
        w = weights.get(purpose)
        if not w:
            continue
        for m, buckets in by.items():
            miss = sum(share * (sum(1 for x in buckets.get(b, []) if x > deadline) / len(buckets[b]))
                       for b, share in w.items() if buckets.get(b))
            out.setdefault(purpose, {})[m] = round(miss, 4)
    return out


FIXED_WEIGHTS = {"turn_plan": {"1k-2.5k": 1.0}, "guardrail": {"<1k": 1.0}, "guardrail_prompt": {"<1k": 1.0},
                 "face_check": {"<1k": 1.0}, "reaction": {"1k-2.5k": 1.0}, "follow_plan": {"1k-2.5k": 1.0},
                 "debate_plan": {"2.5k-4k": 1.0}, "deep_check": {"<1k": 1.0}, "route": {"<1k": 1.0}}


def live_weights(data_dir: Path) -> tuple[dict[str, dict[str, float]], str]:
    """Each live purpose's share of requests per size bucket, from M15's latency run ledger; D10's fixed mapping when
    that run isn't on this machine."""
    from horizon.evals.compare_probes import bucket_of

    rows = ledger(data_dir, LIVE_LATENCY_RUN)
    if not rows:
        return FIXED_WEIGHTS, "fixed (D10's live sizes; M15's latency run isn't on this machine)"
    out: dict[str, dict[str, float]] = {}
    for p in {r["purpose"] for r in rows}:
        mine = [bucket_of(max(0, int(r["tokens_in"] or 0) - 200)) for r in rows if r["purpose"] == p]   # Jev's overhead
        named = [b for b in mine if b]
        out[p] = {b: round(named.count(b) / len(named), 4) for b in sorted(set(named))} if named else {}
    return out, f"M15's latency run `{LIVE_LATENCY_RUN}` (its ledger's input tokens, less Jev's ~200 overhead)"


def repeat_figures(rows: Sequence[Row]) -> dict[str, Any]:
    """Per model: items whose choice changed across the asks, and the largest p and score moves."""
    by: dict[str, dict[str, list[Mapping[str, Any]]]] = {}
    for r in rows:
        by.setdefault(str(r["model"]), {}).setdefault(str(r["id"]), []).append(r["answers"])
    out: dict[str, Any] = {}
    for m, items in by.items():
        changed = 0
        max_p = max_score = 0.0
        for asks in items.values():
            moved = False
            for qid in set().union(*(a.keys() for a in asks)):
                got = [a.get(qid) or {} for a in asks]
                choices = {g.get("choice") for g in got if "choice" in g}
                moved |= len(choices) > 1
                for k in set().union(*((g.get("probabilities") or {}).keys() for g in got)):
                    ps = [float((g.get("probabilities") or {}).get(k, 0.0)) for g in got]
                    max_p = max(max_p, max(ps) - min(ps))
                nouls = [float(g["noul"]) for g in got if "noul" in g]
                if nouls:
                    max_p = max(max_p, max(nouls) - min(nouls))
                scores = [float(g["score"]) for g in got if "score" in g]
                if scores:
                    max_score = max(max_score, max(scores) - min(scores))
            changed += moved
        out[m] = {"items": len(items), "changed": changed, "max_p_move": round(max_p, 4),
                  "max_score_move": round(max_score, 4)}
    return out


# ── the report (D8, D9, D18) ──
def _shown(path: str) -> str:
    """A path as the committed report shows it: relative to the repo when it is inside it (no local user folder)."""
    try:
        return Path(path).resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return Path(path).name


def _local(run_id: str) -> str:
    """A run id's UTC start, in Kuala Lumpur time."""
    from zoneinfo import ZoneInfo

    at = dt.datetime.strptime(run_id[:15], "%Y%m%dT%H%M%S").replace(tzinfo=dt.UTC)
    return at.astimezone(ZoneInfo("Asia/Kuala_Lumpur")).strftime("%Y-%m-%d %H:%M")


def _ms_ci(c: tuple[float, float] | None) -> str:
    return f"{c[0]:.0f}–{c[1]:.0f}" if c else "—"


def _ci(x: tuple[float, float]) -> str:
    return f"{x[0]:.2f}–{x[1]:.2f}"


def _pair_line(p: Mapping[str, Any]) -> str:
    if not p.get("n"):
        return "no paired items"
    verdict = ("**moves**" if p["moves"] else
               f"no difference shown (the smallest {p['n']} items could show: {p['smallest']:.2f})"
               if p.get("smallest") is not None else "no difference shown")
    return (f"{p['base']}/{p['n']} ({_ci(p['base_ci'])}) vs {p['new']}/{p['n']} ({_ci(p['new_ci'])}); b {p['b']}, "
            f"c {p['c']}, McNemar p {p['p']:.3f}: {verdict}")


def _runs(state: Mapping[str, Any], prefix: str) -> list[str]:
    return [v for k, v in state.get("runs", {}).items() if k.startswith(prefix) and v]


def collect(data_dir: Path, state: Mapping[str, Any]) -> dict[str, Any]:
    """Every saved row the report reads, by side and suite; nothing is sent."""
    sides: dict[str, dict[str, list[dict[str, Any]]]] = {"base": {}, "new": {}}
    meta: dict[str, list[dict[str, Any]]] = {"base": [], "new": []}
    for side in ("base", "new"):
        for run_id in _runs(state, f"sets:{side}:"):
            m = run_meta(data_dir, run_id)
            key = str(m.get("suite")) + (":judges" if m.get("set") == "judges" else "")
            sides[side].setdefault(key, []).extend(run_rows(data_dir, run_id))
            meta[side].append({**m, "ledger": ledger(data_dir, run_id)})
    runs = state.get("runs", {})
    return {"sides": sides, "meta": meta,
            "canary": {s: run_rows(data_dir, runs[f"canary:{s}"]) for s in ("base", "new") if runs.get(f"canary:{s}")},
            "repeat": run_rows(data_dir, runs["repeat"]) if runs.get("repeat") else [],
            "timing": [row for w in ("timing-a", "timing-b") if runs.get(w) for row in run_rows(data_dir, runs[w])]}


def not_in_manifest(manifest: Mapping[str, Any]) -> list[str]:
    """Items whose body the manifest doesn't list (set, id), for the report ($0)."""
    from horizon.evals.manifest import allowed, item_hashes

    ok = allowed(manifest)
    return sorted(f"{s}: {i}" for (s, i), hs in item_hashes(test_mode=True).items() if any(h not in ok for h in hs))


def build_report(data_dir: Path,
                 state: Mapping[str, Any]) -> tuple[list[str], dict[str, Any], dict[str, list[dict[str, Any]]]]:
    """(report lines, figures, per-item rows by file). Reads saved rows only."""
    from horizon.domain.pricing import load_price_table
    from horizon.evals import judges
    from horizon.evals.safety_suite import CUT
    from horizon.evals.suites import all_items

    base, new = str(state["base"]), str(state["new"])
    got = collect(data_dir, state)
    sides = got["sides"]
    sets_of = item_sets()
    manifest = json.loads(Path(str(state["manifest"])).read_text(encoding="utf-8"))
    figures: dict[str, Any] = {"base": base, "new": new, "generated": dt.datetime.now(dt.UTC).isoformat()}
    lines = [f"# Jev comparison: {base} vs {new}", "",
             f"- manifest `{_shown(str(state['manifest']))}`; base runs {', '.join(_runs(state, 'sets:base:')) or '—'}; candidate "
             f"runs {', '.join(_runs(state, 'sets:new:')) or '—'}",
             "- b: items only the base got right; c: only the candidate. A set **moves** only at McNemar p < 0.05.",
             "- English items are scored (the English-first rule). Re-tuned: the candidate's value chosen on its dev "
             "rows, then read on test once, against the base at its live values.", ""]
    # canary
    can = got["canary"]
    if can:
        lines.append("## Canary")
        for s, rows in can.items():
            drift = [r for r in rows if r.get("drift")]
            lines.append(f"- {base if s == 'base' else new}: {len(rows) - len(drift)}/{len(rows)} within tolerance "
                         f"of {'its own baseline' if s == 'base' else base + chr(39) + 's answers (its first run)'}")
            lines += [f"  - {r['id']}: " + "; ".join(r["drift"]) for r in drift]
        figures["canary"] = {s: {"n": len(r), "drift": sum(1 for x in r if x.get("drift"))} for s, r in can.items()}
        lines.append("")
    # the sets
    dec_b = [{**r, "set": sets_of.get(str(r["id"]))} for r in sides["base"].get("decisions", [])]
    dec_n = [{**r, "set": sets_of.get(str(r["id"]))} for r in sides["new"].get("decisions", [])]
    scored = [score_group(g, [r for r in dec_b if r["set"] == g.set], [r for r in dec_n if r["set"] == g.set])
              for g in GROUPS]
    scored = [s for s in scored if s["drop_in_test"]["n"] or s["drop_in_dev"]["n"]]
    scored += safety_scores(sides["base"].get("safety", []), sides["new"].get("safety", []))
    figures["sets"] = scored
    lines += ["## Accuracy per set (paired)", "",
              "| Set | Group | Live | Drop-in, test | Re-tuned, test (candidate's value) |", "|---|---|---|---|---|"]
    for s in scored:
        live = ", ".join(f"{v:g}" for v in s.get("live") or []) or "—"
        chosen = s.get("chosen")
        tuned = s["retuned"]
        note = f" ({tuned['note']})" if tuned.get("note") else ""
        lines.append(f"| {s['set']} | {s['group']} | {s['knob']} {live} | {_pair_line(s['drop_in_test'])} | "
                     f"{'—' if chosen is None else f'{chosen:g}'}: {_pair_line(tuned)}{note} |")
    lines.append("")
    moved = [s for s in scored if s["drop_in_test"].get("moves") or s["retuned"].get("moves")]
    lines.append(f"- sets that move: {', '.join(s['set'] + '/' + s['group'] for s in moved) or 'none'}")
    rechosen = [s for s in scored if s.get("base_rechosen") is not None and s["base_rechosen"] not in (s.get("live") or [])]
    if rechosen:
        lines.append("- the base's own dev re-tune today differs from its live value on: " + ", ".join(
            f"{s['group']} ({s['base_rechosen']:g} vs {', '.join(f'{v:g}' for v in s['live'])})" for s in rechosen))
    lines.append("")
    # by mode
    modes = sorted({str(r.get("kind")) for r in dec_n if r.get("kind")})
    if modes:
        lines += ["### Drop-in by mode (test, every set with the item's `kind`)", ""]
        figures["by_mode"] = {}
        for mode in modes:
            res_b: dict[str, bool | None] = {}
            res_n: dict[str, bool | None] = {}
            for g in GROUPS:
                for rows, res in ((dec_b, res_b), (dec_n, res_n)):
                    for r in rows:
                        if r["set"] == g.set and g.select(r) and r.get("kind") == mode and r.get("split") == "test" \
                                and _en(r):
                            res[f"{g.name}|{r['question_id']}|{r['id']}"] = g.correct(r, g.live(r))
            pr = paired(res_b, res_n)
            figures["by_mode"][mode] = pr
            lines.append(f"- {mode}: {_pair_line(pr)}")
        lines.append("")
    # deep-check
    dc_b = {f"{r['part']}|{r['id']}": deep_check_direction(r) for r in sides["base"].get("deep-check", [])}
    dc_n = {f"{r['part']}|{r['id']}": deep_check_direction(r) for r in sides["new"].get("deep-check", [])}
    if dc_b or dc_n:
        pr = paired(dc_b, dc_n)
        figures["deep_check"] = pr
        lines += ["## deep-check (form and direction only; the passage thresholds are the known gap)", "",
                  f"- {_pair_line(pr)}", ""]
    # judges
    jb, jn = sides["base"].get("decisions:judges", []), sides["new"].get("decisions:judges", [])
    if jb or jn:
        lines += ["## Judges (information only: the candidate's figures validate no judge)", "",
                  "| Judge | Base B4 | Candidate B4 | Paired accuracy |", "|---|---|---|---|"]
        figures["judges"] = {}
        for qid in sorted({str(r["question_id"]) for r in jb + jn}):
            rb = [r for r in jb if r["question_id"] == qid and "correct" in r]
            rn = [r for r in jn if r["question_id"] == qid and "correct" in r]
            b4b, b4n = judges.b4_for(qid, rb), judges.b4_for(qid, rn)
            pr = paired({str(r["id"]): bool(r["correct"]) for r in rb}, {str(r["id"]): bool(r["correct"]) for r in rn})
            figures["judges"][qid] = {"base_passed": b4b["passed"], "new_passed": b4n["passed"], "paired": pr}
            lines.append(f"| {qid} | {'PASS' if b4b['passed'] else 'FAIL'} | {'PASS' if b4n['passed'] else 'FAIL'} | "
                         f"{_pair_line(pr)} |")
        lines.append("")
    # behaviour
    items = {str(i["id"]): i for i in all_items(judges=True)}
    beh: dict[str, Any] = {}
    lines += ["## Behaviour", ""]
    for side, model, rows in (("base", base, dec_b), ("new", new, dec_n)):
        cal = {}
        for set_ in sorted({str(r["set"]) for r in rows if r.get("p") is not None}):
            pl = _pl([r for r in rows if r["set"] == set_ and str(r["label"]) in ("yes", "no")])
            if pl:
                cal[set_] = calibration(pl)
        safety_pl: dict[str, list[tuple[float, bool]]] = {}
        seen: set[tuple[str, str]] = set()   # tFlag and tBlock read the same answers: each (item, question) once
        for sr in sides[side].get("safety", []):   # safety's nouls: "yes" = the item should trip the check
            for kb in CUT:
                p = (sr.get("p") or {}).get(kb.qid)
                if sr.get("part") == kb.part and p is not None and sr.get("label") in (*kb.pos, *kb.neg) \
                        and (str(sr.get("sha256")), kb.qid) not in seen:
                    seen.add((str(sr.get("sha256")), kb.qid))
                    safety_pl.setdefault(f"safety:{kb.qid}", []).append((float(p), sr["label"] in kb.pos))
        cal.update({k: calibration(v) for k, v in safety_pl.items()})
        order = order_figures(rows, items)
        metas = got["meta"][side]
        errors: dict[str, int] = {}
        for m in metas:
            for e in m.get("errors") or []:
                k = f"{e['code']} {e.get('status') or ''}".strip()
                errors[k] = errors.get(k, 0) + 1
        sent = sum(len(m["ledger"]) for m in metas)
        refused = sum(len(m.get("manifest_refused") or []) for m in metas)
        invalid = sum(1 for k in sides[side] for r in sides[side][k] if r.get("invalid"))
        all_rows = sum(len(v) for v in sides[side].values())
        cost_by: dict[str, Any] = {}
        for r in rows:
            if r.get("sent"):
                c = cost_by.setdefault(str(r["set"]), {"usd": 0.0, "requests": 0})
                c["usd"] += float(r.get("usd") or 0.0)
                c["requests"] += int(r["sent"])
        for m in metas:
            if m.get("suite") in ("deep-check", "safety") and m["ledger"]:
                c = cost_by.setdefault(str(m["suite"]), {"usd": 0.0, "requests": 0})
                c["usd"] += sum(x["usd"] for x in m["ledger"])
                c["requests"] += len(m["ledger"])
        beh[side] = {"model": model, "calibration": cal, "order": order, "errors": errors, "requests_sent": sent,
                     "invalid_rows": invalid, "rows": all_rows, "refused": refused,
                     "cost_per_request": {k: round(v["usd"] / v["requests"], 8) for k, v in cost_by.items()
                                          if v["requests"]}}
        asked = sent + sum(errors.values())
        lines += [f"### {model}",
                  f"- order (choices asked both ways, n {order['n']}): flip {order['flip']:.3f}; first option "
                  f"declared {order['first_declared']:.3f}, reversed {order['first_reversed']:.3f}, both "
                  f"{order['first_both']:.3f}",
                  f"- requests sent {sent} (store hits excluded); provider errors "
                  + (", ".join(f"{k} × {v}/{asked}" for k, v in sorted(errors.items())) or "none")
                  + f"; unanswered rows {invalid}/{all_rows} (of which not in the manifest: {refused})",
                  "- calibration (ECE, n): " + ", ".join(f"{k} {v['ece']:.3f} ({v['n']})" for k, v in sorted(cal.items())),
                  "- cost per request sent: " + (", ".join(f"{k} ${v:.7f}" for k, v in sorted(
                      beh[side]["cost_per_request"].items())) or "— (every answer was stored)"), ""]
    figures["behaviour"] = beh
    prices = load_price_table(SEED)
    tc = turn_cost(data_dir, {base: prices.decision.input_per_m, new: _price_of(new, prices)})
    figures["turn_cost"] = tc
    lines.append("- Jev cost per 1:1 reply (computed from M15's latency run, not paid): " + (
        f"{tc['tokens_per_turn']:.0f} input tokens per turn → " + ", ".join(
            f"{m} ${v:.7f}" for m, v in tc["usd_per_turn"].items()) if tc else "not available (no latency run here)"))
    lines.append("")
    # timing
    if got["timing"]:
        tf = timing_figures(got["timing"])
        weights, source = live_weights(data_dir)
        deadlines = _deadlines()
        misses = deadline_misses(got["timing"], deadlines, weights)
        figures["timing"] = {**tf, "deadline_misses": misses, "weights_source": source}
        lines += ["## Timing (paired probe; store bypassed)", "",
                  f"- warm-up requests excluded: {tf['warmup_excluded']}; padded bodies measured: {tf['padded']} "
                  "(timing only, never scored)",
                  *[f"- window {w[-1]}: run `{state['runs'][w]}`, started {_local(str(state['runs'][w]))} KL"
                    for w in ("timing-a", "timing-b") if state.get("runs", {}).get(w)],
                  "- Jev's latency moves with the hour (M15's run at 07:35 KL: 1.13 p50 ≈ 440 ms); compare the two "
                  "models within a window, and read the projected misses as that hour's only", "",
                  "| Model | Bucket | Window | n | p50 (CI) | p90 (CI) | p99 |", "|---|---|---|---|---|---|---|"]
        for m, by in sorted(tf["stats"].items()):
            for b, wins in by.items():
                for w, st in sorted(wins.items()):
                    lines.append(f"| {m} | {b} | {w} | {st['n']} | {st['p50']:.0f} ({_ms_ci(st['p50_ci'])}) | "
                                 f"{st['p90']:.0f} ({_ms_ci(st['p90_ci'])}) | {st['p99']:.0f} |")
        if tf["errors"]:
            lines.append("- errors: " + ", ".join(f"{k} × {v}" for k, v in sorted(tf["errors"].items())))
        lines += ["", f"### Projected deadline misses (weights: {source})", "",
                  "| Purpose | Deadline ms | " + " | ".join(sorted({m for v in misses.values() for m in v})) + " |",
                  "|---|---|" + "---|" * len({m for v in misses.values() for m in v})]
        for purpose, by_m in sorted(misses.items()):
            lines.append(f"| {purpose} | {deadlines[purpose]:.0f} | "
                         + " | ".join(f"{by_m.get(m, 0.0):.3f}" for m in sorted({m for v in misses.values() for m in v}))
                         + " |")
        lines.append("")
    # repeat
    if got["repeat"]:
        rf = repeat_figures(got["repeat"])
        figures["repeat"] = rf
        lines += ["## Repeat (the canary's 20 items × 3, store bypassed)", "", f"- reference: {GROUP_A_REPEAT}"]
        lines += [f"- {m}: {v['changed']} of {v['items']} choices changed; largest p move {v['max_p_move']:.2f}, "
                  f"score move {v['max_score_move']:.2f}" for m, v in sorted(rf.items())]
        lines.append("")
    gone = not_in_manifest(manifest)
    figures["not_in_manifest"] = gone
    lines += ["## Not in the manifest", "",
              f"- {len(gone)} item(s) whose body the manifest doesn't list (sent on neither model)"
              + (": " + ", ".join(gone[:40]) if gone else ""), ""]
    rows_out = per_item_rows(dec_b, dec_n, sides)
    return lines, figures, rows_out


def _price_of(model: str, prices: Any) -> float:
    from horizon.evals.runner import priced_for

    seed = SEED
    return float(priced_for(prices, model, seed).decision.input_per_m)


def _deadlines() -> dict[str, float]:
    """The live Jev deadlines (ms): `pricing.json` gateway timeouts, and the retrieval checks from `runtime.json`."""
    seed = SEED
    t = json.loads((seed / "pricing.json").read_text(encoding="utf-8"))["data"]["gateway"]["timeoutsMs"]["decision"]
    rt = json.loads((seed / "runtime.json").read_text(encoding="utf-8"))["data"]["runtime"]["retrieval"]["agent"]
    out = {k: float(v) for k, v in t.items() if k in ("route", "turn_plan", "follow_plan", "debate_plan", "guardrail",
                                                      "guardrail_prompt", "reaction", "face_check")}
    out["deep_check"] = float(rt["deepCheckMs"])
    return out


def per_item_rows(dec_b: Sequence[Row], dec_n: Sequence[Row],
                  sides: Mapping[str, Mapping[str, Sequence[Row]]]) -> dict[str, list[dict[str, Any]]]:
    """D18's per-item rows, both models side by side; safety items by hash only (no id, no text)."""
    keep = ("answer", "answer_reversed", "p", "score", "confidence", "invalid")
    out: dict[str, list[dict[str, Any]]] = {}
    by_n = {(r["question_id"], r["id"]): r for r in dec_n}
    for r in dec_b:
        n = by_n.get((r["question_id"], r["id"]), {})
        out.setdefault(str(r.get("set") or "unknown"), []).append(
            {"id": r["id"], "question_id": r["question_id"], "split": r.get("split"), "lang": r.get("lang"),
             "kind": r.get("kind"), "label": r["label"], "base": {k: r[k] for k in keep if k in r},
             "new": {k: n[k] for k in keep if k in n}})
    sn = {str(r.get("sha256")): r for r in sides["new"].get("safety", [])}
    for r in sides["base"].get("safety", []):
        n = sn.get(str(r.get("sha256")), {})
        out.setdefault("safety", []).append({"sha256": r.get("sha256"), "part": r.get("part"), "label": r.get("label"),
                                             "base": {"p": r.get("p")}, "new": {"p": n.get("p")}})
    dn = {(r.get("part"), r.get("id")): r for r in sides["new"].get("deep-check", [])}
    for r in sides["base"].get("deep-check", []):
        n = dn.get((r.get("part"), r.get("id")), {})
        out.setdefault("deep-check", []).append({"id": r.get("id"), "part": r.get("part"), "expect": r.get("expect"),
                                                 "base": {k: v for k, v in r.items() if k not in ("id", "part", "expect")},
                                                 "new": {k: v for k, v in n.items() if k not in ("id", "part", "expect")}})
    return out


def write_report(data_dir: Path, state: Mapping[str, Any]) -> list[str]:
    lines, figures, rows = build_report(data_dir, state)
    d = out_dir(data_dir, str(state["base"]), str(state["new"]))
    (d / "rows").mkdir(parents=True, exist_ok=True)
    (d / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (d / "figures.json").write_text(json.dumps(figures, indent=1, ensure_ascii=False, default=list) + "\n",
                                    encoding="utf-8")
    for name, rs in rows.items():
        (d / "rows" / f"{name}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rs),
                                                  encoding="utf-8")
    return lines


def report_only_state(data_dir: Path, base: str, new: str, manifest: str, run_ids: Sequence[str]) -> dict[str, Any]:
    """`--report-only RUN…`: the named runs instead of the state file's, each placed by its own `run.json`."""
    state: dict[str, Any] = {"base": base, "new": new, "manifest": manifest, "runs": {}}
    for run_id in run_ids:
        m = run_meta(data_dir, run_id)
        if not m:
            raise FileNotFoundError(f"no run.json for run {run_id} under {data_dir / 'evals'}")
        suite = str(m.get("suite"))
        if suite == "compare-repeat":
            state["runs"]["repeat"] = run_id
        elif suite == "compare-timing":
            state["runs"][f"timing-{m.get('part')}"] = run_id
        else:
            side = "base" if m.get("decision_model") == base else "new" if m.get("decision_model") == new else None
            if side is None:
                raise ValueError(f"run {run_id} asked {m.get('decision_model')}, neither {base} nor {new}")
            prefix = "canary" if suite == "canary" else f"sets:{side}:{suite}" + (f":{m['set']}" if m.get("set") else "")
            state["runs"][f"canary:{side}" if suite == "canary" else prefix] = run_id
    return state

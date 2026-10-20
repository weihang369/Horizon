"""`horizon eval <suite>`: one runner, isolated copies, spend that can't run away (docs/ai/02 B7, B12; evaluation-harness
spec; ai-foundation design D33–D35; tasks 7.3, 7.5–7.7).

The run lifecycle:
1. **Plan and estimate** from the suite's planned requests, and print today's eval spend (`data/evals/spend.jsonl`).
2. **Off-peak check:** a paid run that would overlap DeepSeek's peak by its expected end refuses unless `--allow-peak`.
3. **Ask** `y/N` on stdin (`--yes` skips it, used only after the user OKs the estimate in chat). Declining sends
   nothing and leaves no folder.
4. **Isolation:** `data/evals/<run-id>/<profile>/` gets a fresh Config. `HORIZON_AI_*`, `HORIZON_TEST` and
   `HORIZON_DATA_DIR` from the environment are ignored; the key comes from the environment (then the user's
   `secrets.local.json`) and is held in memory only. Its `settings.local.json` caps the day at `--max-usd`
   (default: the estimate × 1.5). The user's own database is never opened.
5. **Run** through the isolated runtime's gateway, so every call is priced in that run's ledger. The runner stops
   itself when the run's ledger reaches `--max-usd`; a budget refusal ends the run `incomplete`, never a wrong answer.
6. **Report:** `report.md` and `results.jsonl` in the run folder; the spend appended to `spend.jsonl`; the newest 20
   run folders kept. M12 (rag D31.4): a paid run's folder is marked `.keep` when it finishes, so a paid output is never
   pruned (M11 lost a source run that way); free smoke runs still are.

Paid suites refuse in test mode. `smoke` runs in either mode: in test mode on the in-process fake ($0).
**The store (D35)** is never attached to the canary, latency or repeatability runs, `capture` or `import`.
"""

from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import SecretStr

from horizon.config import REPO_ROOT, Config
from horizon.domain.clock import FrozenClock, PricingCalendar, calendar_for
from horizon.domain.pricing import PriceTable, estimate_decision_request, load_price_table
from horizon.evals.store import ResponseStore

if TYPE_CHECKING:
    from horizon.runtime import Runtime

EVALS_DIR = REPO_ROOT / "evals"
SAFETY_CACHE = REPO_ROOT / "private" / "evals" / "cache"   # M14 (safety D23): the safety suite's own store
KEEP_RUNS = 20
BYPASS_SUITES = frozenset({"canary", "capture", "import", "latency", "embed-probe"})   # M9 D31: timing never uses the store
PAID_ONLY = frozenset({"canary", "decisions"})
# M15 (images-music D13): a probe never runs a store-bypassing suite, a free one, or a generator that writes committed
# files; and it prices a suite whose items are one request each exactly, any other (chained) one at its whole estimate
NEVER_PROBED = BYPASS_SUITES | frozenset({"smoke", "all", "transcript", "watch-history", "debate-history",
                                          "debate-plant"})
ONE_SHOT = frozenset({"decisions", "deep-check", "debate-quality", "drafter", "summary"})
SMOKE_START = datetime(2026, 10, 3, 3, 0, tzinfo=UTC)   # a Saturday: off-peak, like the test harness


@dataclass
class Options:
    suite: str
    profile: str = "naive"
    limit: int | None = None
    start: int = 0                        # skip the first N planned items (finish an incomplete run without re-paying)
    max_usd: float | None = None
    yes: bool = False
    allow_peak: bool = False
    accept: bool = False
    latency: bool = False
    repeat: bool = False
    set: str | None = None                # decisions: one dataset folder (e.g. `judges`, persona-context D27)
    seed_dir: str | None = None           # a seed folder to run against instead of the repo's (a config experiment)
    force: bool = False                   # M10 watch-history: overwrite a committed history
    mode: str | None = None               # M10 freerun: watch | group
    runs: int | None = None               # M10 freerun: how many scenes or sessions
    turns: int | None = None              # M10 freerun --mode watch: turns per scene
    messages: int | None = None           # M10 freerun --mode group: user lines per session
    part: str | None = None               # M10 latency: follow | watch (None: M9's 1:1 part)
    arm: str | None = None                # M12 retrieval: one comparison arm (rag D23), e.g. `piece=200`
    recut: str | None = None              # M14 safety: re-score and re-cut a saved run (safety D23), no call
    probe: bool = False                   # M15 (images-music D13): serve hits, stop at a miss, send nothing
    against: str | None = None            # M15 (D19): a request manifest; Jev bodies it doesn't list are refused
    short: bool = False                   # M15 transcript (D10): the 7 short `naive` scripts, no drop required
    decision_model: str | None = None     # jev-comparison (D3): ask this Jev model instead of the seed's pinned one


@dataclass
class Plan:
    items: list[Any]
    estimate_usd: float
    expected_s: float
    paid: bool


@dataclass
class Result:
    status: str = "ok"                    # ok | drift | incomplete | failed
    rows: list[dict[str, Any]] = field(default_factory=list)
    summary: list[str] = field(default_factory=list)
    model: str | None = None              # the model id the provider reported (the canary records it)


@dataclass
class RunEnv:
    rt: Runtime
    opts: Options
    store: ResponseStore | None
    run_dir: Path
    max_usd: float

    async def spent(self) -> float:
        from sqlalchemy import func, select

        from horizon.db import tables as t

        async with self.rt.db.read() as conn:
            return float((await conn.execute(select(func.coalesce(func.sum(t.usage_records.c.cost_usd), 0.0))
                                              .where(t.usage_records.c.is_seed.is_(False)))).scalar_one())

    async def over_budget(self) -> bool:
        return await self.spent() >= self.max_usd

    @property
    def decision_model(self) -> str:
        return str(self.rt.gateway.decision_model)

    @property
    def candidate(self) -> bool:
        """jev-comparison (D4): a run on a Jev model other than the seed's pinned one. It never writes the pinned
        model's records: the judges' B4 record, its "already measured" marks, its canary baseline."""
        return self.decision_model != pinned_model(self.rt.seed_settings)

    @property
    def writes_records(self) -> bool:
        """M15 (D13): only a real paid run writes a judge baseline, the measured marks or the private safety folder;
        a probe's answers are fallbacks and the fake's are fake."""
        return not self.opts.probe and not self.rt.cfg.test_mode


def pinned_model(seed_settings: dict[str, Any]) -> str:
    return str(seed_settings["models"]["decision"])


def alias_refusal(model: str | None) -> str | None:
    if model is not None and "latest" in model:
        return f"horizon: --decision-model must be a pinned id, never an alias ({model})"
    return None


def priced_for(prices: PriceTable, model: str | None, seed_dir: Path) -> PriceTable:
    """jev-comparison (D3): a candidate model's own Jev price, when `pricing.json` lists one under `decisionPrices`
    (keyed by model id, read only here); otherwise the pinned model's price, which is right when the two are equal."""
    if not model or model == prices.decision.model:
        return prices
    own = json.loads((seed_dir / "pricing.json").read_text(encoding="utf-8"))["data"].get("decisionPrices", {}).get(model)
    d = prices.decision
    if own is None:
        return replace(prices, decision=replace(d, model=model))
    return replace(prices, decision=replace(d, model=model, input_per_m=float(own["inputPerM"]),
                                            cached_input_per_m=float(own.get("cachedInputPerM", own["inputPerM"])),
                                            output_per_m=float(own.get("outputPerM", 0.0))))


def set_decision_model(rt: Runtime, model: str, prices: PriceTable) -> None:
    """D3: every Jev request of this isolated runtime goes to `model`; nothing on disk changes."""
    rt.gateway.decision_model = model
    rt.gateway.decisions.model = model
    rt.gateway.prices = prices
    if rt.fake is not None:   # the in-process fake lists the model too (it answers any model already)
        rt.fake.models.add(model)


def candidate_refusal(opts: Options, seed_dir: Path) -> str | None:
    """D5: a candidate model's answers can't be stored before its canary baseline exists (they'd carry no salt and be
    lost to it), so every other suite on it waits for the canary."""
    from horizon.evals import canary as canary_mod

    if not opts.decision_model or opts.suite == "canary":
        return None
    seed_dir = Path(opts.seed_dir).resolve() if opts.seed_dir else seed_dir
    pinned = json.loads((seed_dir / "settings.json").read_text(encoding="utf-8"))["data"]["models"]["decision"]
    if opts.decision_model == pinned or canary_mod.fingerprint_for(EVALS_DIR, opts.decision_model) is not None:
        return None
    return (f"horizon: {opts.decision_model} has no canary baseline yet; run "
            f"`horizon eval canary --decision-model {opts.decision_model}` first (nothing was sent)")


def store_for(opts: Options, data_dir: Path, fingerprint: str | None, *, test_mode: bool = False) -> ResponseStore | None:
    """D35: the runner, not the caller, decides; these runs never read or write the store. A test-mode run (the
    in-process fake) never touches it either: a fake answer saved there would later be served to a paid run as real
    (persona-context 10.2 found `smoke` had done exactly that)."""
    if (test_mode and not opts.probe) or opts.suite in BYPASS_SUITES or opts.latency or opts.repeat:
        return None
    if opts.suite == "safety":   # M14 (safety D23, W10): its private items never enter `data/cache/`
        return ResponseStore.eval_view(SAFETY_CACHE, fingerprint)
    return ResponseStore.eval_view(data_dir / "cache", fingerprint)


# ── spend and runs on disk ──
def spend_file(data_dir: Path) -> Path:
    return data_dir / "evals" / "spend.jsonl"


def spent_today(data_dir: Path, cal: PricingCalendar, now: datetime) -> float:
    p = spend_file(data_dir)
    if not p.is_file():
        return 0.0
    today = cal.today(now)
    total = 0.0
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            if cal.today(datetime.fromisoformat(rec["at"])) == today:
                total += float(rec["usd"])
    return total


def prune_runs(runs_dir: Path, keep: int = KEEP_RUNS) -> list[str]:
    if not runs_dir.is_dir():
        return []
    # a run holding a `.keep` file is a dataset's source (evals/datasets/judges/labels.json `_sources`): never pruned.
    # 10.6 lost three source runs to this pruning before the marker existed.
    runs = sorted(p for p in runs_dir.iterdir() if p.is_dir() and p.name[:1].isdigit() and not (p / ".keep").exists())
    gone = runs[:-keep] if len(runs) > keep else []
    for p in gone:
        shutil.rmtree(p, ignore_errors=True)
    return [p.name for p in gone]


def finish_run(runs_dir: Path, run_id: str, *, paid: bool) -> list[str]:
    """M12 (rag D31.4): mark a paid run's folder `.keep`, then prune the unmarked ones past `KEEP_RUNS`."""
    if paid and (runs_dir / run_id).is_dir():
        (runs_dir / run_id / ".keep").write_text("paid run: never pruned (rag D31.4)\n", encoding="utf-8")
    return prune_runs(runs_dir)


def overlaps_peak(cal: PricingCalendar, start: datetime, seconds: float) -> bool:
    end = start + timedelta(seconds=max(0.0, seconds))
    if cal.period(start) == "peak" or cal.period(end) == "peak":
        return True
    nxt = cal.next_change(start)
    return nxt <= end and cal.period(nxt) == "peak"


def _user_key(base: Config) -> SecretStr | None:
    if base.openrouter_key is not None:
        return base.openrouter_key
    p = base.data_dir / "secrets.local.json"
    try:
        k = json.loads(p.read_text(encoding="utf-8")).get("openRouterKey")
    except (OSError, ValueError):
        return None
    return SecretStr(k) if isinstance(k, str) and k.strip() else None


def isolated_config(base: Config, run_dir: Path, opts: Options, *, test_mode: bool) -> Config:
    seed_dir = Path(opts.seed_dir).resolve() if opts.seed_dir else base.seed_dir
    key = None if test_mode or opts.probe else _user_key(base)   # a probe never holds the real key
    return Config(repo_root=base.repo_root, data_dir=run_dir, seed_dir=seed_dir, tz=base.tz, test_mode=test_mode,
                  port=base.port, log_level=base.log_level, openrouter_key=key,
                  ai_env={"HORIZON_AI_PROFILE": opts.profile}, probe=opts.probe)


@dataclass
class ProbeResult:
    """M15 (D13): one suite's probe: stored answers it would reuse, and what a real run would pay."""
    suite: str
    profile: str
    hits: int
    misses: int
    would_pay_usd: float
    blocked: int
    one_shot: bool
    note: str = ""


# ── the run ──
@dataclass
class Runner:
    base: Config
    stdin: Callable[[str], str] = input
    out: Callable[[str], None] = print
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    store_hits: int = 0   # the last run's store hits, for its report
    last_probe: ProbeResult | None = None
    probe_estimate: float = 0.0

    @property
    def data_dir(self) -> Path:
        return self.base.data_dir

    @property
    def runs_dir(self) -> Path:
        return self.data_dir / "evals"

    async def run(self, opts: Options) -> int:
        from horizon.evals import suites

        suite = suites.SUITES.get(opts.suite)
        if suite is None:
            self.out(f"horizon: unknown suite {opts.suite!r} (have: {', '.join(sorted(suites.SUITES))})")
            return 2
        test_mode = self.base.test_mode
        if opts.probe and opts.suite in NEVER_PROBED and not (opts.suite == "transcript" and opts.short):
            self.out(f"horizon: `{opts.suite}` is never probed (it bypasses the store, is free, or writes committed "
                     "files)")
            return 2
        refusal = getattr(suite, "refuse", None)
        why = (alias_refusal(opts.decision_model)
               or candidate_refusal(opts, self.base.seed_dir)
               or (refusal(opts) if refusal is not None else None))
        if why:   # checked before the plan, the prompt and any call (M10 watch-history)
            self.out(why)
            return 2
        if opts.suite in PAID_ONLY and test_mode and not opts.probe:
            self.out(f"horizon: `{opts.suite}` makes paid calls and refuses to run in test mode")
            return 2
        prices = priced_for(load_price_table(self.base.seed_dir), opts.decision_model, self.base.seed_dir)
        plan = suite.plan(opts, prices, paid=not test_mode or opts.probe)
        if opts.probe:   # priced as a real run, but nothing is spent, asked or logged
            plan = Plan(items=plan.items, estimate_usd=plan.estimate_usd, expected_s=plan.expected_s, paid=False)
            self.probe_estimate = plan.estimate_usd
        cal = calendar_for(self.base.tz)
        now = self.now()
        self.out(f"plan: {opts.suite}, {len(plan.items)} item(s), estimate ${plan.estimate_usd:.5f}"
                 f"{' (fake provider, $0)' if not plan.paid else ''}; eval spend today "
                 f"${spent_today(self.data_dir, cal, now):.5f}")
        if plan.paid and not opts.allow_peak and overlaps_peak(cal, now, plan.expected_s):
            self.out("horizon: the run would overlap DeepSeek's peak pricing; run off-peak or pass --allow-peak")
            return 2
        if plan.paid and self.base.openrouter_key is None and _user_key(self.base) is None:
            self.out("horizon: no OpenRouter key (OPENROUTER_API_KEY in the repo's .env)")
            return 2
        if not opts.yes and not opts.probe:
            try:
                ans = self.stdin("Run it? [y/N] ").strip().lower()
            except EOFError:   # no terminal (CI, a pipe): the answer is no
                ans = ""
            if ans not in ("y", "yes"):
                self.out("horizon: cancelled; nothing was sent")
                return 1
        run_id = f"{now.strftime('%Y%m%dT%H%M%S')}-{opts.suite}-{uuid.uuid4().hex[:6]}"
        run_dir = self.runs_dir / run_id / opts.profile
        run_dir.mkdir(parents=True, exist_ok=True)
        if opts.max_usd is not None:
            max_usd = opts.max_usd
        elif plan.paid:
            max_usd = round(max(plan.estimate_usd * 1.5, 0.0001), 6)
        elif opts.probe:
            max_usd = 1.0   # the isolated copy's own cap; the deny transport and the store's miss send nothing
        else:
            max_usd = 1.0   # the in-process fake's prices: nothing real is spent; --max-usd still forces a cap
        (run_dir / "settings.local.json").write_text(json.dumps({"budget": {"dailyCapUsd": max_usd}}), encoding="utf-8")
        result, ports, spent, model = await self._execute(suite, plan, opts, run_dir, max_usd, test_mode)
        self._report(run_dir, opts, plan, result, ports, spent, max_usd, model)
        if plan.paid:
            p = spend_file(self.data_dir)
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"at": now.isoformat(), "run": run_id, "suite": opts.suite, "usd": round(spent, 6)})
                        + "\n")
        finish_run(self.runs_dir, run_id, paid=plan.paid)
        self.out(f"{opts.suite}: {result.status} | spent ${spent:.5f} | report {run_dir / 'report.md'}")
        return 0 if result.status in ("ok", "probe") else 1

    async def _execute(self, suite: Any, plan: Plan, opts: Options, run_dir: Path, max_usd: float,
                       test_mode: bool) -> tuple[Result, dict[str, str], float, str | None]:
        from horizon.runtime import Runtime

        cfg = isolated_config(self.base, run_dir, opts, test_mode=test_mode)
        clock = FrozenClock(calendar_for(cfg.tz), SMOKE_START) if test_mode else None
        rt = Runtime(cfg, clock=clock)
        await rt.start()
        if test_mode:   # the in-process fake answers any key; a test-mode Config never holds a real one
            rt.keys.set_key("sk-or-test-eval-0001")
        elif opts.probe:   # ports resolve as with a key; the deny transport sends nothing (D13)
            rt.keys.set_key("sk-or-probe-0000")
        if opts.decision_model:   # jev-comparison (D3)
            set_decision_model(rt, opts.decision_model, priced_for(rt.prices, opts.decision_model, cfg.seed_dir))
        from horizon.evals import canary as canary_mod

        # jev-comparison (D5): the asked model's own baseline salts its stored answers (the pinned one: canary.json's)
        fingerprint = canary_mod.fingerprint_for(EVALS_DIR, str(rt.gateway.decision_model))
        store = store_for(opts, self.data_dir, fingerprint, test_mode=test_mode)
        if store is not None and opts.probe:
            store.probe = True
        rt.gateway.store = store
        if opts.against:
            from horizon.evals.manifest import load_allowed

            rt.gateway.allowed_bodies = load_allowed(opts.against)
        env = RunEnv(rt=rt, opts=opts, store=store, run_dir=run_dir, max_usd=max_usd)
        try:
            from horizon.gateway.errors import ProviderError

            try:
                result: Result = await suite.run(env, plan)
            except ProviderError as e:
                if e.code in ("daily_budget_exceeded", "creation_budget_exceeded", "energy_exhausted"):
                    result = Result(status="incomplete", summary=[f"stopped: {e.code} (the run's cap ${max_usd})"])
                elif opts.probe:   # a call the deny transport refused, uncaught by the suite: the probe still reports
                    result = Result(summary=[f"the suite stopped at a refused call ({e.code}); the counts cover what "
                                             "ran before it"])
                else:
                    raise
            except TimeoutError as e:
                if not opts.probe:
                    raise
                # a probe answers misses empty, so a chained session may never settle (found in 8.2: a free debate);
                # its misses already price it whole (D13)
                result = Result(summary=[f"the suite stopped: {e}; the counts cover what ran before it"])
            spent = await env.spent()
            self.store_hits = store.hits if store is not None else 0
            if opts.probe:
                self.last_probe = self._probe_result(opts, store, rt.probe_blocked)
                result.status = "probe"
                result.summary = [*self._probe_lines(self.last_probe), "", *result.summary]
            ports = rt.ai.resolved(key_set=rt.keys.status() == "set")
            return result, ports, spent, result.model
        finally:
            await rt.stop()

    def _probe_result(self, opts: Options, store: ResponseStore | None, blocked: list[str]) -> ProbeResult:
        misses = store.misses if store is not None else []
        one_shot = opts.suite in ONE_SHOT
        if one_shot:
            usd = sum(float(m["usd"]) for m in misses)
        else:   # a chained item's later requests follow its first miss, so a real run pays the whole estimate
            usd = self.probe_estimate if misses or blocked else 0.0
        note = "" if store is not None else "no store attached"
        return ProbeResult(opts.suite, opts.profile, store.hits if store is not None else 0, len(misses), round(usd, 6),
                           len(blocked), one_shot, note)

    @staticmethod
    def _probe_lines(p: ProbeResult) -> list[str]:
        how = "exact (one request per item)" if p.one_shot else "the whole estimate (chained items)"
        return [f"## Probe ({p.profile})", "",
                f"- stored answers reused: {p.hits}; requests with no stored answer: {p.misses}; non-store requests "
                f"refused: {p.blocked}",
                f"- a real run would pay about ${p.would_pay_usd:.5f}, priced {how}. Nothing was sent or spent."]

    def _report(self, run_dir: Path, opts: Options, plan: Plan, result: Result, ports: dict[str, str], spent: float,
                max_usd: float, model: str | None) -> None:
        with (run_dir / "results.jsonl").open("w", encoding="utf-8") as f:
            for r in result.rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        hits = max(sum(1 for r in result.rows if r.get("cached")), self.store_hits)
        lines = [f"# eval {opts.suite} · {result.status}", "",
                 f"- profile: `{opts.profile}`; ports: " + ", ".join(f"{k}={v}" for k, v in sorted(ports.items())),
                 f"- items: {len(plan.items)}; estimate ${plan.estimate_usd:.5f}; spent ${spent:.5f}; cap ${max_usd:.5f}",
                 f"- provider: {'paid' if plan.paid else 'in-process fake ($0)'}; store hits: {hits}",
                 *( [f"- decision model asked: `{opts.decision_model}` (not the pinned one)"]
                    if opts.decision_model else []),
                 *( [f"- model: `{model}`"] if model else []),
                 *( [f"- seed folder: `{opts.seed_dir}` (a config experiment)"] if opts.seed_dir else []),
                 "", *result.summary, ""]
        (run_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def decision_estimate(prices: Any, state: Any, questions: dict[str, Any]) -> float:
    """The gateway's formula (budget-caps "Cost estimates per category"; persona-context design D23): one copy."""
    return float(estimate_decision_request(prices, state, questions))


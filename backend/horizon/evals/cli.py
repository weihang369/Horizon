"""The `horizon eval …` subcommands (evaluation-harness spec; ai-foundation design D33–D37).

Registered on the main parser by `horizon.cli`. Each command lives in its own function so the main CLI stays small.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any


def _bank_lock(_args: argparse.Namespace) -> int:
    """Record the bank's versions and content hashes (design D1). Refuses a changed entry whose version didn't go up."""
    from horizon.ai.questions import BankError, check_lock, load_bank, write_lock

    b = load_bank()
    try:
        lock = write_lock(b)
    except BankError as e:
        print(f"horizon: {e}", file=sys.stderr)
        return 2
    problems = check_lock(b)
    for p in problems:
        print(f"horizon: {p}", file=sys.stderr)
    print(f"horizon: questions.lock.json records {len(lock)} question(s)")
    return 1 if problems else 0


def _suite(args: argparse.Namespace) -> int:
    import asyncio

    from horizon.config import load_config
    from horizon.evals.runner import Options, Runner

    opts = Options(suite=args.eval_cmd, profile=args.profile, limit=args.limit, start=args.start, max_usd=args.max_usd,
                   yes=args.yes,
                   allow_peak=args.allow_peak, accept=getattr(args, "accept", False), set=getattr(args, "set", None),
                   seed_dir=args.seed_dir)
    return asyncio.run(Runner(load_config()).run(opts))


def _overlap(_args: argparse.Namespace) -> int:
    from horizon.evals.datachecks import overlap_problems, split_changes, split_problems
    from horizon.evals.runner import EVALS_DIR
    from horizon.evals.suites import all_items, dataset_files

    items = list(all_items())
    problems = overlap_problems(items) + split_problems(items)
    for f in dataset_files():
        problems += split_changes(f, EVALS_DIR.parent)
    for p in problems:
        print(f"horizon: {p}", file=sys.stderr)
    print(f"horizon: {len(items)} item(s) checked for copied bank phrases (6-word shingles: catches copying, not "
          f"paraphrase) and split changes: {len(problems)} problem(s)")
    return 1 if problems else 0


def _review(args: argparse.Namespace) -> int:
    import json
    import random

    from horizon.evals.datachecks import review_sample
    from horizon.evals.runner import EVALS_DIR
    from horizon.evals.suites import DATASETS, load_dataset

    path = DATASETS / f"{args.set}.jsonl"
    if not path.is_file():
        print(f"horizon: no dataset {path.name}", file=sys.stderr)
        return 2
    rows = load_dataset(path)
    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(1 << 30)
    ids = review_sample([str(r["id"]) for r in rows], seed)
    out = EVALS_DIR / "reviews" / f"{args.set}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"set": args.set, "seed": seed, "sample": ids, "disagree": []}, indent=1) + "\n",
                   encoding="utf-8")
    by_id = {str(r["id"]): r for r in rows}
    for i in ids:
        print(f"{i}\tlabel={by_id[i]['label']}\t{json.dumps(by_id[i]['item'], ensure_ascii=False)[:160]}")
    print(f"horizon: {len(ids)} item(s) to review; list the ids you disagree with under `disagree` in {out}")
    return 0


def _corpus_check(_args: argparse.Namespace) -> int:
    from horizon.evals.datachecks import corpus_problems

    problems = corpus_problems()
    for p in problems:
        print(f"horizon: {p}", file=sys.stderr)
    print(f"horizon: corpus licence check: {len(problems)} problem(s)")
    return 1 if problems else 0


def _capture(args: argparse.Namespace) -> int:
    from horizon.config import load_config
    from horizon.evals.stats import capture_case

    cfg = load_config()
    p = capture_case(cfg.db_path, args.message_id, cfg.data_dir / "evals" / "cases")
    if p is None:
        print(f"horizon: no captured calls for {args.message_id}: capture was off for this message "
              "(HORIZON_CAPTURE_AI_CALLS=1)", file=sys.stderr)
        return 1
    print(f"horizon: wrote {p}")
    return 0


def _stats(args: argparse.Namespace) -> int:
    from horizon.config import load_config
    from horizon.evals.stats import stats

    print(stats(load_config().db_path, args.days))
    return 0


def register(sub: Any) -> None:
    ev = sub.add_parser("eval", help="the evaluation harness and its dev commands")
    esub = ev.add_subparsers(dest="eval_cmd", required=True)
    esub.add_parser("bank-lock", help="record the question bank's versions (after bumping an edited question)") \
        .set_defaults(fn=_bank_lock)
    for name, helptext in (("canary", "Jev's drift canary (paid, < $0.001)"),
                           ("decisions", "layer-1 decision accuracy (paid)"),
                           ("smoke", "the free smoke run (HORIZON_TEST=1: the fake provider, $0)"),
                           ("drafter", "the profile drafter on 20 seeds (paid, M8)"),
                           ("summary", "the rolling summariser on 40 inputs (paid, M8)"),
                           ("long", "agent-only long conversations past two drops (paid, rare, M8)"),
                           ("transcript", "generate the long-history frozen transcripts with naive (paid, M8)")):
        s = esub.add_parser(name, help=helptext)
        s.add_argument("--profile", default="naive", choices=["scripted", "naive", "agent"])
        s.add_argument("--limit", type=int, default=None)
        s.add_argument("--start", type=int, default=0, help="skip the first N items (finish an incomplete run)")
        s.add_argument("--max-usd", type=float, default=None, dest="max_usd")
        s.add_argument("--yes", action="store_true", help="skip the y/N prompt (only after OKing the estimate)")
        s.add_argument("--allow-peak", action="store_true", dest="allow_peak")
        s.add_argument("--seed-dir", default=None, dest="seed_dir",
                       help="run against another seed folder (a runtime.json experiment); the report names it")
        if name == "canary":
            s.add_argument("--accept", action="store_true", help="accept the new answers as the baseline")
        if name in ("decisions", "long", "transcript", "drafter"):
            s.add_argument("--set", default=None, help="decisions: one dataset folder (`judges`); long, transcript: "
                                                       "one script id; drafter: a seed file in evals/drafter/")
        s.set_defaults(fn=_suite)
    esub.add_parser("overlap", help="dataset items must not copy the bank's wording").set_defaults(fn=_overlap)
    rv = esub.add_parser("review", help="sample a dataset for label review")
    rv.add_argument("set")
    rv.add_argument("--seed", type=int, default=None)
    rv.set_defaults(fn=_review)
    esub.add_parser("corpus-check", help="the corpus licence check").set_defaults(fn=_corpus_check)
    cp = esub.add_parser("capture", help="write a message's captured AI calls to data/evals/cases/")
    cp.add_argument("message_id")
    cp.set_defaults(fn=_capture)
    st = sub.add_parser("stats", help="live latency, cost and fallback stats (read-only)")
    st.add_argument("--days", type=int, default=None)
    st.set_defaults(fn=_stats)

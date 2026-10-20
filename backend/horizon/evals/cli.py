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
                   seed_dir=args.seed_dir, force=getattr(args, "force", False), mode=getattr(args, "mode", None),
                   runs=getattr(args, "runs", None), turns=getattr(args, "turns", None),
                   messages=getattr(args, "messages", None), part=getattr(args, "part", None),
                   arm=getattr(args, "arm", None), latency=getattr(args, "latency", False),
                   recut=getattr(args, "recut", None), probe=getattr(args, "probe", False),
                   against=getattr(args, "against", None), short=getattr(args, "short", False))
    if opts.recut:   # M14 (safety D23): from the saved answers, no provider call and no run folder
        from horizon.evals.safety_suite import recut_run

        try:
            print("\n".join(recut_run(opts.recut)))
        except FileNotFoundError as e:
            print(f"horizon: {e}")
            return 2
        return 0
    return asyncio.run(Runner(load_config()).run(opts))


def _all(args: argparse.Namespace) -> int:
    """M15 (images-music D13): `horizon eval all` is the probe over every suite, under `agent` and `naive`. It sends
    nothing and spends nothing; it prints, per suite, the stored answers it would reuse and what a real run would pay.
    Re-running a suite that would pay is its own run, with its own OK."""
    import asyncio
    import datetime as dt

    from horizon.config import load_config
    from horizon.evals import suites
    from horizon.evals.runner import NEVER_PROBED, Options, Runner

    cfg = load_config()

    async def go() -> list[str]:
        rows = ["| Suite | Profile | Reused | No stored answer | Refused (not store) | A real run would pay |",
                "|---|---|---|---|---|---|"]
        for profile in ("agent", "naive"):
            for name in sorted(suites.SUITES):
                if name in NEVER_PROBED:
                    continue
                said: list[str] = []
                r = Runner(cfg, out=said.append)
                try:
                    code = await r.run(Options(suite=name, profile=profile, probe=True, yes=True, limit=args.limit))
                except Exception as e:   # one suite's crash is its own row, never the end of the table (8.2)
                    rows.append(f"| {name} | {profile} | — | — | — | not probed: crashed ({type(e).__name__}: {e}) |")
                    continue
                p = r.last_probe
                if p is None:
                    why = (said[-1] if said else f"exit {code}").removeprefix("horizon: ")
                    rows.append(f"| {name} | {profile} | — | — | — | not probed: {why} |")
                    continue
                how = "exact" if p.one_shot else "whole estimate"
                rows.append(f"| {name} | {profile} | {p.hits} | {p.misses} | {p.blocked} | "
                            f"${p.would_pay_usd:.5f} ({how}) |")
        return rows

    rows = asyncio.run(go())
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%S")
    out = cfg.data_dir / "evals" / f"all-{stamp}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(rows)
    out.write_text(f"# horizon eval all (probe: nothing sent, nothing spent)\n\n{text}\n", encoding="utf-8")
    print(text)
    print(f"horizon: written to {out}")
    return 0


def _manifest(args: argparse.Namespace) -> int:
    """M15 (images-music D19): write the Jev request manifest from the datasets and the store ($0, nothing sent)."""
    import json

    from horizon.config import load_config
    from horizon.evals.manifest import MANIFEST_NAME, build
    from horizon.evals.runner import EVALS_DIR, SAFETY_CACHE

    cfg = load_config()
    canary = json.loads((EVALS_DIR / "canary.json").read_text(encoding="utf-8"))
    model = str(json.loads((cfg.seed_dir / "pricing.json").read_text(encoding="utf-8"))["data"]["decision"]["model"])
    doc = build(model=model, fingerprint=canary.get("fingerprint"), store_root=cfg.data_dir / "cache",
                private_store_root=SAFETY_CACHE, test_mode=cfg.test_mode)
    out = args.out or str(EVALS_DIR / "baselines" / MANIFEST_NAME)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    for name, s in doc["sets"].items():
        print(f"{name}: {s['n']} request(s), {s['stored']} with a stored {model} answer")
    print(f"horizon: written to {out}")
    return 0


def _overlap(_args: argparse.Namespace) -> int:
    from horizon.evals.datachecks import overlap_problems, split_changes, split_problems
    from horizon.evals.retrieval import DATASET, load_questions
    from horizon.evals.runner import EVALS_DIR
    from horizon.evals.suites import all_items, dataset_files

    # M12: the retrieval questions are checked too (their message and earlier lines; rag D22)
    asked = [{"id": q["id"], "split": q["split"], "item": [q["message"], *q.get("earlier", [])]}
             for q in load_questions()]
    items = list(all_items())
    problems = overlap_problems(items + asked) + split_problems(items + asked)
    for f in [*dataset_files(), *([DATASET] if DATASET.is_file() else [])]:
        problems += split_changes(f, EVALS_DIR.parent)
    items += asked
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
    from horizon.evals.retrieval import load_questions, seed_chunks, span_problems

    seeds = {cid: text for cid, (_, text) in seed_chunks().items()}
    problems = corpus_problems() + span_problems(load_questions(), seeds)   # M12: every span still sits in its source
    for p in problems:
        print(f"horizon: {p}", file=sys.stderr)
    print(f"horizon: corpus licence check: {len(problems)} problem(s)")
    return 1 if problems else 0


def _retrieval_compare(args: argparse.Namespace) -> int:
    from pathlib import Path

    from horizon.evals.retrieval import compare_report

    try:
        lines = compare_report(Path(args.base), Path(args.arm), Path(args.base_test) if args.base_test else None,
                               Path(args.arm_test) if args.arm_test else None)
    except (ValueError, KeyError) as e:
        print(f"horizon: {e}", file=sys.stderr)
        return 2
    text = "\n".join(lines) + "\n"
    print(text, end="")
    (Path(args.arm) / "compare.md").write_text(text, encoding="utf-8")
    return 0


def _memory_compare(args: argparse.Namespace) -> int:
    from pathlib import Path

    from horizon.evals.memory_suite import compare_report

    try:
        lines = compare_report(Path(args.base), Path(args.arm))
    except (ValueError, KeyError) as e:
        print(f"horizon: {e}", file=sys.stderr)
        return 2
    text = "\n".join(lines) + "\n"
    (Path(args.arm) / "compare.md").write_text(text, encoding="utf-8")   # first: a console that can't print it
    print(text, end="")
    return 0


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
                           ("transcript", "generate the long-history frozen transcripts with naive (paid, M8)"),
                           ("moodline", "the mood line on vs off over non-neutral transcript turns (paid, once, M9)"),
                           ("latency", "agent 1:1 time to the face and the first word, store bypassed (paid, M9); "
                                       "--part follow|watch for M10's follow plan and watch timing, debate for M11's, deep for "
                                       "M12's deep turns, recall for M13's recall timing (--profile agent)"),
                           ("watch-history", "generate the committed watch histories with naive (paid, once, M10)"),
                           ("freerun", "agent group and watch free runs: signals, no target (paid, M10)"),
                           ("debate-history", "generate the committed debate histories with naive (paid, once, M11)"),
                           ("debate-plant", "write the planted weak sides of the debate histories (paid, once, M11)"),
                           ("debate-quality", "the debate-quality judge over the committed histories (paid, M11)"),
                           ("debate", "the agent verdict on the 12 debates, the margin, the prose and host checks "
                                      "(paid, M11)"),
                           ("retrieval", "the agent deep path on the labelled retrieval questions; --arm for one "
                                         "comparison arm (paid, M12)"),
                           ("notfound", "the Not-found reply end to end: 40 unanswerable + 10 partly 1:1 turns and "
                                        "its two judges (paid, M12)"),
                           ("deep-check", "doc 10 check 5: deep_check on 20 passages, the set check on 5 pairs, the two "
                                          "nouls on 20 messages (paid, M12)"),
                           ("memory", "the memory suite: rewrite, recall (in-session, overflow; --arm), layer 3, the "
                                      "dupCosine sweep (--part dup) (paid, M13; --profile agent)"),
                           ("safety", "the safety suite: input, care, output, motion, image, song (Jev); care_method, "
                                      "injection, honesty, drafter, drift (end to end, --profile agent); --recut <run> "
                                      "re-cuts a saved run for free (paid, M14)"),
                           ("embed-probe", "query embeddings on each named OpenRouter provider of the active space's "
                                           "model, timed, store-bypassed (paid, M13 U3; --set A,B)"),
                           ("conversations", "layer 3: agent beside naive on the 20 frozen transcripts, both copies, "
                                             "the judges and the free runs (paid, M15)"),
                           ("faithfulness", "sentence faithfulness on the 10 two-passage questions as agent deep turns "
                                            "(paid, M15; --profile agent)")):
        s = esub.add_parser(name, help=helptext)
        s.add_argument("--profile", default="naive", choices=["scripted", "naive", "agent"])
        s.add_argument("--limit", type=int, default=None)
        s.add_argument("--start", type=int, default=0, help="skip the first N items (finish an incomplete run)")
        s.add_argument("--max-usd", type=float, default=None, dest="max_usd")
        s.add_argument("--yes", action="store_true", help="skip the y/N prompt (only after OKing the estimate)")
        s.add_argument("--allow-peak", action="store_true", dest="allow_peak")
        s.add_argument("--against-manifest", default=None, dest="against",
                       help="a request manifest: refuse any Jev request whose body it doesn't list (a model comparison)")
        s.add_argument("--probe", action="store_true",
                       help="serve stored answers, stop at a miss, send nothing; report what a real run would pay (M15)")
        s.add_argument("--seed-dir", default=None, dest="seed_dir",
                       help="run against another seed folder (a runtime.json experiment); the report names it")
        if name == "canary":
            s.add_argument("--accept", action="store_true", help="accept the new answers as the baseline")
        if name in ("watch-history", "debate-history", "debate-plant"):
            s.add_argument("--force", action="store_true", help="overwrite a committed history")
        if name == "freerun":
            s.add_argument("--mode", choices=["watch", "group", "debate"], default="watch")
            s.add_argument("--runs", type=int, default=3)
            s.add_argument("--turns", type=int, default=30)
            s.add_argument("--messages", type=int, default=12)
        if name == "transcript":
            s.add_argument("--short", action="store_true", help="the 7 short scripts (images-music D10): no drop "
                                                                "required, the line labels kept; can be probed")
        if name == "latency":
            s.add_argument("--part", choices=["follow", "watch", "debate", "deep", "recall", "output", "blended"],
                           default=None)
            s.add_argument("--arm", default=None, help="blended: rate=R, the deep rate fixed before the run (M15)")
        if name == "safety":
            s.add_argument("--part", default=None, help="comma-separated: input, care, output, motion, image, song, "
                                                        "care_method, injection, honesty, drafter, drift")
            s.add_argument("--recut", default=None, help="a saved run's id: re-score and re-cut its thresholds, no call")
        if name == "retrieval":
            s.add_argument("--arm", default=None, help="space=<id> | piece=200|300|400[:kept] | lambda=0.5|0.7|1.0 | "
                                                       "rewrite=off")
        if name == "conversations":
            s.add_argument("--part", choices=["units"], default=None,
                           help="units: the compared units only, no free runs (a store-backed slice, M15 8.9)")
        if name == "memory":
            s.add_argument("--part", choices=["rewrite", "recall", "layer3", "dup", "rejudge"], default=None)
            s.add_argument("--arm", default=None, help="recall only: search=bm25|dense | mmr=off | lambda=0.5|0.7|1.0 | "
                                                       "space=<id>")
            s.add_argument("--latency", action="store_true", help="store-bypassed: recall reads every check to its "
                                                                  "end (the tail for recall.checkMs); rewrite times "
                                                                  "each run (doc 09 check 2)")
        if name in ("decisions", "long", "transcript", "drafter", "watch-history", "summary", "debate-history",
                    "debate-plant", "debate-quality", "retrieval", "notfound", "memory", "embed-probe",
                    "conversations", "moodline"):
            s.add_argument("--set", default=None, help="decisions: one dataset folder (`judges`); long, transcript: "
                                                       "one script id; drafter: a seed file in evals/drafter/")
        s.set_defaults(fn=_suite)
    al = esub.add_parser("all", help="probe every suite under agent and naive: what the store would serve and what a "
                                     "real run would pay ($0, nothing sent; M15)")
    al.add_argument("--limit", type=int, default=None)
    al.set_defaults(fn=_all)
    mf = esub.add_parser("manifest", help="write the Jev request manifest for the model comparison ($0, M15)")
    mf.add_argument("--out", default=None)
    mf.set_defaults(fn=_manifest)
    esub.add_parser("overlap", help="dataset items must not copy the bank's wording").set_defaults(fn=_overlap)
    rv = esub.add_parser("review", help="sample a dataset for label review")
    rv.add_argument("set")
    rv.add_argument("--seed", type=int, default=None)
    rv.set_defaults(fn=_review)
    esub.add_parser("corpus-check", help="the corpus licence check").set_defaults(fn=_corpus_check)
    rc = esub.add_parser("retrieval-compare", help="an arm's retrieval run against the default's, by K3's rule (free, "
                                                   "M12)")
    rc.add_argument("base", help="the default run's folder (dev)")
    rc.add_argument("arm", help="the arm run's folder (dev); compare.md is written there")
    rc.add_argument("--base-test", default=None)
    rc.add_argument("--arm-test", default=None)
    rc.set_defaults(fn=_retrieval_compare)
    mc = esub.add_parser("memory-compare", help="a recall arm's memory run against the default's, by K3's rule "
                                                "(free, M13)")
    mc.add_argument("base", help="the default `memory --part recall` run's folder")
    mc.add_argument("arm", help="the arm run's folder; compare.md is written there")
    mc.set_defaults(fn=_memory_compare)
    cp = esub.add_parser("capture", help="write a message's captured AI calls to data/evals/cases/")
    cp.add_argument("message_id")
    cp.set_defaults(fn=_capture)
    st = sub.add_parser("stats", help="live latency, cost and fallback stats (read-only)")
    st.add_argument("--days", type=int, default=None)
    st.set_defaults(fn=_stats)

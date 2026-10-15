"""The retrieval suite (docs/ai/02 B2, B5; doc 10 K7, K14; rag design D22–D24; evaluation-harness "The retrieval suite",
"Labels live on the text, not on pieces", "The passage thresholds are cross-validated").

**The questions** (`evals/datasets/retrieval/retrieval.jsonl`, built by its `build.py`): each line is
`{id, split, kind, lang, character, message, earlier, needs_two, named, origin, spans}`. A span is quoted source text
with its offsets, graded 2 (answers) or 1 (partly):
- corpus: `{doc: "amara/niosh-module-3.md", start, end, grade, text}`, offsets in the file's decoded text, which is
  exactly what the pipeline stores as `extracted.md`;
- seed: `{doc: "seed:kno_seedAmara1", chunk: "kch_…", start, end, grade, text}`, offsets in that authored piece.

**Coverage** (B2, the 80 % rule): a piece covers a span when it holds at least 80 % of the span's characters by offset,
in the same source; a seed piece (authored, never re-chunked) covers the spans written on it. So every piece size is
scored against the same labels.

**The run:** the corpus documents are added as their characters' sources in the run's own database (the seed's are
there already) and indexed; each question runs the `agent` deep path as a confident 1:1 turn (the gate taken as yes;
"standalone?" and "English?" asked as live), and the report gives Recall@20, Recall@8, MRR, nDCG@8, kept-set precision
and recall, the outcomes against B5's targets, the share of turns missing their dense half, and every set check, with
seed and corpus apart. `t_keep` and `t_found` are then chosen by leave-one-out over {0.5 … 0.9} from the recorded
check probabilities (K7).
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from horizon.ai.agent import keep as keeping
from horizon.evals.metrics import bootstrap_mean, wilson
from horizon.evals.runner import EVALS_DIR

DATASET = EVALS_DIR / "datasets" / "retrieval" / "retrieval.jsonl"
CORPUS = EVALS_DIR / "corpus"
SEED_CHUNKS = EVALS_DIR.parent / "seed" / "knowledge" / "chunks"
CHARACTERS = {"amara": "chr_seedAmara", "mei": "chr_seedMei", "victor": "chr_seedVictor", "hana": "chr_seedHana"}
COVER = 0.8
THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.9)
KINDS = ("answerable", "unanswerable", "followup", "non_english", "naming")
SET_TUNE_MIN = 20     # D14: `t_set` is re-tuned only with this many set checks


# ── the questions ──
def load_questions(path: Path = DATASET) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    out = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            row = json.loads(line)
            for k in ("id", "split", "kind", "character", "message", "spans"):
                if k not in row:
                    raise ValueError(f"{path.name}:{n}: missing {k}")
            out.append(row)
    return out


def seed_chunks(root: Path = SEED_CHUNKS) -> dict[str, tuple[str, str]]:
    """chunk id → (source id, text) for every authored seed piece (never re-chunked, so its spans sit on the piece)."""
    out: dict[str, tuple[str, str]] = {}
    for f in sorted(root.glob("*.json")):
        for c in json.loads(f.read_text(encoding="utf-8"))["data"]:
            out[str(c["id"])] = (str(c["sourceId"]), str(c["text"]))
    return out


def corpus_text(doc: str, root: Path = CORPUS) -> str:
    """A corpus document exactly as the pipeline stores it (`read_plain`: UTF-8, a BOM dropped, nothing else)."""
    return (root / doc).read_bytes().decode("utf-8-sig")


def resolve(text: str, quote: str) -> tuple[int, int]:
    """The one place `quote` sits in `text` (a label must be unambiguous)."""
    i = text.find(quote)
    if i < 0:
        raise ValueError(f"span not found: {quote[:60]!r}")
    if text.find(quote, i + 1) >= 0:
        raise ValueError(f"span is ambiguous (found twice): {quote[:60]!r}")
    return i, i + len(quote)


def span_problems(questions: Iterable[Mapping[str, Any]], seed_chunks: Mapping[str, str],
                  root: Path = CORPUS) -> list[str]:
    """Every span's quote still sits at its offsets in its source (B2)."""
    out: list[str] = []
    for q in questions:
        for s in q["spans"]:
            doc = str(s["doc"])
            text = seed_chunks.get(str(s.get("chunk"))) if doc.startswith("seed:") else corpus_text(doc, root)
            if text is None:
                out.append(f"{q['id']}: unknown piece {s.get('chunk')}")
            elif text[int(s["start"]):int(s["end"])] != s["text"]:
                out.append(f"{q['id']}: span moved in {doc}")
    return out


# ── coverage and the metrics ──
@dataclass(frozen=True)
class Piece:
    chunk_id: str
    doc: str                  # corpus path, or "seed:<source id>"
    start: int
    end: int
    tokens: int = 0


def covers(piece: Piece, span: Mapping[str, Any]) -> bool:
    if piece.doc != span["doc"]:
        return False
    if piece.doc.startswith("seed:"):
        return piece.chunk_id == span.get("chunk")
    a, b = int(span["start"]), int(span["end"])
    overlap = max(0, min(b, piece.end) - max(a, piece.start))
    return overlap >= COVER * max(1, b - a)


def grade_of(piece: Piece, spans: Sequence[Mapping[str, Any]]) -> int:
    return max((int(s["grade"]) for s in spans if covers(piece, s)), default=0)


def recall_at(pieces: Sequence[Piece], spans: Sequence[Mapping[str, Any]], k: int) -> float | None:
    """The share of the question's grade-2 spans covered within the first `k` pieces (None: nothing to find)."""
    want = [s for s in spans if int(s["grade"]) == 2]
    if not want:
        return None
    top = pieces[:k]
    return sum(1 for s in want if any(covers(p, s) for p in top)) / len(want)


def recall_within(pieces: Sequence[Piece], spans: Sequence[Mapping[str, Any]], budget: int = 1200) -> float | None:
    """Recall over the leading pieces that fit in `budget` tokens (D23: the piece-size arms compared at one budget)."""
    top: list[Piece] = []
    used = 0
    for p in pieces:
        if used + p.tokens > budget:
            break
        top.append(p)
        used += p.tokens
    return recall_at(top, spans, len(top))


def reciprocal_rank(pieces: Sequence[Piece], spans: Sequence[Mapping[str, Any]], k: int = 8) -> float | None:
    want = [s for s in spans if int(s["grade"]) == 2]
    if not want:
        return None
    for i, p in enumerate(pieces[:k]):
        if any(covers(p, s) for s in want):
            return 1.0 / (i + 1)
    return 0.0


def ndcg_at(pieces: Sequence[Piece], spans: Sequence[Mapping[str, Any]], k: int = 8) -> float | None:
    """Graded gains (2 / 1 / 0 by the best span a piece covers, each span credited once)."""
    if not spans:
        return None
    seen: set[int] = set()
    dcg = 0.0
    for i, p in enumerate(pieces[:k]):
        best, which = 0, -1
        for j, s in enumerate(spans):
            if j not in seen and covers(p, s) and int(s["grade"]) > best:
                best, which = int(s["grade"]), j
        if which >= 0:
            seen.add(which)
        dcg += (2 ** best - 1) / math.log2(i + 2)
    ideal = sorted((int(s["grade"]) for s in spans), reverse=True)[:k]
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg else None


def kept_precision(kept: Sequence[Piece], spans: Sequence[Mapping[str, Any]]) -> float | None:
    if not kept:
        return None
    return sum(1 for p in kept if grade_of(p, spans) > 0) / len(kept)


def mean(xs: Iterable[float | None]) -> float | None:
    vals = [x for x in xs if x is not None]
    return sum(vals) / len(vals) if vals else None


# ── the outcomes and the thresholds (K7) ──
@dataclass
class Row:
    """One question's recorded run: what the search gave and every check's probabilities."""

    id: str
    split: str
    kind: str
    origin: str
    needs_two: bool
    spans: list[dict[str, Any]]
    pool: list[Piece]
    candidates: list[Piece]
    kept: list[Piece]
    outcome: str
    checks: list[dict[str, Any]] = field(default_factory=list)
    set_check: dict[str, Any] | None = None
    dense_missing: bool = False
    rewrite: str | None = None

    @property
    def answerable(self) -> bool:
        return self.kind != "unanswerable"


def outcome_at(row: Row, t_keep: float, t_found: float, t_set: float = 0.5) -> str:
    """The outcome the recorded checks give at these thresholds. The set check is reused only when it was asked over
    the same usable pieces as these thresholds would choose; otherwise it counts as missing (D7: partly)."""
    checked = [keeping.Checked(rid=i, order=int(c["order"]), p_answers=c["p_answers"], p_partly=c["p_partly"],
                               unit=c["unit"]) for i, c in enumerate(row.checks)]
    set_yes: bool | None = None
    if row.set_check is not None and row.set_check.get("p") is not None \
            and keeping.needs_set_check(checked, t_keep=t_keep, t_found=t_found):
        use = keeping.best_first([c for c in checked if keeping.usable(c, t_keep)])
        ids = [row.checks[c.rid]["chunkId"] for c in use][:len(row.set_check["chunkIds"])]
        if ids == list(row.set_check["chunkIds"]):
            set_yes = float(row.set_check["p"]) >= t_set
    failed = bool(checked) and not any(c.back for c in checked)
    return keeping.keep(checked, k=3, t_keep=t_keep, t_found=t_found, set_yes=set_yes, abstain_ok=True,
                        failed=failed).outcome


def score_pair(rows: Sequence[Row], t_keep: float, t_found: float) -> tuple[int, int]:
    """(errors, -correct abstains): B5 counts a wrong abstain on an answerable question and a missed abstain on an
    unanswerable one; fewer errors first, then more correct abstains."""
    errors = abstains = 0
    for r in rows:
        o = outcome_at(r, t_keep, t_found)
        if r.answerable and o == "not_found":
            errors += 1
        elif not r.answerable:
            if o == "not_found":
                abstains += 1
            else:
                errors += 1
    return errors, -abstains


def best_pair(rows: Sequence[Row]) -> tuple[float, float]:
    pairs = [(a, b) for a in THRESHOLDS for b in THRESHOLDS]
    return min(pairs, key=lambda p: (*score_pair(rows, *p), abs(p[0] - 0.6) + abs(p[1] - 0.6)))


def leave_one_out(rows: Sequence[Row]) -> dict[str, Any]:
    """K7: each question's outcome under the thresholds chosen on all the others; then the counts against B5."""
    outcomes: list[tuple[Row, str]] = []
    for i, r in enumerate(rows):
        rest = [x for j, x in enumerate(rows) if j != i]
        tk, tf = best_pair(rest) if rest else (0.6, 0.6)
        outcomes.append((r, outcome_at(r, tk, tf)))
    answerable = [o for r, o in outcomes if r.answerable]
    unanswerable = [o for r, o in outcomes if not r.answerable]
    return {"chosen": best_pair(rows), "wrong_abstains": sum(o == "not_found" for o in answerable),
            "answerable": len(answerable), "abstained": sum(o == "not_found" for o in unanswerable),
            "unanswerable": len(unanswerable)}


def scaled(n: int, of: int, target_of: int) -> float:
    return n * target_of / of if of else 0.0


# ── the report ──
def _f(x: float | None) -> str:
    return "—" if x is None else f"{x:.3f}"


def metric_lines(rows: Sequence[Row], title: str) -> list[str]:
    ans = [r for r in rows if r.answerable]
    p = mean(kept_precision(r.kept, r.spans) for r in ans)
    kr = mean(recall_at(r.kept, r.spans, 3) for r in ans)
    return [f"### {title} ({len(rows)} questions, {len(ans)} answerable)",
            f"- Recall@20 {_f(mean(recall_at(r.pool, r.spans, 20) for r in ans))} · "
            f"Recall@8 {_f(mean(recall_at(r.candidates, r.spans, 8) for r in ans))} · "
            f"MRR {_f(mean(reciprocal_rank(r.candidates, r.spans) for r in ans))} · "
            f"nDCG@8 {_f(mean(ndcg_at(r.candidates, r.spans) for r in ans))}",
            f"- kept-set precision {_f(p)} · kept-set recall {_f(kr)}",
            "- outcomes: " + ", ".join(f"{o} {sum(r.outcome == o for r in rows)}"
                                        for o in ("found", "partly", "not_found", "fallback")),
            f"- deep turns missing their dense half: {sum(r.dense_missing for r in rows)} of {len(rows)}"]


def report(rows: Sequence[Row]) -> list[str]:
    out = ["## Retrieval (docs/ai/10 K14; B5's targets: ≤ 3 wrong abstains in 100 answerable, ≥ 32 of 40 "
           "unanswerable abstained)"]
    for origin in ("corpus", "seed"):
        mine = [r for r in rows if r.origin == origin]
        if mine:
            out += metric_lines(mine, origin)
    naming = [r for r in rows if r.kind == "naming"]
    if naming:
        out += metric_lines(naming, "naming a document (reported apart)")
    for split in ("dev", "test"):
        mine = [r for r in rows if r.split == split]
        ans = [r for r in mine if r.answerable]
        una = [r for r in mine if not r.answerable]
        if not mine:
            continue
        wa = sum(r.outcome == "not_found" for r in ans)
        ab = sum(r.outcome == "not_found" for r in una)
        lo, hi = wilson(wa, len(ans)) if ans else (0.0, 0.0)
        lo2, hi2 = wilson(ab, len(una)) if una else (0.0, 0.0)
        out.append(f"- {split}: wrong abstains {wa}/{len(ans)} (95% {lo:.2f}–{hi:.2f}; per 100: "
                   f"{scaled(wa, len(ans), 100):.1f}); unanswerable abstained {ab}/{len(una)} (95% {lo2:.2f}–{hi2:.2f};"
                   f" per 40: {scaled(ab, len(una), 40):.1f})")
    dev = [r for r in rows if r.split == "dev"]
    if dev:
        loo = leave_one_out(dev)
        tk, tf = loo["chosen"]
        out += ["### The passage thresholds (K7: leave-one-out over dev, {0.5 … 0.9})",
                f"- chosen on all of dev: t_keep {tk}, t_found {tf}",
                f"- out of fold: wrong abstains {loo['wrong_abstains']}/{loo['answerable']}, unanswerable abstained "
                f"{loo['abstained']}/{loo['unanswerable']}"]
    sets = [r for r in rows if r.set_check is not None]
    head = ("re-tune t_set" if len(sets) >= SET_TUNE_MIN else
            f"fewer than {SET_TUNE_MIN}: t_set stays at its bank value")
    out.append(f"### Set checks: {len(sets)} ({head})")
    for r in sets:
        p = r.set_check.get("p") if r.set_check else None
        out.append(f"- {r.id}: p {'missing' if p is None else f'{p:.2f}'}; needs two passages: {r.needs_two}; "
                   f"outcome {r.outcome}")
    return out


# ── the comparisons (D23; K3's rule) ──
WIN_GAIN = 0.03        # K3: a challenger must gain >= 3 points on dev, with a paired bootstrap interval above 0
ARM_FOCUS: dict[str, tuple[str, tuple[str, ...] | None]] = {
    # arm key -> (the metric it is judged on, the question kinds it is judged on; None: every answerable kind)
    "space": ("recall8", None),
    "piece": ("recall_1200", None),
    "lambda": ("recall8", None),
    "rewrite": ("recall8", ("followup", "non_english")),
}


def load_results(run: Path) -> tuple[str | None, list[dict[str, Any]]]:
    """A retrieval run's arm (None: the default) and its per-question rows, from its folder or its report folder."""
    folder = next((p for p in [run, *sorted(run.glob("*"))] if (p / "results.jsonl").is_file()), None)
    if folder is None:
        raise ValueError(f"{run}: no results.jsonl")
    rows = [json.loads(x) for x in (folder / "results.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    arm = next((str(r["arm"]) for r in rows if r.get("arm")), None)
    return arm, rows


def paired(base: Sequence[Mapping[str, Any]], arm: Sequence[Mapping[str, Any]], metric: str,
           kinds: tuple[str, ...] | None, split: str | None = None) -> list[float]:
    """Per-question gains (arm - default) on the questions both runs scored (of one split, when given)."""
    b = {str(r["id"]): r for r in base}
    out: list[float] = []
    for r in arm:
        o = b.get(str(r["id"]))
        if o is None or r.get(metric) is None or o.get(metric) is None:
            continue
        if (kinds is not None and r.get("kind") not in kinds) or (split is not None and r.get("split") != split):
            continue
        out.append(float(r[metric]) - float(o[metric]))
    return out


def verdict(dev: Sequence[float], test: Sequence[float] | None = None) -> tuple[str, float, float, float]:
    """K3's rule: (verdict, dev gain, interval low, interval high). Nothing is changed: a win goes to the user."""
    if not dev:
        return "no paired questions", 0.0, 0.0, 0.0
    gain = sum(dev) / len(dev)
    lo, hi = bootstrap_mean([[d] for d in dev])
    if gain < WIN_GAIN or lo <= 0:
        return "tie or loss: the default stays", gain, lo, hi
    if test is None:
        return "wins on dev: confirm once on test", gain, lo, hi
    if test and sum(test) / len(test) < 0:
        return "test reverses the gain: the default stays", gain, lo, hi
    return "wins (dev, and test does not reverse it): goes to the user", gain, lo, hi


def _pts(d: Sequence[float]) -> str:
    return f"{sum(d) / len(d) * 100:+.1f} points ({len(d)})"


def compare_report(base_dev: Path, arm_dev: Path, base_test: Path | None = None,
                   arm_test: Path | None = None) -> list[str]:
    """Each row is scored in its own split: the dev runs' dev rows decide, the test rows (from the test runs, or from
    the same runs when they hold any) confirm."""
    _, bd = load_results(base_dev)
    name, ad = load_results(arm_dev)
    if not name:
        raise ValueError(f"{arm_dev}: not an arm run (the default run comes first)")
    key = name.partition("=")[0]
    metric, kinds = ARM_FOCUS[key]
    bt, at = (load_results(base_test)[1], load_results(arm_test)[1]) if base_test and arm_test else (bd, ad)
    test: list[float] | None = paired(bt, at, metric, kinds, "test") or None
    dev = paired(bd, ad, metric, kinds, "dev")
    v, gain, lo, hi = verdict(dev, test)
    out = [f"## Comparison: `{name}` against the default (D23; K3's rule: >= {WIN_GAIN * 100:.0f} points of {metric} "
           f"on dev with a paired bootstrap interval above 0, then test >= 0)",
           f"- judged on: {', '.join(kinds) if kinds else 'every answerable question'} ({len(dev)} paired on dev)",
           f"- dev gain {gain * 100:+.1f} points (95% {lo * 100:+.1f} to {hi * 100:+.1f})"
           + (f"; test gain {_pts(test)}" if test else ""),
           f"- **verdict: {v}**"]
    for m in ("recall8", "ndcg8", "recall20"):
        if m != metric:
            d = paired(bd, ad, m, kinds, "dev")
            if d:
                out.append(f"- {m}: {_pts(d)} (reported, not judged)")
    naming = paired(bd, ad, metric, ("naming",), "dev")
    if naming and kinds is None:
        out.append(f"- naming a document, apart: {_pts(naming)}")
    if key == "piece":
        kp = [float(r["kept_precision"]) for r in ad if r.get("kept_precision") is not None and r.get("split") == "dev"]
        out.append(f"- kept-set precision on dev: {sum(kp) / len(kp):.3f} ({len(kp)})" if kp else
                   "- kept-set precision on dev: not run (`piece=...:kept --set dev` asks Jev)")
    return out

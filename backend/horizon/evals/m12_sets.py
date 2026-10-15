"""M12's decision sets (rag design D9, D22; docs/ai/02 B5; evaluation-harness "The gate sets"; tasks 9.5).

Three noul sets run in `decisions` like any other (`evals/datasets/{docs,standalone,english}/`), and their thresholds
are chosen here, on dev, by B5's rules, then scored once on test:
- **`docs`** ("needs documents?", asked per candidate as `docs:{id}`, the live key):
  - `t_gate`: the highest threshold with recall ≥ 90 % (go deep); the deep rate on items that need no documents is
    reported next to it;
  - `t_confident`: the lowest threshold with precision ≥ 95 % (abstaining allowed, A6), never below `t_gate`.
- **`standalone`:** a message is rewritten when p(standalone) < `t_standalone`. B5's "the highest threshold that sends
  ≥ 90 % of follow-ups to the rewrite" is stated on the follow-up side (1 − p); on this scale it is the **lowest**
  `t_standalone` that sends ≥ 90 % of the follow-ups to the rewrite, so no more standalone messages are rewritten than
  that needs. Their share is reported.
- **`english`:** ≥ 95 % accuracy at 0.5, per language reported.

English is scored for the thresholds (the English-first rule); other languages are reported apart.

**D9's re-ask** (`decisions --set reask`): the labelled who-speaks and emotion items (debate members included) whose
cast holds a seed character with searchable documents, on dev and with a recorded answer at the live version, asked
again (the live option order only) with those titles in `quoted_documents`, as every M12 plan carries them. Each
question's policy accuracy on dev, at its live floor, is compared with the recorded answers (`docs/ai/checks/`); an
entry moves (a new version, its floor re-chosen) only when the re-asked accuracy leaves the recorded one's interval.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from horizon.ai.questions import bank
from horizon.evals import policies, who_policies
from horizon.evals.metrics import wilson
from horizon.evals.runner import EVALS_DIR

GRID = tuple(round(0.05 * i, 2) for i in range(1, 20))
GATE_RECALL = 0.90
CONFIDENT_PRECISION = 0.95
FOLLOWUPS_SENT = 0.90
ENGLISH_ACCURACY = 0.95
SETS = ("docs", "standalone", "english")
REASK_SET = "reask"
REASK_FROM = ("who_speaks", "emotion", "debate_member")
SEED = EVALS_DIR.parent / "seed"
CHECKS = EVALS_DIR.parent / "docs" / "ai" / "checks"
SEARCHABLE = ("indexed", "keyword_only")


def _pl(rows: Sequence[Mapping[str, Any]], split: str, *, english: bool = True) -> list[tuple[float, bool]]:
    """(p, label is yes) for the answered rows of one split (English only by default)."""
    return [(float(r["p"]), str(r["label"]) == "yes") for r in rows
            if r.get("split") == split and r.get("p") is not None and not r.get("invalid")
            and (not english or str(r.get("lang") or "en") == "en")]


def _rates(rows: Sequence[tuple[float, bool]], t: float) -> tuple[float, float]:
    """(recall, precision) of "p ≥ t means yes"."""
    tp = sum(1 for p, y in rows if p >= t and y)
    fp = sum(1 for p, y in rows if p >= t and not y)
    pos = sum(1 for _, y in rows if y)
    return (tp / pos if pos else 0.0), (tp / (tp + fp) if tp + fp else 1.0)


# ── needs documents? ──
def choose_t_gate(rows: Sequence[tuple[float, bool]]) -> float | None:
    ok = [t for t in GRID if _rates(rows, t)[0] >= GATE_RECALL]
    return max(ok) if ok else None


def choose_t_confident(rows: Sequence[tuple[float, bool]], t_gate: float) -> float | None:
    ok = [t for t in GRID if t >= t_gate and _rates(rows, t)[1] >= CONFIDENT_PRECISION
          and any(p >= t for p, _ in rows)]
    return min(ok) if ok else None


def docs_report(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    dev, test = _pl(rows, "dev"), _pl(rows, "test")
    if not dev or not test:
        return [f"## Needs documents? (docs): needs dev and test items (dev {len(dev)}, test {len(test)})"]
    tg = choose_t_gate(dev)
    if tg is None:
        return ["## Needs documents? (docs): no threshold reaches recall 0.90 on dev — the question is reworded (B5)"]
    tc = choose_t_confident(dev, tg)
    rec, _ = _rates(test, tg)
    no = [p for p, y in test if not y]
    deep = sum(1 for p in no if p >= tg)
    out = [f"## Needs documents? (docs): t_gate {tg:.2f} (highest with recall ≥ 0.90 on dev), t_confident "
           + (f"{tc:.2f} (lowest with precision ≥ 0.95 on dev, ≥ t_gate)" if tc is not None else
              "— (no threshold reaches precision 0.95 on dev: abstaining stays off, B5)"),
           f"- English test: recall at t_gate {rec:.2f}; deep rate on items needing no documents {deep}/{len(no)}"]
    if tc is not None:
        _, prec = _rates(test, tc)
        n = sum(1 for p, _ in test if p >= tc)
        out.append(f"- English test: precision at t_confident {prec:.2f} ({n} at or above it)")
    out += _other_languages(rows, tg)
    out.append("- dev table: " + ", ".join(f"{t:.2f}: R {_rates(dev, t)[0]:.2f} P {_rates(dev, t)[1]:.2f}"
                                           for t in GRID[::2]))
    for mode in sorted({str(r.get("kind")) for r in rows if r.get("kind")}):
        m = [(float(r["p"]), str(r["label"]) == "yes") for r in rows if r.get("kind") == mode and r.get("p") is not None]
        rr, pp = _rates(m, tg)
        out.append(f"- {mode}: recall {rr:.2f}, precision {pp:.2f} at t_gate ({len(m)}, both splits)")
    return out


def _other_languages(rows: Sequence[Mapping[str, Any]], t: float) -> list[str]:
    out = []
    for lang in sorted({str(r.get("lang") or "en") for r in rows} - {"en"}):
        m = [(float(r["p"]), str(r["label"]) == "yes") for r in rows
             if str(r.get("lang")) == lang and r.get("p") is not None]
        ok = sum(1 for p, y in m if (p >= t) == y)
        out.append(f"- {lang} (runs, not scored for the threshold): {ok}/{len(m)} agree at {t:.2f}")
    return out


# ── standalone? ──
def sent(rows: Sequence[tuple[float, bool]], t: float) -> tuple[float, float]:
    """(share of follow-ups rewritten, share of standalone messages rewritten) at `t` (rewrite when p < t)."""
    fu = [p for p, y in rows if not y]
    st = [p for p, y in rows if y]
    return (sum(p < t for p in fu) / len(fu) if fu else 0.0), (sum(p < t for p in st) / len(st) if st else 0.0)


def choose_t_standalone(rows: Sequence[tuple[float, bool]]) -> float | None:
    ok = [t for t in GRID if sent(rows, t)[0] >= FOLLOWUPS_SENT]
    return min(ok) if ok else None


def standalone_report(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    dev, test = _pl(rows, "dev"), _pl(rows, "test")
    if not dev or not test:
        return [f"## Standalone? (standalone): needs dev and test items (dev {len(dev)}, test {len(test)})"]
    t = choose_t_standalone(dev)
    if t is None:
        return ["## Standalone? (standalone): no threshold sends 90 % of dev follow-ups to the rewrite (B5)"]
    fu, st = sent(test, t)
    return [f"## Standalone? (standalone): t_standalone {t:.2f} (the lowest sending ≥ 0.90 of dev follow-ups to the "
            f"rewrite; B5's rule read on p(standalone))",
            f"- English test: follow-ups rewritten {fu:.2f}; standalone messages rewritten {st:.2f}",
            "- dev table: " + ", ".join(f"{x:.2f}: F {sent(dev, x)[0]:.2f} S {sent(dev, x)[1]:.2f}" for x in GRID[::2])]


# ── English? ──
def english_report(rows: Sequence[Mapping[str, Any]], t: float = 0.5) -> list[str]:
    got = [r for r in rows if r.get("p") is not None and not r.get("invalid")]
    if not got:
        return ["## English? (english): no answers"]
    ok = sum(1 for r in got if (float(r["p"]) >= t) == (str(r["label"]) == "yes"))
    lo, hi = wilson(ok, len(got))
    verdict = "meets" if ok / len(got) >= ENGLISH_ACCURACY else "misses"
    out = [f"## English? (english): accuracy {ok}/{len(got)} at {t:.2f} (95% {lo:.2f}–{hi:.2f}); {verdict} B5's ≥ 0.95"]
    for lang in sorted({str(r.get("lang") or "en") for r in got}):
        m = [r for r in got if str(r.get("lang") or "en") == lang]
        k = sum(1 for r in m if (float(r["p"]) >= t) == (str(r["label"]) == "yes"))
        out.append(f"- {lang}: {k}/{len(m)}")
    return out


def reports(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    out: list[str] = []
    for qid, fn in (("standalone", standalone_report), ("english", english_report)):
        mine = [r for r in rows if r["question_id"] == qid]
        if mine:
            out += fn(mine)
    docs = [r for r in rows if r["question_id"] == "docs"]
    if docs:
        out += docs_report(docs)
    reask = [r for r in rows if r.get("reask")]
    if reask:
        out += reask_report(reask, recorded())
    return out


# ── D9: the re-ask with titles ──
def seed_titles(root: Path = SEED) -> dict[str, list[str]]:
    """Each seed character's name → its searchable seed sources' titles, newest first, without their extension (the
    live title read, `sessions.context.document_titles`)."""
    from horizon.ai.embedder import strip_extension

    out: dict[str, list[str]] = {}
    for f in sorted((root / "knowledge").glob("chr_*.json")):
        cid = f.stem
        prof = json.loads((root / "characters" / f"{cid}.json").read_text(encoding="utf-8"))["data"]
        name = str(prof.get("profile", prof).get("name") or cid)
        rows = [s for s in json.loads(f.read_text(encoding="utf-8"))["data"] if s.get("status") in SEARCHABLE]
        rows.sort(key=lambda s: (str(s.get("addedAt") or ""), str(s["id"])), reverse=True)
        if rows:
            out[name] = [strip_extension(str(s["title"])) for s in rows]
    return out


def with_titles(state: Mapping[str, Any], titles: Mapping[str, list[str]]) -> dict[str, Any] | None:
    """The state with `quoted_documents` after `quoted_cast` (the plan's order), or None when no candidate has any."""
    names = [str(c.get("name")) for c in state.get("quoted_cast") or [] if isinstance(c, Mapping)]
    docs = {n: list(titles[n]) for n in names if n in titles}
    if not docs:
        return None
    out: dict[str, Any] = {}
    for k, v in state.items():
        out[k] = v
        if k == "quoted_cast":
            out["quoted_documents"] = docs
    return out


def reask_items(root: Path | None = None) -> list[dict[str, Any]]:
    from horizon.evals.suites import DATASETS, all_items

    titles = seed_titles()
    have = recorded()
    out: list[dict[str, Any]] = []
    for folder in REASK_FROM:
        for it in all_items((root or DATASETS) / folder):
            # only what the comparison reads: dev, with a recorded answer at the entry's live version
            recorded_dev = it.get("split") == "dev" and (str(it["question_id"]), str(it["id"])) in have
            if not isinstance(it.get("label"), dict) or it.get("smoke_only") or not recorded_dev:
                continue
            st = with_titles(it["item"]["state"], titles)
            if st is not None:
                out.append({**it, "item": {**it["item"], "state": st}, "reask": True})
    return out


def recorded(root: Path = CHECKS) -> dict[tuple[str, str], dict[str, Any]]:
    """(question id, item id) → the recorded answer at the entry's live version (the newest file wins)."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for f in sorted(root.glob("m*/*.jsonl"), key=lambda p: (p.parent.name.zfill(4), p.name)):
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            qid = r.get("question_id")
            if not qid or "id" not in r or not isinstance(r.get("label"), dict) or qid not in bank().entries:
                continue
            if r.get("version") == bank().get(str(qid)).version:
                out[(str(qid), str(r["id"]))] = r
    return out


def policy_correct(row: Mapping[str, Any]) -> bool | None:
    """The live rule's pick at the entry's live floor, scored against the label (None: not a policy item)."""
    qid = str(row["question_id"])
    floor = float(bank().get(qid).floor or 0.0)
    label = row["label"]
    if policies.kind_of(qid) == "emotion":
        return policies.emotion_correct(policies.emotion_answer(policies.answer_of(row), label, floor), label)
    if qid in who_policies.PARTS:
        ans = who_policies._answer(row)
        return who_policies.who_correct(qid, who_policies.who_answer(qid, ans, label, floor), label)
    if qid in who_policies.MEMBER_QIDS:
        pick = who_policies.member_answer(who_policies._answer(row), label, floor)
        return who_policies.member_correct(pick, label)
    return None


def reask_report(rows: Sequence[Mapping[str, Any]], before: Mapping[tuple[str, str], Mapping[str, Any]]) -> list[str]:
    out = ["## D9: the who-speaks and emotion items re-asked with titles (dev, policy accuracy at the live floor; an "
           "entry moves only when the re-asked accuracy leaves the recorded one's 95% interval)"]
    for qid in sorted({str(r["question_id"]) for r in rows}):
        now = [r for r in rows if r["question_id"] == qid and r.get("split") == "dev" and not r.get("invalid")]
        pairs: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
        for r in now:
            b = before.get((qid, str(r["id"])))
            if b is not None and not b.get("invalid"):
                pairs.append((r, b))
        scored: list[tuple[bool, bool]] = []
        for r, b in pairs:
            x, y = policy_correct(r), policy_correct(b)
            if x is not None and y is not None:
                scored.append((x, y))
        if not scored:
            out.append(f"- {qid}: no recorded dev answers to compare ({len(now)} re-asked)")
            continue
        n = len(scored)
        a_now, a_then = sum(1 for a, _ in scored if a), sum(1 for _, b in scored if b)
        lo, hi = wilson(a_then, n)
        moved = not (lo <= a_now / n <= hi)
        same = sum(1 for r, b in pairs if r.get("answer") == b.get("answer"))
        out.append(f"- {qid} v{bank().get(qid).version}: re-asked {a_now}/{n} = {a_now / n:.2f}, recorded "
                   f"{a_then}/{n} = {a_then / n:.2f} (95% {lo:.2f}–{hi:.2f}); same top answer {same}/{len(pairs)} → "
                   + ("**moved: a new version and its floor re-chosen on dev (to the user first)**" if moved
                      else "keeps its version"))
    return out

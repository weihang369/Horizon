"""Build M13's five decision sets (memory design D40; docs/ai/09 M12; evaluation-harness "The memory decision sets"):
- `evals/datasets/importance/importance.jsonl`: "how much does it matter?" per line (levels 1–5), under its live key
  `importance:l{n}`, in the live state (`jev.importance_request`) of the character told;
- `evals/datasets/memory_guard/memory_guard.jsonl`: "rewrite keeps the old facts?" (yes: faithful, no: lossy);
- `evals/datasets/earlier/earlier.jsonl`: "needs something from earlier?" about the speaker, `earlier:{id}`, in the
  1:1 plan's live state;
- `evals/datasets/recall/recall.jsonl`: "does this earlier line help?" for a line or a memory candidate;
- `evals/datasets/same_fact/same_fact.jsonl` (phase 10, the user's choice): "same fact?" for the duplicate check.

Run from backend/: `uv run python ../evals/datasets/earlier/build.py`. Deterministic. Every item comes from
`facts.py` (written blind, labels by construction, reviewed under `evals/reviews/m13-review.md`).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(HERE))

from facts import CHANGES, FACTS, LOSSY_CHANGES, NEW_TOPICS, SMALL_TALK, Fact  # noqa: E402

from horizon.ai.agent.planner import _name  # noqa: E402
from horizon.ai.memory.jev import importance_request  # noqa: E402
from horizon.evals.datachecks import split_for  # noqa: E402
from horizon.services.memory.stretch import Present  # noqa: E402

_spec = importlib.util.spec_from_file_location("docs_build", HERE.parent / "docs" / "build.py")
assert _spec is not None and _spec.loader is not None
docs_build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(docs_build)
WHO, USER = docs_build.WHO, docs_build.USER
DATASETS = ROOT / "evals" / "datasets"
BY_ID = {f.id: f for f in FACTS}
CHUNK = 5   # importance: at most 5 lines per request, as live


def name_of(prof: dict[str, Any], who: str) -> str:
    return str(prof[WHO[who]]["name"])


# ── importance ──
def build_importance(prof: dict[str, Any]) -> list[dict[str, Any]]:
    by_who: dict[str, list[tuple[str, int, str, str]]] = {}
    for f in FACTS:
        by_who.setdefault(f.who, []).append((f.said, f.level, f.lang, f"fact:{f.id}"))
    for who, line, level, lang in SMALL_TALK:
        by_who.setdefault(who, []).append((line, level, lang, "written (small talk)"))
    rows: list[dict[str, Any]] = []
    for who in sorted(by_who):
        lines = by_who[who]
        mixed = [x for pair in zip(lines[::2], lines[1::2], strict=False) for x in pair] + \
            ([lines[-1]] if len(lines) % 2 else [])   # facts and small talk interleaved within each request
        p = prof[WHO[who]]
        present = Present(n=1, character_id=WHO[who], name=str(p["name"]), role=str(p.get("role") or ""),
                          about=str((p.get("personality") or {}).get("summary") or ""))
        for start in range(0, len(mixed), CHUNK):
            chunk = mixed[start:start + CHUNK]
            state, _ = importance_request(present, USER, [x[0] for x in chunk])
            for i, (_line, level, lang, source) in enumerate(chunk, 1):
                item_id = f"imp-{len(rows) + 1:03d}"
                rows.append({"id": item_id, "question_id": "importance", "split": split_for(item_id), "lang": lang,
                             "kind": "one_on_one",
                             "item": {"state": state, "name": _name(str(p["name"])), "n": i, "key": f"importance:l{i}"},
                             "label": level, "source": source})
    return rows


# ── the rewrite guard ──
def build_guard(prof: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def add(f: Fact, new: str, label: str, how: str, said: str | None = None) -> None:
        item_id = f"mgd-{len(rows) + 1:03d}"
        state = {"quoted_old": f.memory, "quoted_new": new, "quoted_source": f"{USER}: {said or f.said}"}
        rows.append({"id": item_id, "question_id": "memory_guard", "split": split_for(item_id), "lang": f.lang,
                     "kind": how, "item": {"state": state, "key": "memory_guard"}, "label": label,
                     "source": f"fact:{f.id}"})

    for f in FACTS:
        add(f, f.extend, "yes", "extend")
        add(f, f.lossy, "no", "lossy")
        if f.reword:
            add(f, f.reword, "yes", "reword")
        if f.lossy2:
            add(f, f.lossy2, "no", "lossy")
    # memory_guard v2: a detail the conversation changed counts as kept when the new line gives its new value
    for fid, (said, new) in CHANGES.items():
        add(BY_ID[fid], new, "yes", "changed", said)
        if fid in LOSSY_CHANGES:
            add(BY_ID[fid], LOSSY_CHANGES[fid], "no", "changed_lossy", said)
    return rows


# ── same fact? (the duplicate check, the user's choice in phase 10) ──
def build_same_fact() -> list[dict[str, Any]]:
    """A memory against a line that says the same thing (its rewording: yes), or doesn't: its extension (a new
    detail), another fact of the same character, or its changed value."""
    rows: list[dict[str, Any]] = []

    def add(f: Fact, new: str, label: str, how: str) -> None:
        item_id = f"sfa-{len(rows) + 1:03d}"
        rows.append({"id": item_id, "question_id": "same_fact", "split": split_for(item_id), "lang": "en",
                     "kind": how, "item": {"state": {"quoted_old": f.memory, "quoted_new": new}, "key": "same_fact"},
                     "label": label, "source": f"fact:{f.id}"})

    for i, f in enumerate(FACTS):
        if f.reword:
            add(f, f.reword, "yes", "reworded")
        add(f, f.extend, "no", "extended")
        other = next(g for g in FACTS[i + 1:] + FACTS if g.who == f.who and g.id != f.id)
        add(f, other.memory, "no", "other")
    for fid, (_said, new) in CHANGES.items():
        add(BY_ID[fid], new, "no", "changed")
    return rows


# ── needs something from earlier? ──
FILLER = {who: [line for w, line, level, lang in SMALL_TALK if w == who and level == 1 and lang == "en"]
          for who in WHO}
ACK = "Oh, that's good to know."


def earlier_row(n: int, prof: dict[str, Any], docs: dict[str, list[str]], who: str, before: list[tuple[str, str]],
                message: str, label: str, lang: str, source: str) -> dict[str, Any]:
    cid = WHO[who]
    sctx = docs_build.session(docs_build.WORLD_OF[who], [cid], [*before, ("you", message)], prof, "one_on_one")
    from horizon.ai.agent.plan_state import build_turn_plan_state
    from horizon.ai.agent.planner import plan_state_input
    from horizon.ai.contexts import PlanRequest

    req = PlanRequest(session=sctx, speaker_id=cid, cast=docs_build.views([cid], prof), kind="reply", latest=message,
                      started_at=docs_build.T0, documents={cid: docs[cid]} if cid in docs else {})
    state = dict(build_turn_plan_state(plan_state_input(req)).state)
    item_id = f"erl-{n:03d}"
    return {"id": item_id, "question_id": "earlier", "split": split_for(item_id), "lang": lang, "kind": "one_on_one",
            "item": {"state": state, "name": _name(name_of(prof, who)), "key": f"earlier:{cid}"}, "label": label,
            "source": source}


def build_earlier(prof: dict[str, Any], docs: dict[str, list[str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i, f in enumerate(FACTS):   # yes: the line refers back to a fact that isn't shown
        filler = FILLER[f.who][i % len(FILLER[f.who])]
        before = [("you", filler), (f.who, "Ha, fair enough.")]
        rows.append(earlier_row(len(rows) + 1, prof, docs, f.who, before, f.probe, "yes", f.lang,
                                f"fact:{f.id} (not shown)"))
        if f.probe2:
            rows.append(earlier_row(len(rows) + 1, prof, docs, f.who, [], f.probe2, "yes", f.lang,
                                    f"fact:{f.id} (not shown, probe 2)"))
    for who, message in NEW_TOPICS:   # no: it starts something new
        rows.append(earlier_row(len(rows) + 1, prof, docs, who, [], message, "no", "en", "written (new topic)"))
    for f in [f for f in FACTS if f.lang == "en"][:30]:   # no: what it needs is right there in the lines shown
        rows.append(earlier_row(len(rows) + 1, prof, docs, f.who, [("you", f.said), (f.who, ACK)], f.probe, "no",
                                f.lang, f"fact:{f.id} (shown)"))
    return rows


# ── does this earlier line help? ──
def overlap(a: str, b: str) -> int:
    wa = {w.strip(".,?!'").lower() for w in a.split() if len(w) > 3}
    wb = {w.strip(".,?!'").lower() for w in b.split() if len(w) > 3}
    return len(wa & wb)


def distractor(f: Fact) -> Fact:
    """Another fact told to the same character (the one sharing most words with the probe), never this one."""
    others = [g for g in FACTS if g.id != f.id and g.who == f.who] or [g for g in FACTS if g.id != f.id]
    return max(others, key=lambda g: (overlap(f.probe, g.said) + overlap(f.probe, g.memory), g.id))


def build_recall(prof: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def add(f: Fact, kind: str, candidate: str, label: str, source: str) -> None:
        item_id = f"rcl-{len(rows) + 1:03d}"
        state = {"mode": "one_on_one", "candidate_kind": "earlier line" if kind == "line" else "memory",
                 "quoted_query": f.probe, "quoted_candidate": candidate}
        cand_id = f"msg_{f.id}" if kind == "line" else f"mem_{f.id}"
        rows.append({"id": item_id, "question_id": "recall", "split": split_for(item_id), "lang": f.lang,
                     "kind": kind, "item": {"state": state, "name": _name(name_of(prof, f.who)),
                                            "key": f"recall:{cand_id}"},
                     "label": label, "source": source})

    for i, f in enumerate(FACTS):
        name = name_of(prof, f.who)
        d = distractor(f)
        add(f, "line", f"{name}: Hi {USER}, what's new?\n{USER}: {f.said}", "yes", f"fact:{f.id}")
        add(f, "line", f"{name}: Hi {USER}, what's new?\n{USER}: {d.said}", "no", f"fact:{f.id} vs {d.id}")
        if i % 2 == 0:
            add(f, "memory", f.memory, "yes", f"fact:{f.id}")
            add(f, "memory", d.memory, "no", f"fact:{f.id} vs {d.id}")
    return rows


def problems(sets: dict[str, list[dict[str, Any]]]) -> list[str]:
    out: list[str] = []
    imp = sets["importance"]
    if len(imp) != 100 or sum(r["label"] == 1 for r in imp) < 30:
        out.append(f"importance: {len(imp)} items, {sum(r['label'] == 1 for r in imp)} to drop (want 100, ≥ 30)")
    g = sets["memory_guard"]
    if not 110 <= len(g) <= 160 or sum(r["label"] == "no" for r in g) < 60:   # v2: + the changed values
        out.append(f"memory_guard: {len(g)} items, {sum(r['label'] == 'no' for r in g)} lossy (want 110–160, ≥ 60)")
    sf = sets.get("same_fact", [])
    if sets.get("same_fact") is not None and (len(sf) < 100 or sum(r["label"] == "yes" for r in sf) < 20):
        out.append(f"same_fact: {len(sf)} items, {sum(r['label'] == 'yes' for r in sf)} same (want ≥ 100, ≥ 20)")
    e = sets["earlier"]
    if not 110 <= len(e) <= 130 or sum(r["label"] == "yes" for r in e) < 60:
        out.append(f"earlier: {len(e)} items, {sum(r['label'] == 'yes' for r in e)} yes (want ~120, ≥ 60)")
    r_ = sets["recall"]
    if not 110 <= len(r_) <= 130 or sum(r["label"] == "yes" for r in r_) < 60:
        out.append(f"recall: {len(r_)} items, {sum(r['label'] == 'yes' for r in r_)} relevant (want ~120, ≥ 60)")
    for name, rows in sets.items():
        if not any(r["split"] == "test" for r in rows) or not any(r["split"] == "dev" for r in rows):
            out.append(f"{name}: needs both splits")
    return out


def main() -> int:
    prof = docs_build.profiles()
    docs = docs_build.titles(prof)
    sets = {"importance": build_importance(prof), "memory_guard": build_guard(prof),
            "earlier": build_earlier(prof, docs), "recall": build_recall(prof), "same_fact": build_same_fact()}
    bad = problems(sets)
    for line in bad:
        print(line)
    for name, rows in sets.items():
        out = DATASETS / name / f"{name}.jsonl"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        c = Counter((str(r["label"]), r["split"]) for r in rows)
        print(f"{name}: {len(rows)} -> {out.relative_to(ROOT).as_posix()}: "
              + ", ".join(f"{k}/{s} {n}" for (k, s), n in sorted(c.items())))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())

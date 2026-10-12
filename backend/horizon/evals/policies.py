"""How the emotion and reaction decision items are scored: the live code rules, applied to Jev's answer (docs/ai/06 E8;
docs/ai/02 B5; turn-plan-emotion design D26; evaluation-harness "Decision suite").

- **Emotion:** the policy answer is the face `decide_face` would send for the item's base face, with the merge, keep
  and fade applied. Correct when that face is in the item's acceptable set, or it is the kept (or faded) base face and
  the item allows keeping. The trivial baseline is "always keep the current face" (with the fade).
- **Reaction:** one listener per item. The policy answer is the face that would show, or `none` when nothing shows
  (no cap: a single listener). Correct when it is in the acceptable set. The baseline is "always `none`".
- **Floors** come from {0.5, 0.6, 0.7, 0.8, 0.9}, chosen on the dev split from each item's one seeded order (B5, E8). A
  floor must beat both "no floor" and "fallback only"; ties go to the lower floor (more Jev answers used). The emotion
  grid also holds 0.2, 0.3 and 0.4 (turn-plan-emotion D36, the user's choice): Jev's 8-option confidences sit low
  (median 0.58) while its picks are mostly right, so B5's grid only removed right answers.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from horizon.ai.agent.emotion import MERGED, decide_face, kept
from horizon.ai.agent.reactions import keep as keep_reactions
from horizon.ai.contexts import ListenerView
from horizon.ai.decider import ChoiceAnswer
from horizon.evals.metrics import mcnemar_exact, wilson

FLOORS = (0.5, 0.6, 0.7, 0.8, 0.9)
GRIDS = {"emotion": (0.2, 0.3, 0.4, *FLOORS), "reaction": (0.2, 0.3, 0.4, *FLOORS)}   # D36 (reactions: D39)
FADE = frozenset({"surprised", "embarrassed"})


def emotion_answer(answer: ChoiceAnswer | None, label: Mapping[str, Any], floor: float,
                   fade: frozenset[str] = FADE) -> str:
    return decide_face(answer, base=str(label["previous"]), floor=floor, fade=fade).face


def emotion_correct(face: str, label: Mapping[str, Any], fade: frozenset[str] = FADE) -> bool:
    if face in set(label.get("acceptable") or []):
        return True
    return bool(label.get("keep_ok")) and face == kept(str(label["previous"]), fade)[0]


def emotion_baseline(label: Mapping[str, Any], fade: frozenset[str] = FADE) -> bool:
    """"Always keep the current face" on this item."""
    return emotion_correct(kept(str(label["previous"]), fade)[0], label, fade)


def reaction_answer(answer: ChoiceAnswer | None, label: Mapping[str, Any], floor: float,
                    fade: frozenset[str] = FADE) -> str:
    lv = ListenerView(id="chr_item", name="item", face=str(label["previous"]))
    shown = keep_reactions({"chr_item": answer}, [lv], floor=floor, fade=fade, seed="item", window=(300.0, 800.0))
    return shown[0].emotion if shown else "none"


def reaction_correct(face: str, label: Mapping[str, Any]) -> bool:
    return face in set(label.get("acceptable") or [])


def reaction_baseline(label: Mapping[str, Any]) -> bool:
    return reaction_correct("none", label)


def accuracy(rows: Sequence[tuple[ChoiceAnswer | None, Mapping[str, Any]]], score: Callable[..., bool]) -> float:
    return sum(1 for a, lab in rows if score(a, lab)) / len(rows) if rows else 0.0


def choose_floor(rows: Sequence[tuple[ChoiceAnswer | None, Mapping[str, Any]]], kind: str) -> dict[str, Any]:
    """B5 on dev rows (answer, label): accuracy per floor, "no floor" (0) and "fallback only" (above any confidence)."""
    answer = emotion_answer if kind == "emotion" else reaction_answer
    correct: Callable[..., bool] = emotion_correct if kind == "emotion" else (lambda f, lab, *_: reaction_correct(f, lab))

    def acc(floor: float) -> float:
        return accuracy(rows, lambda a, lab: correct(answer(a, lab, floor), lab))

    floors = GRIDS.get(kind, FLOORS)
    grid = {f: acc(f) for f in floors}
    no_floor, fallback_only = acc(0.0), acc(1.01)
    best = max(floors, key=lambda f: (grid[f], -f))
    return {"floor": best, "accuracy": grid[best], "grid": grid, "no_floor": no_floor, "fallback_only": fallback_only,
            "beats_both": grid[best] >= no_floor and grid[best] > fallback_only}


# ── the report (D26) ──
def answer_of(row: Mapping[str, Any]) -> ChoiceAnswer | None:
    """A stored row's first-order (live seeded order) answer, or None when it was invalid."""
    if row.get("invalid") or row.get("answer") is None:
        return None
    return ChoiceAnswer(str(row["answer"]), confidence=row.get("confidence"), probabilities=row.get("probabilities"))


def kind_of(question_id: str) -> str | None:
    return "emotion" if question_id.startswith("emotion_") else "reaction" if question_id == "reaction" else None


def report(rows: Sequence[Mapping[str, Any]], kind: str, fade: frozenset[str] = FADE) -> list[str]:
    """B5's floor from dev, then the test split once with it, on its English items: accuracy (Wilson), the baseline
    and its paired difference (exact McNemar), coverage, the merge rate (emotion) or the reaction share (reactions).
    Other languages are a "runs" check only (the user's rule, 2026-10-12)."""
    answer = emotion_answer if kind == "emotion" else reaction_answer
    title = "Emotion" if kind == "emotion" else "Reactions"
    dev = [(answer_of(r), r["label"]) for r in rows if r.get("split") == "dev"]
    test = [r for r in rows if r.get("split") == "test"]
    if not dev or not test:
        return [f"## {title}: needs dev and test items (dev {len(dev)}, test {len(test)})"]
    sel = choose_floor(dev, kind)
    floor = float(sel["floor"])

    def score(r: Mapping[str, Any]) -> tuple[bool, bool, str]:
        lab = r["label"]
        face = answer(answer_of(r), lab, floor)
        if kind == "emotion":
            return emotion_correct(face, lab, fade), emotion_baseline(lab, fade), face
        return reaction_correct(face, lab), reaction_baseline(lab), face

    everything = [(r, *score(r)) for r in test]
    # The user's rule (2026-10-12): English is evaluated for accuracy; other languages only need to run, right or
    # wrong isn't judged. So every figure and target below is on the English test items.
    scored = [x for x in everything if str(x[0].get("lang") or "en") == "en"]
    others = [x for x in everything if str(x[0].get("lang") or "en") != "en"]
    if not scored:
        return [f"## {title}: no English test items"]
    k = sum(ok for _, ok, _, _ in scored)
    n = len(scored)
    base = sum(b for _, _, b, _ in scored)
    only_policy = sum(ok and not b for _, ok, b, _ in scored)
    only_base = sum(b and not ok for _, ok, b, _ in scored)
    lo, hi = wilson(k, n)
    blo, bhi = wilson(base, n)
    out = [f"## {title}: floor {floor:.1f} (chosen on dev: {sel['accuracy']:.2f}; no floor {sel['no_floor']:.2f}, "
           f"fallback only {sel['fallback_only']:.2f}{'' if sel['beats_both'] else '; DOES NOT beat both'})",
           f"- English test accuracy {k}/{n} = {k / n:.2f} (95% Wilson {lo:.2f}–{hi:.2f}); target ≥ 0.80",
           f"- baseline ({'always keep' if kind == 'emotion' else 'always none'}) {base}/{n} = {base / n:.2f} "
           f"(Wilson {blo:.2f}–{bhi:.2f}); difference {(k - base) / n:+.2f} (target ≥ +0.15), exact McNemar "
           f"p {mcnemar_exact(only_policy, only_base):.3f} ({only_policy} only the policy right, {only_base} only "
           f"the baseline)"]
    used = 0
    merged_n = neutral_n = 0
    shown = 0
    for r, _, _, face in scored:
        a, lab = answer_of(r), r["label"]
        if kind == "emotion":
            f = decide_face(a, base=str(lab["previous"]), floor=floor, fade=fade)
            used += f.outcome == "jev"
            if lab["previous"] == "neutral":
                neutral_n += 1
                merged_n += any(c.get("name") == MERGED for c in f.compared)
        else:
            used += a is not None and a.source != "fallback"
            shown += face != "none"
    out.append(f"- coverage: Jev's answer used on {used}/{n} items ({used / n:.2f})")
    if kind == "emotion":
        out.append(f"- the neutral + none merge decided {merged_n}/{neutral_n} items with a neutral previous face")
    else:
        out.append(f"- reaction share: {shown}/{n} items would show a reaction ({shown / n:.2f}; under ~0.30 is read "
                   "by hand)")
    if others:
        ran = sum(1 for r, *_ in others if answer_of(r) is not None)
        out.append(f"- other languages: {ran}/{len(others)} test items ran and returned an answer (only that they run "
                   "is checked; right or wrong isn't judged)")
    return out

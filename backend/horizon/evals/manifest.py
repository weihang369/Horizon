"""`horizon eval manifest`: the Jev request manifest for the model comparison after the AI stage (images-music design
D19; evaluation-harness "The Jev request manifest").

For every Jev set the evaluation asks, the manifest records the SHA-256 of each request **body** (`{state,
questions}`, without the model or the canary fingerprint), compiled exactly as the suite sends it today, and whether
the accepted jev-1.13 answer for it is in the store. A later run on another Jev model loads it with
`--against-manifest`: the gateway then refuses any Jev request whose body is not listed, so the comparison measures
the model and nothing else (a changed state, question or bank version would be refused and named).

The sets:
- every `decisions` dataset folder (the judges' B4 sets included); a choice is also listed in its reversed-option order,
  which the order-bias rows send;
- the drift canary's 20 requests (never stored: the canary always reaches Jev);
- `deep-check`'s 45 requests;
- `safety`'s Jev parts. The private items appear only as hashes, like every other body here.

Built from the datasets and the store at $0; nothing is sent.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from horizon.evals.store import sha


def manifest_name(model: str) -> str:
    """jev-comparison (D11): the manifest of a pinned model is named after it (`typesafe/jev-1.13` gives
    `jev-1.13-requests.json`), so a switch writes a new one beside the old."""
    return f"{model.rsplit('/', 1)[-1]}-requests.json"


def body_hash(state: Any, questions: Mapping[str, Any]) -> str:
    return sha({"state": state, "questions": dict(questions)})


def _stored(root: Path, model: str, state: Any, questions: Mapping[str, Any], fingerprint: str | None,
            order: Mapping[str, list[str]] | None = None) -> bool:
    from horizon.evals.store import jev_key

    return (root / f"{jev_key(model, state, dict(questions), fingerprint, order)}.json").is_file()


def _decisions_items() -> Iterable[tuple[str, str, Any, dict[str, Any], dict[str, list[str]] | None]]:
    """Every body `Decisions.run` sends, exactly as it sends it (jev-comparison D20 found two that M15's builder got
    wrong): a noul or a levelled score under the item's live key (`docs:{id}`, `earlier:{id}`, …); the pairwise judge's
    two asks, the second with the replies swapped in the state; a choice in its seeded order and reversed."""
    from horizon.ai.decider import Choice, Noul, Score, wire_question
    from horizon.evals import judges
    from horizon.evals.suites import DATASETS, dataset_files, item_question, load_dataset, reordered

    for path in dataset_files():
        name = path.relative_to(DATASETS).parts[0]
        for i in load_dataset(path):
            if i.get("smoke_only"):
                continue
            q = item_question(i)   # the item's own seed, as the suite compiles it
            qid, iid, state = str(i["question_id"]), str(i["id"]), i["item"]["state"]
            if isinstance(q, Noul) or (isinstance(q, Score) and isinstance(i["label"], int)):
                yield name, iid, state, {str(i["item"].get("key") or qid): wire_question(q)}, None
            elif qid == judges.PAIRWISE:
                yield name, iid, state, {qid: wire_question(q)}, None
                yield name, iid, judges.swapped(state), {qid: wire_question(q)}, None
            else:
                yield name, iid, state, {qid: wire_question(q)}, None
                if isinstance(q, Choice) and not i.get("reask"):
                    r = reordered(q)
                    assert isinstance(r, Choice)
                    yield name, iid, state, {qid: wire_question(r)}, {qid: list(r.options)}


def decisions_bodies() -> Iterable[tuple[str, Any, dict[str, Any], dict[str, list[str]] | None]]:
    """(set, state, wire questions, order salt) for every decisions item, in both option orders for a choice."""
    for name, _id, state, qs, order in _decisions_items():
        yield name, state, qs, order


def item_hashes(*, test_mode: bool) -> dict[tuple[str, str], list[str]]:
    """jev-comparison (D8): (set, item id) → the body hashes its run asks (a choice in both orders), so the comparison
    report names each item whose body the manifest doesn't list. Built from the datasets at $0."""
    out: dict[tuple[str, str], list[str]] = {}
    for name, iid, state, qs, _order in _decisions_items():
        out.setdefault((name, iid), []).append(body_hash(state, qs))
    for name, iid, state, qs in _other_items(test_mode=test_mode):
        out.setdefault((name, iid), []).append(body_hash(state, qs))
    return out


def _other_items(*, test_mode: bool) -> Iterable[tuple[str, str, Any, dict[str, Any]]]:
    from horizon.ai.decider import wire_question
    from horizon.evals import deep_check_suite, safety_suite
    from horizon.evals.runner import EVALS_DIR

    canary = json.loads((EVALS_DIR / "canary.json").read_text(encoding="utf-8"))
    for it in canary["items"]:
        yield "canary", str(it["id"]), it["state"], dict(it["questions"])
    for it in deep_check_suite.items():
        state, qs, _purpose = deep_check_suite.request(it)
        yield "deep-check", str(it["id"]), state, qs
    for r in safety_suite.load_items(test_mode=test_mode).items:
        if r["part"] in safety_suite.JEV_PARTS:
            state, qs = safety_suite.state_for(r["part"], r["item"])
            yield f"safety:{r['part']}", str(r["id"]), state, {k: wire_question(q) for k, q in qs.items()}


def other_bodies(*, test_mode: bool) -> Iterable[tuple[str, Any, dict[str, Any]]]:
    """(set, state, wire questions) for the canary, deep-check and the safety suite's Jev parts."""
    for name, _id, state, qs in _other_items(test_mode=test_mode):
        yield name, state, qs


def build(*, model: str, fingerprint: str | None, store_root: Path, private_store_root: Path,
          test_mode: bool = False) -> dict[str, Any]:
    from horizon.ai.questions import load_bank

    sets: dict[str, dict[str, Any]] = {}

    def add(name: str, h: str, stored: bool | None) -> None:
        s = sets.setdefault(name, {"n": 0, "stored": 0, "bodies": []})
        s["n"] += 1
        s["stored"] += bool(stored)
        s["bodies"].append(h)

    for name, state, qs, order in decisions_bodies():
        add(name, body_hash(state, qs), _stored(store_root, model, state, qs, fingerprint, order))
    for name, state, qs in other_bodies(test_mode=test_mode):
        root = private_store_root if name.startswith("safety:") else store_root
        add(name, body_hash(state, qs), None if name == "canary" else _stored(root, model, state, qs, fingerprint))
    for s in sets.values():
        s["bodies"] = sorted(set(s["bodies"]))
    bank = load_bank()
    return {"model": model, "fingerprint": fingerprint,
            "bank": {qid: e.version for qid, e in sorted(bank.entries.items())},
            "sets": dict(sorted(sets.items()))}


def allowed(manifest: Mapping[str, Any]) -> frozenset[str]:
    """Every body the manifest lists, for the gateway's `--against-manifest` check."""
    return frozenset(h for s in manifest["sets"].values() for h in s["bodies"])


def load_allowed(path: str | Path) -> frozenset[str]:
    return allowed(json.loads(Path(path).read_text(encoding="utf-8")))

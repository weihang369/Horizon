"""The watch part of the who-speaks set: `who_scene.jsonl` from the committed watch histories (group-watch D23; task
10.2). Imported by `build.py` once `evals/watch/*.json` exist.

Each item is a cut of a history at a turn: the premise, the lines before it, the last line as `quoted_latest`, and the
candidates (the cast minus the last speaker; the histories keep all three awake). The labels are written blind under
`evals/reviews/m10-labels.md` after reading the histories and before any Jev answer: `SCENE_LABELS` maps
(history, turn) to the acceptable characters and the language. `round_robin_next` is the next character in cast order
after the last speaker (the baseline); `last_spoke` counts the lines since each candidate last spoke in the scene.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
WATCH = ROOT / "evals" / "watch"
sys.path.insert(0, str(ROOT / "backend"))

from horizon.ai.agent.cast_plan import state_input  # noqa: E402
from horizon.ai.agent.plan_state import build_turn_plan_state  # noqa: E402
from horizon.ai.contexts import CastRequest, CharacterView, MessageView, ParticipantView, SessionContext, WorldView  # noqa: E402
from horizon.evals.datachecks import split_for  # noqa: E402

USER = "Kai"
WINDOW = 12   # the scene's recent lines as the cast plan sees them (doc 07 G6's state: premise, summary, 12 lines)

# (history, the number of character lines before the cut) → (acceptable short names, lang). Labelled blind in task
# 10.2 after reading both histories, before any Jev answer. One name each: the candidates are the two characters
# who didn't just speak, so accepting both would accept anyone (m10-labels.md). All English (both histories are;
# the user's choice of 2026-10-13, recorded in docs/ai/checks/m10.md).
SCENE_LABELS: dict[tuple[str, int], tuple[list[str], str]] = {
    ("meridian_long", 1): (["mei"], "en"), ("meridian_long", 2): (["victor"], "en"),
    ("meridian_long", 5): (["amara"], "en"), ("meridian_long", 9): (["mei"], "en"),
    ("meridian_long", 10): (["mei"], "en"), ("meridian_long", 11): (["victor"], "en"),
    ("meridian_long", 12): (["amara"], "en"), ("meridian_long", 14): (["victor"], "en"),
    ("meridian_long", 15): (["amara"], "en"), ("meridian_long", 17): (["victor"], "en"),
    ("meridian_long", 19): (["victor"], "en"), ("meridian_long", 23): (["victor"], "en"),
    ("meridian_long", 24): (["amara"], "en"), ("meridian_long", 26): (["victor"], "en"),
    ("meridian_long", 27): (["amara"], "en"), ("meridian_long", 29): (["amara"], "en"),
    ("meridian_long", 36): (["amara"], "en"), ("meridian_long", 37): (["mei"], "en"),
    ("meridian_long", 38): (["amara"], "en"), ("meridian_long", 41): (["amara"], "en"),
    ("meridian_long", 42): (["amara"], "en"), ("meridian_long", 47): (["victor"], "en"),
    ("meridian_long", 48): (["amara"], "en"), ("meridian_long", 51): (["amara"], "en"),
    ("meridian_long", 52): (["victor"], "en"), ("meridian_long", 53): (["amara"], "en"),
    ("meridian_long", 56): (["victor"], "en"), ("meridian_long", 67): (["mei"], "en"),
    ("meridian_long", 68): (["amara"], "en"), ("meridian_long", 70): (["mei"], "en"),
    ("meridian_long", 71): (["victor"], "en"), ("meridian_long", 74): (["amara"], "en"),
    ("meridian_long", 78): (["mei"], "en"), ("meridian_long", 80): (["amara"], "en"),
    ("meridian_long", 85): (["victor"], "en"), ("meridian_long", 99): (["mei"], "en"),
    ("sunnyhollow", 1): (["takeshi"], "en"), ("sunnyhollow", 2): (["takeshi"], "en"),
    ("sunnyhollow", 4): (["rin"], "en"), ("sunnyhollow", 5): (["takeshi"], "en"),
    ("sunnyhollow", 6): (["rin"], "en"), ("sunnyhollow", 7): (["rin"], "en"), ("sunnyhollow", 8): (["hana"], "en"),
    ("sunnyhollow", 9): (["hana"], "en"), ("sunnyhollow", 10): (["takeshi"], "en"),
    ("sunnyhollow", 11): (["hana"], "en"), ("sunnyhollow", 12): (["hana"], "en"),
    ("sunnyhollow", 13): (["takeshi"], "en"), ("sunnyhollow", 14): (["takeshi"], "en"),
    ("sunnyhollow", 18): (["hana"], "en"), ("sunnyhollow", 21): (["hana"], "en"),
    ("sunnyhollow", 22): (["takeshi"], "en"), ("sunnyhollow", 23): (["takeshi"], "en"),
    ("sunnyhollow", 26): (["takeshi"], "en"), ("sunnyhollow", 29): (["takeshi"], "en"),
    ("sunnyhollow", 30): (["rin"], "en"), ("sunnyhollow", 32): (["takeshi"], "en"),
    ("sunnyhollow", 33): (["hana"], "en"), ("sunnyhollow", 34): (["rin"], "en"),
    ("sunnyhollow", 39): (["hana"], "en"),
}
# G11's growth (task 10.3, the user's choice of 2026-10-13): the first 60's test interval straddled 0.80, so B2's 40
# more cuts come from two further histories, labelled blind under the same rule before any Jev answer to them. In
# written order: four Meridian Inquiry cuts whose window held a six-word run of a bank example ("I'll be there at
# six", `overlap`) were replaced in place by four Sunny Hollow Market cuts, so no id or split moved.
SCENE_GROWN: dict[tuple[str, int], tuple[list[str], str]] = {
    ("meridian_inquiry", 1): (["victor"], "en"), ("meridian_inquiry", 4): (["victor"], "en"),
    ("meridian_inquiry", 5): (["amara"], "en"), ("meridian_inquiry", 7): (["victor"], "en"),
    ("meridian_inquiry", 9): (["mei"], "en"), ("meridian_inquiry", 10): (["victor"], "en"),
    ("meridian_inquiry", 18): (["amara"], "en"), ("meridian_inquiry", 24): (["mei"], "en"),
    ("meridian_inquiry", 25): (["mei"], "en"), ("meridian_inquiry", 29): (["amara"], "en"),
    ("meridian_inquiry", 30): (["amara"], "en"), ("sunnyhollow_market", 11): (["takeshi"], "en"),
    ("sunnyhollow_market", 28): (["takeshi"], "en"), ("sunnyhollow_market", 36): (["hana"], "en"),
    ("sunnyhollow_market", 37): (["rin"], "en"), ("meridian_inquiry", 44): (["amara"], "en"),
    ("meridian_inquiry", 45): (["mei"], "en"), ("meridian_inquiry", 49): (["victor"], "en"),
    ("sunnyhollow_market", 2): (["takeshi"], "en"), ("sunnyhollow_market", 4): (["rin"], "en"),
    ("sunnyhollow_market", 5): (["takeshi"], "en"), ("sunnyhollow_market", 7): (["takeshi"], "en"),
    ("sunnyhollow_market", 10): (["takeshi"], "en"), ("sunnyhollow_market", 15): (["rin"], "en"),
    ("sunnyhollow_market", 16): (["takeshi"], "en"), ("sunnyhollow_market", 17): (["hana"], "en"),
    ("sunnyhollow_market", 19): (["rin"], "en"), ("sunnyhollow_market", 23): (["takeshi"], "en"),
    ("sunnyhollow_market", 24): (["rin"], "en"), ("sunnyhollow_market", 29): (["hana"], "en"),
    ("sunnyhollow_market", 32): (["takeshi"], "en"), ("sunnyhollow_market", 33): (["hana"], "en"),
    ("sunnyhollow_market", 35): (["hana"], "en"), ("sunnyhollow_market", 39): (["hana"], "en"),
    ("sunnyhollow_market", 40): (["takeshi"], "en"), ("sunnyhollow_market", 41): (["takeshi"], "en"),
    ("sunnyhollow_market", 43): (["takeshi"], "en"), ("sunnyhollow_market", 44): (["hana"], "en"),
    ("sunnyhollow_market", 45): (["hana"], "en"), ("sunnyhollow_market", 46): (["takeshi"], "en"),
}
SHORT = {"amara": "chr_seedAmara", "mei": "chr_seedMei", "victor": "chr_seedVictor", "hana": "chr_seedHana",
         "rin": "chr_seedRin", "takeshi": "chr_seedTakeshi"}


def history(hid: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((WATCH / f"{hid}.json").read_text(encoding="utf-8"))
    return data


def cut(h: dict[str, Any], k: int, prof: dict[str, dict[str, Any]],
        faces: dict[str, str] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """The state and the label skeleton for the turn after the k-th character line. `faces` (M11's watch emotion
    growth): each character's face then; neutral by default, as M10's items were built."""
    from datetime import UTC, datetime

    lines = h["lines"]
    idx = [i for i, x in enumerate(lines) if x["kind"] == "line"]
    seen = lines[: idx[k - 1] + 1]
    summary = seen[-1]["summary"]
    upto = seen[-1]["summary_upto"]
    after = [x for x in seen if upto is None or int(x["seq"]) > int(upto)][-WINDOW:]
    cast = list(h["cast"])
    parts = [ParticipantView(character_id=c, name=str(prof[c]["name"]), role="speaker",
                             character_role=str(prof[c].get("role") or ""), energy={"current": 500, "max": 1000})
             for c in cast]
    recent = [MessageView(id=f"m{x['seq']}", seq=int(x["seq"]), author_type="user" if x["kind"] == "note" else "character",
                          character_id=None if x["kind"] == "note" else x["speaker"],
                          name=USER if x["kind"] == "note" else str(prof[x["speaker"]]["name"]),
                          kind="direction" if x["kind"] == "note" else "chat", content=x["text"]) for x in after]
    sctx = SessionContext(session_id="ses_eval", seed="m10-eval", world=WorldView(id=h["world"], name="",
                                                                                  you={"displayName": USER}),
                          mode="watch", title="eval", config={"premise": h["premise"]}, participants=parts,
                          recent=recent, summary=summary)
    speakers = [x["speaker"] for x in seen if x["kind"] == "line"]
    last = speakers[-1]
    cands = [c for c in cast if c != last]
    since: dict[str, int | None] = {}
    for c in cands:
        j = max((i for i, s in enumerate(speakers) if s == c), default=None)
        since[c] = None if j is None else len(speakers) - 1 - j
    latest_line = seen[-1]
    latest = latest_line["text"] if latest_line["kind"] == "note" else f"{prof[last]['name']}: {latest_line['text']}"
    req = CastRequest(session=sctx, kind="scene", candidates=cands,
                      cast=[CharacterView(id=c, name=str(prof[c]["name"]), profile=prof[c]) for c in cast],
                      latest=latest, base_faces={c: (faces or {}).get(c, "neutral") for c in cast}, turns_since=since,
                      started_at=datetime(2026, 10, 3, 3, 0, tzinfo=UTC))
    state = build_turn_plan_state(state_input(req)).state
    label = {"candidates": cands, "none_ok": False, "last_spoke": since,
             "round_robin_next": cast[(cast.index(last) + 1) % len(cast)]}
    return state, label


def scene_prefix(n: int, tests: int = 20) -> str:
    """`build.id_prefix` for this part (D23's built note: the first of wsc, wsc1, … with at least 20 test items). Kept
    here so the module loads by path without importing a module named `build`."""
    k = 0
    while sum(split_for(f"{'wsc' if k == 0 else f'wsc{k}'}-{i:03d}") == "test" for i in range(1, n + 1)) < tests:
        k += 1
    return "wsc" if k == 0 else f"wsc{k}"


def build_scene(prof: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    prefix = scene_prefix(len(SCENE_LABELS))   # from the first 60 alone, so their ids and splits never move
    order = sorted(SCENE_LABELS.items()) + list(SCENE_GROWN.items())   # the growth after them, in written order
    for n, ((hid, k), (ok, lang)) in enumerate(order, 1):
        state, label = cut(history(hid), k, prof)
        label["acceptable"] = [SHORT[c] for c in ok]
        item_id = f"{prefix}-{n:03d}"
        rows.append({"id": item_id, "question_id": "who_scene", "split": split_for(item_id), "lang": lang,
                     "kind": "watch", "item": {"state": state, "seed": f"m10-scene:{n}", "none": False,
                                               "values": [{"key": c, "name": str(prof[c]["name"]),
                                                           "role": str(prof[c].get("role") or "")}
                                                          for c in label["candidates"]]},
                     "label": label, "source": f"watch:{hid}#{k}"})
    return rows


def write_scene(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("who_scene: no labels yet (SCENE_LABELS is filled in task 10.2)")
        return
    (HERE / "who_scene.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                          encoding="utf-8", newline="\n")
    print(f"wrote {len(rows)} who_scene items")

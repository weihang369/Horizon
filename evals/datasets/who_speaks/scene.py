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

# (history, the number of character lines before the cut) → (acceptable short names, lang). Filled in task 10.2.
SCENE_LABELS: dict[tuple[str, int], tuple[list[str], str]] = {}
SHORT = {"amara": "chr_seedAmara", "mei": "chr_seedMei", "victor": "chr_seedVictor", "hana": "chr_seedHana",
         "rin": "chr_seedRin", "takeshi": "chr_seedTakeshi"}


def history(hid: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((WATCH / f"{hid}.json").read_text(encoding="utf-8"))
    return data


def cut(h: dict[str, Any], k: int, prof: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """The state and the label skeleton for the turn after the k-th character line."""
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
                      latest=latest, base_faces=dict.fromkeys(cast, "neutral"), turns_since=since,
                      started_at=datetime(2026, 10, 3, 3, 0, tzinfo=UTC))
    state = build_turn_plan_state(state_input(req)).state
    label = {"candidates": cands, "none_ok": False, "last_spoke": since,
             "round_robin_next": cast[(cast.index(last) + 1) % len(cast)]}
    return state, label


def build_scene(prof: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for n, ((hid, k), (ok, lang)) in enumerate(sorted(SCENE_LABELS.items()), 1):
        state, label = cut(history(hid), k, prof)
        label["acceptable"] = [SHORT[c] for c in ok]
        item_id = f"wsc1-{n:03d}"
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

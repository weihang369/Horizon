"""The 20 frozen transcripts of layer 3 (docs/ai/02 B2–B3; images-music design D10; evaluation-harness "Frozen
transcripts for layer 3"). No network, no key.

- **Kept (4):** the long ones, unchanged (`long_*.json`): the "past one drop" four. Their compared turns are 10, evenly
  spaced from the first turn with a summary.
- **Cut (9), at $0:** windows of the committed `naive` histories, written by `write_cuts()`:
  - debate × 4, from the debate suite's dev debates (`debate_split`), so the two measures stay independent;
  - watch × 5, from the four watch histories, two from `meridian_long`.

  A cut file names its source and window, keeps the source's lines unchanged up to the window's end (the lines before
  it are the history), and marks the compared ones. The M11 free runs are left out: they are `agent` output.
- **Short (7):** generated once with `naive` from `transcripts/scripts/short_*.json` (`transcript --short`).

Every transcript carries the memory list at its start (the seed memories of its cast; a transcript has no pause, so it
doesn't change inside it) and, per turn or line, the rolling summary in force. The split is the hash rule on the
transcript's id with M10's prefix search, per mode, for a third of each mode on test (`split`): computed from the
ids alone, so it can't move once the 20 exist.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from horizon.config import REPO_ROOT
from horizon.evals.datachecks import split_for
from horizon.evals.runner import EVALS_DIR

TRANSCRIPTS = EVALS_DIR / "transcripts"
KEPT = ("long_one_on_one_en", "long_one_on_one_ms", "long_group_meridian", "long_group_sunnyhollow")
LONG_COMPARED = 10
EXPECTED = {"one_on_one": 6, "group": 5, "debate": 4, "watch": 5}

# (id, source history relative to evals/, first compared seq, last compared seq; the round banners take seqs too).
# The debates are the dev side of `debate_split` over the 13 (d06, d09, d10, d11, d12; d12 left out to keep two per
# world); a 15-argument debate keeps its last 12, so its first three arguments are the history.
CUTS: tuple[tuple[str, str, int, int], ...] = (
    ("cut_debate_d06", "debates/d06.json", 2, 15),
    ("cut_debate_d09", "debates/d09.json", 5, 18),
    ("cut_debate_d10", "debates/d10.json", 5, 18),
    ("cut_debate_d11", "debates/d11.json", 2, 10),
    ("cut_watch_meridian_long_a", "watch/meridian_long.json", 34, 45),     # the clinic call (note 37) inside
    ("cut_watch_meridian_long_b", "watch/meridian_long.json", 90, 101),    # late: 88 lines of history
    ("cut_watch_meridian_inquiry", "watch/meridian_inquiry.json", 24, 35),
    ("cut_watch_sunnyhollow", "watch/sunnyhollow.json", 19, 30),
    ("cut_watch_sunnyhollow_market", "watch/sunnyhollow_market.json", 41, 52),
)
SOURCE_KEYS = {"debate": ("motion", "format", "roundsPreset", "phases", "sides"), "watch": ("premise",)}


def seed_memories(cast: Sequence[str], seed_dir: Path | None = None) -> dict[str, list[dict[str, str]]]:
    """The start-of-session memory list per cast member: the seed memories (a character with none has an empty list)."""
    root = seed_dir or REPO_ROOT / "seed"
    out: dict[str, list[dict[str, str]]] = {}
    for cid in cast:
        p = root / "memory" / f"{cid}.json"
        rows = json.loads(p.read_text(encoding="utf-8"))["data"] if p.is_file() else []
        out[cid] = [{"id": str(r["id"]), "text": str(r["text"])} for r in rows]
    return out


# ── the cuts ──
def cut(tid: str, source: str, first: int, last: int, root: Path = EVALS_DIR) -> dict[str, Any]:
    src: dict[str, Any] = json.loads((root / source).read_text(encoding="utf-8"))
    lines = [ln for ln in src["lines"] if int(ln["seq"]) <= last]
    seqs = [int(ln["seq"]) for ln in lines]
    if first not in seqs or last not in seqs:
        raise ValueError(f"{tid}: window {first}–{last} is outside {source}")
    out_lines = [{**ln, "summary_upto": ln.get("summary_upto"), "summary": ln.get("summary"),
                  "compared": int(ln["seq"]) >= first and ln["kind"] in ("argument", "line")} for ln in lines]
    doc: dict[str, Any] = {"schemaVersion": 1, "id": tid, "mode": src["mode"], "world": src["world"],
                           "cast": src["cast"], "language": src["language"],
                           "source": {"history": source, "id": src["id"], "from_seq": first, "to_seq": last}}
    doc.update({k: src[k] for k in SOURCE_KEYS[src["mode"]] if k in src})
    doc["memories"] = seed_memories(src["cast"])
    doc["lines"] = out_lines
    return doc


def write_cuts(root: Path = EVALS_DIR) -> list[Path]:
    """Writes the 9 cut files (deterministic: a re-run rewrites the same bytes)."""
    out = []
    for tid, source, first, last in CUTS:
        p = root / "transcripts" / f"{tid}.json"
        p.write_text(json.dumps(cut(tid, source, first, last, root), ensure_ascii=False, indent=1) + "\n",
                     encoding="utf-8", newline="\n")
        out.append(p)
    return out


# ── the loader ──
def kind_of(t: dict[str, Any]) -> str:
    if t["id"] in KEPT:
        return "kept"
    return "cut" if "source" in t else "short"


def long_compared(t: dict[str, Any]) -> list[int]:
    """10 turns evenly spaced from the first turn with a summary to the end."""
    turns = t["turns"]
    first = next(i for i, x in enumerate(turns) if x.get("summary"))
    span = list(range(first, len(turns)))
    step = len(span) / LONG_COMPARED
    return [span[int(k * step)] for k in range(LONG_COMPARED)]


def compared(t: dict[str, Any]) -> list[int]:
    """The compared units: turn indices (1:1, group) or line seqs (debate, watch)."""
    if "lines" in t:
        return [int(ln["seq"]) for ln in t["lines"] if ln.get("compared")]
    if t["id"] in KEPT:
        return long_compared(t)
    return list(range(len(t["turns"])))


def load(name: str, root: Path = TRANSCRIPTS) -> dict[str, Any]:
    t: dict[str, Any] = json.loads((root / f"{name}.json").read_text(encoding="utf-8"))
    t.setdefault("memories", seed_memories(t["cast"]))
    t["compared"] = compared(t)
    return t


def split(ids_by_mode: Mapping[str, Sequence[str]]) -> dict[str, str]:
    """The hash rule on the transcript id, with M10's prefix search (as `debate_split`): per mode, the first prefix that
    puts round(n / 3) of its transcripts (at least 1) on test."""
    out: dict[str, str] = {}
    for ids in ids_by_mode.values():
        want = max(1, round(len(ids) / 3))
        k = 0
        while True:
            pre = "tr" if k == 0 else f"tr{k}"
            sp = {i: split_for(f"{pre}-{i}") for i in ids}
            if sum(v == "test" for v in sp.values()) == want:
                out.update(sp)
                break
            k += 1
    return out


def load_all(root: Path = TRANSCRIPTS) -> list[dict[str, Any]]:
    """Every frozen transcript (kept, cut and short), by id, each with its `split`."""
    ts = [load(p.stem, root) for p in sorted(root.glob("*.json"))]
    by_mode: dict[str, list[str]] = {}
    for t in ts:
        by_mode.setdefault(t["mode"], []).append(t["id"])
    sp = split(by_mode)
    for t in ts:
        t["split"] = sp[t["id"]]
    return ts


def labelled(ts: Sequence[dict[str, Any]], label: str) -> int:
    """Compared user lines carrying a label: `non_english` (a script's `lang` other than English) or `wrong_claim`."""
    n = 0
    for t in ts:
        if "turns" not in t:
            continue
        for i in t["compared"]:
            turn = t["turns"][i]
            if label == "wrong_claim" and turn.get("kind") == "wrong_claim":
                n += 1
            elif label == "non_english" and (turn.get("lang") or t.get("language", "en")) != "en":
                n += 1
    return n

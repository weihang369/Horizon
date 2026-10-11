"""System 1 rows on a turn's trace (contract rev 1.4 `TurnTrace.system1`; docs/ai/13 W1; system1-trace spec;
ai-foundation design D24, D25).

Pure helpers: `merge_rows` keys rows by `(purpose, id, about)` (a later row replaces an earlier one, in place), `cut`
keeps at most 64 rows (dropping `not_used` rows, latest first, before anything else), `route_row` builds the naive
router's row, and `fixture_row` the scripted profile's row from `seed/system1.fixture.json` (the MockClient reads the
same file). `forget_guard` is the writer-transaction step that keeps an append from restoring a forgotten memory.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from functools import cache
from pathlib import Path
from typing import Any

from sqlalchemy import select

from horizon.db import tables as t

MAX_ROWS = 64
Row = dict[str, Any]


def _key(r: Mapping[str, Any]) -> tuple[str, str, str]:
    return str(r.get("purpose")), str(r.get("id")), str(r.get("about") or "")


def merge_rows(existing: Iterable[Mapping[str, Any]], new: Iterable[Mapping[str, Any]]) -> list[Row]:
    out: dict[tuple[str, str, str], Row] = {}
    for r in [*existing, *new]:
        out[_key(r)] = dict(r)   # dict keeps first-insert order; a later row replaces the value in place
    return list(out.values())


def cut(rows: list[Row]) -> list[Row]:
    """≤ 64 rows: `not_used` rows go first (latest first), then the tail."""
    rows = list(rows)
    extra = len(rows) - MAX_ROWS
    if extra <= 0:
        return rows
    drop: set[int] = set()
    for i in range(len(rows) - 1, -1, -1):
        if len(drop) >= extra:
            break
        if rows[i].get("result") == "not_used":
            drop.add(i)
    return [r for i, r in enumerate(rows) if i not in drop][:MAX_ROWS]


def section(existing: Mapping[str, Any] | None, rows: Iterable[Mapping[str, Any]], seed: str | None = None) -> dict[str, Any]:
    """The trace's `system1` value after merging `rows` into `existing`."""
    old = dict(existing or {})
    out: dict[str, Any] = {"questions": cut(merge_rows(old.get("questions") or [], rows))}
    s = seed or old.get("seed")
    if s:
        out = {"seed": s, **out}
    return out


def route_row(*, version: int, label: str, answer: str, p: float | None, confidence: float | None, fallback: bool,
              action: str) -> Row:
    """The naive `route` row (D25): Jev's pick and its p, or a fallback row with no p."""
    row: Row = {"purpose": "route", "id": "route", "version": version, "label": label, "answer": answer}
    if not fallback:
        if p is not None:
            row["p"] = round(min(1.0, max(0.0, float(p))), 2)
        if confidence is not None:
            row["confidence"] = round(min(1.0, max(0.0, float(confidence))), 2)
    row["compared"] = []
    row["result"] = "fallback" if fallback else "used"
    row["action"] = action
    return row


@cache
def _fixture(seed_dir: str) -> dict[str, Row]:
    doc = json.loads((Path(seed_dir) / "system1.fixture.json").read_text(encoding="utf-8"))
    rows: dict[str, Row] = doc["data"]["rows"]
    return rows


def fixture_row(seed_dir: Path, qid: str, answer: str) -> Row:
    """A scripted row: the fixture's fixed fields, the answer from what actually happened (D25)."""
    r = _fixture(str(seed_dir))[qid]
    out: Row = {k: v for k, v in r.items() if k != "compared"}
    out["answer"] = answer
    out["compared"] = [dict(c) for c in r.get("compared") or []]
    return {k: out[k] for k in ("purpose", "id", "version", "label", "answer", "p", "confidence", "compared", "result",
                                "action") if k in out}


async def forget_guard(conn: Any, trace: dict[str, Any]) -> dict[str, Any]:
    """Inside the append's writer transaction (D24): drop recalled entries and `system1` rows about memories that no
    longer exist, so an append queued before a Forget commit can't write the memory back."""
    recalled = list(((trace.get("memory") or {}).get("recalled")) or [])
    rows = list(((trace.get("system1") or {}).get("questions")) or [])
    ids = {str(r["memoryItemId"]) for r in recalled if isinstance(r, Mapping) and r.get("memoryItemId")}
    ids |= {str(r["about"]) for r in rows if str(r.get("about") or "").startswith("mem_")}
    if not ids:
        return trace
    alive = set((await conn.execute(select(t.memory_items.c.id).where(t.memory_items.c.id.in_(sorted(ids))))).scalars())
    gone = ids - alive
    if not gone:
        return trace
    out = dict(trace)
    if recalled:
        out["memory"] = {**trace["memory"], "recalled": [r for r in recalled if str(r.get("memoryItemId")) not in gone]}
    if rows:
        out["system1"] = {**trace["system1"], "questions": [r for r in rows if str(r.get("about") or "") not in gone]}
    return out

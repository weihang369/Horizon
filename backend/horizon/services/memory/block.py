"""The memory list (docs/ai/09 M8; memory design D22; persona-prompt "The memory list").

A character's current memories, ranked by importance × recency × mode weight and added in rank order until
`memory.blockTokens` (1,000). The same list is the `agent` reply's "# What you remember" block and, numbered m1…mN, what
a pause run shows the writer (doc 09 M3), so the model merges into the lines the character already carries.

- **Recency** = max(`recencyFloor`, 0.5 ^ (days / `halfLifeDays`)), from the later of `created_at` and
  `last_recalled_at`: old facts sink but never vanish.
- **Mode weight** = `memory.modeWeight[source_mode]` (D-71's down-weighting); a seed or unknown mode weighs 1.0.
- Each line is newline-collapsed (doc 11 S6: a line can't start a fake heading) and cut at 40 words.
- Ties: the newer `created_at`, then the id.

`rank` and `fill` are pure; `memory_list` reads one character's current memories (one query).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncConnection

from horizon.db import tables as t
from horizon.domain.pricing import count_tokens
from horizon.domain.runtime_config import MemoryKnobs
from horizon.domain.timeutil import parse_iso

LINE_WORDS = 40
_SPACE = re.compile(r"\s+")
M = t.memory_items.c


@dataclass(frozen=True)
class ListedMemory:
    """One memory as the list shows it. `label` is its place in the list ("m1"…), used by the writer's answer."""

    label: str
    id: str
    kind: str
    text: str
    importance: float


@dataclass(frozen=True)
class MemoryRow:
    id: str
    kind: str
    text: str
    importance: float
    source_mode: str | None
    created_at: str
    last_recalled_at: str | None


def one_line(text: str, words: int = LINE_WORDS) -> str:
    """Newlines and runs of spaces collapse to one space; past `words` words the line is cut with "…"."""
    w = _SPACE.sub(" ", text).strip().split(" ")
    return " ".join(w) if len(w) <= words else " ".join(w[:words]) + " …"


def recency(row: MemoryRow, now: datetime, knobs: MemoryKnobs) -> float:
    stamps = [parse_iso(row.created_at)] + ([parse_iso(row.last_recalled_at)] if row.last_recalled_at else [])
    days = max(0.0, (now - max(stamps)).total_seconds() / 86400.0)
    return float(max(knobs.recency_floor, 0.5 ** (days / knobs.half_life_days)))


def score(row: MemoryRow, now: datetime, knobs: MemoryKnobs) -> float:
    return float(row.importance) * recency(row, now, knobs) * knobs.weight(row.source_mode)


def rank(rows: list[MemoryRow], now: datetime, knobs: MemoryKnobs) -> list[MemoryRow]:
    """Best first; ties to the newer memory, then the id."""
    newest = sorted(rows, key=lambda r: (r.created_at, r.id), reverse=True)
    return sorted(newest, key=lambda r: score(r, now, knobs), reverse=True)   # stable: ties keep the newest first


def fill(ranked: list[MemoryRow], budget_tokens: int) -> list[ListedMemory]:
    """Add lines in rank order while the block (one "- " line each) stays within `budget_tokens`."""
    out: list[ListedMemory] = []
    used = 0
    for r in ranked:
        line = one_line(r.text)
        cost = count_tokens(f"- {line}\n")
        if used + cost > budget_tokens:
            break
        used += cost
        out.append(ListedMemory(label=f"m{len(out) + 1}", id=r.id, kind=r.kind, text=line, importance=r.importance))
    return out


def rows_of(raw: list[Any]) -> list[MemoryRow]:
    return [MemoryRow(id=str(r["id"]), kind=str(r["kind"]), text=str(r["text"]), importance=float(r["importance"]),
                      source_mode=r["source_mode"], created_at=str(r["created_at"]),
                      last_recalled_at=r["last_recalled_at"]) for r in raw]


async def current_rows(conn: AsyncConnection, character_id: str, world_id: str) -> list[MemoryRow]:
    raw = (await conn.execute(select(M.id, M.kind, M.text, M.importance, M.source_mode, M.created_at,
                                     M.last_recalled_at).where(and_(
        M.character_id == character_id, M.world_id == world_id, M.superseded_by.is_(None))))).mappings().all()
    return rows_of(list(raw))


async def memory_list(conn: AsyncConnection, character_id: str, world_id: str, now: datetime,
                      knobs: MemoryKnobs) -> tuple[list[ListedMemory], bool]:
    """The character's list, and whether it has an overflow (current memories that didn't fit)."""
    rows = await current_rows(conn, character_id, world_id)
    listed = fill(rank(rows, now, knobs), knobs.block_tokens)
    return listed, len(listed) < len(rows)

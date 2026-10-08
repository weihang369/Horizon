"""0002_knowledge_memory (knowledge-memory-storage, M5).

- `knowledge_sources.embed_sent_at`: set when an embedding batch is sent and cleared in the ledger row's transaction
  with the batch's vectors (design D2). A source left `embedding` with the marker set had a batch in flight at a
  crash, so recovery ends it `keyword_only` instead of re-sending (the paying-twice rule).
- FTS5 `secure-delete` on `memory_fts` and `knowledge_fts` (design D16): a delete removes the row's terms from the
  index segments instead of appending a tombstone, so forgotten text leaves the file. Needs SQLite >= 3.44; on an
  older library the option is skipped and Forget runs an FTS `optimize` instead (`db/fts.py`).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-08
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SECURE_DELETE_MIN = (3, 44, 0)


def upgrade() -> None:
    # A plain ADD COLUMN, never a batch rebuild: rebuilding would renumber nothing (rid is explicit) but would drop
    # the FTS sync triggers attached to the table.
    op.add_column("knowledge_sources", sa.Column("embed_sent_at", sa.Text(), nullable=True))
    if sqlite3.sqlite_version_info >= SECURE_DELETE_MIN:
        for table in ("memory_fts", "knowledge_fts"):
            op.execute(f"INSERT INTO {table}({table}, rank) VALUES ('secure-delete', 1)")


def downgrade() -> None:  # pragma: no cover - no downgrades (doc 02 §5)
    raise NotImplementedError("Horizon migrations are forward-only; restore a copy of data/ instead.")

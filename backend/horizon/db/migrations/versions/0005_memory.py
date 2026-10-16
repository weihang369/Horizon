"""0005_memory (memory, M13; design D5; doc 09 M2, M9; doc 13 W13).

- `sessions.memory_seq`, `memory_reread`, `memory_tries`: the pause run's bookkeeping (doc 09 M2), set by runs and
  never by events (the session-event-sourcing exemption). The upgrade sets `memory_seq` to each session's highest
  message `seq`, so old history is never mined in one burst.
- `message_index`: one row per line that has **left the window** (design D29), with the "Name: text" recall searches.
  It carries its own `rid INTEGER PRIMARY KEY` because `messages` is keyed by its TEXT id, and SQLite's implicit rowid
  on such a table isn't stable across `VACUUM` (design D3, D5). Deleting the message cascades.
- `message_fts`: FTS5 external content over `message_index.text`, `porter unicode61` (doc 10 K11), kept by triggers,
  with `secure-delete` on like 0002's tables.

The vectors (`message_vec__{space}`) belong to the SpaceManager, never to Alembic. Like 0004 this can be downgraded:
the index is derived, and the run columns only cost a re-run.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-16
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SECURE_DELETE_MIN = (3, 44, 0)

# Frozen copies (a migration never changes after it ships).
FTS_DDL: tuple[str, ...] = (
    "CREATE VIRTUAL TABLE message_fts USING fts5(text, content='message_index', content_rowid='rid', tokenize='porter unicode61')",
    "CREATE TRIGGER message_index_ai AFTER INSERT ON message_index BEGIN INSERT INTO message_fts(rowid, text) VALUES (new.rid, new.text); END",
    "CREATE TRIGGER message_index_ad AFTER DELETE ON message_index BEGIN INSERT INTO message_fts(message_fts, rowid, text) VALUES ('delete', old.rid, old.text); END",
    "CREATE TRIGGER message_index_au AFTER UPDATE OF text ON message_index BEGIN INSERT INTO message_fts(message_fts, rowid, text) VALUES ('delete', old.rid, old.text); INSERT INTO message_fts(rowid, text) VALUES (new.rid, new.text); END",
)
FTS_DROP: tuple[str, ...] = (
    "DROP TRIGGER IF EXISTS message_index_au",
    "DROP TRIGGER IF EXISTS message_index_ad",
    "DROP TRIGGER IF EXISTS message_index_ai",
    "DROP TABLE IF EXISTS message_fts",
)


def upgrade() -> None:
    op.add_column("sessions", sa.Column("memory_seq", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column("sessions", sa.Column("memory_reread", sa.JSON(none_as_null=True), nullable=False,
                                        server_default=sa.text("'[]'")))
    op.add_column("sessions", sa.Column("memory_tries", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.execute("UPDATE sessions SET memory_seq = COALESCE((SELECT MAX(m.seq) FROM messages m "
               "WHERE m.session_id = sessions.id), 0)")
    op.create_table(
        "message_index",
        sa.Column("rid", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("message_id", sa.Text(), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False,
                  unique=True),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("author", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index("ix_message_index_session_seq", "message_index", ["session_id", "seq"])
    for stmt in FTS_DDL:
        op.execute(stmt)
    if sqlite3.sqlite_version_info >= SECURE_DELETE_MIN:
        op.execute("INSERT INTO message_fts(message_fts, rank) VALUES ('secure-delete', 1)")


def downgrade() -> None:
    for stmt in FTS_DROP:
        op.execute(stmt)
    op.drop_index("ix_message_index_session_seq", table_name="message_index")
    op.drop_table("message_index")
    op.drop_column("sessions", "memory_tries")
    op.drop_column("sessions", "memory_reread")
    op.drop_column("sessions", "memory_seq")

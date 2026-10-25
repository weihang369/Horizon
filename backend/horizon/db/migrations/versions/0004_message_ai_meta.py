"""0004_message_ai_meta (rag, M12; design D19; doc 13 W13).

`message_ai_meta`: AI-owned data derived per message, like `turn_traces` (the session-event-sourcing exemption): it is
never projected from events, fork copies the rows of the messages it copies, and deleting a message cascades.
- `rewrites`: `{speakerId: {"text", "at"}}`, the accepted query rewrites for the user message the row is keyed by
  (doc 10 K4), reused on regenerate. M14 adds `safety` (W13).

It holds no vectors (the SpaceManager owns vec tables). Unlike 0001–0003 it can be downgraded: the data is derived, so
dropping it loses nothing a turn can't recompute (rag design's migration plan).

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "message_ai_meta",
        sa.Column("message_id", sa.Text(), sa.ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("rewrites", sa.JSON(none_as_null=True), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("updated_at", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("message_ai_meta")

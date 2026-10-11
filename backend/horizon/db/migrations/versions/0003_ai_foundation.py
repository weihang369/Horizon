"""0003_ai_foundation (ai-foundation, M7; design D6, D18, D27).

- `usage_records.finish_reason`: how the call ended. Chat: the provider's finish reason (`stop`, `length`, …). A Jev
  decision: `on_time`, `late` (a deadline read already fell back), `cancelled` or `final` (read only in full).
- `usage_records.tokens_reasoning`: `completion_tokens_details.reasoning_tokens` (catches thinking left on).
- `ai_calls`: opt-in full prompt capture (`HORIZON_CAPTURE_AI_CALLS=1`, docs/ai/02 B10). World and session rows
  cascade; character and message references have no foreign key (characters are tombstoned and purged by the AI
  state hooks; a prefetched turn exists before its message).

Plain ADD COLUMNs, never a batch rebuild (the FTS and vec triggers must stay attached).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("usage_records", sa.Column("finish_reason", sa.Text(), nullable=True))
    op.add_column("usage_records", sa.Column("tokens_reasoning", sa.Integer(), nullable=True))
    op.create_table(
        "ai_calls",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("provider", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("finish_reason", sa.Text(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("usage_record_id", sa.Text(), nullable=True),
        sa.Column("world_id", sa.Text(), sa.ForeignKey("worlds.id", ondelete="CASCADE"), nullable=True),
        sa.Column("session_id", sa.Text(), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=True),
        sa.Column("character_id", sa.Text(), nullable=True),
        sa.Column("message_id", sa.Text(), nullable=True),
        sa.Column("request", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("response", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("dropped_before", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.CheckConstraint("kind IN ('call','turn')", name="ck_ai_calls_kind"),
    )
    op.create_index("ix_ai_calls_created_at", "ai_calls", ["created_at"])
    op.create_index("ix_ai_calls_character", "ai_calls", ["character_id"])
    op.create_index("ix_ai_calls_session", "ai_calls", ["session_id"])
    op.create_index("ix_ai_calls_message", "ai_calls", ["message_id"])


def downgrade() -> None:  # pragma: no cover - no downgrades (doc 02 §5)
    raise NotImplementedError("Horizon migrations are forward-only; restore a copy of data/ instead.")

"""0006_safety (safety, M14; design D5; doc 11 S3, S4; doc 13 W13).

- `message_ai_meta.safety`: the stored safety answers for the user line the row is keyed by,
  `{steer, care, pInput, pCare, at, v}` (design D5). Only Jev's answers are written, by the runtime right after the
  plan request returns; a fallback writes nothing. AI-owned and not event-sourced (the session-event-sourcing
  exemption), copied by fork with the row, cascaded by delete.

Every row from before M14 reads NULL, which means "not flagged": history is never checked after the fact. Like 0004
and 0005 this can be downgraded: the data is derived, and dropping it loses only cues on later regenerates.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("message_ai_meta", sa.Column("safety", sa.JSON(none_as_null=True), nullable=True))


def downgrade() -> None:
    op.drop_column("message_ai_meta", "safety")

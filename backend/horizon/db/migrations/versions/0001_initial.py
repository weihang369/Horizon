"""0001_initial: every ordinary table + the FTS5 tables and their sync triggers (doc 02 §3, §5).

Generated from `horizon/db/tables.py`, then reviewed by hand. vec0 tables are not created here: the SpaceManager
creates them at startup (doc 02 §3.9), and `env.py` `include_object` skips every virtual and shadow table.

Revision ID: 0001
Revises:
Create Date: 2026-10-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Frozen copies (a migration never changes after it ships).
FTS_DDL: tuple[str, ...] = (
    "CREATE VIRTUAL TABLE memory_fts USING fts5(text, content='memory_items', content_rowid='rid', tokenize='porter unicode61')",
    "CREATE TRIGGER memory_items_ai AFTER INSERT ON memory_items BEGIN INSERT INTO memory_fts(rowid, text) VALUES (new.rid, new.text); END",
    "CREATE TRIGGER memory_items_ad AFTER DELETE ON memory_items BEGIN INSERT INTO memory_fts(memory_fts, rowid, text) VALUES ('delete', old.rid, old.text); END",
    "CREATE TRIGGER memory_items_au AFTER UPDATE OF text ON memory_items BEGIN INSERT INTO memory_fts(memory_fts, rowid, text) VALUES ('delete', old.rid, old.text); INSERT INTO memory_fts(rowid, text) VALUES (new.rid, new.text); END",
    "CREATE VIRTUAL TABLE knowledge_fts USING fts5(text, heading, content='knowledge_chunks', content_rowid='rid', tokenize='porter unicode61')",
    "CREATE TRIGGER knowledge_chunks_ai AFTER INSERT ON knowledge_chunks BEGIN INSERT INTO knowledge_fts(rowid, text, heading) VALUES (new.rid, new.text, new.heading); END",
    "CREATE TRIGGER knowledge_chunks_ad AFTER DELETE ON knowledge_chunks BEGIN INSERT INTO knowledge_fts(knowledge_fts, rowid, text, heading) VALUES ('delete', old.rid, old.text, old.heading); END",
    "CREATE TRIGGER knowledge_chunks_au AFTER UPDATE OF text, heading ON knowledge_chunks BEGIN INSERT INTO knowledge_fts(knowledge_fts, rowid, text, heading) VALUES ('delete', old.rid, old.text, old.heading); INSERT INTO knowledge_fts(rowid, text, heading) VALUES (new.rid, new.text, new.heading); END",
)
FTS_DROP: tuple[str, ...] = (
    "DROP TRIGGER IF EXISTS knowledge_chunks_au",
    "DROP TRIGGER IF EXISTS knowledge_chunks_ad",
    "DROP TRIGGER IF EXISTS knowledge_chunks_ai",
    "DROP TABLE IF EXISTS knowledge_fts",
    "DROP TRIGGER IF EXISTS memory_items_au",
    "DROP TRIGGER IF EXISTS memory_items_ad",
    "DROP TRIGGER IF EXISTS memory_items_ai",
    "DROP TABLE IF EXISTS memory_fts",
)

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_purge_queue",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("ids", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("done_at", sa.Text(), nullable=True),
        sa.CheckConstraint("scope IN ('memory','message','session','character','world')", name="ck_purge_scope"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("data", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_app_settings_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "characters",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("world_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("creation_step", sa.Text(), nullable=True),
        sa.Column("seed_prompt", sa.Text(), nullable=False),
        sa.Column("intent", sa.Text(), nullable=False),
        sa.Column("advisory", sa.Boolean(), nullable=False),
        sa.Column("profile", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("profile_meta", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("appearance", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("palette_id", sa.Text(), nullable=False),
        sa.Column("emotion_set", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("theme_song_id", sa.Text(), nullable=True),
        sa.Column("active_job_id", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("energy_max", sa.Integer(), nullable=False),
        sa.Column("energy_current", sa.Float(), nullable=False),
        sa.Column("energy_as_of", sa.Text(), nullable=False),
        sa.Column("energy_spent_today", sa.Float(), nullable=False),
        sa.Column("energy_day", sa.Text(), nullable=False),
        sa.Column("is_seed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("approved_at", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["active_job_id"], ["generation_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["theme_song_id"], ["theme_songs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("characters", schema=None) as batch_op:
        batch_op.create_index("ix_characters_world_status", ["world_id", "status"], unique=False)

    op.create_table(
        "embedding_spaces",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("dims", sa.Integer(), nullable=False),
        sa.Column("dtype", sa.Text(), server_default=sa.text("'float32'"), nullable=False),
        sa.Column("normalized", sa.Boolean(), nullable=False),
        sa.Column("query_instruction", sa.Text(), nullable=True),
        sa.Column("doc_template", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint("status IN ('building','active','retired')", name="ck_embedding_spaces_status"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("embedding_spaces", schema=None) as batch_op:
        batch_op.create_index(
            "ux_embedding_spaces_one_active", ["status"], unique=True, sqlite_where=sa.text("status = 'active'")
        )

    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("character_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("target_field", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False),
        sa.Column("actual_cost_usd", sa.Float(), nullable=False),
        sa.Column("input", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("error", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("is_seed", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("started_at", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("generation_jobs", schema=None) as batch_op:
        batch_op.create_index("ix_generation_jobs_character_created", ["character_id", "created_at"], unique=False)
        batch_op.create_index("ix_generation_jobs_status", ["status"], unique=False)
        batch_op.create_index(
            "ux_generation_jobs_one_active", ["character_id"], unique=True, sqlite_where=sa.text("status IN ('queued','running')")
        )

    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("body_sha256", sa.Text(), nullable=False),
        sa.Column("status", sa.Integer(), nullable=True),
        sa.Column("response", sa.Text(), nullable=True),
        sa.Column("content_type", sa.Text(), nullable=True),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.Text(), nullable=False),
        sa.CheckConstraint("state IN ('in_flight','done')", name="ck_idempotency_state"),
        sa.PrimaryKeyConstraint("key"),
    )
    with op.batch_alter_table("idempotency_keys", schema=None) as batch_op:
        batch_op.create_index("ix_idempotency_keys_expires_at", ["expires_at"], unique=False)

    op.create_table(
        "theme_songs",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("character_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("rel_path", sa.Text(), nullable=True),
        sa.Column("duration_sec", sa.Float(), nullable=True),
        sa.Column("format", sa.Text(), nullable=True),
        sa.Column("bytes", sa.Integer(), nullable=True),
        sa.Column("loop", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("gain_db", sa.Float(), nullable=True),
        sa.Column("brief", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("instrumental", sa.Boolean(), nullable=False),
        sa.Column("generation", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("license_note", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("is_seed", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "worlds",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(collation="NOCASE"), nullable=False),
        sa.Column("cover", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("you", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("is_seed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("last_active_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "generation_tasks",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("job_id", sa.Text(), nullable=False),
        sa.Column("ord", sa.Integer(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("emotion", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default=sa.text("3"), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("provider_called_at", sa.Text(), nullable=True),
        sa.Column("target_path", sa.Text(), nullable=True),
        sa.Column("result_ref", sa.Text(), nullable=True),
        sa.Column("preview_url", sa.Text(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("error", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("started_at", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["generation_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    with op.batch_alter_table("generation_tasks", schema=None) as batch_op:
        batch_op.create_index("ix_generation_tasks_status_created", ["status", "created_at"], unique=False)

    op.create_table(
        "image_assets",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("world_id", sa.Text(), nullable=False),
        sa.Column("character_id", sa.Text(), nullable=True),
        sa.Column("job_id", sa.Text(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("emotion", sa.Text(), nullable=True),
        sa.Column("variant", sa.Text(), server_default=sa.text("'default'"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("rel_path", sa.Text(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("format", sa.Text(), nullable=True),
        sa.Column("bytes", sa.Integer(), nullable=True),
        sa.Column("vfx_preset", sa.Text(), server_default=sa.text("'none'"), nullable=False),
        sa.Column("generation", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("selected", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("ord", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint("(kind = 'cover') = (character_id IS NULL)", name="ck_image_assets_cover_has_no_character"),
        sa.CheckConstraint("kind IN ('candidate','emotion','cover')", name="ck_image_assets_kind"),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["generation_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("image_assets", schema=None) as batch_op:
        batch_op.create_index("ix_image_assets_character_kind_job", ["character_id", "kind", "job_id"], unique=False)
        batch_op.create_index(
            "ux_image_assets_cover_version", ["world_id", "version"], unique=True, sqlite_where=sa.text("kind = 'cover'")
        )
        batch_op.create_index(
            "ux_image_assets_emotion_active",
            ["character_id", "emotion", "variant"],
            unique=True,
            sqlite_where=sa.text("kind = 'emotion' AND is_active"),
        )
        batch_op.create_index(
            "ux_image_assets_emotion_version",
            ["character_id", "emotion", "variant", "version"],
            unique=True,
            sqlite_where=sa.text("kind = 'emotion'"),
        )

    op.create_table(
        "knowledge_sources",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("character_id", sa.Text(), nullable=False),
        sa.Column("world_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("mime", sa.Text(), nullable=True),
        sa.Column("original_name", sa.Text(), nullable=True),
        sa.Column("bytes", sa.Integer(), nullable=True),
        sa.Column("pages", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("extractor_version", sa.Text(), nullable=True),
        sa.Column("chunker_version", sa.Text(), nullable=False),
        sa.Column("tokenizer", sa.Text(), nullable=False),
        sa.Column("embedding_space_id", sa.Text(), nullable=True),
        sa.Column("has_original", sa.Boolean(), nullable=False),
        sa.Column("error", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("added_at", sa.Text(), nullable=False),
        sa.Column("indexed_at", sa.Text(), nullable=True),
        sa.Column("is_seed", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued','extracting','chunking','embedding','indexed','keyword_only','failed')",
            name="ck_knowledge_sources_status",
        ),
        sa.CheckConstraint("type IN ('text','file','url')", name="ck_knowledge_sources_type"),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("knowledge_sources", schema=None) as batch_op:
        batch_op.create_index(
            "ux_knowledge_sources_sha", ["character_id", "sha256"], unique=True, sqlite_where=sa.text("sha256 IS NOT NULL")
        )

    op.create_table(
        "memory_items",
        sa.Column("rid", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("character_id", sa.Text(), nullable=False),
        sa.Column("world_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("importance", sa.Float(), nullable=False),
        sa.Column("source_session_id", sa.Text(), nullable=True),
        sa.Column("source_message_id", sa.Text(), nullable=True),
        sa.Column("source_variant_id", sa.Text(), nullable=True),
        sa.Column("source_mode", sa.Text(), nullable=True),
        sa.Column("about_character_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("last_recalled_at", sa.Text(), nullable=True),
        sa.Column("recall_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("superseded_by", sa.Text(), nullable=True),
        sa.Column("is_seed", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("rid"),
        sa.UniqueConstraint("id"),
    )
    with op.batch_alter_table("memory_items", schema=None) as batch_op:
        batch_op.create_index("ix_memory_items_character_created", ["character_id", "created_at"], unique=False)

    op.create_table(
        "sessions",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("world_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("title_is_custom", sa.Boolean(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("paused_reason", sa.Text(), nullable=True),
        sa.Column("emotion_mode", sa.Text(), nullable=False),
        sa.Column("music_policy", sa.Text(), nullable=False),
        sa.Column("readable_mode", sa.Boolean(), nullable=False),
        sa.Column("config", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("state", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("continued_from", sa.Text(), nullable=True),
        sa.Column("is_seed", sa.Boolean(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("message_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("last_message_at", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["continued_from"], ["sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.create_index("ix_sessions_world_updated", ["world_id", "updated_at"], unique=False)

    op.create_table(
        "knowledge_sections",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("character_id", sa.Text(), nullable=False),
        sa.Column("world_id", sa.Text(), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("heading_path", sa.Text(), nullable=True),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["knowledge_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "idx", name="uq_knowledge_sections_source_idx"),
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("author_type", sa.Text(), nullable=False),
        sa.Column("author_character_id", sa.Text(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("target_character_id", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("interrupted_by", sa.Text(), nullable=True),
        sa.Column("emotion", sa.Text(), nullable=True),
        sa.Column("emotion_source", sa.Text(), nullable=True),
        sa.Column("debate", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("forced_speaker", sa.Boolean(), nullable=True),
        sa.Column("reactions", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("variants", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("active_variant_id", sa.Text(), nullable=True),
        sa.Column("usage", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("citations", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("error", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "seq", name="uq_messages_session_seq"),
    )
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.create_index("ix_messages_author_created", ["author_character_id", "created_at"], unique=False)

    op.create_table(
        "participants",
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("character_id", sa.Text(), nullable=False),
        sa.Column("ord", sa.Integer(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("side", sa.Text(), nullable=True),
        sa.Column("current_emotion", sa.Text(), nullable=False),
        sa.Column("muted", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id", "character_id"),
    )
    op.create_table(
        "session_events",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("at", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("message_id", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(none_as_null=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "seq", name="uq_session_events_session_seq"),
    )
    with op.batch_alter_table("session_events", schema=None) as batch_op:
        batch_op.create_index("ix_session_events_message_id", ["message_id"], unique=False)

    op.create_table(
        "session_summaries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("upto_seq", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("character_id", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint("kind IN ('rolling','perspective','watch')", name="ck_session_summaries_kind"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("session_summaries", schema=None) as batch_op:
        batch_op.create_index("ix_session_summaries_lookup", ["session_id", "kind", "upto_seq"], unique=False)

    op.create_table(
        "usage_records",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("at", sa.Text(), nullable=False),
        sa.Column("local_day", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("provider", sa.Text(), nullable=True),
        sa.Column("price_period", sa.Text(), nullable=True),
        sa.Column("generation_id", sa.Text(), nullable=True),
        sa.Column("session_id", sa.Text(), nullable=True),
        sa.Column("character_id", sa.Text(), nullable=True),
        sa.Column("job_id", sa.Text(), nullable=True),
        sa.Column("message_id", sa.Text(), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_cached", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("cost_source", sa.Text(), server_default=sa.text("'provider'"), nullable=False),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=True),
        sa.Column("energy_points", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("counts_to_creation_cap", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_seed", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "category IN ('chat','decision','image','music','profile','summary','memory','embedding','energy_topup')",
            name="ck_usage_records_category",
        ),
        sa.CheckConstraint("cost_source IN ('provider','estimate')", name="ck_usage_records_cost_source"),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_id"], ["generation_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("usage_records", schema=None) as batch_op:
        batch_op.create_index("ix_usage_records_category_at", ["category", "at"], unique=False)
        batch_op.create_index("ix_usage_records_character_at", ["character_id", "at"], unique=False)
        batch_op.create_index("ix_usage_records_local_day", ["local_day"], unique=False)
        batch_op.create_index("ix_usage_records_message", ["message_id"], unique=False)
        batch_op.create_index("ix_usage_records_session", ["session_id"], unique=False)

    op.create_table(
        "knowledge_chunks",
        sa.Column("rid", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("section_id", sa.Text(), nullable=False),
        sa.Column("character_id", sa.Text(), nullable=False),
        sa.Column("world_id", sa.Text(), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("locator", sa.Text(), nullable=True),
        sa.Column("heading", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["section_id"], ["knowledge_sections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["knowledge_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("rid"),
        sa.UniqueConstraint("id"),
        sa.UniqueConstraint("source_id", "idx", name="uq_knowledge_chunks_source_idx"),
    )
    op.create_table(
        "message_citations",
        sa.Column("message_id", sa.Text(), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("chunk_id", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("message_id", "n"),
    )
    with op.batch_alter_table("message_citations", schema=None) as batch_op:
        batch_op.create_index("ix_message_citations_source_id", ["source_id"], unique=False)

    op.create_table(
        "trace_memory_refs",
        sa.Column("memory_item_id", sa.Text(), nullable=False),
        sa.Column("message_id", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("memory_item_id", "message_id"),
    )
    op.create_table(
        "turn_traces",
        sa.Column("message_id", sa.Text(), nullable=False),
        sa.Column("trace", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("engine", sa.Text(), nullable=True),
        sa.Column("engine_version", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("message_id"),
    )

    for stmt in FTS_DDL:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in FTS_DROP:
        op.execute(stmt)
    op.drop_table("turn_traces")
    op.drop_table("trace_memory_refs")
    with op.batch_alter_table("message_citations", schema=None) as batch_op:
        batch_op.drop_index("ix_message_citations_source_id")

    op.drop_table("message_citations")
    op.drop_table("knowledge_chunks")
    with op.batch_alter_table("usage_records", schema=None) as batch_op:
        batch_op.drop_index("ix_usage_records_session")
        batch_op.drop_index("ix_usage_records_message")
        batch_op.drop_index("ix_usage_records_local_day")
        batch_op.drop_index("ix_usage_records_character_at")
        batch_op.drop_index("ix_usage_records_category_at")

    op.drop_table("usage_records")
    with op.batch_alter_table("session_summaries", schema=None) as batch_op:
        batch_op.drop_index("ix_session_summaries_lookup")

    op.drop_table("session_summaries")
    with op.batch_alter_table("session_events", schema=None) as batch_op:
        batch_op.drop_index("ix_session_events_message_id")

    op.drop_table("session_events")
    op.drop_table("participants")
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.drop_index("ix_messages_author_created")

    op.drop_table("messages")
    op.drop_table("knowledge_sections")
    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.drop_index("ix_sessions_world_updated")

    op.drop_table("sessions")
    with op.batch_alter_table("memory_items", schema=None) as batch_op:
        batch_op.drop_index("ix_memory_items_character_created")

    op.drop_table("memory_items")
    with op.batch_alter_table("knowledge_sources", schema=None) as batch_op:
        batch_op.drop_index("ux_knowledge_sources_sha", sqlite_where=sa.text("sha256 IS NOT NULL"))

    op.drop_table("knowledge_sources")
    with op.batch_alter_table("image_assets", schema=None) as batch_op:
        batch_op.drop_index("ux_image_assets_emotion_version", sqlite_where=sa.text("kind = 'emotion'"))
        batch_op.drop_index("ux_image_assets_emotion_active", sqlite_where=sa.text("kind = 'emotion' AND is_active"))
        batch_op.drop_index("ux_image_assets_cover_version", sqlite_where=sa.text("kind = 'cover'"))
        batch_op.drop_index("ix_image_assets_character_kind_job")

    op.drop_table("image_assets")
    with op.batch_alter_table("generation_tasks", schema=None) as batch_op:
        batch_op.drop_index("ix_generation_tasks_status_created")

    op.drop_table("generation_tasks")
    op.drop_table("worlds")
    op.drop_table("theme_songs")
    with op.batch_alter_table("idempotency_keys", schema=None) as batch_op:
        batch_op.drop_index("ix_idempotency_keys_expires_at")

    op.drop_table("idempotency_keys")
    with op.batch_alter_table("generation_jobs", schema=None) as batch_op:
        batch_op.drop_index("ux_generation_jobs_one_active", sqlite_where=sa.text("status IN ('queued','running')"))
        batch_op.drop_index("ix_generation_jobs_status")
        batch_op.drop_index("ix_generation_jobs_character_created")

    op.drop_table("generation_jobs")
    with op.batch_alter_table("embedding_spaces", schema=None) as batch_op:
        batch_op.drop_index("ux_embedding_spaces_one_active", sqlite_where=sa.text("status = 'active'"))

    op.drop_table("embedding_spaces")
    with op.batch_alter_table("characters", schema=None) as batch_op:
        batch_op.drop_index("ix_characters_world_status")

    op.drop_table("characters")
    op.drop_table("app_settings")
    op.drop_table("ai_purge_queue")

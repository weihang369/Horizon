"""Every ordinary table in doc 02 §3, as SQLAlchemy Core tables (the migration mirrors them; a test checks for drift).

Conventions (doc 02 §1):
- IDs are TEXT `prefix_ULID`; tables indexed by FTS5/vec0 also carry `rid INTEGER PRIMARY KEY` (the index key).
- Timestamps are TEXT ISO-8601 UTC with millisecond precision.
- `J` columns hold whole value objects in wire form (camelCase JSON).
- Every FK declares its ON DELETE. FTS and vec rows are kept in sync by triggers (migration 0001 + SpaceManager).

Additions to the doc 02 tables (recorded there): `image_assets.selected` (a portrait candidate's `selected` flag).
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    Table,
    Text,
    UniqueConstraint,
    text,
)

metadata = MetaData()

J = JSON(none_as_null=True)


def _fk(target: str, ondelete: str) -> ForeignKey:
    return ForeignKey(target, ondelete=ondelete)


# ── 3.1 Settings, idempotency, outbox ────────────────────────────────────────
app_settings = Table(
    "app_settings", metadata,
    Column("id", Integer, primary_key=True, autoincrement=False),
    Column("data", J, nullable=False),
    Column("updated_at", Text, nullable=False),
    CheckConstraint("id = 1", name="ck_app_settings_singleton"),
)

idempotency_keys = Table(
    "idempotency_keys", metadata,
    Column("key", Text, primary_key=True),
    Column("method", Text, nullable=False),
    Column("path", Text, nullable=False),
    Column("body_sha256", Text, nullable=False),
    Column("status", Integer, nullable=True),
    Column("response", Text, nullable=True),
    Column("content_type", Text, nullable=True),
    Column("state", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    Column("expires_at", Text, nullable=False),
    CheckConstraint("state IN ('in_flight','done')", name="ck_idempotency_state"),
    Index("ix_idempotency_keys_expires_at", "expires_at"),
)

ai_purge_queue = Table(
    "ai_purge_queue", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("scope", Text, nullable=False),
    Column("ids", J, nullable=False),
    Column("created_at", Text, nullable=False),
    Column("attempts", Integer, nullable=False, server_default=text("0")),
    Column("done_at", Text, nullable=True),
    CheckConstraint("scope IN ('memory','message','session','character','world')", name="ck_purge_scope"),
)

# ── 3.2 Worlds, characters, assets ───────────────────────────────────────────
worlds = Table(
    "worlds", metadata,
    Column("id", Text, primary_key=True),
    Column("name", Text(collation="NOCASE"), nullable=False, unique=True),
    Column("cover", J, nullable=False),
    Column("you", J, nullable=True),
    Column("is_seed", Boolean, nullable=False),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Column("last_active_at", Text, nullable=False),
)

characters = Table(
    "characters", metadata,
    Column("id", Text, primary_key=True),
    Column("world_id", Text, _fk("worlds.id", "CASCADE"), nullable=False),
    Column("status", Text, nullable=False),
    Column("creation_step", Text, nullable=True),
    Column("seed_prompt", Text, nullable=False),
    Column("intent", Text, nullable=False),
    Column("advisory", Boolean, nullable=False),
    Column("profile", J, nullable=False),
    Column("profile_meta", J, nullable=True),
    Column("appearance", J, nullable=False),
    Column("palette_id", Text, nullable=False),
    Column("emotion_set", J, nullable=False),
    Column("theme_song_id", Text, _fk("theme_songs.id", "SET NULL"), nullable=True),
    Column("active_job_id", Text, _fk("generation_jobs.id", "SET NULL"), nullable=True),
    Column("version", Integer, nullable=False),
    Column("energy_max", Integer, nullable=False),
    Column("energy_current", Float, nullable=False),
    Column("energy_as_of", Text, nullable=False),
    Column("energy_spent_today", Float, nullable=False),
    Column("energy_day", Text, nullable=False),
    Column("is_seed", Boolean, nullable=False),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Column("approved_at", Text, nullable=True),
    Column("archived_at", Text, nullable=True),
    Column("deleted_at", Text, nullable=True),
    Index("ix_characters_world_status", "world_id", "status"),
)

image_assets = Table(
    "image_assets", metadata,
    Column("id", Text, primary_key=True),
    Column("world_id", Text, _fk("worlds.id", "CASCADE"), nullable=False),
    Column("character_id", Text, _fk("characters.id", "CASCADE"), nullable=True),
    Column("job_id", Text, _fk("generation_jobs.id", "SET NULL"), nullable=True),
    Column("kind", Text, nullable=False),
    Column("emotion", Text, nullable=True),
    Column("variant", Text, nullable=False, server_default=text("'default'")),
    Column("status", Text, nullable=False),
    Column("rel_path", Text, nullable=True),
    Column("width", Integer, nullable=True),
    Column("height", Integer, nullable=True),
    Column("format", Text, nullable=True),
    Column("bytes", Integer, nullable=True),
    Column("vfx_preset", Text, nullable=False, server_default=text("'none'")),
    Column("generation", J, nullable=True),
    Column("version", Integer, nullable=False, server_default=text("1")),
    Column("is_active", Boolean, nullable=False),
    Column("selected", Boolean, nullable=False, server_default=text("0")),
    Column("ord", Integer, nullable=False, server_default=text("0")),
    Column("created_at", Text, nullable=False),
    CheckConstraint("kind IN ('candidate','emotion','cover')", name="ck_image_assets_kind"),
    CheckConstraint("(kind = 'cover') = (character_id IS NULL)", name="ck_image_assets_cover_has_no_character"),
    Index("ux_image_assets_emotion_version", "character_id", "emotion", "variant", "version",
          unique=True, sqlite_where=text("kind = 'emotion'")),
    Index("ux_image_assets_emotion_active", "character_id", "emotion", "variant",
          unique=True, sqlite_where=text("kind = 'emotion' AND is_active")),
    Index("ux_image_assets_cover_version", "world_id", "version", unique=True, sqlite_where=text("kind = 'cover'")),
    Index("ix_image_assets_character_kind_job", "character_id", "kind", "job_id"),
)

theme_songs = Table(
    "theme_songs", metadata,
    Column("id", Text, primary_key=True),
    Column("character_id", Text, _fk("characters.id", "CASCADE"), nullable=False),
    Column("status", Text, nullable=False),
    Column("rel_path", Text, nullable=True),
    Column("duration_sec", Float, nullable=True),
    Column("format", Text, nullable=True),
    Column("bytes", Integer, nullable=True),
    Column("loop", J, nullable=True),
    Column("gain_db", Float, nullable=True),
    Column("brief", J, nullable=False),
    Column("instrumental", Boolean, nullable=False),
    Column("generation", J, nullable=True),
    Column("license_note", Text, nullable=False),
    Column("version", Integer, nullable=False, server_default=text("1")),
    Column("is_seed", Boolean, nullable=False, server_default=text("0")),
    Column("created_at", Text, nullable=False),
)

# ── 3.4 Sessions, messages, events (event-sourced) ───────────────────────────
sessions = Table(
    "sessions", metadata,
    Column("id", Text, primary_key=True),
    Column("world_id", Text, _fk("worlds.id", "CASCADE"), nullable=False),
    Column("title", Text, nullable=False),
    Column("title_is_custom", Boolean, nullable=False),
    Column("mode", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("paused_reason", Text, nullable=True),
    Column("emotion_mode", Text, nullable=False),
    Column("music_policy", Text, nullable=False),
    Column("readable_mode", Boolean, nullable=False),
    Column("config", J, nullable=True),
    Column("state", J, nullable=True),
    Column("continued_from", Text, _fk("sessions.id", "SET NULL"), nullable=True),
    Column("is_seed", Boolean, nullable=False),
    Column("cost_usd", Float, nullable=False),
    Column("message_count", Integer, nullable=False),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Column("last_message_at", Text, nullable=True),
    Index("ix_sessions_world_updated", "world_id", "updated_at"),
)

participants = Table(
    "participants", metadata,
    Column("session_id", Text, _fk("sessions.id", "CASCADE"), nullable=False),
    Column("character_id", Text, _fk("characters.id", "RESTRICT"), nullable=False),
    Column("ord", Integer, nullable=False),
    Column("role", Text, nullable=False),
    Column("side", Text, nullable=True),
    Column("current_emotion", Text, nullable=False),
    Column("muted", Boolean, nullable=False),
    PrimaryKeyConstraint("session_id", "character_id"),
)

session_events = Table(
    "session_events", metadata,
    Column("id", Text, primary_key=True),
    Column("session_id", Text, _fk("sessions.id", "CASCADE"), nullable=False),
    Column("seq", Integer, nullable=False),
    Column("at", Text, nullable=False),
    Column("type", Text, nullable=False),
    Column("message_id", Text, nullable=True),
    Column("payload", J, nullable=False),
    UniqueConstraint("session_id", "seq", name="uq_session_events_session_seq"),
    Index("ix_session_events_message_id", "message_id"),
)

messages = Table(
    "messages", metadata,
    Column("id", Text, primary_key=True),
    Column("session_id", Text, _fk("sessions.id", "CASCADE"), nullable=False),
    Column("seq", Integer, nullable=False),
    Column("author_type", Text, nullable=False),
    Column("author_character_id", Text, nullable=True),
    Column("kind", Text, nullable=False),
    Column("target_character_id", Text, nullable=True),
    Column("content", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("interrupted_by", Text, nullable=True),
    Column("emotion", Text, nullable=True),
    Column("emotion_source", Text, nullable=True),
    Column("debate", J, nullable=True),
    Column("forced_speaker", Boolean, nullable=True),
    Column("reactions", J, nullable=True),
    Column("variants", J, nullable=True),
    Column("active_variant_id", Text, nullable=True),
    Column("usage", J, nullable=True),
    Column("citations", J, nullable=True),
    Column("error", J, nullable=True),
    Column("created_at", Text, nullable=False),
    UniqueConstraint("session_id", "seq", name="uq_messages_session_seq"),
    Index("ix_messages_author_created", "author_character_id", "created_at"),
)

message_citations = Table(
    "message_citations", metadata,
    Column("message_id", Text, _fk("messages.id", "CASCADE"), nullable=False),
    Column("n", Integer, nullable=False),
    Column("chunk_id", Text, nullable=False),
    Column("source_id", Text, nullable=False),
    PrimaryKeyConstraint("message_id", "n"),
    Index("ix_message_citations_source_id", "source_id"),
)

turn_traces = Table(
    "turn_traces", metadata,
    Column("message_id", Text, _fk("messages.id", "CASCADE"), primary_key=True),
    Column("trace", J, nullable=False),
    Column("engine", Text, nullable=True),
    Column("engine_version", Text, nullable=True),
    Column("prompt_version", Text, nullable=True),
    Column("created_at", Text, nullable=False),
)

trace_memory_refs = Table(
    "trace_memory_refs", metadata,
    Column("memory_item_id", Text, nullable=False),
    Column("message_id", Text, _fk("messages.id", "CASCADE"), nullable=False),
    PrimaryKeyConstraint("memory_item_id", "message_id"),
)

session_summaries = Table(
    "session_summaries", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", Text, _fk("sessions.id", "CASCADE"), nullable=False),
    Column("upto_seq", Integer, nullable=False),
    Column("kind", Text, nullable=False),
    Column("character_id", Text, nullable=True),
    Column("text", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    CheckConstraint("kind IN ('rolling','perspective','watch')", name="ck_session_summaries_kind"),
    Index("ix_session_summaries_lookup", "session_id", "kind", "upto_seq"),
)

# ── 3.5 Generation jobs ──────────────────────────────────────────────────────
generation_jobs = Table(
    "generation_jobs", metadata,
    Column("id", Text, primary_key=True),
    Column("character_id", Text, _fk("characters.id", "CASCADE"), nullable=False),
    Column("kind", Text, nullable=False),
    Column("target_field", Text, nullable=True),
    Column("status", Text, nullable=False),
    Column("progress", Float, nullable=False),
    Column("estimated_cost_usd", Float, nullable=False),
    Column("actual_cost_usd", Float, nullable=False),
    Column("input", J, nullable=True),
    Column("error", J, nullable=True),
    Column("is_seed", Boolean, nullable=False, server_default=text("0")),
    Column("created_at", Text, nullable=False),
    Column("started_at", Text, nullable=True),
    Column("finished_at", Text, nullable=True),
    Index("ix_generation_jobs_status", "status"),
    Index("ix_generation_jobs_character_created", "character_id", "created_at"),
    Index("ux_generation_jobs_one_active", "character_id", unique=True,
          sqlite_where=text("status IN ('queued','running')")),
)

generation_tasks = Table(
    "generation_tasks", metadata,
    Column("id", Text, primary_key=True),
    Column("job_id", Text, _fk("generation_jobs.id", "CASCADE"), nullable=False),
    Column("ord", Integer, nullable=False),
    Column("type", Text, nullable=False),
    Column("emotion", Text, nullable=True),
    Column("status", Text, nullable=False),
    Column("attempt", Integer, nullable=False),
    Column("max_attempts", Integer, nullable=False, server_default=text("3")),
    Column("idempotency_key", Text, nullable=False, unique=True),
    Column("provider_called_at", Text, nullable=True),
    Column("target_path", Text, nullable=True),
    Column("result_ref", Text, nullable=True),
    Column("preview_url", Text, nullable=True),
    Column("cost_usd", Float, nullable=True),
    Column("error", J, nullable=True),
    Column("created_at", Text, nullable=False),
    Column("started_at", Text, nullable=True),
    Column("finished_at", Text, nullable=True),
    Index("ix_generation_tasks_status_created", "status", "created_at"),
)

# ── 3.6 Ledger ───────────────────────────────────────────────────────────────
usage_records = Table(
    "usage_records", metadata,
    Column("id", Text, primary_key=True),
    Column("at", Text, nullable=False),
    Column("local_day", Text, nullable=False),
    Column("category", Text, nullable=False),
    Column("purpose", Text, nullable=True),
    Column("model", Text, nullable=True),
    Column("provider", Text, nullable=True),
    Column("price_period", Text, nullable=True),
    Column("generation_id", Text, nullable=True),
    Column("session_id", Text, _fk("sessions.id", "SET NULL"), nullable=True),
    Column("character_id", Text, _fk("characters.id", "SET NULL"), nullable=True),
    Column("job_id", Text, _fk("generation_jobs.id", "SET NULL"), nullable=True),
    Column("message_id", Text, nullable=True),
    Column("tokens_in", Integer, nullable=True),
    Column("tokens_cached", Integer, nullable=True),
    Column("tokens_out", Integer, nullable=True),
    Column("cost_usd", Float, nullable=False),
    Column("cost_source", Text, nullable=False, server_default=text("'provider'")),
    Column("estimated_cost_usd", Float, nullable=True),
    Column("energy_points", Float, nullable=True),
    Column("latency_ms", Integer, nullable=True),
    Column("counts_to_creation_cap", Boolean, nullable=False, server_default=text("0")),
    Column("is_seed", Boolean, nullable=False),
    CheckConstraint(
        "category IN ('chat','decision','image','music','profile','summary','memory','embedding','energy_topup')",
        name="ck_usage_records_category"),
    CheckConstraint("cost_source IN ('provider','estimate')", name="ck_usage_records_cost_source"),
    Index("ix_usage_records_local_day", "local_day"),
    Index("ix_usage_records_character_at", "character_id", "at"),
    Index("ix_usage_records_session", "session_id"),
    Index("ix_usage_records_category_at", "category", "at"),
    Index("ix_usage_records_message", "message_id"),
)

# ── 3.7 Long-term memory ─────────────────────────────────────────────────────
memory_items = Table(
    "memory_items", metadata,
    Column("rid", Integer, primary_key=True, autoincrement=True),
    Column("id", Text, nullable=False, unique=True),
    Column("character_id", Text, _fk("characters.id", "CASCADE"), nullable=False),
    Column("world_id", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("text", Text, nullable=False),
    Column("importance", Float, nullable=False),
    Column("source_session_id", Text, nullable=True),
    Column("source_message_id", Text, nullable=True),
    Column("source_variant_id", Text, nullable=True),
    Column("source_mode", Text, nullable=True),
    Column("about_character_id", Text, nullable=True),
    Column("created_at", Text, nullable=False),
    Column("last_recalled_at", Text, nullable=True),
    Column("recall_count", Integer, nullable=False, server_default=text("0")),
    Column("superseded_by", Text, nullable=True),
    Column("is_seed", Boolean, nullable=False),
    Index("ix_memory_items_character_created", "character_id", "created_at"),
)

# ── 3.8 Knowledge ────────────────────────────────────────────────────────────
knowledge_sources = Table(
    "knowledge_sources", metadata,
    Column("id", Text, primary_key=True),
    Column("character_id", Text, _fk("characters.id", "CASCADE"), nullable=False),
    Column("world_id", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("type", Text, nullable=False),
    Column("url", Text, nullable=True),
    Column("mime", Text, nullable=True),
    Column("original_name", Text, nullable=True),
    Column("bytes", Integer, nullable=True),
    Column("pages", Integer, nullable=True),
    Column("sha256", Text, nullable=True),
    Column("status", Text, nullable=False),
    Column("chunk_count", Integer, nullable=False, server_default=text("0")),
    Column("extractor_version", Text, nullable=True),
    Column("chunker_version", Text, nullable=False),
    Column("tokenizer", Text, nullable=False),
    Column("embedding_space_id", Text, nullable=True),
    Column("embed_sent_at", Text, nullable=True),          # 0002: an embedding batch is in flight (design D2)
    Column("has_original", Boolean, nullable=False),
    Column("error", J, nullable=True),
    Column("added_at", Text, nullable=False),
    Column("indexed_at", Text, nullable=True),
    Column("is_seed", Boolean, nullable=False),
    CheckConstraint("type IN ('text','file','url')", name="ck_knowledge_sources_type"),
    CheckConstraint(
        "status IN ('queued','extracting','chunking','embedding','indexed','keyword_only','failed')",
        name="ck_knowledge_sources_status"),
    Index("ux_knowledge_sources_sha", "character_id", "sha256", unique=True, sqlite_where=text("sha256 IS NOT NULL")),
)

knowledge_sections = Table(
    "knowledge_sections", metadata,
    Column("id", Text, primary_key=True),
    Column("source_id", Text, _fk("knowledge_sources.id", "CASCADE"), nullable=False),
    Column("character_id", Text, nullable=False),
    Column("world_id", Text, nullable=False),
    Column("idx", Integer, nullable=False),
    Column("heading_path", Text, nullable=True),
    Column("page_start", Integer, nullable=True),
    Column("page_end", Integer, nullable=True),
    Column("text", Text, nullable=False),
    Column("token_count", Integer, nullable=False),
    Column("char_start", Integer, nullable=False),
    Column("char_end", Integer, nullable=False),
    UniqueConstraint("source_id", "idx", name="uq_knowledge_sections_source_idx"),
)

knowledge_chunks = Table(
    "knowledge_chunks", metadata,
    Column("rid", Integer, primary_key=True, autoincrement=True),
    Column("id", Text, nullable=False, unique=True),
    Column("source_id", Text, _fk("knowledge_sources.id", "CASCADE"), nullable=False),
    Column("section_id", Text, _fk("knowledge_sections.id", "CASCADE"), nullable=False),
    Column("character_id", Text, nullable=False),
    Column("world_id", Text, nullable=False),
    Column("idx", Integer, nullable=False),
    Column("locator", Text, nullable=True),
    Column("heading", Text, nullable=True),
    Column("text", Text, nullable=False),
    Column("token_count", Integer, nullable=False),
    Column("char_start", Integer, nullable=False),
    Column("char_end", Integer, nullable=False),
    UniqueConstraint("source_id", "idx", name="uq_knowledge_chunks_source_idx"),
)

# ── 3.9 Embedding spaces ─────────────────────────────────────────────────────
embedding_spaces = Table(
    "embedding_spaces", metadata,
    Column("id", Text, primary_key=True),
    Column("model", Text, nullable=False),
    Column("provider", Text, nullable=False),
    Column("dims", Integer, nullable=False),
    Column("dtype", Text, nullable=False, server_default=text("'float32'")),
    Column("normalized", Boolean, nullable=False),
    Column("query_instruction", Text, nullable=True),
    Column("doc_template", Text, nullable=True),
    Column("status", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    CheckConstraint("status IN ('building','active','retired')", name="ck_embedding_spaces_status"),
    Index("ux_embedding_spaces_one_active", "status", unique=True, sqlite_where=text("status = 'active'")),
)

# FTS5 external-content tables + their sync triggers (created by migration 0001; skipped by autogenerate).
FTS_DDL: tuple[str, ...] = (
    "CREATE VIRTUAL TABLE memory_fts USING fts5(text, content='memory_items', content_rowid='rid', "
    "tokenize='porter unicode61')",
    "CREATE TRIGGER memory_items_ai AFTER INSERT ON memory_items BEGIN "
    "INSERT INTO memory_fts(rowid, text) VALUES (new.rid, new.text); END",
    "CREATE TRIGGER memory_items_ad AFTER DELETE ON memory_items BEGIN "
    "INSERT INTO memory_fts(memory_fts, rowid, text) VALUES ('delete', old.rid, old.text); END",
    "CREATE TRIGGER memory_items_au AFTER UPDATE OF text ON memory_items BEGIN "
    "INSERT INTO memory_fts(memory_fts, rowid, text) VALUES ('delete', old.rid, old.text); "
    "INSERT INTO memory_fts(rowid, text) VALUES (new.rid, new.text); END",
    "CREATE VIRTUAL TABLE knowledge_fts USING fts5(text, heading, content='knowledge_chunks', content_rowid='rid', "
    "tokenize='porter unicode61')",
    "CREATE TRIGGER knowledge_chunks_ai AFTER INSERT ON knowledge_chunks BEGIN "
    "INSERT INTO knowledge_fts(rowid, text, heading) VALUES (new.rid, new.text, new.heading); END",
    "CREATE TRIGGER knowledge_chunks_ad AFTER DELETE ON knowledge_chunks BEGIN "
    "INSERT INTO knowledge_fts(knowledge_fts, rowid, text, heading) VALUES ('delete', old.rid, old.text, old.heading); END",
    "CREATE TRIGGER knowledge_chunks_au AFTER UPDATE OF text, heading ON knowledge_chunks BEGIN "
    "INSERT INTO knowledge_fts(knowledge_fts, rowid, text, heading) VALUES ('delete', old.rid, old.text, old.heading); "
    "INSERT INTO knowledge_fts(rowid, text, heading) VALUES (new.rid, new.text, new.heading); END",
)
FTS_DROP: tuple[str, ...] = (
    "DROP TRIGGER IF EXISTS knowledge_chunks_au", "DROP TRIGGER IF EXISTS knowledge_chunks_ad",
    "DROP TRIGGER IF EXISTS knowledge_chunks_ai", "DROP TABLE IF EXISTS knowledge_fts",
    "DROP TRIGGER IF EXISTS memory_items_au", "DROP TRIGGER IF EXISTS memory_items_ad",
    "DROP TRIGGER IF EXISTS memory_items_ai", "DROP TABLE IF EXISTS memory_fts",
)

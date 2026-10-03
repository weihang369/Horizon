# 02: Storage

> **v1.0.** This revision applies the review debate between the backend and AI representatives (Rounds 1–2, 2026-10-03).

## 1. The rule: where each piece of data lives

| Put it in… | When | Examples |
|---|---|---|
| **A SQLite column** | We filter, join, sort, sum, constrain or update it on its own | ids, foreign keys, status, seq, timestamps, energy, cost, purpose, flags |
| **A JSON column** (`TEXT`, validated by Pydantic on write) | A nested **value object**, always read and written whole with its row, never filtered on | profile, appearance, debate config and state, message usage, citations, reactions, variants, TurnTrace, event payloads |
| **The filesystem** | Binary or large blobs | portraits, candidates, covers, songs, provider originals, uploaded documents, extracted Markdown |
| **Nowhere (derived when read)** | Computable from stored facts | `World.characterCount`, `AppSettings.spentTodayUsd`, `Energy.state/fullAt` (+ lazy regen), `Character.emotions`, `pricing.period`, `KnowledgeSource.citedCount` |

**JSON columns.**
- Doc 05 owns the shapes, and they are stored **in wire form (camelCase)**.
- A JSON field that ever needs filtering becomes a real column through a migration; SQLite JSON operators are never used in hot paths.

**Money and energy.**
- USD is `REAL` (the provider-reported `usage.cost`). This is display accounting, rounded to 6 decimal places at the API edge.
- **Energy is `REAL` in storage and floored to an integer on the wire.** Flooring on every write would erase fractional regeneration.

**Time.**
- `TEXT` ISO-8601 UTC with **exactly millisecond precision** (`2026-10-03T08:15:02.123Z`), so text order equals time order.
- Seed timestamps are normalised to this form on import.

**IDs.**
- `TEXT` primary keys in the form `prefix_ULID`; seed IDs stay readable.
- **Every table that FTS5 or vec0 indexes also has `rid INTEGER PRIMARY KEY`, plus `id TEXT NOT NULL UNIQUE`. The indexes key on `rid`.** The hidden `rowid` is never used, because `VACUUM` and Alembic batch migrations may renumber it.
- Every retrieval that joins back from FTS or vec0 **re-binds `character_id` and `world_id`** on the source row (defence in depth for NFR-23).

**Foreign keys.** Every FK declares an explicit `ON DELETE` (CASCADE, SET NULL or RESTRICT), listed in §3. Cascades don't reach virtual tables, so FTS and vec rows are kept in sync by **triggers** (§3.9).

## 2. Files on disk

```
data/                                       gitignored (NFR-22)
  horizon.db  (+ -wal, -shm)                domain source of truth
  graph.db                                  LangGraph checkpointer (AI-owned; stores IDs, never memory text)
  secrets.local.json                        { "openRouterKey": "sk-or-…" }, written by PUT /settings/key
  settings.local.json                       UI-edited AppSettings overrides
  assets/gen/{worldId}/cover_v{n}.webp
  assets/gen/{worldId}/{characterId}/candidate_{assetId}.webp
  assets/gen/{worldId}/{characterId}/portrait_{emotion}[_blink]_v{n}.webp
  assets/gen/{worldId}/{characterId}/song_v{n}.{mp3|aac|opus}
  originals/{worldId}/{characterId}/{taskId}.{jpg|png|mp3}       raw provider output (written first, see §3.6)
  knowledge/{worldId}/{characterId}/{sourceId}/original.{pdf|docx|md|txt}
  knowledge/{worldId}/{characterId}/{sourceId}/extracted.md     Docling output + <!-- page N --> markers
  models/                                   Docling / Hugging Face cache (downloaded once; HF_HUB_OFFLINE=1 afterwards)
  logs/horizon.log*
seed/assets/**                              committed seed art and themes, served read-only at /assets/**
```

- **URLs.**
  - A generated asset's URL is `/assets/gen/...`, and seed assets keep `/assets/placeholder/...`.
  - `GET /assets/{path}` resolves `data/assets/` first, then `seed/assets/`, and blocks traversal.
  - Generated names are immutable, so `gen/` is served with `Cache-Control: public, max-age=31536000, immutable`.
- **Atomic writes.** A file is written to `*.tmp`, `fsync`ed, then `os.replace`d. The row that points to it commits **after** the file exists. A startup sweeper removes `*.tmp` files and unreferenced files older than 1 hour.
- **Image pipeline (D-61).**
  1. The provider JPEG goes to `originals/` **first** (it's the paid artefact).
  2. Pillow resizes it to 768×1024 (Lanczos, a 1–2 px centre crop) and saves WebP q≈85, about 80–120 KB.
  3. The WebP is **re-derivable** from the original for free.
  4. The emotion edit sends the base portrait to the provider as a data URL.
- **Seed SVG placeholders** are served as-is; their `EmotionAsset.format` is omitted (the contract enum is `webp | avif`).

## 3. Tables

> `PK` · `FK→t (CASCADE|SET NULL|RESTRICT)` · `IX` index · `UQ` unique · `pUQ` partial unique index · `J` JSON (wire shape).

### 3.1 Settings, idempotency, outbox

```
app_settings      id INTEGER PK CHECK(id=1), data J, updated_at
                  -- persisted AppSettings parts only. No tz here: HORIZON_TZ comes from env/config.
idempotency_keys  key TEXT PK, method, path, body_sha256, status INTEGER NULL, response J NULL,
                  state ('in_flight'|'done'), created_at, expires_at          IX(expires_at)
ai_purge_queue    id INTEGER PK, scope ('memory'|'message'|'session'|'character'|'world'), ids J,
                  created_at, attempts INTEGER, done_at NULL                   -- outbox for AiStateHooks (doc 05 §4)
```

`openRouterKeyStatus`, `demoMode`, `spentTodayUsd` and `pricing` are computed per request. The key is never in the database.

### 3.2 Worlds, characters, assets

```
worlds        id PK, name TEXT UQ COLLATE NOCASE, cover J, you J NULL, is_seed,
              created_at, updated_at, last_active_at
characters    id PK, world_id FK→worlds (CASCADE), status, creation_step NULL, seed_prompt, intent, advisory,
              profile J, profile_meta J NULL, appearance J,       -- attributes + summary + style preset; candidates/base derived
              palette_id, emotion_set J, theme_song_id NULL FK→theme_songs (SET NULL),
              active_job_id NULL FK→generation_jobs (SET NULL), version INTEGER,
              energy_max INTEGER, energy_current REAL, energy_as_of TEXT,
              energy_spent_today REAL, energy_day TEXT,               -- local date (HORIZON_TZ) of spent_today
              is_seed, created_at, updated_at, approved_at NULL, archived_at NULL, deleted_at NULL
              IX(world_id, status)
image_assets  id PK (emo_… / cand_…), world_id FK→worlds (CASCADE), character_id NULL FK→characters (CASCADE),
              job_id NULL FK→generation_jobs (SET NULL),
              kind ('candidate'|'emotion'|'cover'), emotion NULL, variant ('default'|'blink'),
              status, rel_path NULL, width, height, format NULL, bytes, vfx_preset,
              generation J NULL, version INTEGER, is_active BOOLEAN, created_at
              CHECK ((kind = 'cover') = (character_id IS NULL))
              pUQ(character_id, emotion, variant, version) WHERE kind='emotion'
              pUQ(character_id, emotion, variant)          WHERE kind='emotion' AND is_active      -- ≤ 1 active per slot
              pUQ(world_id, version)                       WHERE kind='cover'
              IX(character_id, kind, job_id)
theme_songs   id PK (song_…), character_id FK→characters (CASCADE), status, rel_path NULL, duration_sec, format, bytes,
              loop J NULL, gain_db NULL, brief J, instrumental, generation J NULL, license_note, version, created_at
              -- no UQ(character_id): regeneration inserts a new row; characters.theme_song_id is the active pointer
```

- **Derived on read:**
  - `Character.emotions` comes from the active `emotion` rows with variant `default`.
  - `blink` comes from the active `neutral`/`blink` row.
  - `basePortraitUrl` is the active `neutral`/`default` row.
  - **`Appearance.candidates`** comes from the `candidate` rows of the **latest `job_id` batch**, or from the seed batch (`job_id IS NULL`) when there is no job.
- **`characters.assets`** returns `kind='emotion'` rows only, in every version.
- **`acceptAssetVersion`** runs in one transaction: it **deactivates the old row first, then activates the new one** (SQLite can't defer unique checks).
- **Seed candidate IDs must be globally unique.** The seed generator emits `cand_{characterSuffix}{n}`, because `cand_1` currently collides across six characters (M1a fix).

### 3.3 Energy (columns on `characters`; formulas in doc 04 §4)

`energy_current` and `energy_spent_today` are `REAL`. One rule decides both the displayed **state** and the **speak/skip gate**: `EST_REPLY_POINTS[period]` (4 off-peak, 8 peak), the same constant as `frontend/src/domain/energy.ts`.

### 3.4 Sessions, messages, events (event-sourced)

```
sessions          id PK, world_id FK→worlds (CASCADE), title, title_is_custom, mode, status, paused_reason NULL,
                  emotion_mode, music_policy, readable_mode, config J NULL, state J NULL,
                  continued_from NULL FK→sessions (SET NULL), is_seed, cost_usd REAL, message_count INTEGER,
                  created_at, updated_at, last_message_at NULL                    IX(world_id, updated_at DESC)
participants      session_id FK→sessions (CASCADE), character_id FK→characters (RESTRICT),
                  ord, role, side NULL, current_emotion, muted BOOLEAN            PK(session_id, character_id)
session_events    id PK (evt_…), session_id FK→sessions (CASCADE), seq INTEGER, at TEXT, type TEXT,
                  message_id TEXT NULL, payload J                                  -- message_id: scrub + forget lookups
                  UQ(session_id, seq)   IX(message_id)
messages          id PK (msg_…), session_id FK→sessions (CASCADE), seq INTEGER,
                  author_type, author_character_id NULL, kind, target_character_id NULL,
                  content TEXT, status, interrupted_by NULL, emotion NULL, emotion_source NULL,
                  debate J NULL, forced_speaker BOOLEAN, reactions J NULL, variants J NULL, active_variant_id NULL,
                  usage J NULL, citations J NULL, error J NULL, created_at
                  UQ(session_id, seq)   IX(author_character_id, created_at)
message_citations message_id FK→messages (CASCADE), n INTEGER, chunk_id TEXT, source_id TEXT,
                  PK(message_id, n)   IX(source_id)                               -- citedCount = COUNT(*) per source
turn_traces       message_id PK FK→messages (CASCADE), trace J,
                  engine TEXT NULL, engine_version TEXT NULL, prompt_version TEXT NULL, created_at
trace_memory_refs memory_item_id TEXT, message_id FK→messages (CASCADE),    PK(memory_item_id, message_id)
session_summaries id INTEGER PK, session_id FK→sessions (CASCADE), upto_seq INTEGER,   -- = messages.seq
                  kind ('rolling'|'perspective'|'watch'), character_id NULL, text, created_at
                  IX(session_id, kind, upto_seq DESC)                              -- AI-owned content; never on the wire
```

- **Event-sourced.** `session_events` is the **source of truth** for a session's timeline.
  - `messages`, `participants.current_emotion`/`muted` and `sessions.status`/`state`/settings are **derived rows**. They are maintained by `services/runtime/reducer.py`, a Python port of `frontend/src/engine/sessionReducer.ts` `applyEvent`.
  - **The actor applies the reducer in the same transaction as the event insert.**
  - A cross-language fixture test asserts `reduce(seed events) == seed messages.json` in both Python and TS.
- **Two sequences.**
  - `messages.seq` orders messages.
  - `session_events.seq` orders the stream. **SSE `id:` = event seq**, and `SessionSnapshot.lastSeq` = the latest event seq.
  - The SessionActor assigns both.
- **Token events are coalesced** (one per ~50 ms or 64 characters) *before* both persist and publish, so a reply is about 30 rows. Replay timing is kept by `at`.
- **Crash recovery.** On startup, any message still `streaming` is **re-reduced** from its persisted `token` events and then closed with `turn.end` (`status:"interrupted"`, `interruptedBy:"error"`). There is no periodic content flush.
- **Insight.** The actor merges every `TracePatch` (doc 05 §2) **before** emitting, and each `insight` event carries the **full** trace. The reducer already replaces the trace on each `insight`, so the last one wins, and `turn_traces` holds the latest. While persisting a trace, the actor writes `trace_memory_refs` for every `memory.recalled[].memoryItemId`.
- **Fork** (`forkSeedSession(id, atSeq?)`):
  - **`atSeq` is an event seq.** The cut extends to the `turn.end` of any turn streaming at `atSeq`, matching the MockClient.
  1. Copy those events with new event and message IDs, renumbered from 1.
  2. **Re-reduce** them into a new live session with `continued_from` set.
  3. Copy the summaries with `upto_seq ≤` the last copied message seq.
  4. Multi-speaker forks start `paused` (`user`), as in the mock.

### 3.5 Generation jobs

```
generation_jobs  id PK (job_…), character_id FK→characters (CASCADE), kind, target_field NULL, status, progress REAL,
                 estimated_cost_usd, actual_cost_usd, input J, error J NULL, created_at, started_at NULL, finished_at NULL
                 IX(status)  IX(character_id, created_at DESC)
                 pUQ(character_id) WHERE status IN ('queued','running')      -- one non-terminal job per character (= activeJobId)
generation_tasks id PK (task_…), job_id FK→generation_jobs (CASCADE), ord INTEGER, type, emotion NULL, status,
                 attempt, max_attempts (3), idempotency_key TEXT UQ,          -- '{job_id}:{ord}'
                 provider_called_at NULL, target_path NULL, result_ref NULL, preview_url NULL, cost_usd REAL NULL,
                 error J NULL, created_at, started_at NULL, finished_at NULL
                 IX(status, created_at)
```

- **Paying-twice rule** (NFR-19, NFR-30):
  1. `provider_called_at` is committed **before** the provider call.
  2. On receipt, the original is written atomically, **then** `result_ref` and the ledger row are committed together, **then** the derived WebP is made.
  3. **On restart:**
     - a task with no `provider_called_at` is requeued;
     - a task with `result_ref` set has only its derived output finished;
     - a task with **`provider_called_at` set but no `result_ref` becomes `failed` (retryable)**.

     Only an explicit user Retry pays again.
- **Internal job kinds** reuse these tables and are never exposed as `GenerationJob` on the wire: `knowledge_index`, `knowledge_reindex`, `seed_embed`, and later `memory_consolidate`.

### 3.6 Ledger

```
usage_records  id PK, at TEXT, local_day TEXT,
               category ('chat'|'decision'|'image'|'music'|'profile'|'summary'|'memory'|'embedding'|'energy_topup'),
               purpose TEXT NULL,            -- reply|route|gate|rerank|guardrail|reaction|emotion|importance|query_embed|…
               model NULL, provider NULL, price_period NULL, generation_id NULL,
               session_id NULL FK (SET NULL), character_id NULL FK (SET NULL), job_id NULL FK (SET NULL),
               message_id TEXT NULL,          -- no FK: allocated before generation; discarded prefetches keep it NULL
               tokens_in NULL, tokens_cached NULL, tokens_out NULL,
               cost_usd REAL, cost_source ('provider'|'estimate'), estimated_cost_usd NULL,
               energy_points REAL NULL, latency_ms NULL, counts_to_creation_cap BOOLEAN, is_seed BOOLEAN
               IX(local_day)  IX(character_id, at)  IX(session_id)  IX(category, at)  IX(message_id)
```

- **Append-only, with one exception.** A row with `cost_source='estimate'` (a cancelled stream, or a request cancelled after being sent) may be **corrected once** to the provider's actual cost via `generation_id`. Reference columns go `SET NULL` on delete. Nothing else is ever updated.
- **`Message.usage`** is built from the ledger rows with `message_id = X AND purpose = 'reply'`, plus the actor's timings.
- **`spentTodayUsd`** = `SUM(cost_usd) WHERE local_day = today`. **Creation spend** = `SUM WHERE character_id = ? AND counts_to_creation_cap`.

### 3.7 Long-term memory (storage; the policy is AI-owned)

```
memory_items   rid INTEGER PK, id TEXT UQ (mem_…), character_id FK→characters (CASCADE), world_id,
               kind, text, importance REAL,
               source_session_id NULL, source_message_id NULL, source_variant_id NULL,
               source_mode ('one_on_one'|'group'|'debate'|'watch') NULL,     -- D-71
               about_character_id NULL,                                       -- whom the memory is about (perspective)
               created_at, last_recalled_at NULL, recall_count INTEGER DEFAULT 0,
               superseded_by TEXT NULL, is_seed BOOLEAN
               IX(character_id, created_at DESC)
memory_fts     FTS5(text, content='memory_items', content_rowid='rid', tokenize='porter unicode61')
memory_vec__{space}  vec0(rid INTEGER PRIMARY KEY, character_id TEXT PARTITION KEY,
                          embedding FLOAT[{dims}] distance_metric=cosine)
```

- **Writes go through one backend API.** `MemoryStore.apply(character_id, ops: list[MemoryOp])` applies `Insert | Supersede | Reinforce | Touch` (doc 05 §2) in **one transaction**, covering the row, FTS and vectors. The embeddings are computed *before* the writer lock is taken.
- **Forget**, in one transaction:
  1. Delete the item, its whole `superseded_by` chain, their FTS and vector rows, and their `trace_memory_refs`.
  2. Rewrite the matching `turn_traces.trace` **and** `session_events` `insight` payloads (looked up via `trace_memory_refs.message_id` → `session_events.message_id`), replacing the memory `text` with `"(forgotten)"`.
  3. Write an `ai_purge_queue` row (`scope:'memory'`) so the AI layer purges summaries and checkpoints (doc 05 §4).
  4. Emit `entity.changed{kind:"memory"}`.

### 3.8 Knowledge (storage; the chunking and retrieval policy is AI-owned)

```
knowledge_sources  id PK (kno_…), character_id FK→characters (CASCADE), world_id,
                   title, type ('text'|'file'|'url'(legacy, read-only)), mime NULL, original_name NULL,
                   bytes NULL, pages NULL, sha256 NULL,
                   status ('queued'|'extracting'|'chunking'|'embedding'|'indexed'|'keyword_only'|'failed'),
                   chunk_count, extractor_version NULL, chunker_version, tokenizer TEXT, embedding_space_id NULL,
                   has_original BOOLEAN, error J NULL, added_at, indexed_at NULL, is_seed BOOLEAN
                   pUQ(character_id, sha256) WHERE sha256 IS NOT NULL          -- the same document twice → 409
knowledge_sections id PK (ksec_…), source_id FK→knowledge_sources (CASCADE), character_id, world_id,
                   idx, heading_path TEXT, page_start NULL, page_end NULL, text, token_count, char_start, char_end
                   UQ(source_id, idx)                                          -- parents: what the LLM reads
knowledge_chunks   rid INTEGER PK, id TEXT UQ (kch_…), source_id FK (CASCADE), section_id FK→knowledge_sections (CASCADE),
                   character_id, world_id, idx, locator ('p. 4'|'§ Heading'), heading TEXT,
                   text, token_count, char_start, char_end                     -- children: indexed + cited
                   UQ(source_id, idx)
knowledge_fts      FTS5(text, heading, content='knowledge_chunks', content_rowid='rid', tokenize='porter unicode61')
knowledge_vec__{space} vec0(rid INTEGER PRIMARY KEY, character_id TEXT PARTITION KEY,
                            embedding FLOAT[{dims}] distance_metric=cosine)
```

- **Wire mapping.**
  - `KnowledgeChunk` = a child chunk.
  - The API status is `indexing` (queued, extracting, chunking or embedding), `indexed`, `keyword_only` (rev 1.3) or `failed`.
  - `citedCount` is derived from `message_citations`.
  - `O28` highlights by the child's `char_start`/`char_end`.
- **Layers.** Each layer is rebuildable from the one above: `original → extracted.md → sections/chunks → FTS/vectors`. The `*_version`, `tokenizer` and `embedding_space_id` columns mark which rows are stale.
  - A source with **no original** (seed, `has_original = 0`) can only be **re-embedded**, never re-chunked.
- **Seed knowledge** has chunks but no sections. The import synthesises **one section per chunk** (parent text = child text), with `sha256`, `original_name` and `extracted.md` absent.
- **Limits (D-65):**

  | Limit | Value |
  |---|---|
  | File size | ≤ 10 MB |
  | Pages | ≤ 300 |
  | Sources per character | ≤ 20 |
  | Child chunks per character | ≤ 3,000 |
  | Pasted text | ≤ 200 KB |

  MIME types are PDF, DOCX, Markdown and plain text, checked by **magic bytes**.
- **Deleting a source** removes its folder and its rows; the triggers (§3.9) clean FTS and vectors. Messages keep their `citations` snapshots, so the chips open the "source removed" state (PRF-10 AC5).

### 3.9 Embedding spaces, FTS and vec maintenance (D-64)

```
embedding_spaces  id PK ('qwen3-emb-8b@1024'), model, provider, dims, dtype ('float32'), normalized BOOLEAN,
                  query_instruction TEXT, doc_template TEXT, status ('building'|'active'|'retired'), created_at
```

- **A `SpaceManager` creates vec tables at runtime; Alembic does not.**
  - It creates `memory_vec__{space}` and `knowledge_vec__{space}`, **plus their `AFTER DELETE` triggers** on `memory_items` / `knowledge_chunks`.
  - Alembic's `include_object` skips every virtual table and its shadow tables.
  - At startup the SpaceManager makes sure the active space's tables exist. That's the default space on first run, embedded only after a key is set; see doc 04 §3.
- **FTS sync.** External-content FTS tables are kept in sync by `AFTER INSERT/UPDATE/DELETE` triggers that use the FTS `'delete'` command with the **old** values. An M1 spike confirms that the triggers fire on FK-cascade deletes.
- **Switching spaces.**
  1. A reindex job builds the new space (`building`).
  2. Ingestion meanwhile **writes to both** spaces.
  3. Before the flip, a final pass embeds any rows still missing.
  4. In one transaction, the new space becomes `active` and the old one `retired`.
  5. The retired tables are dropped on the next startup.
- **Search is exact flat KNN**, bounded by the character partition. sqlite-vec bit vectors with an exact rescore are the escape hatch if a partition grows huge. There is no ANN index.
- **Embedding failure** ends ingestion as `keyword_only`, with a background re-embed **only** for user-added sources while a key is set.

### 3.10 Isolation (NFR-23)

- Repository methods for characters, sessions, memory and knowledge **require `world_id`** (and `character_id` where relevant). Vector KNN always binds the partition key, and the join back re-checks the scope.
- `tests/isolation/` builds two near-identical worlds and asserts that no API call, recall or retrieval in world A ever returns world B data.
- It also asserts that **after Forget, the forgotten text appears nowhere** in `horizon.db` or `graph.db`.

## 4. Lifecycles (D-70)

| Action | What happens |
|---|---|
| **Archive / Restore** | Sets or clears `archived_at` |
| **Delete a character** | **409 while it is in the currently streaming session.** Otherwise:<ol><li>cancel its non-terminal job;</li><li>**tombstone** it (`deleted_at`; keep the name, a minimal profile, the palette and the active neutral portrait);</li><li>delete its other assets and files, songs, memory, knowledge and jobs;</li><li>purge the AI state (`ai_purge_queue`).</li></ol>In sessions, a tombstoned participant is skipped with reason `"archived"` |
| **Delete a world** | Stops the actors of its sessions, then cascades: sessions (events, messages, traces, summaries), characters (fully), memory and knowledge. Ledger references become NULL. Removes the `assets/gen/{worldId}` and `knowledge/{worldId}` folders, and queues an AI purge (`scope:'world'`) |
| **Delete a session** | Through its actor (which stops first). Cascades the events, messages, traces and summaries; ledger `session_id` becomes NULL; queues an AI purge |
| **Forget a memory** | §3.7 |
| **Guardrail block after streaming** | `turn.end` with `status:"error"`, `content_refused`. The message content **and its persisted `token` events are scrubbed** (the Forget path, by `message_id`), and the message is excluded from memory |
| **Reset demo data** | **Upserts** seed worlds and characters in place (user forks may reference them). **Deletes and re-inserts seed sessions.** Replaces seed ledger rows (`is_seed`). Seed memory and knowledge are restored, while **user-earned memories on seed characters (`is_seed = 0`) survive**. Queues an AI purge for the seed sessions. Emits a global `mock.reset` so screens re-query |
| **Factory reset** | Double-confirmed:<ol><li>stop the actors, the scheduler and any Docling process;</li><li>close the `graph.db` checkpointer;</li><li>dispose the engines and close the log handlers (Windows file locks);</li><li>`rmtree data/` except `models/`, with retries;</li><li>re-run the startup lifespan in-process.</li></ol> |

## 5. Migrations and seed import

- **Alembic** `0001_initial` creates every ordinary table and the FTS tables (vec tables are left to the SpaceManager). The app runs `upgrade head` at startup. There are no downgrades; backup is a copy of `data/`.
- **Seed import** (`services/seed.py`):
  1. **Validate** every file against the contract schema.
  2. **Normalise** timestamps to milliseconds.
  3. **Insert** in one transaction with `is_seed=1`.
  4. **Reduce** seed `events.json` into messages and **assert** the result equals `messages.json`.
  5. **Synthesise** knowledge sections.
  6. **Index** FTS immediately.

  Vectors are created by an explicit **"Index seed knowledge"** action offered after `setKey`, an estimated < $0.001 (NFR-30). Until then the seed sources are `keyword_only`. `seed/_mock/**` is never imported.
- **Contract schema.**
  - The frontend command `npm run export-schema` uses zod 4's native `z.toJSONSchema` to write `backend/horizon/contract/schema.json`.
  - CI fails on drift.
  - Contract tests validate every response and every SSE payload against it.

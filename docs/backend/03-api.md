# 03: API

## 1. Conventions

| Topic | Rule |
|---|---|
| Base | `http://127.0.0.1:8000/api/v1`. The backend binds to loopback only (NFR-13). No auth (ground rule 1) |
| Format | JSON, **camelCase**, the shapes of doc 05 exactly. Optional fields are **omitted**, not `null`, unless the contract says `| null` |
| Docs | OpenAPI at `/api/docs` and `/api/openapi.json`, generated from the wire models |
| Queries | `GET`, safe, cacheable by `ETag` where cheap (settings, world, character) |
| CRUD | `POST` creates (201 + body) · `PATCH` updates with a partial body (deep-merge for `profile`/`appearance.attributes`, matching `CharacterPatch`) · `DELETE` returns 204 |
| Commands | `POST …/{verb}` returns **202 Accepted** `{ "commandId": "cmd_…" }`. The *effects* arrive as SSE events (`HorizonClient` commands resolve on 202) |
| Idempotency | Every `POST` accepts `Idempotency-Key` (the HttpClient sends a UUID per user action). Keys are stored in the **`idempotency_keys` table**, so they **survive a restart** (`POST /jobs` pays), and live for 24 h:<ul><li>same key + same body → the stored status and body are replayed;</li><li>same key + **different** body → 409 `conflict`;</li><li>same key while the first request is still in flight → the second waits for it and returns its result</li></ul> |
| Pagination | `GET /sessions/{id}/messages`, `GET /sessions/{id}/events` and `GET /usage` **always** return `{ items, nextCursor: string \| null }`. They take `?limit=` (default 200, max 1,000) and `?cursor=`, an opaque cursor: an event or message seq, or `(at,id)` for usage. The `HorizonClient` methods keep returning plain arrays, because the HttpClient follows `nextCursor` until it is null |
| Uploads | `multipart/form-data`. The request is rejected early on `Content-Length` (413 → `validation`), and the size limit is enforced again by **counting bytes while streaming to disk** (python-multipart buffers the whole file otherwise). `POST /characters/{id}/knowledge` dispatches on `Content-Type`: multipart = file, JSON = pasted text |
| Versioning | `/api/v1` is the transport version, and `schemaVersion: 1` is the contract version. Additive changes don't bump either |

## 2. Errors

Every non-2xx response has this body:
```json
{ "error": { "code": "conflict", "message": "Another session is live.", "retryable": false,
             "retryAfterSec": 12, "details": { "activeSessionId": "ses_…" } } }
```
`code` is an `ErrorCode` (doc 05, plus rev 1.3's `not_found`, `validation` and `conflict`). `details` is optional and machine-readable.

| HTTP | `code` |
|---|---|
| 400 | `missing_key` (an AI action with no key set), `validation` (business-rule violation) |
| 401 | `invalid_key` (OpenRouter rejected the key) |
| 402 | `insufficient_credits`, `daily_budget_exceeded`, `creation_budget_exceeded`, `energy_exhausted` |
| 404 | `not_found` (also returned for a cross-world access attempt, so the API never reveals that another world's ID exists) |
| 409 | `conflict` (duplicate world name, duplicate document, another live session, a job already running for the same slot, an invalid lifecycle transition) |
| 413 / 422 | `validation` (payload too big / schema-invalid: FastAPI's 422 is **re-mapped** to this shape) |
| 429 | `rate_limited` (+ `Retry-After` header and `retryAfterSec`) |
| 451 | `content_refused` |
| 502 | `provider_error` |
| 504 | `timeout` |

`network` is client-side only, used when the server can't be reached.

## 3. Endpoint catalogue (mapped to `HorizonClient`)

### Settings · `settings.*`
| Method | Route | Body → Response |
|---|---|---|
| `get` | `GET /settings` | → `AppSettings` |
| `update` | `PATCH /settings` | `DeepPartial<AppSettings>` (computed and config-owned fields such as `estReplyPoints` are ignored, M2 OQ-E) → `AppSettings` |
| `setKey` | `PUT /settings/key` | `{ key: string \| null }` → `AppSettings` (validates the format and saves it; it doesn't call the network, `testConnection` does). `null` deletes the secret file |
| `testConnection` | `POST /settings/test-connection` | → `{ ok, latencyMs, creditsUsd? }` (OpenRouter key-info call; sets `openRouterKeyStatus`) |
| `testModel` | `POST /settings/test-model` | `{ role: "chat"\|"decision"\|"image"\|"music"\|"embedding" }` → `{ ok, latencyMs, model }`: the cheapest possible probe per role (chat: 1-token completion; decision: a one-question Jev call; embedding: one word; image and music: a *metadata* check only, **never** a paid generation) |

### Worlds · `worlds.*`
| `list` `GET /worlds` · `get` `GET /worlds/{id}` · `create` `POST /worlds` (`WorldInput`) · `update` `PATCH /worlds/{id}` · `delete` `DELETE /worlds/{id}` |
|---|
| **rev 1.3** `uploadCover`: `POST /worlds/{id}/cover` (multipart `file`, PNG, JPEG or WebP, ≤ 5 MB) → `World` (re-encoded to 1600×900 WebP) |

### Characters · `characters.*`
| Method | Route |
|---|---|
| `list` | `GET /worlds/{worldId}/characters?includeArchived=` |
| `get` | `GET /characters/{id}` (also returns tombstoned characters, `deletedAt` set) |
| `createDraft` | `POST /worlds/{worldId}/characters` `DraftInput` → `{ character, job }` (starts a `profile_draft` job; needs a key) |
| `update` | `PATCH /characters/{id}` `CharacterPatch` (bumps `version` on saved edits; `profileMeta.editedFields` maintained by the client) |
| `lockPortrait` | `POST /characters/{id}/lock-portrait` `{ candidateId }` (copies the candidate to `portrait_neutral_v1`, active) |
| `approve` | `POST /characters/{id}/approve` (gate: profile valid, age ≥ 18, base portrait locked → `approved`, `approvedAt`) |
| `archive` / `restore` | `POST /characters/{id}/archive` · `POST /characters/{id}/restore` |
| `delete` | `DELETE /characters/{id}` → tombstone (doc 02 §4). Returns 409 while the character is in the currently streaming session; cancels its non-terminal job |
| `assets` | `GET /characters/{id}/assets` → `EmotionAsset[]` (all versions) |
| `acceptAssetVersion` | `POST /assets/{assetId}/accept` → `Character` |
| `song` | `GET /characters/{id}/song` → `ThemeSong \| null` |
| `topUpEnergy` | `POST /characters/{id}/energy/top-up` `{ points }` → `Energy` (ledger `energy_topup`; bounded by the daily cap) |
| `setEnergyMax` | `PUT /characters/{id}/energy/max` `{ points }` → `Energy` |
| `memory` | `GET /characters/{id}/memory` → `MemoryItem[]` |
| `forgetMemory` | `DELETE /memory/{memoryItemId}` → 204 (scrubs traces) |
| `knowledge` | `GET /characters/{id}/knowledge` → `KnowledgeSource[]` |
| `knowledgeSource` | `GET /knowledge/{sourceId}` → `{ source, chunks }` |
| **rev 1.3** `addKnowledge` | `POST /characters/{id}/knowledge`: multipart `file` **or** JSON `{ type:"text", title, text }` → `KnowledgeSource` (`status: indexing`) |
| **rev 1.3** `deleteKnowledge` | `DELETE /knowledge/{sourceId}` → 204 |
| **rev 1.3** `reindexKnowledge` | `POST /knowledge/{sourceId}/reindex` → `KnowledgeSource` |

Knowledge status changes are pushed as `entity.changed {kind:"knowledge", id}` on the global stream.

### Jobs · `jobs.*`
| `estimate` `POST /jobs/estimate` (`StartJobInput` → `{ estimatedCostUsd }`) · `start` `POST /jobs` (→ `GenerationJob`, 201) · `get` `GET /jobs/{id}` · `listActive` `GET /jobs?active=true` · `cancel` `POST /jobs/{id}/cancel` · `retryTask` `POST /jobs/{id}/tasks/{taskId}/retry` |
|---|

**M1b ships the reads** (`get`, `listActive` and `subscribe`); estimate/start/cancel/retry arrive with M4.

**`subscribe`** has no dedicated stream. The HttpClient does `GET /jobs/{id}` (emitted as the first `job.progress` snapshot), then filters the **global** stream for this `jobId` (`job.progress`, `task.update` including `previewUrl`, `job.done`). This keeps the browser at ≤ 2 EventSources.

`start` **reserves** the job's estimated cost against the caps (doc 04 §3). It rejects with 402 `creation_budget_exceeded` / `daily_budget_exceeded` **before** queueing if the estimate wouldn't fit (NFR-07). It rejects with 409 if the character already has a non-terminal job.

### Sessions · `sessions.*`
| Method | Route |
|---|---|
| `list` | `GET /worlds/{worldId}/sessions` |
| `get` | `GET /sessions/{id}` → `SessionSnapshot { session, messages, lastSeq }` (messages without `trace`) |
| `create` | `POST /sessions` `CreateSessionInput` → `SessionSnapshot` (validates cast size by mode, all participants `approved` and in the same world) |
| `rename` | `PATCH /sessions/{id}` `{ title }` → `Session` |
| `delete` | `DELETE /sessions/{id}` |
| `forkSeedSession` | `POST /sessions/{id}/fork` `{ atSeq? }` → `SessionSnapshot` |
| `messages` | `GET /sessions/{id}/messages?cursor=&limit=` → `{ items, nextCursor }` |
| `trace` | `GET /messages/{messageId}/trace` → `TurnTrace \| null` |
| `events` | `GET /sessions/{id}/events?cursor=&limit=` → `{ items, nextCursor }` (Replay) |
| `export` | `GET /sessions/{id}/export` → `text/markdown` (citations as footnotes, PRF-10 AC4) |
| `subscribe` | `GET /sessions/{id}/stream?sinceSeq=` (SSE; also honours `Last-Event-ID`) |
| `leave` | `POST /sessions/{id}/leave` (pauses with `navigated_away` if live) |
| `end` | `POST /sessions/{id}/end` |

### Session commands (all **202**, results via the session stream)
| Group | Route `POST /sessions/{id}/…` | Body |
|---|---|---|
| chat | `send` | `{ text, mentions? }` |
| | `stop` · `everyone-answer` | — |
| | `regenerate` | `{ messageId }` |
| | `set-emotion` | `{ characterId, emotion }` (MANUAL face change; emits `emotion` with no `messageId`, `source:"user"`) |
| | `set-emotion-mode` · `set-responder-policy` · `set-music-policy` · `set-readable-mode` | `{ mode }` · `{ policy }` · `{ policy }` · `{ on }` (each emits `session.state.settings`) |
| | `next-speaker` | `{ characterId? }` |
| | `mute` | `{ characterId, muted }` |
| debate | `debate/pause` · `debate/resume` · `debate/next` · `debate/extend-round` · `debate/skip-to-closing` | — |
| | `debate/auto-advance` | `{ on }` |
| | `debate/ask` | `{ characterId, text }` |
| | `debate/interject` | `{ text }` |
| | `debate/end` | `{ withVerdict }` |
| | `debate/pick` | `{ side }` |
| watch | `watch/play` · `watch/pause` · `watch/step` · `watch/summarise` | — |
| | `watch/pace` | `{ paceMs }` |
| | `watch/direct` · `watch/step-in` | `{ text }` |
| | `watch/extend` | `{ turns? }` (default 10) |

**Rejected before 202** (preconditions ported from the MockClient's `liveSession()`):
- unknown session (404);
- seed session (409, "fork first");
- ended session (409);
- a debate command in a chat session (409);
- another live session (409 + `activeSessionId`);
- no key (400 `missing_key`);
- a cap still reached (402);
- empty text (422).

**Not a rejection:**
- sending to a **paused** 1:1 or group session **auto-resumes** it;
- **energy exhaustion is never a pre-202 rejection.** It arrives as an async event: the speaker is skipped (`turn.next.skipped`), or in 1:1 a `system_note` plus an `error` event with `energy_exhausted`.

All session commands, plus `rename`, `leave`, `end` and `delete`, run through the session's actor inbox (doc 01 §4.2).

### Usage · `usage.*`
`list` `GET /usage?sinceDays=` → `UsageRecord[]` · `summary` `GET /usage/summary` → `UsageSummary`

### Global and admin
| Route | Purpose |
|---|---|
| `GET /events` | Global SSE: `entity.changed` (+ optional `progress` for knowledge), `budget.warning`, `budget.reached`, `job.progress`, **`task.update`**, `job.done`, `error`, `mock.reset` (`HorizonClient.onGlobal`; `jobs.subscribe` filters it) |
| `GET /health` | `{ ok, version, schemaVersion, db: "ok", vec: "ok", docling: "ready"\|"models_missing"\|"not_installed" }` |
| `POST /admin/reset-demo` | Re-seed seed data only (doc 02 §4). Body `{ confirm: true }`. Emits `mock.reset` on the global stream so screens re-query |
| `/_test/*` | **Only when `HORIZON_TEST=1`:** `POST /_test/clock` (`{ freezeAt?, advanceMs?, release? }`), `POST /_test/scenario` (`{ id }`; a registry, empty in M1b: an unsupported id is `validation` with `details.availableIn`), and later `POST /_test/ai-profile` (M3), `POST /_test/decider-fixtures` (M2/M3). Test mode also validates every response against `schema.json` and imports the default-scenario `seed/_mock/**` overlays, so the portable `clientContract` suite sees the MockClient's dataset. Per-test isolation uses `POST /admin/factory-reset` |
| `POST /admin/factory-reset` | Body `{ confirm: "DELETE EVERYTHING" }`. Deletes `data/` except `models/` |
| `GET /assets/{path}` | Static files: `data/assets` first, then `seed/assets`. Immutable caching for `gen/` |

## 4. SSE streams

```
id: 412
event: token
data: {"messageId":"msg_…","delta":"Honestly? "}

: keepalive            ← comment line every 15 s
```

- **Session stream** (`/sessions/{id}/stream`).
  - `id` = the event seq, and `event` = the doc 05 §6 type.
  - `data` is the whole stored `SessionEvent` = `{id, sessionId, seq, at, type, payload}` (M1b: the SSE fields can't carry `at` or the event id, which the reducer needs).
  - **Resume:**
    1. The effective start is `max(?sinceSeq, Last-Event-ID)`. EventSource reconnects reuse the original URL, so `Last-Event-ID` must win when it is higher.
    2. The server registers the live queue **first**.
    3. It replays the stored events above the start, in short read transactions.
    4. It then drains the queue, skipping `seq ≤ lastSent`.
- **Global stream** (`/events`). This is the only other stream; job events are mirrored onto it. There's no replay: on reconnect the client re-queries what it shows and re-fetches the snapshot of any job it watches.
- **Only two EventSources:** global and the open session. HTTP/1.1 allows 6 connections per origin, and more streams would starve ordinary requests.
- **Proxying.** Responses carry `Cache-Control: no-cache` and `X-Accel-Buffering: no`. The Vite proxy is configured not to buffer.

## 5. The HttpClient

- **Location:** `frontend/src/client/http/`, implementing `HorizonClient` with no changes to the interface. Additive rev 1.3 methods are added to both the MockClient and the HttpClient.
- **Subscriptions:** `subscribe(...)` uses `EventSource`. Reconnection is automatic, and `Last-Event-ID` is sent by the browser.
- **Errors:** every non-2xx response is parsed into a `HorizonError`.
- **Idempotency:** every command sends an `Idempotency-Key`.
- **Delivery:** each milestone ships the HttpClient methods for its own routes, so M1b already browses and replays via HTTP.
- **Tests:** the `clientContract.test.ts` suite is split into **portable** tests, which run against both clients, and **mock-only** tests (those using `c.dev.*`).
  - The HTTP run starts a backend with `HORIZON_TEST=1` and drives time and scenarios through `/_test/*`.
  - The mock's reset test is updated to D-70: **user forks survive** a demo reset.

## 6. Concurrency semantics (OQ-SWE-09)

- A character may be a participant in several **paused** sessions, but only one session streams at a time (doc 01 §4.3).
- Writes to a character's energy are serialised by a per-character `asyncio.Lock` and done inside the writer transaction (top-ups can race with a reply's drain).
- Memory ops are serialised per character by the post-turn queue and applied through `MemoryStore.apply` (doc 02 §3.7).
- Every write to a session's rows goes through that session's actor (doc 01 §4.2).

## 7. Contract rev 1.3 (additive)

`schemaVersion` stays `1`. Doc 05, `frontend/src/contract/{types,schemas}.ts`, the MockClient and the seed are all updated in M1a, under the `contract-rev-1-3` OpenSpec change. **Addendum for M1b:** `HorizonClient.admin.resetDemo()` (→ `POST /admin/reset-demo`), so "Reset demo data" works on the HttpClient too. **Shipped in M1b**; the Settings and World Select buttons call it on both clients. Also added in M1b: world names unique case-insensitively with shipped seed names reserved (`conflict`, `details.field: "name"`), and `SessionSnapshot`/`UsageSummary` in `schema.json`.

| # | Change |
|---|---|
| 1 | `ErrorCode` += `"not_found" \| "validation" \| "conflict"`; `HorizonErrorShape.details?: Record<string, unknown>` |
| 2 | ID prefixes += `kno_` (knowledge source), `kch_` (child chunk), `ksec_` (section), `cmd_` (command receipt) |
| 3 | `KnowledgeSource.type` is `"text" \| "file"` for **new** sources. `"url"` stays in the enum as **legacy/read-only** (no route creates it). `KnowledgeSource.status` += `"keyword_only"` |
| 4 | `CharactersApi` += `addKnowledge(id, input: { file: File } \| { type:"text"; title; text })`, `deleteKnowledge(sourceId)`, `reindexKnowledge(sourceId)` |
| 5 | `WorldsApi` += `uploadCover(id, file)` |
| 6 | `AppSettings.models` += `embedding: string`; `testModel` role += `"embedding"` |
| 7 | `UsageRecord.category` += `"embedding"` |
| 8 | Seed data, changed through `frontend/scripts/seed-build` and `pricing.config.ts`, then `seed:build`:<ul><li>D-61 image model and price;</li><li>Jev $0.042/M input, output $0;</li><li>an `embedding` pricing entry;</li><li>Amara's source `url → file`;</li><li>Mei's CSV source removed;</li><li>**globally unique candidate IDs**</li></ul> |
| 9 | `TurnTrace.calls?: { purpose, model, costUsd, latencyMs, fallback?: boolean }[]`: every paid call behind one turn (Jev, embeddings, reply) |
| 10 | `entity.changed` += optional `progress?: { stage, pct }` (knowledge ingestion). Global stream += `task.update` (job mirroring). `mock.reset` is also emitted by the backend after a demo reset |
| 11 | Doc 05 §6 is reconciled with `types.ts`: it gains `turn.start.message?`, `energy.spent?` and `error.messageId?`, which the code already has. It also documents that **a later `insight` for the same `messageId` replaces the earlier one** (the reducer already does this) |
| 12 | `AppSettings.energy.estReplyPoints: { off_peak, peak }` (read-only, from config), so the UI and backend read one energy threshold (doc 04 §4) |
| 13 | **MockClient parity:** the new error codes, the tombstone, seed-only reset (user forks survive), knowledge add/delete, cover upload and the top-up gate (D-76) |

**`chat.continue` (D-58 candidate) is deferred again.** "Continue" keeps meaning *regenerate* in the MVP. A real continuation needs prefix-completion support on the pinned DeepSeek endpoint, which the AI stage verifies.

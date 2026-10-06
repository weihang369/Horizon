# Design: generation-jobs (M4)

## Context

See proposal.md for the motivation. This section records what M4 builds on and what the code shows today.

- **From M1b:**
  - every table M4 writes already exists: `generation_jobs` (with the one-active-job partial unique index), `generation_tasks` (`provider_called_at`, `result_ref`, `idempotency_key UNIQUE`), `image_assets` (partial unique indexes per emotion slot, `selected`, `ord`), `theme_songs`, `idempotency_keys`;
  - the read routes `GET /jobs/{id}`, `GET /jobs?active=true`, the character reads with the derived `emotions`/`blink`/`candidates` (`contract/mappers.character_wire`);
  - `GET /assets/*` with traversal blocking and immutable `gen/`;
  - the startup sweeper (`runtime.sweep`) and the seed importer, which already loads `seed/_mock/jobs/*` in test mode and deactivates (never deletes) non-seed emotion versions on reset (M1b OQ-13).
- **From M2:**
  - `Gateway.paid()` and `generate_image()`; `ReservationBook.reserve_job/take_from_job/release_job` (a job-wide hold that preflight already draws from when `ctx.job_id` is set);
  - `call_ctx` with `creation`, the `image_*` purposes and the `profile`/`song` categories;
  - `FakeOpenRouter`, which routes `POST /v1/images` but is not yet exercised.
  - **Live finding (M2 design OQ-C):** `google/lyria-3-clip` returns 404 on OpenRouter. The image response shape was never verified by a paid call.
- **From M3:** the virtual-time clock (`vclock`, `Slots`, `rt.spawn`, settle), the AI profile/override mechanism, the `LiveSessionManager` (`actors`, `generating`), the purge outbox, and the scripted simulated-spend pattern (D-81).
- **The oracle is the MockClient.** `mock/engines/jobs.ts` defines the task plans, parallelism, the 250 ms tick, the 60 % failure point, the outcome rules, cancel/retry and what each task applies. `MockClient.ts` defines `createDraft`, `update`, `lockPortrait`, `approve`, `archive`/`restore`, the tombstone, `acceptAssetVersion` and `uploadCover`.
- **Two mismatches found while reading:**
  - The gateway's images client sends `images: [...]`, but the D-61 run (`docs/ai/image-model-test/run.mjs`, the only proven request) sends `input_references: [{type:"image_url", image_url:{url}}]` with `n: 1`, and reads `data[0].b64_json` and `usage.cost`.
  - `paid()` writes the ledger row in its own transaction, but doc 02 §3.5 requires the original on disk **before** `result_ref` and the ledger row, **committed together**.

## Goals / Non-Goals

**Goals:**
- All 13 M4 portable tests pass on the HttpClient against a test-mode backend, and keep passing on the MockClient.
- Jobs are deterministic under the frozen clock (scripted profile), so the tests are reproducible on Windows.
- **No path pays a provider twice** without a user Retry, including a crash at any point. This is proven with a provider-call counter across a restart.
- The wizard works end to end in `naive` mode against real OpenRouter, for less than $0.05 per manual live run.

**Non-Goals:**
- No contract changes (`schemaVersion` 1, `schema.json` unchanged), and no MockClient behaviour changes.
- No AI-stage policy: no Jev image-quality or emotion-validation gate, and no prompt tuning beyond the TESTING.md v2 fixes (doc 05 §6).
- No real music model (OQ-1), and no `autoGenerateMissingEmotions` behaviour (OQ-6).
- No knowledge or memory work beyond deleting a tombstoned character's rows (M5 owns ingestion and Forget).

## Decisions

### D1. Module layout

| Module | Role |
|---|---|
| `horizon/services/jobs/plans.py` | Pure: `plan(input, settings, prices, timing) → [TaskPlan{type, emotion?, est_usd, duration_ms, price_kind}]` and parallelism. A port of `planTasks`/`estimateJob` |
| `horizon/services/jobs/scheduler.py` | `JobScheduler`: start/cancel/retry entry points, the per-job runner, slot semaphores, events, recovery |
| `horizon/services/jobs/worker.py` | One task attempt: the fault check, `before_send`, the port call, `commit_with`, derive, apply |
| `horizon/services/jobs/apply.py` | What a succeeded task does to the character (profile, appearance, palette, brief, candidate, emotion version, song), in one writer transaction |
| `horizon/storage/atomic.py`, `storage/images.py` | Atomic file writes; Pillow decode/verify, 3:4 crop, 768×1024 WebP, 1600×900 cover, sheet slicing, size ladder |
| `horizon/services/assets.py` | Version numbering, `lockPortrait`, `acceptAssetVersion`, candidate rows, file paths and URLs |
| `horizon/services/characters.py` | `createDraft`, PATCH, approve, archive, restore, delete (tombstone) |
| `horizon/services/theme.py` | The `themeSpecFromBrief` port (procedural song) |
| `horizon/ai/image_prompt.py` | `ImagePromptCompiler` (real in both profiles) |
| `horizon/ai/scripted/creation.py`, `ai/naive/creation.py` | `ProfileDrafter`, `ImageGenerator`, `SongGenerator` implementations; the scripted drafter is a port of `mock/banks/drafts.ts` |
| `horizon/api/characters.py`, `api/jobs.py` | Routes, including `POST /worlds/{id}/cover` |

The Runtime gains `jobs` (the scheduler), `image_slots = Slots(2)`, `music_slots = Slots(1)` (the M3 `llm_slots` is shared, as doc 01 §4.4 and M3 D1 say) and a `job_faults` registry. Startup runs `jobs.recover()` as step 6, after `close_interrupted_streams` and before serving. `stop()` and factory reset stop the scheduler first (`_stop_m4`). The scheduler creates tasks only through `rt.spawn`, so the virtual clock settles over them, and the M3 static test that forbids `asyncio.create_task` extends to `services/jobs/`.

### D2. Job and task model

- **Plans are a port of `planTasks`.**
  - The `ord` follows the plan.
  - `idempotency_key = f"{job_id}:{ord}"` (doc 02).
  - The job `input` column stores the `StartJobInput`, so recovery and retry can rebuild the plan without the caller.
  - Parallelism comes from `seed/runtime.json` timing (`portraitParallel`, `emotionParallel`; 1 for the others).
- **The scheduler runs one runner coroutine per non-terminal job.**
  1. It starts up to `parallel` queued tasks in `ord` order.
  2. Each task holds the slot of its provider kind (`image_slots`, `music_slots` or `llm_slots`) only around the provider call, never while it paces.
  3. An expression sheet runs alone, and its emotion tasks are filled from the sheet (`skipped` if the sheet fails), as the mock does.
- **Progress.**
  - Each running task advances on `clock.sleep(jobTickMs)` ticks: `elapsed / expected_ms`, capped at 0.95 until the task ends.
  - `expected_ms` comes from the timing table for scripted ports, and from a small latency table for naive ports (profile 4 s, base 17 s, edit 8 s, the D-61 run's numbers).
  - `job.progress` = the mean task progress, rounded to 3 decimals.
  - The runner publishes `job.progress` every tick while anything runs, and `task.update` on each status change.
  - Progress is persisted with each published event; that's one small UPDATE per tick, which is fine for one user.
- **`previewUrl`** is set when a task's WebP exists, so it equals the final URL. The mock's 50 % shadow preview has no backend equivalent, since a real provider returns nothing until it finishes. No portable test reads it (OQ-4).
- **Outcome** is ported from the mock's `tick` end block. `actualCostUsd` = `SUM(usage_records.cost_usd WHERE job_id)`, read when the job ends and after each task.

### D3. Never pay twice (the ordering)

The pipeline gains two optional hooks on `paid()` and `generate_image()`:
- `before_send: Callable[[], Awaitable[None]]`, run after preflight has reserved and before `send()`;
- `commit_with: Callable[[AsyncConnection, row_id], Awaitable[None]]`, run inside the ledger's write transaction.
- `after_response: Callable[[T], Awaitable[None]]`, run after `send()` returns and before the row is recorded (the job writes the original here).

`LedgerPort.record` gains the matching optional `extra` callback. A worker attempt runs:

| Step | Durable effect | Crash after this step → on restart |
|---|---|---|
| 1. preflight (caps, takes the task's share of the job hold) | none | task still `running`, `provider_called_at` NULL → **requeue** |
| 2. `before_send`: commit `provider_called_at = now`, `attempt += 1`, `target_path` | task marked as sent | sent, no result → **failed (retryable)** |
| 3. provider call (the scripted source sleeps here instead) | provider charges | same as 2 |
| 4. `send()` returns bytes. `after_response` writes the original atomically to `originals/{w}/{c}/{task}.{ext}` | original on disk | same as 2. The original is kept for audit; the sweeper never deletes originals |
| 5. record: ledger row **plus** `commit_with` sets `result_ref = original rel path`, `cost_usd` | paid result recorded | result present → **derive only** |
| 6. derive the WebP (`to_thread`), then `apply` in one transaction (asset row with `rel_path`, character change, task `succeeded`) | done | — |

- **When the post-response step fails** (disk full, decode error), `paid()` still records the row (the provider charged), without `commit_with`, then raises. The task fails as `provider_error`, retryable, and the user decides whether to pay again.
- **When the provider errors after sending** (`maybe_charged`), M2 already records an estimate row. The task fails retryable.
- **The fault scenarios** fail a task at 60 % of its paced duration, **before** step 1, so a scripted failure costs nothing, matching the mock (which charges only successes).
- **Alternative rejected:** have the job write its own ledger row outside the gateway. That would bypass caps, warnings and the `on_call` hook, and break the "single network boundary" spec.

### D4. Restart recovery

`jobs.recover()` runs at startup step 6:
1. For every job `queued`/`running`, per task:
   - `queued`, or `running` without `provider_called_at` → `queued` (the attempt is not counted);
   - `result_ref` set but not `succeeded` → derive and apply only (no provider);
   - `provider_called_at` set without `result_ref` → `failed { provider_error, retryable: true, message: "Interrupted after the request was sent; Retry to pay again." }`.
2. Then reserve the job's remaining estimate again (the book is empty after a restart). This is not a cap check: an over-cap recovered task is refused at its own preflight and fails retryably with the cap code.
3. Then start the runner.

Test-mode overlay jobs (`job_mockKenjiEmotions`, `is_seed`) take the same path, which mirrors `MockClient.resumeJobs` (OQ-13).

**The kill test (acceptance).** An in-process "kill" must not run shutdown code, so the test:
1. starts a naive-image job against the counting fake provider, which **parks** the second image request on an `asyncio.Event`;
2. takes a **SQLite online backup** of `horizon.db` and copies `data/` (originals, assets) at that moment, which is exactly what a power cut would leave;
3. starts a fresh Runtime on the copy;
4. asserts:
   - the fake's images counter does not grow during recovery or after any `advance`;
   - the first candidate is `ready`;
   - the parked one is `failed` and retryable;
   - the ledger has one row per paid call.

A second case covers "crash after step 5": the result is present, so only the WebP is derived and no call is made. A third covers "never sent": the task runs once. An optional subprocess smoke test (`taskkill /F` on Windows) is out of scope; the backup snapshot is deterministic and equivalent (OQ-8).

### D5. Reservations and caps

- **`Gateway.reserve_job(ctx, estimate) → None | raises`** is new. Under `book.lock` it runs the same daily and creation checks as `_preflight` against `estimate` (with `reserved` including other jobs' holds), publishes `budget.reached` on refusal, and otherwise calls `book.reserve_job`. `jobs.start` and `retryTask` call it **before** inserting rows. The insert happens in the same request, after the hold exists. If the insert fails (the 409 unique race), the hold is released.
- **Per task**, preflight already moves `min(remaining, estimate)` out of the job hold into a call hold (M2 `take_from_job`). Settling releases the call hold, and the actual cost lands in the ledger. When the actual is not the estimate:
  - the job hold is not adjusted (its remaining share is still the other tasks' estimates);
  - the overrun bound stays Σ(actual − estimate) of calls in flight, as in M2.
- **At the job's end** (any terminal status), `release_job`.
- **Retry** adds the retried task's estimate to the job hold through `reserve_job` (it is a fresh check), so a retry is refused at the cap, never sent.
- **Creation scope.** `ctx.creation = character.status != "approved"`, read at each task, so approving mid-job stops counting later tasks.

### D6. Cancel and delete

- **`cancel(jobId)`** sets the runner's cancel flag and returns the job state at once (no key, as the mock does).
  - Queued tasks, and tasks paused before step 2, become `skipped`.
  - **A task past step 2 is not cancelled.** Its provider call is shielded (as M2 shields recording), so it finishes, the original is stored and the ledger row is written at the **real** cost. The task then becomes `skipped` with its result kept but not applied to the character.
  - The mock charges a running image at its estimate. The backend charges what the provider billed, which is NFR-30's "no hidden spend" in the stricter direction (OQ-5).
- **`characters.delete(id)`:**
  1. `409 conflict` with `details.activeSessionId` if `LiveSessionManager.generating_with(id)` (a new helper: any actor that is generating and has the character as a participant).
  2. Cancel the job, and wait (bounded, 5 s of real time) for the runner to stop or reach a shielded call.
  3. One writer transaction:
     - tombstone the row (the mock's `tombstone()` port: minimal profile, palette, no `profileMeta`, no song, no job, `deletedAt`);
     - delete the image rows except the active neutral row;
     - delete theme songs, jobs (tasks cascade), memory rows and knowledge rows (FTS triggers fire, M1b);
     - insert `ai_purge_queue {scope: "character", ids:[id]}`.
  4. After the commit, delete files: `assets/gen/{w}/{c}/*` except the neutral file, `originals/{w}/{c}/`, `knowledge/{w}/{c}/`.
  5. Publish `entity.changed character`.
- A shielded call that lands after the delete records its ledger row (spend is never lost), but `apply` sees a tombstone and stores nothing.
- **Sessions.** M3 already skips a `deleted_at` speaker (`TurnOutcome "missing"`). Task 6.6 checks that each mode maps it to `skipped` with reason `"archived"`, and fixes any mode that doesn't.

### D7. Image and file pipeline

- **Atomic write:** `*.tmp` in the same folder → `fsync` → `os.replace`. Windows-safe with a short retry on `PermissionError`.
- **Derive:**
  1. `ImageOps.exif_transpose`, then RGB;
  2. centre-crop to 3:4 (Seedream 1K 3:4 gives 832×1110, so the crop is 1–2 px);
  3. Lanczos to 768×1024;
  4. WebP `quality=85, method=6`. If it is over 250 KB, step down through 80/75/70/65; if it is still too big, fail `provider_error`, which never happens with real portraits (about 100 KB).
- **Covers:** the same, centre-cropped to 16:9 at 1600×900.
- **Upload limits:** Pillow `verify()`, magic bytes PNG `89 50 4E 47`, JPEG `FF D8 FF`, WebP `RIFF....WEBP`, and a 40 MP decompression guard.
- **Names (immutable)** under `assets/gen/{worldId}/`:
  - `{characterId}/candidate_{assetId}.webp`;
  - `{characterId}/portrait_{emotion}[_blink]_v{n}.webp`;
  - `cover_v{n}.webp`;
  - `{characterId}/song_v{n}.proc.json`.

  `n` is `MAX(version)+1` for that slot.
- **Expression sheet:** a 2×4 grid. Each cell is cropped evenly (gutters ignored), cropped to 3:4 and upscaled to 768×1024. One ledger row (one image), as in the mock. Quality is the D-61 caveat ("passes only if the cells line up"); the wizard already labels it Variant C (OQ-3).
- **Sweeper:** M1b's rules. The referenced set gains the `theme_songs` `.proc.json` paths (already in the union) and all image versions. Originals are never swept.

### D8. Assets: candidates, lock, versions, accept

- **Candidates.** At job start, one `image_assets` row per candidate task is inserted (`kind: "candidate"`, `status: "generating"`, `rel_path` NULL, `job_id`, `ord`), so `characters.get` shows them at once. The ID is `cand_` + the task ID suffix, mirroring the mock's `task_ → cand_`.
- **Derivation** (changes doc 02 §3.2, D-85). Candidates are the rows of the latest `portrait_candidates` batch, plus every later `portrait_tweak` batch, plus earlier rows with `selected = 1`; or the seed batch (`job_id IS NULL`) when there is no job. This reproduces the mock's list (selected + new; tweak appends) without mutating old rows. The mapper needs each batch's job kind: one extra join in the character read.
- **`lockPortrait`:**
  1. clear `selected` on the character's candidates, then set it on the chosen one;
  2. insert the next neutral version pointing at the candidate's own WebP (no copy: the portable lock test needs
     `emotions.neutral.url` to equal the candidate's URL; the file is immutable either way), active, after deactivating
     the old active neutral (the M1b "deactivate, then activate" order for the partial unique index);
  3. move `creationStep` to `emotions` (mock rule).

  A seed candidate (an SVG placeholder) is locked by URL: the row keeps the placeholder `rel_path`, and `format` is omitted (doc 02 §2).
- **New emotion version:** active when the character isn't approved or the slot has no active row; otherwise inactive (mock `replaceLater`). `acceptAssetVersion` deactivates, then activates, in one transaction, and bumps `version` on an approved character.
- **Seed rows** keep `version 1`. Generated versions start at `MAX+1`, so they never collide with a seed row under `ux_image_assets_emotion_version`. Reset deactivates the non-seed versions of seed characters (M1b OQ-13) and now first cancels their non-terminal user jobs (demo-data delta).

### D9. Ports and profiles

- **`AiPorts`** gains `drafter`, `image` and `song`. `NAIVE_PORTS` becomes `{turn, router, drafter, image}`. The env names are `HORIZON_AI_DRAFTER` and `HORIZON_AI_IMAGE`. The port is called `drafter`, not `profile`: `HORIZON_AI_PROFILE` is the selector itself, so that name would collide. `ImagePromptCompiler` is not selectable; it is one class.
- **Scripted drafter.** It ports `draftFromSeed`/`regenerateField` (88 lines, deterministic) byte for byte. Shared fixtures (`backend/tests/fixtures/drafts/*.json`) are written by the existing `scripts/fork-fixtures/build.ts` (renamed in spirit to "shared fixtures"), and both languages assert them.
  - Billing follows the mock: four `profile` tasks, each a `simulated_call` at `profileDraft/4`.
- **Naive drafter.**
  - One DeepSeek `chat_complete` in JSON mode (`response_format: {type: "json_object"}`), with a JSON schema in the system prompt built from the contract's `CharacterProfile` + `AppearanceAttributes` + `paletteId` enum + `SongBrief`, restating every contract limit (a unit test keeps them in step).
  - The call uses `purpose: "profile"`, `creation: True`, `reasoning: {enabled: false}`, pinned routing (M2), and a 2,400 max-token budget (one field: 1,200).
  - *Amended after the live run (D13).* The first plan was strict `json_schema` with 1,200 tokens. Live, a whole draft measured 1,229 tokens, so every draft was cut off mid-JSON; and DeepSeek's own endpoint has no structured outputs, so under `require_parameters` the pinned provider was always skipped (45–99 s on a fallback, against 7–8 s on DeepSeek). The schema also lacked the contract's `vibe` ≤ 2, `tagline` ≤ 80 and non-empty `name`/`role`.
  - Its result is validated with the contract validator, and `age < 18` is a failure.
  - It runs in the first task. The other three tasks apply parts of the same result, at $0 and with no provider call. Their estimates are still `profileDraft/4` each, so the job's estimate stays mock-equal; the release at job end returns the unused hold.
  - `regenerate_field` uses one smaller call for one field.
- **Image generators.**
  - **Scripted** draws a deterministic 832×1110 PNG with Pillow: palette background, a silhouette, and the emotion name, seeded by the task ID. It returns it through `simulated_call(category="image", cost=price_kind)` after sleeping the paced duration. It goes through the same D3 and D7 path.
  - **Naive** calls `generate_image(model=settings.models.image, aspect_ratio="3:4", resolution="1K", n=1)`.
    - The emotion, blink and tweak edits send the **locked neutral original** (the JPEG in `originals/`, else the WebP) as one data-URL reference.
    - If the locked base is a seed SVG placeholder, `jobs.start` for an edit kind rejects with `validation` and `details.reason: "base_not_raster"`, since an SVG can't be sent to Seedream (OQ-2). The scripted generator accepts any base.
- **`ImagePromptCompiler`:**
  - **base:** the TESTING.md A1 template with the style preset's `promptFragment` and the adult clause, then the appearance (the summary, plus attributes rendered in rule-2 order), and the v2 fixes:
    - `baseline` soft/sharp expression;
    - the compound hair colour with the base colour first;
  - **emotion edit:** the A2 instruction with the v2 table (thinking reworded, no flush on angry);
  - **tweak:** the A2 frame with the tweak text;
  - **sheet:** A3.
  - Age < 18 → an empty prompt plus `REFUSED`, which fails the task without a call. Golden fixtures are in `backend/tests/fixtures/image_prompt/`; they are Python-only, because the frontend has no compiler.
- **Song (D-83).** One implementation in both profiles while OpenRouter lists no music model. It ports `themeSpecFromBrief` (pinned by `fixtures/theme_spec/` from the TS function), writes `song_v{n}.proc.json` and inserts a `theme_songs` row:
  - `status: ready`, `format` omitted;
  - `durationSec` from the mock's formula;
  - `generation.model: "procedural"`, `costUsd: 0`;
  - the license note says so.

  There is no ledger row, and the estimate is $0.
  - The music provider is checked with `meta.model_exists(settings.models.music)` **once per job start**, and the result is logged. A real music client is left for later; when it lands, it plugs in behind `SongGenerator` and the estimate uses `pricing.generation.song`.
  - The mock keeps billing $0.04 for its sketch, so the cost confirmation differs between clients for songs only (OQ-9).

### D10. Character services and routes

- **`createDraft`** runs the key check, then the world check, then `reserve_job` for the profile draft. It inserts the character (the mock's draft defaults: first-capitalised-word name, the `pal_` default, the default style preset, full energy), the job and its tasks in **one** transaction, then starts the runner. It returns `{character, job}` with 201.
- **PATCH** runs in one writer transaction: read the row, deep-merge `profile`/`appearance` (lists replaced), set the other `CharacterPatch` fields (allow-listed by the contract schema), bump `version` when approved, write. Workers apply their results the same way, in their own transaction, so SQLite's single writer serialises the two and neither loses the other's fields (doc 01 §3).
- **Lifecycle routes** port the mock exactly. A tombstone is `not_found` for every command (one `live_character(conn, id)` helper). Approval needs `name`, `role`, `age ≥ 18` and an active neutral row.
- **Cover upload** (`POST /worlds/{id}/cover`):
  1. Reject on `Content-Length` > 5 MB + 64 KB envelope (413).
  2. Stream the `file` part to a temp file, counting bytes (413 past 5 MB), using Starlette's request stream with a counted `python-multipart` parser instead of `UploadFile`'s full spool.
  3. Check magic bytes, verify, re-encode (D7), atomically write `cover_v{n}.webp`.
  4. In one transaction: insert an `image_assets` `cover` row, set `worlds.cover = {kind:"upload", url}`, publish `entity.changed world`.

  No key is needed.

### D11. Frontend

- **`Transport.postForm(path, form)`** sends the `Idempotency-Key`, lets the browser set the multipart boundary, and maps errors like the others. The HttpClient implements every `later("M4")` method. `clientContract.http.test.ts` declares `supports: "M4"`, and `Milestone` pending becomes `M5|M6`.
- **`WorldEditor.tsx`:**
  - keeps the picked `File` and previews it with `URL.createObjectURL`;
  - checks the type (PNG/JPEG/WebP) and 5 MB (the old 2.5 MB guard goes);
  - after a successful `create`/`update` with the previous or preset cover, calls `worlds.uploadCover(id, file)`. An upload error stays in the editor (the world is saved, the cover isn't), with the error text.
- The MockClient's `uploadCover` already returns a data URL, so the mock path keeps working and no data URL is sent to `create`/`update` any more.
- A unit test covers the editor flow with a fake client.

### D12. Test routes and scenarios

- `SCENARIOS` gains `image_fail_partial`, `image_fail_all` and `song_fails`, which set `rt.job_faults` (`"partial" | "all" | "song"`). The rules are the mock's:
  - **partial:** the second image task of a job, first attempt only;
  - **all:** every image task, every attempt;
  - **song:** theme-song tasks.
- A fault applies to jobs **started** after it is set, persists until factory reset, and is applied at 60 % of the paced duration before step 1 (D3).
- `SCENARIO_MILESTONE` moves those three to the registry.
- `/_test/ai-profile` accepts the new port names in `overrides`.

### D13. Live test (manual, ≤ $0.05)

`tests/live/test_live_jobs.py` (marker `live`, key presence checked, never printed):
1. `createDraft` (naive drafter, ~$0.001);
2. one Lean `portrait_candidates` (Seedream base, $0.018);
3. lock it;
4. one `emotion_regenerate` for `happy` ($0.018).

It asserts:
- the response shape (`data[0].b64_json`, `usage.cost`), recording any difference in this design;
- a WebP ≤ 250 KB;
- `actualCostUsd` equal to the ledger sum;
- a total under $0.05.

The song check is free (`model_exists` only). A paid music call needs a separate approval (OQ-1).

**Live run, 2026-10-06 (user-approved; $0.0062 of diagnosis plus $0.0379 for the passing run, $0.044 in all).** The first run failed at the draft (see D9: the 1,200-token cut-off and the routing). After the fix it passed in 35 s:
- draft on DeepSeek, contract-valid, $0.001873;
- Seedream base portrait 67 KB and `happy` edit 70 KB, both 768×1024 WebP, $0.018 each with `cost_source: provider`, so the image response shape matched;
- each job's `actualCostUsd` equalled its ledger rows; total $0.037873.

`model_exists("google/lyria-3-clip")` is false, but OpenRouter now lists `google/lyria-3-clip-preview` and `google/lyria-3-pro-preview`. D-83's premise ("OpenRouter lists no music model") no longer holds; wiring a real music model is a separate decision (OQ-1).

### D14. Tooling

- `pyproject.toml` adds `pillow` (with WebP; wheels exist for Windows). mypy strict extends to `horizon.services.jobs.*`, `horizon.services.{assets,characters,theme}` and `horizon.storage.*`.
- The leak sweep adds job rows, task errors and the uploaded-cover route. No key may appear in `generation_tasks.error` or `input`.
- `npm run fixtures:build`/`check` gains the `drafts` and `theme_spec` fixture sets.

## Risks / Trade-offs

- [A Seedream response that differs from `run.mjs` (field names, a URL instead of base64)] → the client accepts `b64_json` and data URLs (already), and the live run (D13) checks the shape before the wizard is declared done. A mismatch is a one-function fix plus a fixture update.
- [Pillow WebP output is over 250 KB for a busy image] → the quality ladder (85 → 65), and a test with a noisy 1024×1024 image asserts ≤ 250 KB.
- [The parked-request kill test misses a real-crash ordering] → the step table (D3) is tested at every boundary with injected failures. The backup snapshot captures committed state exactly, as a crash would.
- [A long naive image call holds a slot while the user cancels] → the shielded call completes at real cost and its result is not applied. The UI already warns that "images in progress may still be charged".
- [The job tick floods the global stream] → 4 events/s per running job, well under the 1,000-event per-subscriber queue. Persisting on each tick is one UPDATE.
- [Scripted spend (D-81) on Kenji's overlay job in every test-mode reset changes test totals] → the mock does the same. Tests that assert exact spend set their own caps or run without the overlay; this is checked in task 8.4.
- [Delete races a worker writing a new asset for the same character] → `apply` re-reads the row inside its transaction and stores nothing for a tombstone. File deletion happens after the commit, so a late WebP is swept as unreferenced after an hour.
- [Scope: ~70 tasks] → vertical slices, each ending green (OQ-12).

## Migration Plan

- **No database migration.** Pillow is a new dependency (`uv sync`). The shared fixture folders are new.
- **Doc updates in this change:**
  - doc 02 §3.2 (the candidate derivation);
  - doc 04 §1 (the image request shape, music status);
  - doc 05 §2.2 (`SongGenerator` = procedural until a music model exists; the `drafter` port name);
  - doc 06 M4 (the song acceptance reads "procedural theme");
  - the decision log D-83 (procedural songs), D-84 (pipeline hooks for never-pay-twice), D-85 (candidate derivation) and D-86 (cancel lets a sent call finish at real cost).
- **Rollback:** revert the squash commit. Jobs and assets written under M4 stay readable by M3 code, which has the read routes. Their files stay on disk and are swept only if unreferenced.

## Open Questions

Recommended defaults are recorded here; confirm or override them before apply. The tasks implement the defaults.

**Resolved on 2026-10-06 (stakeholder):** OQ-1/OQ-9 → Lyria 3 Clip in naive, procedural in scripted and as the fallback (D-87); OQ-7 → no automated image gate, users judge by eye (D-88); OQ-6 → hide the setting until specified (D-89); OQ-2 → keep the refusal, show "Generate a portrait first" in the UI (D-90). These four are built in a follow-up change. OQ-3, OQ-4, OQ-5, OQ-8, OQ-10, OQ-11, OQ-12 and OQ-13 are closed as implemented.

| # | Question | Default (implemented) | Why |
|---|---|---|---|
| OQ-1 | **Theme songs without Lyria** (404 on OpenRouter) | **The procedural theme in both profiles, $0, no ledger row** (D9, D-83). `model_exists` is logged. A paid music call is never made in M4. | OpenRouter-only constraint. The app already renders `.proc.json`, and R-05 names this fallback. |
| OQ-2 | Naive emotion edits on a seed character (SVG base) | **`validation` with `details.reason: "base_not_raster"`** at `jobs.start`. Scripted is unaffected. | Seedream needs a raster reference. Rasterising SVG would add a native dependency (cairo). |
| OQ-3 | Expression sheet under `naive` | **Supported:** one 2×4 sheet, sliced evenly | One image instead of 3–7. D-61 already flags its alignment risk, and the wizard offers it as Variant C. |
| OQ-4 | `previewUrl` timing | **Set when the task's WebP exists** (the final URL) | Real providers return nothing earlier; no portable test reads it. |
| OQ-5 | Cancel during a sent call | **Let it finish, record the real cost, keep but don't apply the result** (D6, D-86) | Never lose spend (NFR-30). The mock's estimate charge is the looser version of the same rule. |
| OQ-6 | `autoGenerateMissingEmotions` | **Deferred.** The setting is stored and shown, with no behaviour. | The mock has none either, and its trigger ("missing" when? which mode?) is undefined. It pre-authorises spend, so it needs its own spec. |
| OQ-7 | Jev gates for images (candidate quality, emotion validation) | **None in M4** | Doc 05 §6 lists emotion validation as AI-stage policy. A Decider hook point is left in `worker.apply`. |
| OQ-8 | How "kill mid-job" is simulated | **SQLite online backup + data copy while the provider request is parked**, then a fresh Runtime on the copy | Deterministic on Windows and exact to committed state. A subprocess kill adds flakiness, not coverage. |
| OQ-9 | Song cost display | **$0 on the backend.** The mock keeps $0.04. | It's honest about the real cost. Only the cost confirmation for songs differs. |
| OQ-10 | Live run budget | **About $0.037:** draft + one base + one edit | ≤ $0.05 rule. Blink and sheet are covered by the fake. |
| OQ-11 | Profile PATCH merge | **Deep merge, lists replaced** (doc 03 wording) | The mock's shallow profile merge only differs for nested partial patches, which the UI never sends. Deep is the safe superset. |
| OQ-12 | One change or a split | **One change, vertical slices:** gateway/storage → scheduler (scripted) → kinds → recovery → lifecycle → cover + UI → HttpClient/portable → naive + live. Split only past ~85 tasks. | The slices share the scheduler and the asset service. |
| OQ-13 | Test-mode overlay job (Kenji) | **Resumed by recovery**, like the mock's `resumeJobs` | Parity: the profile `JobPill` in E2E expects it to finish. |

## Implementation notes (apply)

Recorded while implementing; each keeps the specified behaviour and resolves a detail the plan didn't settle.

- **Contract-valid drafts.** The contract requires a non-empty `name` and `role` and at least three
  `personality.traits`, and the backend validates every response. A new draft therefore starts with placeholders (the
  seed's first capitalised word or "New character", role "Drafting…", three neutral traits) until `profile_draft`
  fills them in about 4 s. The approve gate treats the placeholder role as missing. The mock's empty fields are unchanged.
- **Candidates without a file** carry a blank 1×1 data URL (the contract requires `url`); the wizard renders it as nothing.
- **Recovered jobs start on their first tick**, not at startup, and wait for virtual time again if the clock was frozen
  meanwhile. Startup never races a request, so the HTTP portable run is deterministic with the overlay job present.
- **Shutdown vs cancel.** A user cancel lets a sent call finish at its real cost (D-86). Stopping the scheduler (shutdown,
  factory reset, the overlay job during a demo reset) cancels sent calls too; the gateway records them at their estimate
  (shielded) and recovery marks them failed and retryable.
- **Deleting during a sent call.** The late answer is billed (the ledger stores a dangling job or character reference
  as NULL), but its original is not written for a deleted character.
- **Provider slots** are held only by naive calls (images: `image_slots`, the drafter: `llm_slots`). Scripted calls pace
  on the clock and hold none, so the overlay job never delays a user's job.
- **The procedural song** is paced like the mock's song (`songMs`) only in the scripted profile; in naive it is immediate.
- **`budget.reached` for a refused job** is published but doesn't pause live sessions: a whole job not fitting doesn't
  mean a small reply can't.
- **Demo reset** also removes user candidate batches of seed characters, so the shipped candidates show again; a locked
  one survives as an inactive neutral version.
- **Group sessions** skip a deleted participant with reason `archived`, even when @-mentioned (task 6.6).
- **The portable cover test** uploads a real 16×9 PNG: the backend decodes and re-encodes uploads, so a file that is only
  magic bytes plus zeros is (correctly) rejected there.
- **The World editor's save flow** lives in `worldSave.ts` and is tested with a fake client in the node test
  environment; the repo has no DOM test setup, and adding one was out of scope.
- **Progress ticks publish `job.progress` only.** It carries the whole job; `entity.changed` (kind `job`) is published
  when a job starts, changes state or finishes, not on every 250 ms tick (that made a client refetch 4×/s).
- **A late fetch never overwrites newer data** (frontend `stores/entities.ts`, found by the 10.2 browser check). A job
  GET that started before `job.done` could land after it and leave the wizard on "Developing…". A fetch that started
  before an invalidation or a write is no longer reused, and its answer is dropped (a first load still "loading" is
  fetched again). The MockClient never hit this: its calls resolve in the same tick.
- **Factory reset vs a shielded write.** A stop that cancels an attempt while it is marking itself sent let that
  shielded write run on after the database was disposed, which reopened `horizon.db` and failed the wipe on Windows
  (about one `test:http` run in five, cascading). Such writes now go through `JobScheduler.shielded` (tracked, spawned
  with `rt.spawn`), and `stop()` waits for them. The wipe's lock back-off also grows to about 11 s, since a virus
  scan can hold the file briefly after a burst of writes.
- **Factory reset vs a late cost correction.** `_stop_m2` stopped the cost corrector before draining the gateway's
  shielded ledger writes, so a late estimate row could enqueue a correction into the stopped corrector. That untracked
  task read the disposed engine, reopened `horizon.db` and kept retrying, so every later reset in the run failed. Now
  the drain runs first, `enqueue` after `stop()` does nothing (the next startup `scan()` picks the row up), and a
  disposed `Database` raises on `read()`/`write()` instead of reopening the file.
- **Preflight read order (an M2 race found here).** `_preflight` and `reserve_job` read today's spend, then the
  reservation total. Holds are released outside the lock, so a call could commit and release during the spend read
  (whose snapshot predates the commit) and be counted nowhere: one call over the cap, about one run in thirty of the
  overrun test. Reservations are now read first; since a hold is released only after its row commits, the race can
  only count a call twice.
- **Factory reset vs a request in flight (an M1b bug found here).** `Gate.closed()` let one gated request stay in
  flight, assuming the reset's own request was counted, but the middleware never gates `/admin/factory-reset`. So the
  reset could stop the runtime and dispose the database under a request still writing (caught by tracing pool
  checkouts: the idempotency middleware's write). `engine.dispose()` cannot close a checked-out connection, so it went
  back to the detached pool and held `horizon.db` open: every later reset in the run failed (WinError 32). The gate
  now waits for every gated request, and `Database.dispose` gives a read or write already under way up to 5 s to
  return its connection (with a warning if one does not).

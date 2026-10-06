# Proposal: generation-jobs (M4)

## Why

After M3, sessions are live on the local backend, but no character can be created there. `characters.createDraft`, `update`, `lockPortrait`, `approve`, `archive`, `restore`, `delete`, `acceptAssetVersion`, `jobs.estimate/start/cancel/retryTask` and `worlds.uploadCover` all reject with `later("M4")`, and 13 portable contract tests are pending. M4 is the milestone that makes the creation wizard work against the backend:
- a resumable job system that **never pays a provider twice**;
- the image pipeline (Seedream 5.0 Flash, D-61) with originals and small WebP derivatives;
- the character lifecycle (draft → approved → archived → tombstone);
- the `HttpClient` methods for all of it.

The design pack locks the shape (doc 01 §4.4, doc 02 §2–3.5 and §4, doc 03 Characters/Jobs, doc 04 §3, doc 05 §2.2, doc 06 M4). The MockClient (`mock/engines/jobs.ts` and the character methods of `MockClient.ts`) is the behavioural oracle.

## What Changes

- **JobScheduler and workers.**
  - Jobs and tasks live in the existing `generation_jobs`/`generation_tasks` tables.
  - Workers run under provider semaphores (image 2, music 1, LLM shared with sessions).
  - One non-terminal job per character (`activeJobId`); a second start is 409.
  - `estimate`, `start` (reserves the whole remaining estimate, and refuses with 402/409/`missing_key` **before anything is queued**), cooperative `cancel` and `retryTask` (max 3 attempts; the only path that pays again).
  - Progress is paced on the backend clock, so the virtual-time test clock drives jobs like it drives sessions.
- **Never pay twice (NFR-19, NFR-30).**
  - `provider_called_at` is committed after the cap preflight and before the provider call.
  - The provider's original is written atomically **before** `result_ref` and the ledger row commit together.
  - The derived WebP is made last.
  - Restart recovery: a task that was never sent is requeued; a task with a result only finishes its derived output; a task that was sent with no result becomes `failed` (retryable).
  - Asserted by a restart test that counts provider calls over the same data directory.
- **Job kinds behind AI ports.**
  - `profile_draft` (from `createDraft`), `profile_regenerate`, `portrait_candidates`, `portrait_tweak`, `emotion_set` (per-emotion edits or one expression sheet, with the blink frame in Standard mode), `emotion_regenerate` and `song`.
  - New ports: `ProfileDrafter`, `ImagePromptCompiler` (the real compiler in both profiles: the TESTING.md template plus the v2 fixes), `ImageGenerator` and `SongGenerator`.
  - Scripted versions are deterministic and bill simulated spend (D-81).
  - Naive versions:
    - DeepSeek structured output for the profile;
    - **Seedream 5.0 Flash** for portraits, tweaks and emotion edits of the locked base;
    - the theme song (see below).
- **Theme songs without Lyria.** M2's live run found `google/lyria-3-clip` is not on OpenRouter (404). The `song` job therefore produces the free procedural theme (R-05, D-52), which the frontend already plays. It is a `.proc.json` spec built from the character's brief, with the same function as the MockClient, pinned by shared fixtures. A real music model plugs in behind `SongGenerator` once OpenRouter lists one.
- **Image and asset pipeline.**
  - Provider bytes go to `originals/` first. Pillow then makes 768×1024 WebP (≤ 250 KB) under `assets/gen/`.
  - Atomic writes, immutable names and versioned emotion assets.
  - `acceptAssetVersion` (deactivate, then activate, in one transaction) and `lockPortrait` (candidate → `portrait_neutral_v1`, active).
  - Candidates appear as `generating` the moment their job starts.
- **Gateway fixes and additions.**
  - The images request uses OpenRouter's `input_references: [{type:"image_url", …}]` (the shape the D-61 test run proved), not the unverified `images` field.
  - `paid()` gains a `before_send` hook (commit `provider_called_at`), an `after_response` hook (write the original) and a `commit_with` hook (write `result_ref` in the ledger transaction).
  - A scripted image/song source runs through the same pipeline.
  - A job-start reservation check that refuses before queueing.
- **Character lifecycle.**
  - `createDraft` → `{ character, job }`.
  - `PATCH` with a deep merge in one writer transaction (no lost updates against a worker), with a version bump on approved characters.
  - The approve gate: profile valid, age ≥ 18, base portrait locked.
  - Archive and restore.
  - **Delete → tombstone:** 409 while the character is speaking in the live session. Otherwise it cancels the character's job, removes the other assets, files, songs, memory, knowledge and jobs, and queues an AI purge.
- **World cover upload.** Multipart, magic-byte check, counted ≤ 5 MB, PNG/JPEG/WebP only, re-encoded to a 1600×900 WebP (`cover_v{n}.webp`). The World editor UI calls it (OQ-3); it stops inlining data URLs into `World.cover`.
- **Test harness.**
  - The scenarios `image_fail_partial`, `image_fail_all` and `song_fails` are registered.
  - Test-mode overlay jobs (Kenji's running emotion set) resume like recovered jobs.
- **HttpClient.**
  - Every `later("M4")` method is implemented, including the multipart `uploadCover`.
  - The HTTP portable suite moves to `supports: "M4"`.

There are no **BREAKING** changes. The contract stays additive (`schemaVersion` 1), `schema.json` is unchanged, and the MockClient's behaviour is unchanged. One pure function (`themeSpecFromBrief`) and the draft bank stay where they are and gain shared fixtures.

## Capabilities

### New Capabilities
- `generation-jobs`: the JobScheduler, which covers:
  - the job and task state machine;
  - per-kind task plans and progress;
  - estimate/start/cancel/retry;
  - the one-active-job rule;
  - the never-pay-twice ordering and restart recovery;
  - job events on the global stream;
  - the job fault scenarios.
- `generated-assets`: generated files and asset versions. It covers:
  - originals first, then WebP derivatives, written atomically;
  - size and format limits;
  - candidate batches and how candidates are derived;
  - emotion asset versions and `acceptAssetVersion`, and `lockPortrait`;
  - the procedural theme song;
  - sweeping orphans.

### Modified Capabilities
- `character-lifecycle`:
  - adds draft creation, profile/appearance editing, the approve gate, and archive/restore;
  - the delete requirement gains the job cancel and the AI purge.
- `worlds`: cover upload checks magic bytes, counts bytes, and re-encodes to a 1600×900 WebP; the World editor uses it.
- `ai-ports`: the profile selection gains naive `drafter` and `image` ports; adds the creation ports (`ProfileDrafter`, `ImagePromptCompiler`, `ImageGenerator`, `SongGenerator`).
- `provider-gateway`:
  - the image request shape;
  - the pipeline's `before_send`/`commit_with` hooks;
  - scripted image and song spend;
  - test mode fakes the images endpoint.
- `budget-caps`: a job is refused before queueing when its whole estimate doesn't fit; estimates cover profile and music.
- `event-streams`:
  - character create/edit/lifecycle changes and job changes are announced;
  - `job.progress`, `task.update` and `job.done` are mirrored on the global stream.
- `http-api`: the character, job and cover write routes; the test routes gain the M4 scenarios.
- `http-client`:
  - characters, jobs and cover upload over HTTP;
  - the "not available yet" example moves to M5.
- `client-contract`: the HTTP portable run supports M4.
- `demo-data`: reset cancels user jobs on seed characters and deactivates (keeps) their generated versions; test-mode overlay jobs resume.
- `local-backend`: startup recovers jobs; factory reset stops the scheduler first.

## Impact

- **Backend, new:**
  - `horizon/services/jobs/` (`scheduler.py`, `plans.py`, `worker.py`, `recovery.py`, `kinds.py`), following doc 01 §7's layout;
  - `horizon/storage/{atomic,images}.py` (atomic write, originals, WebP, cover re-encode) and `horizon/services/assets.py` (versions, accept, lock, candidates);
  - `horizon/services/theme.py` (the procedural theme port);
  - `horizon/services/characters.py` (createDraft/patch/approve/archive/restore/delete);
  - `horizon/ai/{scripted,naive}/creation.py` and `horizon/ai/image_prompt.py`;
  - `horizon/api/characters.py` and `horizon/api/jobs.py`.
- **Backend, changed:**
  - `gateway/{images,pipeline,fake}.py`: the request shape, hooks, the scripted image source, and the fake `/v1/images`;
  - `runtime.py`: `_build_m4`/`_stop_m4`, startup step 6, reset and factory reset;
  - `ai/profile.py`: new ports and naive set;
  - `contract/mappers.py`: the candidate derivation;
  - `api/routes.py`: scenarios and the cover route;
  - `services/seed.py`: reset vs. user jobs.
- **Database:** no migration. Every table and column exists (`generation_jobs`, `generation_tasks`, `image_assets`, `theme_songs`, `idempotency_keys`).
- **Dependency:** Pillow (with WebP), added to `pyproject.toml`; it's pure-wheel on Windows.
- **Shared fixtures:** `backend/tests/fixtures/{drafts,theme_spec,image_prompt}/`, generated by `npm run fixtures:build` and checked by `fixtures:check`.
- **Frontend:**
  - `client/http/HttpClient.ts` (all M4 methods; multipart transport);
  - `clientContract.http.test.ts` (`supports: "M4"`);
  - `features/worlds/WorldEditor.tsx` (upload after save, a 5 MB limit, PNG/JPEG/WebP);
  - the fixture build script.
  - No MockClient behaviour change.
- **Docs:** doc 02 §3.2 (the candidate derivation rule), doc 04 §1 (the music status, the image request shape), doc 05 §2.2 (`SongGenerator` without Lyria), doc 06 (the M4 acceptance note on songs), and the decision log D-83+.
- **Out of scope:**
  - knowledge, memory, embeddings and Forget (M5);
  - the `VITE_HORIZON_CLIENT` flip and E2E on the HttpClient (M6);
  - a real music model (blocked on OpenRouter);
  - `autoGenerateMissingEmotions` behaviour (OQ-6);
  - AI-stage prompt tuning and Jev image-quality gates (doc 05 §6).

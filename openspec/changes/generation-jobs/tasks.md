# Tasks

> **Before starting:** confirm or override design.md OQ-1…OQ-13. The tasks below implement the recorded defaults. OQ-1 (songs are procedural because Lyria isn't on OpenRouter) and OQ-2 (no naive emotion edits on SVG seed portraits) change user-visible behaviour, so confirm those two first.
>
> **Constraints for every task:**
> - no network in automated tests (the socket guard stays);
> - only obviously fake `sk-or-test-…` keys, and the real key is never printed;
> - the contract stays additive and `schema.json` unchanged;
> - the MockClient's behaviour is unchanged;
> - commits without Claude attribution, at green group boundaries; nothing is pushed.
>
> **Slices (OQ-12).** Each numbered group ends with its own tests green.

## 1. Gateway, storage and scaffolding

- [x] 1.1 Add `pillow` to `backend/pyproject.toml`. Create the skeletons `horizon/services/jobs/`, `horizon/storage/`, `horizon/services/{assets,characters,theme}.py`, `horizon/ai/image_prompt.py`, `horizon/ai/{scripted,naive}/creation.py`. Extend mypy strict to `horizon.services.jobs.*`, `horizon.services.{assets,characters,theme}`, `horizon.storage.*`. Extend the M3 static test so `horizon/services/jobs/**` can't call `asyncio.create_task`. Verify: `uv sync`, `uv run mypy` and `ruff` are clean, and `python -c "from PIL import features; assert features.check('webp')"` passes on Windows.
- [x] 1.2 Implement `storage/atomic.py` (tmp → fsync → `os.replace`, with a Windows `PermissionError` retry) and `storage/images.py`:
  - magic-byte sniffing (PNG/JPEG/WebP);
  - `verify` with a 40 MP guard;
  - EXIF transpose;
  - centre-crop to 3:4 → 768×1024 Lanczos WebP with the 85 → 65 quality ladder;
  - 16:9 → 1600×900 for covers;
  - 2×4 sheet slicing (design D7).

  Verify with unit tests:
  - an 832×1110 JPEG gives a 768×1024 WebP;
  - a noisy 1024×1024 image stays ≤ 250 KB;
  - a GIF, a text file named `.png` and a 50 MP PNG are rejected;
  - a sheet yields 8 cells of 768×1024;
  - a crash simulated between write and replace leaves only a `.tmp`.
- [x] 1.3 Fix the images request (design D3, D-84 context): `input_references: [{type:"image_url", image_url:{url}}]`, `n: 1`, `aspect_ratio`, `resolution`. Teach `FakeOpenRouter` `/v1/images`: a deterministic PNG in `b64_json` plus `usage.cost` from the price table. Add per-endpoint request counters, and a test hook that parks the Nth images request on an event. Verify: a respx/fake test asserts the request body shape, and the counter increments once per call.
- [x] 1.4 Add the pipeline hooks:
  - `paid(..., before_send=, commit_with=, after_response=)`;
  - `generate_image` forwards them;
  - `LedgerPort.record(row, drain, extra=)` runs `extra(conn, row_id)` inside the ledger transaction.

  A failing `after_response` still records the row (from the bill) without `extra`, then re-raises. A preflight refusal runs none of them. Verify with unit tests for:
  - the ordering (preflight → before_send → send → after_response → record + extra in one commit);
  - a refusal running no hooks;
  - an `after_response` failure still writing one ledger row;
  - a rollback of `extra` rolling back the row.
- [x] 1.5 Add `Gateway.reserve_job(ctx, estimate)` (design D5). Under `book.lock` it runs the daily and creation checks including all holds; it publishes `budget.reached` and raises 402 on refusal, and otherwise calls `book.reserve_job`. Add a scripted generation call (`simulated_call` with `category` image or profile, `provider: "scripted"`). Verify: the budget-caps scenarios "Creation cap blocks a portrait job" and "Two jobs share the daily headroom" pass at service level.
- [x] 1.6 Runtime wiring:
  - `image_slots = Slots(2)`, `music_slots = Slots(1)`, `job_faults`;
  - `_build_m4`/`_stop_m4`, with stop before `_stop_m3`;
  - factory reset stops the scheduler first.

  Record D-84 (pipeline hooks for never-pay-twice) in `docs/requirements/09-decision-log.md`, and the request shape in doc 04 §1. Verify: the existing backend suite stays green, and a factory-reset test with an idle scheduler passes.

## 2. Plans, scheduler and the job routes (scripted)

- [x] 2.1 Port `planTasks`/`estimateJob` to `services/jobs/plans.py` (kinds, Lean/Standard, technique, parallelism and durations from `seed/runtime.json`, price kinds). Verify: a table test matches the MockClient for every kind × mode, by comparing against a fixture generated from `estimateJob` by `fixtures:build` (`backend/tests/fixtures/job_plans/`).
- [x] 2.2 Build the `JobScheduler`:
  - `start(input)`: key → character (not a tombstone) → one-active (409) → `reserve_job` → insert the job and tasks in one transaction → set `activeJobId` → spawn the runner;
  - the runner: up to `parallel` tasks, slots held only around the provider call, `jobTickMs` ticks on `clock.sleep`, progress, the outcome, `release_job`, `actualCostUsd` from the ledger;
  - events: `task.update`, `job.progress`, `job.done`, `entity.changed job/character`.

  Verify with integration tests under the frozen clock:
  - a Lean `portrait_candidates` job is `succeeded` after `advance(21000)`;
  - `job.progress` is monotonic;
  - exactly one `job.done`;
  - every payload passes `GlobalEventSchema` validation.
- [x] 2.3 Routes `POST /jobs/estimate` and `POST /jobs` (201), with Idempotency-Key replay across a restart. Verify: the generation-jobs scenarios "Lean emotion set estimate", "Second job for the same character", "Without a key" and "Same Idempotency-Key after a restart" pass over HTTP (pytest + ASGI client).

## 3. Job kinds, scripted ports and assets

- [x] 3.1 Extend `frontend/scripts/fork-fixtures/build.ts` to emit `backend/tests/fixtures/drafts/*.json` (`draftFromSeed` for 6 seeds × 4 intents, plus `regenerateField` cases) and `theme_spec/*.json` (`themeSpecFromBrief` for every seed brief plus 3 edited briefs). Add TS tests that assert them. Verify: `npm run fixtures:build` writes them, and `fixtures:check` fails after a hand edit.
- [x] 3.2 Port `draftFromSeed`/`regenerateField` (scripted `ProfileDrafter`) and `themeSpecFromBrief` (`services/theme.py`). Verify: Python tests assert both fixture sets byte for byte.
- [x] 3.3 Implement `ImagePromptCompiler` (design D9): base (A1 + v2 fixes), emotion edit (A2 + v2 table), tweak, sheet (A3), and the under-18 refusal. Add golden fixtures in `backend/tests/fixtures/image_prompt/` for Hana, Amara, Rin and Victor. Verify: the golden tests pass, and the ai-ports scenario "Angry has no blush" passes.
- [x] 3.4 Scripted `ImageGenerator`: a deterministic Pillow placeholder (palette, silhouette, emotion label, seeded by the task ID), billed through the scripted generation call after the paced duration. Add the AiPorts `drafter`/`image`/`song` with `NAIVE_PORTS = {turn, router, drafter, image}`, `HORIZON_AI_DRAFTER`/`HORIZON_AI_IMAGE`, and `/_test/ai-profile` overrides. Verify: the same task ID gives the same bytes, and the ai-ports scenario "Override one port" still passes.
- [x] 3.5 Implement `worker.py` (one attempt with the D3 step order, using the 1.4 hooks) and `apply.py` for `profile_draft` (4 tasks: profile, appearance summary, palette, song brief → a `theme_songs` row `pending`; the character's `creationStep` becomes `profile`) and `profile_regenerate`. Verify: the character-lifecycle scenario "Draft from a seed prompt" passes at service level with `advance(5000)`, and 4 `profile` ledger rows sum to `profileDraft`.
- [x] 3.6 Candidates (design D8):
  - rows inserted as `generating` at job start;
  - `ready`/`failed` on task end;
  - the new derivation in `contract/mappers.character_wire` plus the batch-kind join in the character read;
  - `lockPortrait` (copy the WebP to `portrait_neutral_v{n}`, deactivate then activate, `creationStep` → `emotions`; seed SVG candidates by URL).

  Update doc 02 §3.2 and record D-85. Verify: the generated-assets scenarios "Candidates appear immediately", "Tweak keeps the batch", "Lock a ready candidate" and "Lock a generating candidate" pass.
- [x] 3.7 Emotion versions:
  - `emotion_set` (per-emotion, plus blink in Standard), `emotion_regenerate`, `expression_sheet` (one sheet, sliced; emotion tasks `skipped` if it fails);
  - version numbering `MAX+1`, active vs. pending by the `replaceLater` rule;
  - `POST /assets/{id}/accept` (deactivate then activate, `version` bump when approved).

  Verify: the generated-assets scenarios "Draft emotions go live", "Approved character keeps its face until accepted", "Accept a regenerated emotion", "Sheet slices into emotions", "Regenerated emotion gets a new URL" and "Emotion image on disk" pass.
- [x] 3.8 The `song` job (design D9, D-83): the procedural theme from the brief (or `input.brief`); `song_v{n}.proc.json`; a `theme_songs` row with no `format`, `generation.model: "procedural"` and `costUsd: 0`; `themeSongId` set; no ledger row; estimate $0; `model_exists(models.music)` logged once per start. Record D-83 and update doc 05 §2.2, doc 04 §1 (music status) and doc 06 M4 acceptance ("procedural theme"). Verify: the generated-assets scenario "Procedural theme" passes, and `GET /assets/gen/.../song_v1.proc.json` serves JSON that the frontend's `isThemeProcSpec` accepts (fixture check).

## 4. Cancel, retry and fault scenarios

- [x] 4.1 `POST /jobs/{id}/cancel` (design D6):
  - queued and not-yet-sent tasks become `skipped`;
  - a sent task runs to completion shielded, records its real cost, and stores its result without applying it;
  - `cancelled` plus `release_job` plus `activeJobId` cleared.

  Record D-86. Verify: the generation-jobs scenario "Cancel during an emotion set" passes with a parked fake image request, and the ledger shows the in-flight call.
- [x] 4.2 `POST /jobs/{id}/tasks/{taskId}/retry`: needs a key; only `failed` tasks; 409 at `maxAttempts`; `reserve_job` for the task's estimate (refused at the cap before sending); the job back to `running`; `activeJobId` set again. Verify: the scenarios "Retry succeeds" and "Out of attempts" pass, and a retry under a reached cap rejects 402 with no provider request.
- [x] 4.3 Scenarios `image_fail_partial`, `image_fail_all` and `song_fails` (design D12), applied at 60 % before the provider step; `SCENARIO_MILESTONE` updated. Verify: the scenario "Partial failure then retry" passes over HTTP, `image_fail_all` gives a `failed` job with `error.code: "provider_error"`, and no ledger row is written for a faulted attempt.

## 5. Restart recovery

- [x] 5.1 Implement `jobs.recover()` as startup step 6 (design D4): requeue the unsent tasks, derive/apply the tasks with a result, fail the sent tasks with no result (retryable, with the documented message), re-reserve, start the runners. Update the `runtime.py` startup docstring. Verify with unit tests for each of the three task states, using rows written directly.
- [x] 5.2 Write the kill tests (OQ-8):
  - park the second naive image request, take a SQLite online backup plus a copy of `data/`, start a fresh Runtime on the copy, and assert the fake's images counter never grows, the first candidate is `ready` and the second is `failed`/retryable;
  - the result-present case: derive only, no call;
  - the never-sent case: exactly one call.

  Verify: the generation-jobs scenarios "Kill mid-job and restart", "Crash after the provider answered" and "Queued task resumes" pass, and the local-backend scenario "Restart with a job in flight" passes.
- [x] 5.3 Test-mode overlay jobs: confirm that the seed importer stores `job_mockKenjiEmotions` with tasks that recovery can resume (no `provider_called_at`). Verify: the demo-data scenario "Kenji's job finishes" passes, and the M1b–M3 HTTP portable tests are still green with the overlay job running.
- [x] 5.4 The generated-assets scenarios "Derived file re-made for free" and "Leftover temp file". The sweeper keeps every referenced version and never touches `originals/`. Verify: both scenarios pass, and an unreferenced `gen/` file older than 1 h is removed at startup.

## 6. Character lifecycle

- [x] 6.1 `POST /worlds/{worldId}/characters` (`createDraft`, design D10): key → world → `reserve_job` → character + job + tasks in one transaction → runner; 201 `{character, job}`. Verify: the character-lifecycle scenarios "Draft from a seed prompt" and "Draft without a key" and the http-api scenario "Draft over HTTP" pass.
- [x] 6.2 `PATCH /characters/{id}`: an allow-listed `CharacterPatch`, deep merge (lists replaced), a `version` bump when approved, one writer transaction. Verify: the scenarios "Edit one profile field" and "Edit while a job writes" pass (the second races a worker `apply` against the PATCH under the frozen clock).
- [x] 6.3 `approve`, `archive`, `restore` (mock rules), with the not_found helper for tombstones on every character command. Verify: the scenarios "Approve without a portrait", "Approve a complete draft", "Archive then restore" and "Command on a tombstone" pass.
- [x] 6.4 `DELETE /characters/{id}` (design D6): `LiveSessionManager.generating_with(id)` → 409 with `activeSessionId`; cancel the job and wait (bounded); tombstone, row deletes and the `ai_purge_queue {scope:"character"}` in one transaction; then delete files; `entity.changed`. Verify: the character-lifecycle scenarios "Tombstone after delete", "Delete during a generation job" and "Delete during a live reply" pass.
- [x] 6.5 Reset demo (demo-data delta): cancel non-terminal jobs on seed characters before re-seeding; keep the generated versions inactive. Verify: the demo-data scenario "Regenerated seed emotion after reset" passes, and the existing reset tests stay green.
- [x] 6.6 Sessions after a delete: check that each M3 mode turns a tombstoned speaker (`TurnOutcome "missing"`) into a skipped entry with reason `"archived"`, and fix any mode that doesn't. Verify: an integration test deletes a group participant between turns, and the next `send` skips them with `reason: "archived"`, while transcripts with the deleted speaker still open, replay and export.

## 7. World cover upload (backend and UI)

- [x] 7.1 `POST /worlds/{id}/cover` (design D10): the early `Content-Length` 413, a counted streaming read of the `file` part, magic bytes + verify, re-encode to `cover_v{n}.webp`, a `cover` asset row plus `worlds.cover` in one transaction, `entity.changed world`; no key needed. Verify: the worlds scenarios "Valid upload", "Wrong type or too large", "Declared type does not match the content", "Unknown world" and "Stored cover on the backend", and the http-api scenario "Chunked oversize upload", pass.
- [x] 7.2 `WorldEditor.tsx` (design D11): keep the `File`, preview via an object URL, PNG/JPEG/WebP ≤ 5 MB, call `worlds.uploadCover` after create/update, keep the editor open with the error if the upload fails; no data URL goes into `create`/`update` any more. Verify: a component test with a fake client covers "New world with an uploaded cover" and "Oversized file", the existing e2e world tests pass on the MockClient, and lint/typecheck are clean.

## 8. HttpClient and the portable suite

- [x] 8.1 Add `Transport.postForm` (multipart, `Idempotency-Key`, error mapping). Implement every `later("M4")` in `HttpClient.ts` (characters, jobs, `uploadCover`). Update `http.test.ts` and the "not available yet" example to `addKnowledge` → `"M5"`. Verify: the http-client scenarios "Upload a cover over HTTP", "Start a job over HTTP" and "Sending a chat message in M1b" pass in the TS unit tests.
- [x] 8.2 `clientContract.http.test.ts` → `supports: "M4"`, with the `Milestone` pending list `M5|M6`. Verify: `npm run test:http` passes every M1b–M4 portable test (including the 13 M4 cases) with only M5/M6 pending, and the MockClient run is unchanged.
- [x] 8.3 Leak sweep: add job rows, task errors, job `input`, and the cover route response. Verify: the leak test passes with a real-looking fake key set.
- [x] 8.4 Check the effect of the Kenji overlay spend and the new global events on the existing M2/M3 portable tests and the backend suite. Fix any test that assumed no background spend by giving it its own cap or setup. Verify: the full backend suite and `test:http` are green twice in a row (determinism).

  Done on 2026-10-06. Tests that count spend or events stop the overlay job first (`tests/jobs/kit.cancel_overlay_jobs`, or a direct cancel): `test_energy_caps`, `test_ports`, `test_runtime_m2` and `test_leak_sweep`; the reservation test expects the overlay job's re-reserved remainder. Chasing the remaining flakes found four backend bugs, each fixed with a regression test (design "Implementation notes"):
  - the factory-reset gate let one request stay in flight (M1b), so a reset could dispose the database under a write and lock `horizon.db` on Windows;
  - a stopped corrector could still accept a late correction that reopened the database;
  - a cancelled job's "sent" mark could outlive `stop()`;
  - the preflight read spend before reservations (M2), so a call finishing mid-read was counted nowhere (one call over the cap, about 1 run in 30).

  Then: the backend suite was green twice in a row (583 passed each), `test:http` five times in a row (43 passed, 9 skipped, no reset errors), and the overrun race test 40 times in a row.

## 9. Naive ports and the live run

- [x] 9.1 Naive `ProfileDrafter` (design D9): one DeepSeek `chat_complete` with a strict JSON schema built from the contract types, `purpose: "profile"`, `creation: True`; contract validation; age < 18 fails; the other three tasks apply parts at $0; `regenerate_field`. Verify: respx tests for a valid answer, a missing field and an under-18 age (the ai-ports scenario "Naive draft is schema-valid"); the request body has `response_format` and pinned routing.
- [x] 9.2 Naive `ImageGenerator`: Seedream through `generate_image` (3:4, 1K, `n: 1`), with the locked neutral original as the single data-URL reference for edit kinds; `jobs.start` rejects an edit kind with `validation` and `details.reason: "base_not_raster"` when the base is an SVG placeholder (OQ-2). Verify: the ai-ports scenario "Emotion edit sends the base portrait" passes against the fake, and the SVG-base rejection test passes.
- [x] 9.3 A naive wizard run against the fake provider: `createDraft` → profile → Lean candidates → lock → emotion set → song → approve, under `HORIZON_AI_PROFILE=naive` in test mode. Verify: an integration test reaches `approved`, every asset is a ≤ 250 KB WebP, and the fake's request counts equal the planned calls exactly.
- [x] 9.4 Write `tests/live/test_live_jobs.py` (design D13; marker `live`, key presence only, never printed): draft + one base + one emotion edit; assert the response shape, WebP ≤ 250 KB, `actualCostUsd` = the ledger sum, total < $0.05; a free `model_exists` for music. Verify: it is skipped in the default run. **The manual run happens only when the user asks**, and its result is recorded in this file and in design D13.

  Run on 2026-10-06 at the user's request. The first run failed at the draft: every naive draft was cut off at 1,200 tokens (one measured 1,229), and strict `json_schema` routing skipped DeepSeek for a 45–99 s fallback. Fixed (design D9): 2,400 tokens, JSON mode on DeepSeek, and the contract limits restated in the schema with a drift test. The rerun passed in 35 s for $0.037873: a contract-valid draft on DeepSeek, a 67 KB base and a 70 KB `happy` edit (768×1024 WebP), and `actualCostUsd` equal to the ledger rows. Total spend, diagnosis included: $0.044. Finding left open: OpenRouter now lists `google/lyria-3-clip-preview` (D-83, OQ-1).

## 10. Close-out (integration checks only)

- [x] 10.1 The full gates:
  - backend: `uv run pytest`, `ruff`, `mypy`;
  - frontend: `npm test`, `typecheck`, `lint` (no new warnings), `seed:check`, `fixtures:check`, `export-schema:check`, `test:http` (only M5/M6 pending), e2e on the MockClient.

  Verify: every command passes, and the counts are recorded in this task.

  Done on 2026-10-06, all on the final code:
  - backend: `uv run pytest` 583 passed, 3 deselected (the `live` tests), twice; `ruff` clean; `mypy` no issues in 118 source files;
  - after the live-run drafter fix (9.4): `uv run pytest` 584 passed (the new schema drift test), `ruff` and `mypy` clean;
  - frontend: `npm test` 381 passed (29 files); `typecheck` clean; `lint` 87 warnings, the same as before this change (none new); `seed:check`, `fixtures:check` and `export-schema:check` pass;
  - `test:http`: 43 passed (every M1b–M4 test) and 9 skipped (the 8 M5 and 1 M6 tests), five runs in a row;
  - e2e on the MockClient: 34 passed.
- [x] 10.2 A manual browser check against the local backend (`HORIZON_AI_PROFILE=scripted`): create a world with an uploaded cover, then run the wizard from seed to approve, cancel a job, retry a failed task under `image_fail_partial`, delete a character and open an old transcript. Verify: each step behaves as on the MockClient, and any difference is listed here.

  Done on 2026-10-05: the real UI (`vite --mode http`, Edge) was driven by a throwaway Playwright script against `horizon serve` (test mode, scripted, so the fake provider was used and nothing was spent). Every step passed:
  - the uploaded cover is stored as a WebP and served;
  - the draft filled in Sarah, a doctor;
  - a portrait was locked as the base;
  - "Stop remaining" cancelled the emotion set;
  - under `image_fail_partial` one face failed, and ↻ Retry succeeded on attempt 2;
  - Compose made a song, then approve and Summon;
  - Elena was archived and deleted, and her lines still show in `ses_mockTooCloseExams`.

  Differences found:
  - Fixed: the wizard stayed on "Developing…" after a job finished. A late job GET overwrote `job.done`; see the implementation notes in the design.
  - Fixed: the backend published `entity.changed` for a job on every progress tick.
  - Kept: opening an old transcript asks for each participant's theme. For the deleted Elena that returns `not_found`, as on the mock, and the session audio ignores it. Over HTTP the browser also logs the 404 in the console.
  - Note: a data directory nested deep enough to push a path past Windows' 260-character limit fails writes (the first try used a nested temp folder). The default `data/` stays under 170 characters.

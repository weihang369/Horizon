# Tasks: creation-followups

## 1. Music model ID and timeouts (D-87, design D2, D8)

- [x] 1.1 In `frontend/src/mock/pricing.config.ts`:
  - set `MODELS.music` to `google/lyria-3-clip-preview`;
  - add `music: 120_000` to `gateway.timeoutsMs`;
  - make `scripts/seed-build/ledger.ts` use `MODELS.music` instead of the literal `"google/lyria-3-clip"`;
  - run `seed:build`.

  Verify that `seed/settings.json` `models.music` and `seed/pricing.json` `timeoutsMs.music` hold the new values, and that `seed:check` passes.
- [x] 1.2 Add `music` to `Timeouts` and `GatewayConfig.from_mapping` in `backend/horizon/gateway/types.py`. Verify with a unit test that the seed pricing parses to `timeouts.music == 120.0`.
- [x] 1.3 Replace the `"google/lyria-3-clip"` fallback labels in `ThemeStep.tsx` and `ThemeTrack.tsx` with the `-preview` ID. Verify that `grep -rn "lyria-3-clip\"" frontend/src frontend/scripts` finds nothing, and that typecheck is clean.

## 2. Gateway music client (provider-gateway "Music request shape", design D1)

- [x] 2.1 Add `gateway/music.py`: `MusicClient.generate(model, prompt) -> MusicResult` sends the D1 body, with no `provider` block and no `models` list. It streams through `HttpCore.stream`, takes the generation id from the first chunk, concatenates `delta.audio.data` and base64-decodes once, reads usage from the final chunk, and turns error chunks into `provider_error` with `maybe_charged`. No audio is `malformed("music stream")`. It honours the first-audio deadline (`timeouts.music`) and `chatIdle`. Verify with respx unit tests:
  - three audio chunks plus a usage chunk → the bytes in order, and the cost;
  - the body has `modalities`, `stream: true` and `usage.include`, and has no `provider.order` or `models`;
  - an empty stream → `provider_error` with `maybe_charged`;
  - an error chunk → `provider_error`;
  - a stall → `timeout` with `maybe_charged`.
- [x] 2.2 Add `Gateway.generate_music(ctx, *, model, prompt, before_send, after_response, commit_with)` through `paid()`, with estimate `prices.generation["song"]`. Verify with a pipeline test on the fake transport: one row with `category: "music"`, `purpose: "song"`, the reported cost and the job id; a 5xx with a body writes no row; a timeout after send writes one row at $0.04.
- [x] 2.3 Extend `FakeOpenRouter`: a chat request with `modalities` containing `"audio"` streams SSE with a synthetic MP3 stub (a few MPEG-1 Layer III frame headers built in code, no binary fixture) and `usage.cost: 0.04`. Add per-test switches for "fail with 503", "stall" and "non-MP3 bytes". It counts music requests. Verify with a fake-transport test reading a clip through `MusicClient`, and that `fixtures:check` passes.
- [x] 2.4 Update `docs/backend/04-gateway-budget-energy.md` §1: the music row (model, request shape, timeouts, the fallback rule) instead of "none yet". Verify that the doc names `google/lyria-3-clip-preview` and links design D1/D7.

## 3. Audio validation and storage (design D6)

- [x] 3.1 Add `backend/horizon/storage/audio.py` with `is_mp3`, `mp3_duration` (skip ID3v2, walk Layer III frames, `None` when no frame parses) and `MAX_SONG_BYTES = 8 MB`. Verify with unit tests on in-code stubs:
  - an ID3-prefixed stub and a bare-frame stub are MP3, and their durations equal frames × samples ÷ rate;
  - PNG, WAV (`RIFF`) and empty bytes are not MP3;
  - oversize is rejected.
- [x] 3.2 Give `assets.song_rel` an `ext` parameter (default `proc.json`), and give the worker's original-file sniff an `mp3` extension. Verify with an assets unit test that the names are `song_v{N}.mp3` and `song_v{N}.proc.json`, and that existing tests still pass.
- [x] 3.3 Add `apply_audio_theme` in `services/jobs/apply.py`, sharing version numbering with `apply_theme`. It writes `song_v{N}.mp3` via the atomic `write_file` before the transaction commits, and sets `format: "mp3"`, `bytes`, `duration_sec` (`mp3_duration` or 30), `instrumental`, `generation` (model, prompt, task cost, job id) and the Lyria `license_note`. Add a `license_note` parameter to `apply_theme` for the fallback note. Verify with a unit test: a new version every time, the file exists before the row, and `characters.song(id)` maps to `format: "mp3"` with a `.mp3` URL.

## 4. Song port and job wiring (ai-ports, generated-assets, design D3–D5, D7)

- [x] 4.1 Reshape `SongGenerator` in `ai/ports.py`:
  - add `paid`, `expected_ms`, `theme`, and `async generate(ctx, job: SongJob, hooks)`;
  - add the `SongJob` dataclass (task id, model, prompt, brief, title);
  - update `ProceduralSong` (`paid = False`, `expected_ms` → `songMs`).

  Verify that mypy is clean and the shared theme-spec fixture test still passes.
- [x] 4.2 Add `song_prompt(brief, title)` and `NaiveSong` in `ai/naive/creation.py`:
  - `paid = True`, `NAIVE_SONG_LATENCY_MS = 40_000`;
  - its `after` hook validates the audio with `is_mp3` and the size cap, raising `provider_error` "audio we couldn't use", before forwarding to `hooks.after_response`;
  - register `"song": NaiveSong(d)` in the naive builders in `ai/profile.py`;
  - update the module docstrings (D-83 → D-87).

  Verify with unit tests:
  - the prompt holds every brief value plus "No vocals" and leaves empty lists out;
  - `HORIZON_AI_PROFILE=naive` selects `NaiveSong`, and `HORIZON_AI_SONG=scripted` selects `ProceduralSong` (the ai-ports scenario).
- [x] 4.3 In `plans.task_spec`, add `song_paid`: when paid, `theme_song` uses `g["song"]` with price kind `"song"`. Thread `sched.song_paid()` through plan (estimate and start), recovery and retry. Add `PURPOSE["theme_song"] = "song"` with category `music` in `task_ctx`. Verify with tests:
  - in naive, `jobs.estimate` for a `song` job is 0.04 and the reservation equals it;
  - in scripted it is 0;
  - the reservation is fully released after the job ends.
- [x] 4.4 Implement the worker's `theme_song` call:
  - when the port is paid, build `SongJob` from the brief (job input → stored brief → draft brief) and call `song.generate` inside `Slot(rt.music_slots)` with `hooks_for`;
  - catch `SONG_FALLBACK` codes and return `Fallback(reason)`;
  - `finish` and `commit_result` apply `apply_audio_theme` from an `originals/*.mp3` result, or `apply_theme` with the fallback license note, setting the song's `generation.costUsd` and the job's `actual_cost_usd` from the ledger rows;
  - replace `song_paced()` with the port's `expected_ms`.

  Verify with backend job tests on `FakeOpenRouter` (naive profile):
  - a success gives an `.mp3` song, one music row and the original kept;
  - a 503 falls back to `.proc.json`, the note says the model was unavailable, and there is no row;
  - a stall/timeout falls back, with one row at $0.04;
  - non-MP3 bytes fall back, with one row;
  - a cap reached before the call means the task is `failed` with `daily_budget_exceeded`, no music request is sent, and the song is unchanged;
  - `song_fails` in test mode still fails the task, retryable.
- [x] 4.5 Restart recovery for songs. Verify with restart tests over the same data directory, counting fake music requests:
  - a song task with a stored `.mp3` original only re-derives, with 0 new requests;
  - a song task sent with no result is `failed` (retryable), with 0 new requests;
  - a queued, never-sent song task runs once after start.
- [x] 4.6 Update `scheduler._probe_music`: it runs only when the song port is paid, with the D-87 log line. Verify with a test that the log names the model and "procedural fallback (D-87)", and that the scripted profile makes no probe request.
- [x] 4.7 Update the docs: `docs/backend/05-ai-seams.md` §2.2 (the SongGenerator row: naive = Lyria 3 Clip with the procedural fallback); `docs/backend/02-storage.md` §2/§3.2 (`song_vN.mp3`, originals); `docs/requirements/09-decision-log.md` (mark D-83 as superseded for the naive profile by D-87). Verify that each doc names D-87 and the fallback rule.

## 5. D-89: hide autoGenerateMissingEmotions (budget-caps)

- [x] 5.1 Remove the "Auto-generate missing emotions" `Row` from `features/settings/CostTab.tsx`. Keep the contract field, the settings API, the seed value and the MockClient. Verify:
  - a Vitest render test of the Cost tab finds no control with that label (add a test file if none exists);
  - `grep -rn autoGenerateMissingEmotions frontend/src backend/horizon` shows only contract, schema, mock-store and settings plumbing, with no job starter.
- [x] 5.2 Update the e2e or portable settings coverage, if any of it touches that control. Verify that `e2e` and `test:http` pass.

## 6. D-90: "Generate a portrait first" (generation-jobs)

- [x] 6.1 In `features/wizard/generate.ts` `startGeneration`, handle `validation` with `details.reason === "base_not_raster"`: show the toast "Generate a portrait first…" with the action "Generate a portrait", which navigates to the wizard `step: "portrait"` (adding `edit: true` for an approved character; `worldId` and status from the entity store, else `client.characters.get`). Other errors still go to `reportError`. Verify with a Vitest test that stubs `client.jobs.start` to throw: the toast text and action for a draft character and for an approved one (the navigation target includes `edit: true`); `no_base` and other validation errors still show the generic toast.
- [x] 6.2 Confirm every emotion-edit and tweak start uses `startGeneration`: `EmotionsStep`, `tabs.tsx`, `EmotionLightbox` and the `PortraitStep` tweak. Verify by grep for `client.jobs.start(` outside `generate.ts` (none for edit kinds).
- [x] 6.3 Extend the backend `base_not_raster` test in `tests/jobs/test_naive.py`: no job row, the reservation book empty for the character, and the scripted image generator starts the same job normally. Verify that the test passes.

## 7. Integration gates

- [x] 7.1 Run all gates and record the counts here:
  - backend pytest;
  - the race loop (40×);
  - `test:http` (5×);
  - unit;
  - typecheck;
  - lint (≤ 87 warnings);
  - `seed:check`, `fixtures:check`, `export-schema:check`;
  - e2e;
  - `openspec validate creation-followups --strict`.

  Verify that every gate is green.

  **Run 2026-10-08:**
  - backend: ruff ok, mypy clean (120 files), 619 passed with 4 live tests deselected;
  - race loop: 0 failures in 40;
  - `test:http`: 5 of 5 runs had 43 passed and 9 skipped, with no reset, closed or checked-out errors;
  - unit: 385 passed;
  - typecheck clean;
  - lint: 87 warnings (the baseline);
  - `seed:check`, `fixtures:check` and `export-schema:check` exited 0;
  - e2e: 34 passed;
  - `openspec validate --strict`: valid.
- [x] 7.2 Add the live check `tests/live/test_live_jobs.py::test_live_song` (marked `live`, deselected by default):
  - a $0.05 cap and the key presence check only;
  - it prints shape, chunks, bytes, format, duration, latency and cost, never the key.

  Verify that `pytest -m live --collect-only` lists it and that a normal run deselects it. **Run it only after the user explicitly approves the spend (≤ $0.05)**, then record the result in design.md (a D9 record) and here. If the real shape differs from D1, fix D1 and re-run 7.1.

  **Run 2026-10-08 (user-approved): 1 passed, $0.040000.**
  - Lyria 3 Clip returned one audio piece: a 679,456-byte ID3 MP3 of 28.056 s.
  - It took 16.3 s, and `usage.cost` was $0.04 (`cost_source: provider`).
  - The song is `song_v2.mp3` with `format: "mp3"`. The D1 shape was confirmed with no change.
  - `NAIVE_SONG_LATENCY_MS` is set to the measured 17,000.

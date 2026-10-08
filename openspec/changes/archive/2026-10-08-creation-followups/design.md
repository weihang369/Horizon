# Design: creation-followups

## Context

See proposal.md for why. The current state this design builds on (observed in the code on 2026-10-08):

- **Songs today (D-83).** `ProceduralSong.theme(seed, brief, title)` is a synchronous port. The worker calls it inside `commit_result`, the writer transaction, and `apply_theme` writes `song_vN.proc.json`. In `plans.task_spec`, `theme_song` is priced `0.0` with no price kind in both profiles. `song_paced()` paces it only in the scripted profile. `scheduler._probe_music` logs whether `models.music` is listed.
- **The gateway.**
  - `ChatClient.body()` always adds the pinned DeepSeek routing block, and a `models` fallback to the fallback chat model. Both are wrong for a Google music model.
  - `ImagesClient` is the pattern for a dedicated client.
  - `Gateway.paid()` handles caps, holds, `before_send`, `after_response` and `commit_with`, and records a row for a charged failure.
- **OpenRouter facts (public metadata, 2026-10-08, no key used).**
  - `google/lyria-3-clip-preview`: modality `text+image->text+audio`, one endpoint (Google AI Studio). Supported parameters: `max_tokens`, `temperature`, `top_p`, `seed`, `response_format`.
  - Per-token prices are `0`; the price is per clip ($0.04, in the description).
  - OpenRouter's audio guide says audio output **requires `stream: true`** with `modalities: ["text","audio"]`, and arrives as base64 in `choices[0].delta.audio.data`.
  - Google documents Lyria 3 Clip output as a 30 s **MP3**.
  - The endpoint showed `status: -5` with 6 % uptime over the last day (Pro: 14 %). It is a preview model on one provider, so the fallback path matters.
- **Contract rev 1.3.** `ThemeSong` already has `url`, `format: "opus" | "aac" | "mp3"`, `bytes`, `durationSec`, `generation` and `licenseNote`, so no contract change is needed.
- **Frontend.** `audio/resolve.ts` plays any URL that is not `.proc.json` with `fetch` and `decodeAudioData` ("swapping placeholders for real audio is a URL change only", R11). `ThemeTrack` already shows `format.toUpperCase()` and the "WebAudio sketch" label for procedural songs.
- **D-90 plumbing.** Every job start goes through `startGeneration()` in `features/wizard/generate.ts`, whose catch calls `reportError`. Toasts support one action. An approved character opens the wizard in edit mode (`edit = route.edit || status === "approved"`), and `lockPortrait` has no status restriction.

## Goals / Non-Goals

**Goals:**
- A naive `song` job yields a real Lyria MP3, honestly billed, through the same never-pay-twice path as images.
- A song job never leaves the user without a theme because of a provider fault.
- Zero network calls in tests, with a tiny synthetic MP3 stub.

**Non-Goals:**
- Lyria 3 Pro, vocals or lyrics, image-conditioned songs, loop points, gain normalisation, transcoding.
- Building `autoGenerateMissingEmotions` (D-89 only hides it).
- Rasterising SVG bases (D-90 rejected it).
- A music path in the MockClient: it stays procedural, as a demo with no network.

## Decisions

### D1. A dedicated music client, not `ChatClient`

**Decision.** Add `gateway/music.py`, with a `MusicClient.generate(model, prompt) -> MusicResult(generation_id, audio, usage, provider)`, and `Gateway.generate_music(ctx, *, model, prompt, before_send, after_response, commit_with)`, which goes through `paid()` with estimate `prices.generation["song"]`.
- **Body:** `{model, messages: [{role: "user", content: prompt}], modalities: ["text","audio"], stream: true, usage: {include: true}}`, with no `provider` block and no `models` list.
- **Streaming:** it reuses `HttpCore.stream` and the SSE line handling of `ChatClient.stream`:
  - `data:` lines, `[DONE]`;
  - the generation id from the first chunk;
  - error chunks become `provider_error` with `maybe_charged`.
- **Output:** it concatenates the `delta.audio.data` strings and base64-decodes them once at the end. Usage comes from the final chunk.
- **Malformed:** no audio at all → `malformed("music stream")`, which may have been charged.

**Why.**
- The pinned DeepSeek routing (`require_parameters: true`, an order list) and the chat fallback model would at best be ignored, and at worst route a music request to a text model.
- Images already proved that one client per modality keeps the request shapes testable (provider-gateway "Image request shape").

**Alternative considered.** A `ChatRequest.extra` override on `ChatClient`. Rejected: `body()` always injects routing and fallback, and changing that would put every chat call at risk.

### D2. Timeouts

Add `music` to `gateway.timeoutsMs` (`frontend/src/mock/pricing.config.ts` → `seed/pricing.json`), at **120 000 ms**: the deadline for the first audio chunk, since Lyria is expected to send the clip late in the stream. Between chunks, the existing `chatIdle` (30 s) applies. Our own timeout after send is `timeout` with `maybe_charged` (existing semantics).

The live check (D9) records the real latency. If it differs widely, only these numbers change.

### D3. The SongGenerator port becomes async and paid-aware

```
class SongGenerator(Protocol):
    model: str
    paid: bool                                   # False: procedural ($0, no row); True: one music call
    def expected_ms(self, duration_ms: float) -> float: ...
    def theme(self, seed, brief, title) -> dict  # the procedural spec (both, used for the fallback)
    async def generate(self, ctx, job: SongJob, hooks: PaidHooks) -> bytes   # paid generators only
```

- **`ProceduralSong`** (scripted): `paid = False`; `expected_ms` returns the timing table's `songMs`; `generate` is never called.
- **`NaiveSong`** (in `ai/naive/creation.py`, following `NaiveDrafter`'s hooks pattern):
  - `paid = True`, `model` from the job, `expected_ms = NAIVE_SONG_LATENCY_MS` (17,000: the D9 live run measured 16.3 s);
  - `generate` builds the prompt (D4) and calls `gateway.generate_music`;
  - its `after` hook validates the bytes (D6) and only then forwards them to `hooks.after_response`, so unusable audio is still recorded as a charged call (the pipeline records a row when `after_response` raises).
- **Registration.** `profile.py` registers `"song": NaiveSong(d)` in the naive builders. `HORIZON_AI_SONG` already works through the per-port override.

### D4. The prompt (deterministic, from the brief)

`song_prompt(brief, title)`, a pure function in `ai/naive/creation.py`:

> `Instrumental theme music for "{title}". Genres: {genres}. Mood: {moods}. Tempo: about {bpm} BPM. Instruments: {instruments}. Feel: {vibe}. No vocals, no lyrics. A 30-second piece that loops cleanly.`

Empty lists are left out. It is unit-tested against a fixed brief (the ai-ports "Naive song prompt comes from the brief" scenario). There is no LLM brief-writer call: the brief is already structured by the drafter, so an extra paid call adds nothing (doc 05 §2.2: the brief comes from the draft or the user's edit).

### D5. Pricing, reservation and pacing follow the port

- `plans.task_spec(..., song_paid: bool)`: when paid, `theme_song` → `TaskPlan(est_usd=g["song"], price_kind="song", category="music")`; otherwise it stays as it is today ($0).
- Every caller (`plan` for estimate and start, recovery, retry) passes `rt.ai.song(True).paid`, through one `sched.song_paid()` helper. `jobs.estimate` in naive therefore shows $0.04, which matches the mock.
- `task_ctx` labels the call `purpose="song"`, `category="music"` (a `PURPOSE` entry). `CATEGORY_FOR["song"] = "music"` already exists in `gateway/context.py`.
- The music call runs inside `Slot(rt.music_slots)` (1).
- `expected_ms` and pacing:
  - `song_paced()` is replaced by the port's `expected_ms`;
  - a scripted song still sleeps `songMs` on the backend clock;
  - a naive one reports progress against `NAIVE_SONG_LATENCY_MS`.
- The scripted profile is unchanged: $0, no row (D-83 stays true for scripted, and D-81 is untouched elsewhere).

### D6. Audio validation, storage and the ThemeSong row

- **`storage/audio.py`** (pure Python, no dependency):
  - `is_mp3(data)`: an ID3v2 header, or an MPEG audio frame sync (`0xFFE` with a valid layer, bitrate and sample-rate index);
  - `mp3_duration(data)`: skip ID3v2, walk the frame headers (MPEG-1/2/2.5 Layer III) and sum `samples_per_frame / sample_rate`. If no frame parses, it returns `None`.
  - **Limits:** `MAX_SONG_BYTES = 8 MB` (a 30 s clip at 320 kbps is about 1.2 MB). More is unusable audio.
- **Unusable audio** (not MP3, too large, no frames) → `ProviderError("provider_error", "The music provider returned audio we couldn't use.")`, raised in NaiveSong's `after` hook, so it is billed and falls back (D7).
- **The original** goes through the existing `hooks_for` path: `after_response` writes `originals/…/{task}_{attempt}.mp3` atomically. `EXT` and `sniff` grow an `mp3` entry, or the worker picks the extension from `is_mp3`. Then `commit_with` sets `result_ref` and the cost in the ledger row's transaction. This is unchanged never-pay-twice ordering.
- **The derived file.** `finish()` for `theme_song`:
  - with an `originals/*.mp3` result → `apply_audio_theme(conn, ch, original=bytes, brief, model, cost, job_id)`;
  - this writes `assets/gen/{world}/{char}/song_v{N}.mp3` (a byte copy through the existing atomic `write_file`, before the transaction commits);
  - it sets `status: ready`, `format: "mp3"`, `bytes`, `duration_sec = mp3_duration or 30`, `instrumental: true`, `generation: {model, prompt, costUsd: task cost, jobId}` and `license_note = "Composed by {model} through OpenRouter."`.
- **Version numbering** is shared with `apply_theme`: a new version every time, so names are never reused.
- `assets.song_rel(world, char, version, ext="proc.json")` gains the extension.
- **Recovery** needs no new rule. A task with a stored `.mp3` original only re-derives (free). A task sent with no result becomes `failed` (retryable), as for images.

### D7. When the song falls back to the procedural theme (the R-05 rule)

The rule runs at the end of the music call, inside `worker.call` for `theme_song`:

| Outcome of the music call | Task result | User sees | User pays |
|---|---|---|---|
| MP3 received and valid | `succeeded`, MP3 version | the Lyria song | the reported cost (or the $0.04 estimate, then corrected) |
| `provider_error` (5xx, other 4xx, error chunk, malformed stream, unusable audio) | `succeeded`, procedural version | a procedural theme; licenseNote: "Lyria was unavailable, so this is the procedural theme. Regenerate to try again." | a charge only if one may have been made (`maybe_charged` / reported cost), else $0 |
| `timeout` | same as above | same | the estimate when sent (`maybe_charged`), corrected later by the CostCorrector |
| `content_refused` | same as above | same | the reported cost, if any |
| `rate_limited` (429) | same as above | same | $0 |
| `missing_key` / `invalid_key` | `failed` (as today) | O05 key prompt | $0 |
| `insufficient_credits` (402) | `failed`, not retryable until credits change (as today) | the error | $0 |
| `daily_budget_exceeded` / `creation_budget_exceeded` (preflight) | `failed` (as today), no request sent | O21 budget overlay | $0 |
| test-mode `song_fails` fault | `failed`, retryable (mock parity) | Retry | $0 |
| process stops mid-call | `failed`, retryable (never-pay-twice recovery) | Retry | whatever was recorded |

**Mechanics.**
- `call()` catches a `ProviderError` whose code is in `SONG_FALLBACK = {"provider_error", "timeout", "content_refused", "rate_limited"}` and returns `Fallback(reason)`. Any charge has already been recorded by `paid()`.
- `run_attempt` passes the outcome to `finish` → `commit_result(..., fallback=reason)`, which applies `theme()` through `apply_theme` with the fallback licenseNote. It sets `generation.costUsd` to the sum of the task's ledger rows. It sets the job's `actual_cost_usd` from the job's rows, as `commit_with` does today.
- The fallback is not stored durably before commit. A crash between the failed call and the commit is the "sent with no result" case: the task is `failed` (retryable), never a silent second call.

**Why fall back on these, and fail on the rest.**
- The fallback cases are provider-side faults the user can't fix. R-05 promises an ambient bed rather than silence, and a procedural theme is free.
- The failing cases need the user to act (add a key, top up credits, raise a cap). A free substitute would hide that. These codes already have overlays (O05, O21), and the generic `fail()` path keeps image and song behaviour the same.
- There is no automatic second Lyria attempt: a retry is the user's Regenerate, the only way a provider is paid again (generation-jobs "Retry a failed task"). The only automatic resend is `HttpCore`'s existing one, for a connect failure or an empty 429/5xx body, where nothing can have been charged.

**Alternatives considered.**
- Fail the task and let the user Retry (no fallback). Rejected: with Lyria at 6 % uptime that day, most songs would end up failed, which contradicts R-05.
- Fall back on every error, budget included. Rejected: it masks caps and key problems.
- Skip the call when the free probe says the model is unlisted. Rejected: the probe runs after start and is informational. Gating on it would add a race, and a delisted model fails fast with a 404 → `provider_error` → fallback anyway.

### D8. The music-model probe and the model ID

- `models.music` changes to `google/lyria-3-clip-preview` in these places:
  - `MODELS.music` in `pricing.config.ts`;
  - the seed ledger builder (`ledger.ts` reads `MODELS.music` instead of the literal);
  - the fallback labels in `ThemeStep.tsx` and `ThemeTrack.tsx`;
  - then `seed:build`.
- **Existing installs need no migration.** `settings_doc()` is the seed file overlaid by `settings.local.json`, and `PATCH /settings` ignores `models` (`IGNORED_TOP`), so no install stores a music model. The new seed value applies at the next start.
- **The probe.** `_probe_music` still runs once per song job start, only in naive. Its log line becomes "music model X is listed/not listed on OpenRouter; the song job calls it, with the procedural fallback (D-87)".

### D9. Live check (manual, ≤ $0.05, user approval required)

`tests/live/test_live_jobs.py::test_live_song` is marked `live`, so it is deselected by default:
- one naive `song` job for the seed character Hana (no draft call needed), with a daily cap of today's spend + $0.05;
- it asserts either:
  - (a) an MP3 song (`format == "mp3"`, `durationSec` between 5 and 40, one music ledger row ≤ $0.05); or
  - (b) a fallback with the licenseNote, recorded as "Lyria unavailable at run time";
- it prints only the request shape, the chunk count, the byte size, the detected format, the duration, the latency and the cost. It never prints the key; the key is checked only for presence.

The result is recorded in this design (D9 record) and in tasks.md. If the real response differs from D1 (for example, the audio needs an `audio: {format: "mp3"}` request field, or arrives in `message.audio` without streaming), D1 changes before archive. It runs **only after the user explicitly approves the spend**.

**D9 record (2026-10-08, approved by the user, one run, $0.04):**
- Lyria 3 Clip worked through the D1 request exactly as designed. Model `google/lyria-3-clip-preview`, served by Google AI Studio. The request was streamed with `modalities: ["text","audio"]`, with no `audio` config, no routing block and no fallback model.
- **Audio:** it arrived as **one** `delta.audio.data` piece (679,456 bytes) starting with an ID3v2 tag (`49 44 33 03`). `is_mp3` accepted it, and the frame walk read **28.056 s**.
- **Latency:** 16.3 s from send to the end of the stream, inside the 120 s first-audio deadline (D2). `NAIVE_SONG_LATENCY_MS` is now 17,000.
- **Cost:** `usage.cost` was reported in the stream as **$0.04**. The ledger row is `music` / `song`, $0.04, `cost_source: provider`, so no CostCorrector pass is needed.
- **Result:** the job succeeded, the song is `song_v2.mp3` with `format: "mp3"`, `durationSec: 28.056` and the Lyria licenseNote. The total was $0.040000, under the $0.05 cap.
- No change to D1 was needed.

### D10. D-90: one place in the client

- `startGeneration()` catches the error and calls `toHorizonError(err)`. When `code === "validation" && details?.reason === "base_not_raster"`, it shows the toast:
  > "Generate a portrait first. This character's portrait is a placeholder drawing the image model can't edit."
  - action `{label: "Generate a portrait", run: () => navigate({name: "wizard", worldId, characterId, step: "portrait", ...(approved ? {edit: true} : {})})}`;
  - `worldId` and the status come from the entity store (`entities.getState()`), or from `client.characters.get(characterId)` when the store doesn't have the character.
- **Why there.** Every emotion edit and tweak start (wizard `EmotionsStep`, profile `tabs.tsx` gallery, `EmotionLightbox`, `PortraitStep` tweak) goes through `startGeneration`, so one branch covers them all. `reportError` stays generic.
- **Testing.**
  - A Vitest unit test stubs `client.jobs.start` to throw `HorizonError("validation", …, {reason: "base_not_raster"})`, and asserts the toast text, the action label and the navigation target, for a draft and for an approved character.
  - The backend `_check_base` test already exists (`test_naive.py`, reason `base_not_raster`); a "no reservation" assertion is added to it.
  - No `/_test` scenario. The portable suite runs the scripted image generator, which never raises it, and adding API surface just for this is not worth it.

### D11. D-89: hide, don't delete

- Remove the `Row` with the toggle from `CostTab.tsx`. The contract field, the settings API, the seed value and the MockClient stay.
- A Vitest/RTL test (or e2e, whichever the settings tests already use) asserts the Cost tab has no "Auto-generate missing emotions" control.
- `grep` confirms nothing in `frontend/src` or `backend/horizon` reads the value to start a job. The budget-caps "Stored value has no effect" scenario is covered by that review plus the existing job-start tests; no new runtime code.

## Risks / Trade-offs

- **[Lyria preview availability is poor (6 % uptime that day)]** → the fallback (D7) keeps every song job useful. The licenseNote tells the user to Regenerate later. Cost is bounded per attempt.
- **[The real response shape differs from the docs]** → D1 is isolated in one client with a fake-backed test. The live check (D9) is the gate before archive, and the fix is local.
- **[A charged failure plus a fallback means the user pays $0.04 for a free theme]** → unavoidable when the provider billed. It is shown honestly in the ledger and on the song's `generation.costUsd`. The CostCorrector fixes estimate rows from the generation id.
- **[MP3 duration parsing of VBR or unusual streams]** → fall back to 30 s (the Clip length) when frames don't parse. `durationSec` is informational only, because the player decodes the real length.
- **[Larger files under `gen/`]** → about 1 MB per song version. The factory reset and delete-character purge already remove the character's `gen/` directory. The sweeper only deletes files no record references.

## Migration Plan

- No database schema change. `theme_songs` already has `format`, `bytes` and `duration_sec`.
- No settings migration: `models` is seed-owned (D8).
- Seed regeneration (`seed:build`) for `settings.json`, `pricing.json` (the music timeout) and the ledger rows. `seed:check` must pass.
- Rollback: revert the branch. Stored MP3 song versions stay playable by URL, because the frontend needs no change to play them.

## Open Questions

- None left. The D9 live check answered both earlier unknowns: the latency is 16.3 s (`NAIVE_SONG_LATENCY_MS` 17,000), and `usage.cost` is reported in the stream ($0.04, `cost_source: provider`).

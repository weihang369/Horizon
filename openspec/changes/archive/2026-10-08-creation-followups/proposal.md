# Proposal: creation-followups

## Why

M4 (`generation-jobs`) shipped character creation on the backend and left three open questions, all closed on 2026-10-06:
- **D-87.** OpenRouter now lists `google/lyria-3-clip-preview` at $0.04 per 30 s clip, the price the mock already shows. Real theme songs no longer need to wait for a music model.
- **D-89.** The `autoGenerateMissingEmotions` toggle is visible but does nothing. If built, it would pre-authorise spend (NFR-30).
- **D-90.** A naive emotion edit on a demo character's SVG placeholder base fails with a generic error toast.

This change implements the three decisions, nothing else.

## What Changes

- **Lyria 3 Clip theme songs in the naive profile (D-87, supersedes D-83's premise).**
  - A naive `SongGenerator` makes one streamed chat call to `google/lyria-3-clip-preview`, using `modalities: ["text","audio"]` and audio returned as base64 `delta.audio` chunks.
  - The call is made through the existing paid-call pipeline: caps, holds, mark-before-send, the original stored first, and the ledger row committed with the result.
  - It is priced at `pricing.generation.song` ($0.04): the estimate, the job reservation and the ledger row (`category: music`, `purpose: song`) all use that price.
  - The MP3 is kept in `originals/`, then copied under `assets/gen/` as `song_vN.mp3`. It becomes a new active `ThemeSong` version with `format: "mp3"`, `bytes`, `durationSec`, `generation.model` and a Lyria `licenseNote`.
- **Procedural fallback (R-05).** When Lyria can't make the song, the task still succeeds with the free procedural theme (`.proc.json`), and its `licenseNote` says why. This covers a provider error, a timeout, a refusal, a rate limit or unusable audio. A charge the provider may already have made is still recorded. A missing or invalid key, no OpenRouter credits, or a reached cap still fail the task as today. The exact rules are in design.md.
- **The scripted profile is unchanged.** It keeps the free procedural theme ($0, no ledger row, D-83). The test-mode `song_fails` fault keeps failing the task (mock parity).
- **Model ID.** `models.music` becomes `google/lyria-3-clip-preview` in `seed/settings.json` (from `frontend/src/mock/pricing.config.ts`), the seed ledger and the UI fallback labels. The free music-model probe and its log line change from "uses the procedural theme" to "calls it, with the procedural fallback".
- **Hide `autoGenerateMissingEmotions` (D-89).** The Cost tab stops showing the toggle. The stored setting, the contract field, the seed value and the backend stay unchanged, and nothing acts on it.
- **"Generate a portrait first" (D-90).** The API keeps `validation` with `details.reason: "base_not_raster"`. Every place an emotion edit or a portrait tweak starts turns that error into the message "Generate a portrait first", with a button that opens the portrait step: in the wizard, or the wizard in edit mode for an approved character.
- **One paid live check (≤ $0.05).** It is skipped by default and runs only on the user's explicit approval. It records the real request and response shape, the format, the duration and the cost in design.md.

No contract change: rev 1.3 `ThemeSong` already carries `url`, `format: "opus" | "aac" | "mp3"`, `bytes` and `durationSec`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ai-ports`:
  - the profile-selection rule lists the song generator among the ports with a naive implementation;
  - the song generator requirement covers the Lyria call in naive and the procedural theme in scripted.
- `provider-gateway`: a new music request shape (streamed chat with audio output, no pinned DeepSeek routing and no fallback chat model, audio read from `delta.audio.data`, cost from `usage.cost`).
- `generated-assets`: the theme-song requirement covers an MP3 version from Lyria, the procedural theme in scripted, and the procedural fallback when Lyria fails.
- `generation-jobs`: a new requirement that naive edits need a raster base, with the client turning `base_not_raster` into "Generate a portrait first".
- `budget-caps`: a new requirement that no setting pre-authorises generation spend (the `autoGenerateMissingEmotions` toggle is hidden, and nothing acts on it).

## Impact

- **Backend:**
  - `ai/naive/creation.py` gets a new `NaiveSong`, and `ai/ports.py` a new `SongGenerator` protocol shape;
  - `ai/profile.py`, `ai/scripted/creation.py`;
  - `gateway/` gets a music client and `Gateway.generate_music`;
  - `gateway/fake.py` gets a streamed audio route;
  - `services/jobs/{plans,scheduler,worker,apply}.py`, `services/theme.py`, `services/assets.py`;
  - `storage/` gets an MP3 sniff and a duration reader.
- **Frontend:**
  - `features/settings/CostTab.tsx`;
  - `features/wizard/generate.ts`, so every job starter gets the D-90 message;
  - the fallback model labels in `ThemeStep.tsx` and `ThemeTrack.tsx`;
  - `mock/pricing.config.ts` and `scripts/seed-build/ledger.ts`, then a seed rebuild.
- **Seed:** `seed/settings.json` (`models.music`), seed ledger rows and `seed/pricing.json` (a music timeout), all regenerated by `seed:build`.
- **Docs:** `docs/backend/04` §1 (the music row), `docs/backend/05` §2.2 (the SongGenerator row) and `docs/requirements/09` (D-83 marked superseded in part by D-87).
- **No new dependencies.** The MP3 duration is read by a small pure-Python frame-header walk.
- **Cost:** naive songs now cost $0.04 each. The only paid test is the approved live check (≤ $0.05).

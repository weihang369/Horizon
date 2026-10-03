# Design: contract rev 1.3 (M1a)

## Context

See proposal.md for the motivation and specs/ for the behaviour. What the code looks like today:

- **Contract.**
  - `frontend/src/contract/types.ts` is the TypeScript contract and `schemas.ts` the zod 4 mirror. `satisfies z.ZodType<T>` ties the two together.
  - `ID_RE = /^[a-z]+_[0-9A-Za-z]{1,40}$/` already accepts any prefix. The `id(prefix)` helper checks a specific one.
  - `errors.ts` holds `HorizonError`, `ERROR_COPY` and `DEFAULT_RETRYABLE`, all keyed by `ErrorCode`. Adding a code is a compile error until all three are filled in, which is what we want.
- **MockClient.** `frontend/src/mock/MockClient.ts` (1,127 lines) misuses error codes:
  - missing records are thrown as `network` ("Session not found.");
  - rule violations are thrown as `provider_error` ("Seed sessions are replay-only", "This mode needs 2–4 characters").
- **Character delete** hard-deletes the character plus its memory and knowledge. `char()` treats `deletedAt` as missing.
- **Reset.** `resetDemoData` lives on the mock-only `dev` API. It clears the snapshot and calls `hardReset(default)` **without** `keepUserData`, so user worlds and forks are lost. The Settings screen, the World Select screen and the dev switcher reach it through `stores/mock.ts`.
- **Top-up** costs `points × usdPerPoint` in the ledger and the gate. That double-counts the replies it funds, which D-76 fixes.
- **Energy.** `energy.ts` uses a fixed `EST_REPLY_POINTS` threshold, and the mock always calls `energyState(current, max)` with the off-peak default. So at peak the UI and the gate disagree with D-78.
- **Seed.** `scripts/seed-build` generates `seed/`, and `seed:check` re-generates it in memory and diffs.
  - The candidate IDs `cand_1` and `cand_2` repeat for every character.
  - Model IDs come from `mock/pricing.config.ts` (`MODELS`), and `qwen/qwen-image-3` is still there.
- **Tests.** `clientContract.test.ts` (16 tests) builds a `MockClient` directly and reaches into `c.dev` (scenarios and reset) in 4 tests.
- **No `backend/` directory exists yet.** This change creates only `backend/horizon/contract/schema.json` and `backend/tests/fixtures/`.

## Goals / Non-Goals

**Goals**

- One contract, frozen enough for M1b to generate Pydantic models from and validate responses against `schema.json`.
- The MockClient behaves like the designed backend wherever the user can see the difference.
- Fixtures that the Python port (M1b reducer, M2 energy) must pass unchanged.

**Non-Goals**

- **The knowledge drop zone and the cover upload stay unwired in the UI** (OQ-3). The new methods are exercised by the contract suite.
- No backend runtime code, no Python tooling, and no root `package.json`. Those are M1b.
- No visual redesign. The only UI edits are copy changes and a badge.

## Decisions

### D1: Rev 1.3 lands as one additive edit to types, schemas and doc 05
Each doc 03 §7 item maps to one edit in `types.ts`, its zod twin and the doc 05 table.
- **Optional on the wire, required in settings.** New fields are optional wherever old fixtures lack them. `models.embedding` and `energy.estReplyPoints` are the exceptions: they're required in `AppSettings`, because the seed is regenerated in the same change.
- **Alternatives considered:**
  - Bump `SCHEMA_VERSION` to 2: rejected, because every change is additive.
  - Ship the items in separate commits: rejected, because `satisfies` makes partial states fail to compile anyway.

### D2: Errors: add codes and centralise the not-found and conflict throws
- Add `not_found`, `validation` and `conflict` (non-retryable, with copy) and `details?: Record<string, unknown>` to `HorizonErrorShape` and to `toJSON`.
- In the MockClient, add small helpers (`notFound(kind)`, `conflict(msg, details?)`, `invalid(msg, details?)`) and switch every misused throw to them. The `network` and `provider_error` throws that model real transport or provider failures in scenarios stay as they are.
- **Alternative considered:** leave the mock as it is and map codes only in the HttpClient. Rejected, because the portable suite would then pass on one client and fail on the other.

### D3: Knowledge in the mock: a timed fake pipeline on the Scheduler
- **Adding a source:** `addKnowledge` validates first (type by extension and MIME, 10 MB, 20 sources, duplicate content hash → `conflict`). It then creates `kno_*` with `status: "indexing"` and schedules stage ticks on the mock Scheduler (`extracting` → `chunking` → `embedding`). Each tick emits `entity.changed {kind:"knowledge", id, progress}`.
- **Chunking:**
  - pasted text splits on blank lines, with `¶ n` locators;
  - files get synthetic passages ("p. n") built from the file name, because the mock can't parse a PDF.
- **Key or no key:**
  - **with a key:** the final status is `indexed` and an `embedding` ledger row is written (tokens ≈ chars/4 at the seed embedding price);
  - **without a key:** the final status is `keyword_only`, with no ledger row.
- **Reindex** re-runs the same pipeline. **Delete** removes the source and its chunks; citations already carry the title and quote.
- **Why the Scheduler:** it already drives demo-speed and ManualClock time, so tests stay deterministic.
- **Alternative considered:** instant indexing. Rejected, because the UI would then never exercise the `indexing` state or the progress events.

### D4: The tombstone is a flag, not a separate record
- `delete` sets `deletedAt` and strips the record down to id, worldId, name, palette and neutral portrait (`emotions` other than neutral become `null`; `blink` is dropped). It removes memory, knowledge, chunks, songs, non-neutral assets and non-terminal jobs, and emits `entity.changed`.
- **Reads:** `get` returns tombstones. `list` and `World.characterCount` skip them.
- **Commands:** they go through `liveChar()`, which rejects tombstones with `not_found`.
- **Conflict:** delete rejects with `conflict` while the character is in a live session that is currently streaming.

### D5: Reset demo data keeps user data
- `resetDemoData` becomes `hardReset(default, { keepUserData: true, seedWins: true })`. Every record whose ID exists in the seed dataset is overwritten with the seed copy; every other record is kept. Ledger rows from the seed are replaced and user rows kept.
- **Scenario overlays** keep today's "user data wins" merge.
- **Why IDs and not `isSeed`:** `MemoryItem`, `KnowledgeSource` and `UsageRecord` have no `isSeed`, and seed IDs are stable (`*_seed*`). This matches doc 02 §4 ("upsert seed, keep user").
- **"Restore demo data"** on the empty World Select screen does the same thing.

### D6: The top-up gate is pure domain logic
- `domain/energy.ts` gains `canTopUp({ spentTodayUsd, todayTopUpPoints, points, usdPerPoint, dailyCapUsd })` (with the same 1e-9 tolerance) and `dayRoll(e, todayKey)`.
- The mock derives `todayTopUpPoints` from today's `energy_topup` ledger rows, then writes the row with `costUsd: 0`.
- `TopUpEnergy.tsx` keeps its layout. The "≈ US$" figure now reads as "uses ≈ US$x of today's budget headroom", and a refusal shows `ERROR_COPY.daily_budget_exceeded` inline.

### D7: One threshold, period-aware everywhere
- `AppSettings.energy.estReplyPoints` is filled in from `EST_REPLY_POINTS`.
- Every mock call to `energyState`, `settle`, `drain` and `topUp` passes `estReplyPoints[period()]`. The UI's `liveEnergy` callers read it from settings. The routing skip check uses the same value.

### D8: The schema export uses zod 4's `z.toJSONSchema`
- `scripts/export-schema.ts` runs through the existing `tsconfig.scripts.json` and the `run.mjs` pattern. It builds one document with `$defs` for every exported `*Schema`, plus `SessionEvent` and `GlobalEvent`.
- **Determinism:** it sorts keys recursively, writes UTF-8 without a BOM with `\n` line endings, and adds a trailing newline.
- `npm run export-schema` writes to `../backend/horizon/contract/schema.json`. `npm run export-schema -- --check` diffs it, so CI can guard against drift as `seed:check` does.
- **`GlobalEvent` has no zod schema today.** One is added (D9), because M1b validates SSE against it.
- **Alternative considered:** `zod-to-json-schema`. Rejected, because it adds a dependency and zod 4 has the feature built in.

### D9: New zod schemas for the client-surface types
Add `GlobalEventSchema`, `JobEventSchema` and `HorizonErrorShapeSchema` (the error envelope body), so `schema.json` covers everything the backend emits.

### D10: Contract suite split with a harness
- **`clientContract.portable.ts`** exports `runPortableContract(makeHarness)`. A harness provides `{ client, advance(ms), setScenario(id), reset(), setKey() }`.
- **`clientContract.mock.test.ts`** runs the portable suite with the mock harness, plus the mock-only tests (`_db` assertions, demo speed).
- **M1b** adds an HTTP harness backed by `/_test/*`.
- New portable tests cover every scenario in the client-contract, knowledge, lifecycle, demo-data, energy and worlds specs.

### D11: Shared fixtures: data in `backend/tests/fixtures`, runners in each language
- **`energy/cases.json`** holds `{ name, fn, input, expected }` cases for regen, drain, pointsForCost, state (both periods), canTopUp and dayRoll.
- **`reducer/*.json`** holds small `{ events, expected: { messages, session } }` cases: insight replacement, variants, interruption, manual emotion and `session.state` patches. The full seed sessions remain the big equivalence test and aren't copied.
- **Runners:** `energy.fixtures.test.ts` and `sessionReducer.fixtures.test.ts` read them through a relative path from the repo root.

### D12: Seed fixes go through the build sources only
- **`pricing.config.ts`:**
  - Jev `inputPerM` and `cachedInputPerM` are 0.042, and `outputPerM` is 0;
  - every `generation` image price is 0.018;
  - a new `embedding: { model: "qwen/qwen3-embedding-8b", provider, inputPerM: 0.01 }` entry is added, and `PricingTable` gains `embedding`.
- **`MODELS`** gets `image: "bytedance-seed/seedream-5-0-flash"` and `embedding`.
- **`data/knowledge.ts`:**
  - Amara's source becomes `type: "file"`, titled "ED triage guidelines.pdf", with `pages` and without `url`;
  - Mei's CSV is replaced, per OQ-4.
- **`data/characters.ts`:** candidate IDs become `cand_<charKey><n>`.
- After these edits, `seed:build` regenerates the seed, then `seed:check` and `fixtures.test.ts` must pass.

## Risks / Trade-offs

- **[A changed seed changes the public Vercel demo]** → No IDs change except candidate IDs, so stored browser snapshots keep working. The mock snapshot hash changes and forces a re-seed, which is acceptable for a demo.
- **[Reset semantics change for users who relied on "wipe everything"]** → In the mock, clearing site data still wipes everything. A "factory reset" is a backend-only concept (doc 03).
- **[`z.toJSONSchema` can't represent `.refine` (`isoDate`, `assetUrl`)]** → Export those as `type: string` with `format: date-time` or `pattern` annotations through zod's `override` hook, and test that every `$def` is present.
- **[Bigger MockClient]** → Put the knowledge pipeline in `mock/engines/knowledge.ts` and keep MockClient as the router, like the existing engines.
- **[E2E selectors tied to seed text]** (Mei's CSV, the triage source glyph) → Update `profile-knowledge-theme.spec.ts` and `citations.spec.ts` in the same change.

## Migration Plan

This is a frontend-only change on `feat/backend-api`:
1. Land everything, run `seed:build` and the export, and get all tests green.
2. `openspec archive`, then squash-merge to `dev`.
3. To roll back, revert the squash commit. Nothing persists outside `seed/` and the browser snapshot, which re-seeds on hash change.

## Open Questions

These are conflicts between the docs and the code. Each one has a **proposed default**, and the tasks assume it; confirm or override any of them before `/opsx:apply`.

- **OQ-1: energy is stored as REAL (doc 04 §4, D-78) but `energy.ts` floors `current` on every settle.**
  - **Default:** follow the doc. `settle`, `drain` and `topUp` keep the fractional `current`, and only `liveEnergy`'s returned value and the `energy` event payload are floored.
  - **Effect:** the fixtures encode the REAL behaviour, so the Python port matches.
- **OQ-2: seed knowledge status.** On the backend, seed sources are `keyword_only` until the user runs "Index seed knowledge" (doc 02 §6). The mock shows them as `indexed`.
  - **Default:** the mock keeps `indexed`, so the Vercel demo's citations and the "indexed" badges stay as they are. The difference is noted in doc 05.
- **OQ-3: UI wiring for the new commands.** No milestone in doc 06 owns wiring the knowledge drop zone, the delete and reindex controls, or cover upload into the UI.
  - **Default:** M1a fixes the copy and adds the badge only. Wiring moves to M5 (knowledge) and M4 (cover), and doc 06 gets one line each.
- **OQ-4: what replaces Mei's failed CSV?** It's the only `failed` source in the seed, and an E2E test covers the failed state.
  - **Default:** a failed `type: "file"` source, "Working-time pilots appendix.docx", with the error "This document is password-protected. Remove the password and add it again." The E2E test only changes its title.
- **OQ-5: reset is not on `HorizonClient`.** The UI calls the mock-only `dev.resetDemoData`, while doc 03 has `POST /admin/reset-demo`.
  - **Default:** M1a keeps the dev API, and its semantics change per D5. M1b adds `HorizonClient.admin.resetDemo()` as a rev 1.3 addendum, so the HttpClient can call it.

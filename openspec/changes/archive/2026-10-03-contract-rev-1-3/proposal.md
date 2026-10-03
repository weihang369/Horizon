# Proposal: contract rev 1.3 (M1a)

## Why

The backend design pack (`docs/backend/`, v1.0) changed the shared contract: it adds knowledge commands, cover upload, error codes, one energy threshold, the top-up gate, tombstones and seed-only reset. The FastAPI backend (M1b onwards) is built and tested against that contract. So the frontend contract, the MockClient and the seed have to move first, or the two clients will disagree from day one. This is milestone **M1a** (doc 06), and it is frontend-only.

## What Changes

**Contract (additive; `SCHEMA_VERSION` stays `1`).** Updates `types.ts`, `schemas.ts`, `errors.ts`, `HorizonClient.ts` and doc 05 (doc 03 §7 items 1–12):

- `ErrorCode` gains `not_found`, `validation` and `conflict`. `HorizonErrorShape` gains `details?`.
- New ID prefixes: `kno_`, `kch_`, `ksec_`, `cmd_`.
- **Knowledge sources:**
  - `KnowledgeSource.status` gains `keyword_only`.
  - `type: "url"` stays as legacy, read-only. Nothing creates it any more.
- **New client methods:**
  - `CharactersApi` gains `addKnowledge`, `deleteKnowledge` and `reindexKnowledge`.
  - `WorldsApi` gains `uploadCover`.
- **Embedding:**
  - `AppSettings.models.embedding` is added, and `testModel` accepts `"embedding"`.
  - `UsageRecord.category` gains `"embedding"`.
- `AppSettings.energy.estReplyPoints` is added (read-only, D-78).
- `TurnTrace.calls[]` is added (every paid call behind a turn).
- **Events:**
  - `entity.changed` gains `progress?`.
  - The global stream carries `task.update`.
  - `mock.reset` is documented as a backend event too.
- **Doc 05 §6 catches up with the code:** `turn.start.message?`, `energy.spent?`, `error.messageId?`, and "a later `insight` for the same `messageId` replaces the earlier one".

**MockClient parity** (item 13):

- It uses the new error codes, replacing today's `network` / `provider_error` misuse for missing records and bad input.
- Mocked knowledge add, delete and reindex, with status progress.
- Mocked cover upload.
- Character delete leaves a **tombstone**.
- **Reset re-seeds seed data only**, so user forks survive.
- The **top-up gate (D-76)**: the ledger row costs $0, and top-ups are bounded by the daily cap.
- It exposes `estReplyPoints` and mirrors `task.update` onto the global stream.

**Seed fixes**, made through `scripts/seed-build` and `pricing.config.ts`, then `seed:build`:

- the D-61 image model, Seedream 5.0 Flash at $0.018 per image;
- Jev at $0.042/M input with free output;
- an embedding price entry;
- Amara's "ED triage guidelines" becomes a `file` source;
- Mei's CSV source is removed;
- candidate IDs become globally unique.

**Tooling:**

- `npm run export-schema` writes `backend/horizon/contract/schema.json`, byte-identical on every run.
- `clientContract.test.ts` is split into a portable suite (any `HorizonClient`) and a mock-only suite.
- Shared JSON fixtures for energy and the reducer go in `backend/tests/fixtures/`. The TS tests consume them now, and the Python tests will from M1b/M2.

**Small, necessary UI updates:**

- The knowledge drop-zone copy changes to "PDF, DOCX, MD, TXT or pasted text".
- A `keyword_only` badge is added.
- The top-up dialog shows the D-76 refusal message.
- Nothing else in the UI changes.

**Not in this change:**

- any FastAPI code (only `schema.json` and `tests/fixtures/` are created under `backend/`);
- the HttpClient (M1b+);
- `chat.continue` (deferred);
- any AI pipeline work.

## Capabilities

### New Capabilities

- `client-contract`: the wire contract shared by the MockClient, the HttpClient and the backend. It covers types, zod schemas, error codes and envelope, ID prefixes, stream and global events, the `HorizonClient` method surface, the JSON Schema export and the portable contract suite.
- `knowledge-sources`: a character's knowledge sources. It covers the accepted input types, status lifecycle (`indexing → indexed | keyword_only | failed`), and the add, delete and reindex behaviour.
- `character-lifecycle`: what deleting a character means (a tombstone that keeps transcripts rendering) and how tombstones are read.
- `demo-data`: the shipped seed dataset (prices, models, sources, unique IDs) and **Reset demo data** (re-seed seed records only, keep user data).
- `energy`: the energy rules shared by the UI and backend. It covers the single `estReplyPoints` threshold, the top-up gate (D-76), and the shared cross-language fixtures.
- `worlds`: world cover upload.

### Modified Capabilities

None. `openspec/specs/` is empty: this is the first OpenSpec change in the repo.

## Impact

- **Code:**
  - `frontend/src/contract/{types,schemas,errors}.ts` and `frontend/src/client/HorizonClient.ts`;
  - `frontend/src/mock/MockClient.ts`, `mock/engines/jobs.ts` and `mock/pricing.config.ts`;
  - `frontend/src/domain/{energy,cost}.ts`;
  - `frontend/scripts/seed-build/**` and the regenerated `seed/**`;
  - `features/profile/tabs.tsx` (copy and badge), `features/session/TopUpEnergy.tsx` (refusal copy) and `features/settings/SettingsScreen.tsx` (reset wording);
  - tests: `clientContract.test.ts` (split), `energy.test.ts`, `fixtures.test.ts`, and E2E `profile-knowledge-theme.spec.ts` (Mei's failed source).
- **New files:**
  - `frontend/scripts/export-schema.*`;
  - `backend/horizon/contract/schema.json`;
  - `backend/tests/fixtures/{energy,reducer}/*.json`.
- **Docs:**
  - `docs/requirements/05-data-contract.md` becomes rev 1.3;
  - `docs/backend/03-api.md` §7 wording "M1" changes to "M1a";
  - the ENG-05 wording (D-76).
- **Dependencies:** none new. Zod 4 has a built-in `z.toJSONSchema`.
- **Public demo (Vercel):** it still runs on the MockClient. After deploy, users see the new seed (Amara's source as a file, no CSV) and the D-76 top-up behaviour.

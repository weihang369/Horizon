# Proposal: ai-foundation (M7)

## Why

The AI stage is designed (docs/ai 01–13), and group A measured Jev and DeepSeek from Malaysia. Every later change (M8–M15) needs the same base. Without it:
- there is nowhere to write a versioned Jev question;
- there is no `Decider` deadline model that allows a late answer;
- `agent` can't be selected;
- there is no harness to tune and accept a question, and no store to stop paying twice;
- Insight has no place to show System 1.

Today:
- the `Decider` discards late answers;
- its budget check trusts a 32K limit that group A showed fails as an HTTP 429;
- the naive engine drops `finish_reason`, can write other speakers' lines, and accepts an empty reply as complete;
- JSON drafts fail 1 time in 20 on a nickname in double quotes.

M7 builds the base that doc 13 W4 assigns to it, and nothing that belongs to M8–M15.

**Lands as one change.** The scope is about twice M5's, but it splits into eight phases that each end green and can be committed alone:
1. bank and Decider;
2. gateway and ledger;
3. LLM parameters;
4. bubbles and demo parity;
5. rev 1.4 and Insight;
6. capture and tracing;
7. store and harness;
8. corpus and docs.

No phase needs code from a later phase except phase 7's `smoke`, which exercises phases 1–6. Splitting it would put the bank in one change and the harness that accepts it in another, so neither could be accepted on its own (W6: M7's evaluation is the canary plus the corpus licence check, both harness-driven). The risk is a large squash. The mitigation is the phase checkpoints and a reviewer pass per phase (design §Risks).

## What Changes

- **Question bank.**
  - Versioned Jev questions live as JSON files under `backend/horizon/ai/questions/`, with a loader, a content-hash lock that forces a version bump on any wording change, and the bank-wide `quoted_*` convention. Every question's instructions end with the doc 11 S6 sentence, and labels are worded as asked.
  - M7's bank holds `route` (v2, now in `quoted_*` form). The judge questions arrive with the suites that use them.
- **Decider.**
  - `start(...) → DecisionCall` with `by(deadline)` on the virtual clock and `final()`, one request and one ledger row; `ask()` = `start().by(now + timeout)`.
  - A mandatory 30k-token size check, counted conservatively (bytes ÷ 3), that refuses before sending.
  - The 429 policy: hot-path purposes fall back; `importance`, `memory_guard` and `rubric` retry once after 1 s.
  - Deadlines are keyed per question, not only per purpose, and requests run as `rt.spawn` tasks.
  - The ledger marks a late answer.
  - The unused `gate`, `rerank`, `emotion` and `watch_end` purposes and timeouts are removed. `eval_judge` is added.
- **LLM parameters (doc 03).**
  - **The settings table.** `runtime.llm.calls` holds one settings row per call type. Thinking is off everywhere behind a switch, and the doc 03 temperatures are sent.
  - **Reply caps and stops.** Shorter reply caps include `one_on_one_deep`, and the cap is chosen after the plan. C6 stop sequences are sent, and the own-name prefix is stripped before or after the emotion tag.
  - **Prompt and replies.** `naive-3` adds length targets and one message per line. Two empty-reply rules apply: a trailing cue, and one retry before any text shows.
  - **Finish reasons.** `finish_reason` is kept, and error finish reasons end `interrupted`. The ledger gains `finish_reason` and `tokens_reasoning`.
  - **JSON calls** follow: quote line → validate → free local quote repair → one paid retry. `cost_usd` is the sum of the attempts.
  - **Models.**
    - **BREAKING (config):** `gateway.fallbackModel` is removed, so no `models` list is sent.
    - The chat model has one source, and Settings → Models becomes a read-only "Models in use" panel whose Test ignores overrides.
- **Bubbles (C5).**
  - 1:1 and group replies render up to 4 bubbles split on line breaks; watch replies become script lines.
  - The auto-Readable rule applies per bubble.
  - The seed transcripts, mock banks and scripted lines gain line breaks.
- **Contract rev 1.4 (pre-approved by doc 13 W1).**
  - Adds the optional `TurnTrace.system1`.
  - The runtime-only `append_system1`, with its three guards.
  - The 64-row cut.
  - `_project` keeps the engine columns.
  - `seed/system1.fixture.json` feeds the scripted profile and the MockClient.
  - Insight gains a "System 1 · Jev" section, and the session cost tooltip gets W7's wording.
- **`agent` profile (opt-in).** `HORIZON_AI_PROFILE=agent` is accepted. Every port resolves to its naive implementation until a later change adds an `agent` one, and the memory writer stays `[]`.
- **`ai_calls` capture (B10).**
  - Off by default (`HORIZON_CAPTURE_AI_CALLS=1`).
  - One row per provider call and one per turn, written by a queued batch writer.
  - Retention is 7 days or 20,000 rows. Sessions and worlds cascade.
  - Forget deletes rows in its own transaction, and also drops rows still queued.
  - The first real `AiStateHooks` purges a deleted character's rows.
- **LangSmith (B11).**
  - Opt-in tracing: `HORIZON_LANGSMITH=1` plus `LANGSMITH_API_KEY`, in an optional `tracing` dependency group.
  - The four tracing variables are forced off at every entry point unless opted in, and a `tracing_context` guard helper is ready for M9's graphs.
- **Response store (W10).**
  - `data/cache/` in group A's exact format.
  - Injected only by `horizon eval` (replies and Jev answers).
  - The live app gets an embeddings-only view, limited to seed rows and corpus pieces.
  - It is never used for latency, repeatability, canary, capture/import or private-safety runs.
- **Evaluation harness (B6, B7, B12).**
  - `horizon eval canary|decisions|smoke` runs with isolated copies per profile, estimate-and-ask, `--max-usd` and self-stop, off-peak by default, a report, baselines and `spend.jsonl`.
  - The canary runs on group A's `canary.json`.
  - `horizon eval capture` and `horizon stats` are added.
  - `evals/` holds datasets with dev/test splits, the corpus with `SOURCES.md` and `LICENSE`, the overlap checker and the label-review sampler.
  - CI runs `horizon eval smoke` in test mode.
- **Offline test tooling (W14).**
  - A test-mode `X-Horizon-Purpose` header.
  - Canned chat responses per purpose, starting with group A's 20 drafts, picked by a test-control route.
  - `park_decision(n)`.
  - Parity for the second `insight` in both reducers' fixtures.

## Capabilities

### New Capabilities
- `question-bank`: versioned Jev questions as data: file format, loader, the version lock, the `quoted_*` convention and its sentence, labels worded as asked, thresholds and floors per question id, and per-question deadline keys.
- `llm-parameters`: one settings row per DeepSeek call type (thinking, temperature, output), length targets with `max_tokens` as a safety net chosen after the plan, stop sequences and the own-name strip, the empty-reply rules, JSON calls with repair and one retry, and the single pinned model set with a read-only Models panel.
- `reply-display`: one message shown as up to 4 bubbles (chat) or script lines (watch), the per-bubble auto-Readable rule, and demo parity.
- `system1-trace`: the System 1 section's rows, who writes them (`append_system1` and its guards), the row limit, the fixture rows for `scripted` and the mock, and the Insight section.
- `ai-call-capture`: the opt-in `ai_calls` table, the queued writer, retention, Forget and delete purges, and `horizon eval capture`.
- `opt-in-tracing`: LangSmith off by default, the entry-point guard, opt-in with the user's key, and what is never sent.
- `response-store`: the shared `data/cache/` store, its key and format, who may inject it, the staleness fingerprint and what bypasses it.
- `evaluation-harness`: `horizon eval` (canary, decisions, smoke), the run lifecycle and its spend controls, reports and baselines, `horizon stats`, the `evals/` data rules (splits, corpus licence, overlap, label review) and CI smoke.

### Modified Capabilities
- `decider`:
  - `start/by/final` with late answers kept;
  - questions from the bank;
  - the 30k size check counted conservatively;
  - the 429 policy;
  - question-level deadline keys;
  - requests started through the runtime's task factory;
  - the late-answer ledger mark.
- `provider-gateway`:
  - the decision timeout table (`route`, `turn_plan`, `follow_plan`, `debate_plan`, `guardrail`, `guardrail_prompt`, `reaction`, `face_check`, default);
  - no fallback model;
  - `finish_reason` kept and error finish reasons mapped;
  - `reasoning_tokens` parsed;
  - the call observer gets request and response bodies when capture is on;
  - the test-mode purpose header, canned responses per purpose, and `park_decision`.
- `spend-ledger`: `finish_reason` and `tokens_reasoning` columns, and the late mark on decision rows.
- `budget-caps`: the decision estimate counts the state once, plus each question.
- `ai-ports`:
  - the `agent` profile;
  - the naive engine's `naive-3` prompt, stops, own-name strip and empty-reply rules;
  - the tag parser's name-prefix buffer;
  - the Jev router built from the bank;
  - the drafter's JSON repair and retry;
  - the first real purge hooks.
- `client-contract`: rev 1.4 is additive (`TurnTrace.system1`).
- `session-runtime`: trace ownership gains `system1`; `append_system1`; the reply cap is chosen after the plan.
- `openrouter-key`: the model probe tests the model in use (overrides ignored) with reasoning off.
- `local-backend`:
  - new known variables;
  - the CLI gains `eval`, `eval capture` and `stats`;
  - a start-up log when capture or tracing is on;
  - a chat-model mismatch error at start-up;
  - factory reset names `data/cache/` and `data/evals/`.
- `data-storage`: migration `0003` (`ai_calls`, the two ledger columns).
- `long-term-memory`: Forget deletes `ai_calls` rows and drops queued capture rows in its transaction.
- `character-lifecycle`: deleting a character purges its `ai_calls` rows through the purge hooks.
- `continuous-integration`: CI runs `horizon eval smoke` in test mode.
- `demo-data`: line breaks in seed chat replies, and `system1.fixture.json` generated and checked.
- `http-api`: `/_test/ai-profile` accepts `agent`; new test routes for canned responses and parked decisions.

## Impact

- **Backend, new:**
  - `ai/questions/` (bank files, loader, lock);
  - `ai/jsonrepair.py`;
  - `sessions/system1.py`;
  - `services/capture.py`;
  - `services/tracing.py`;
  - `evals/` package code (`horizon/evals/`: runner, suites, metrics, store, report, stats);
  - Alembic `0003_ai_foundation`.
- **Backend, changed:**
  - `ai/decider.py`, `ai/profile.py`, `ai/hooks.py`;
  - `ai/naive/{turn,prompt,tag_parser,router,creation}.py`;
  - `gateway/{chat,types,decisions,pipeline,context,fake}.py`;
  - `services/{ledger,probes,purge}.py`, `services/memory/forget.py`, `services/jobs/worker.py`;
  - `sessions/{turn,prefetch,writer,actor}.py`;
  - `domain/runtime_config.py`, `config.py`, `cli.py`, `runtime.py`, `api/routes.py`;
  - the embedder and seed indexing (the store's embeddings view).
- **Frontend:**
  - `contract/{types,schemas}.ts` and `schema.json`;
  - `features/insight/InsightDrawer.tsx`;
  - `features/session/{MessageRow.tsx,sessionContext.ts,SessionScreen.tsx}`;
  - `features/settings/ModelsTab.tsx`;
  - `mock/{pricing.config.ts,MockClient.ts,script/turnScript.ts,banks}`;
  - `domain/cost.ts`;
  - `engine/tagParser.fixtures.test.ts`;
  - `scripts/seed-build` (runtime table, screenplay line breaks, the fixture generator).
- **Seed:** `seed/pricing.json`, `seed/runtime.json`, `seed/sessions/*` (line breaks) and the new `seed/system1.fixture.json`, all regenerated.
- **Repo:** `evals/` (datasets, corpus about 1 MB, baselines), `.env.example`, `.github/workflows/ci.yml`.
- **Dependencies:** none in the core install. `langsmith` goes in a new optional `tracing` group.
- **Docs:**
  - `docs/requirements/05-data-contract.md` (rev 1.4), `02` (SET-05, D-46 wording), `07` (R-13, R-14, NFR-13 note), `09` (D-46, D-93, D-94 wording);
  - `docs/backend/04`, `05`;
  - the docs/ai cross-references this change resolves.
- **Cost:**
  - Live behaviour gets cheaper: shorter caps, and no fallback model.
  - The capture writer and the store are local.
  - M7's evaluation is the canary (< $0.001) with the user's OK first, and the corpus licence check ($0; a manual download of public-domain pages, with the user's OK).

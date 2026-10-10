# Tasks

> **Constraints for every task:**
> - **Tests are offline.** No network in automated tests (the socket guard stays); only the in-process fake provider and obviously fake `sk-or-test-…` keys.
> - **The key stays private.** The real key is never printed, logged or put in fixtures, and live checks only test that a key is present.
> - **Contract.** The only change is rev 1.4's `TurnTrace.system1` (doc 13 W1, pre-approved). Any other contract method, field or UI entry point → **stop and ask the user**.
> - **Background work and waits.** New background work starts only through `rt.spawn`, and new waits use the runtime clock, so `/_test/clock` settles.
> - **Our side stays fast.** Nothing new runs between a request and its first token except what the specs require. Capture, the store and tracing are queued, off the hot path, or off by default.
> - **Commits and pushes.** Commit at each phase's green checkpoint, without Claude attribution. Nothing is pushed unless the user asks.
> - **Ask the user first** before:
>   - any paid call (the canary);
>   - the corpus download (network, $0);
>   - installing the optional `tracing` group.
>
> Each numbered phase ends with its own tests and docs green:
> - `uv run pytest`, `uv run ruff check`, `uv run mypy horizon`;
> - `npm run typecheck`, `npm run lint`, `npm test`, `npm run test:http`;
> - `npm run seed:check`, `npm run fixtures:check`, `npm run export-schema:check`.
>
> **Checkpoint:** commit the phase.

## 1. Question bank and the Decider

- [x] 1.1 Create `backend/horizon/ai/questions/` with `_conventions.json` (the S6 sentence), the loader (`QuestionBank`, design D1–D2) and `questions.lock.json`. Verify with unit tests:
  - the loader appends the sentence;
  - an undeclared or unquoted-text state field is refused;
  - static options compile in `what` / `Not for:` / examples order;
  - a dynamic option fills its template;
  - an unknown id fails.
- [x] 1.2 Add the lock check and the `horizon eval bank-lock` dev command. Verify that `test_bank_lock` fails when an entry's text changes without a version bump, and when a version goes down.
- [x] 1.3 Write `route.json` v2 (D3): label "who replies?", the `quoted_*` state, the cast-option template, `shuffle: true`, `floor: null`, deadline `route`. Verify with a unit test:
  - the same seed gives the same order;
  - the instructions end with the sentence;
  - the request fits the wire schema in `gateway/decisions.py`.
- [x] 1.4 Rework `ai/decider.py` into `start()` → `DecisionCall` with `by(deadline_vt)`, `final()` and `cancel()`, and `ask()` as `start().by(now + timeout)` (D4, D5):
  - requests run through an injected `spawn`, wired to `rt.spawn` in `runtime.py`;
  - fixtures resolve at once.

  Verify with unit tests on the virtual clock:
  - deadline then full answer, with one request;
  - the fallback runs once across two `by()` calls;
  - cancel → `DecisionCancelled`, no fallback, and the request still settles;
  - `stop()` aborts in-flight requests;
  - partial validation still holds;
  - the existing decider tests pass unchanged through `ask()`.
- [x] 1.5 Add the size check (D7): 30,000 tokens on state + longest question, at most 64 questions, reason `too_large`, a warning log, and no reservation or row. Verify with tests at 29,999 / 30,001 counted tokens, 64 / 65 questions, and a Malay/Chinese state counted by bytes.
- [x] 1.6 Add the 429 policy (D8): `RETRY_429 = {importance, memory_guard, rubric}`; the wait is max(1 s, Retry-After) capped at 5 s, on the clock, and only if the deadline allows it. Verify with tests using queued fake 429s: `route` falls back with no second request; `importance` retries once and records one row.
- [x] 1.7 Key deadlines per question (D9). `Timeouts.for_decision(key)` reads the bank entry's `deadline`. Update `pricing.config.ts` `timeoutsMs.decision` to W12's table and remove `gate`, `rerank` and `emotion`, then run `npm run seed:build`. Verify:
  - a `guardrail_prompt`-keyed test question gets 1,500 ms;
  - the provider-gateway timeout tests cover the new table;
  - `seed:check` passes.
- [x] 1.8 Clean up purposes (D10): `rg` for `gate`, `rerank`, `emotion` and `watch_end` as purposes across `backend/` and `frontend/src/`, and record the (empty) result in the commit message. Remove them from `PURPOSE_CATEGORY`, add `eval_judge`, and rewrite the tests that named them. Verify that `call_ctx("gate")` raises and `call_ctx("eval_judge")` is `decision`.
- [x] 1.9 Move the naive router onto the bank (D3): `quoted_*` state, the shuffle seed `"{session seed}:{turn index}:route"`, no floor. Verify:
  - the existing router tests pass (mentions, queue ≤ 2, fallback, candidates);
  - a new test asserts the request body uses `quoted_message`, and that an injected instruction stays inside it.
- [x] 1.10 Pin the decision estimate (D11). Verify with a test: 8 short questions on a 600-token state estimate the state once plus each question's own tokens, as A1 found Jev bills. The counter is bytes ÷ 3, deliberately above Jev's own token count, so the test pins the structure rather than A1's exact figure.
- [x] 1.11 Docs. Amend `docs/backend/05-ai-seams.md` §3:
  - the `start/by/final` API;
  - the 30k check and the 429 policy;
  - the purpose table pointing to W5;
  - removing the "late answers are discarded" wording.

  Verify that every relative link in the edited docs resolves (a link scan over `docs/`). **Checkpoint.**

## 2. Gateway, ledger and offline tooling

- [ ] 2.1 Write Alembic `0003_ai_foundation` (D27): `usage_records.finish_reason`, `tokens_reasoning`, and `ai_calls` with its indexes and cascades. Mirror it in `db/tables.py`. Verify with a migration test:
  - upgrading an M6-shaped database keeps its rows, and the new columns are `NULL`;
  - `ai_calls` exists;
  - a session delete cascades;
  - the migration is forward-only, like `0002`;
  - the no-drift autogenerate check passes.
- [ ] 2.2 Carry `finish_reason` and `tokens_reasoning` through the pipeline (D18): `Usage.tokens_reasoning` comes from `completion_tokens_details.reasoning_tokens`, then `Billing` → `LedgerRow` → the ledger writer. Decision rows take `finish_reason` from the `DecisionCall` outcome callback (D6). Verify with tests:
  - a recorded stream ending in `length` → the row says `length`;
  - reasoning 0 / 20 is stored;
  - a late decision → `late`; a cancelled one → `cancelled`.
- [ ] 2.3 Make the chat client keep the final content-less chunk and map the `error` and `insufficient_system_resource` finishes to a may-be-charged `provider_error` with partial text (D18). Verify with recorded-stream tests, and that the runner ends such a reply `interrupted` with its text kept.
- [ ] 2.4 Remove the fallback model (D20):
  - from `pricing.config.ts`, where `domain/cost.ts` makes it optional;
  - from `GatewayConfig` (tolerating an old file that still has it);
  - from `ChatClient.body`.

  Run `seed:build`. Verify:
  - `test_chat_client.py` asserts that no `models` field is sent;
  - `seed/pricing.json` has no `fallbackModel`;
  - `seed:check` passes.
- [ ] 2.5 Add the test-mode purpose header (D39): a contextvar is set by the pipeline around `send()`, and `HttpCore` adds `X-Horizon-Purpose` only in test mode. Verify with unit tests: a test-mode chat request carries it, and a normal-mode core never does.
- [ ] 2.6 Extend `FakeOpenRouter`:
  - `canned[purpose]`, cycled, in SSE or JSON with real-shaped usage;
  - `park_decision(n)`;
  - Jev answers carry `type`, with tokens counted at bytes ÷ 3.

  Create `backend/tests/fixtures/canned/profile-drafts.json` from group A's `drafts.json` (content and usage per draft; the source and date in a header field). Verify with fake unit tests and one integration test: a naive draft job with `profile-drafts` selected validates the first recorded draft.
- [ ] 2.7 Add the test routes `POST /_test/canned` (unknown set → `validation`) and `POST /_test/park` (decisions). Verify with HTTP tests:
  - a parked `route` decision past 400 ms gives the fallback at the deadline;
  - the row lands after release, with `finish_reason: "late"`;
  - the routes 404 outside test mode.
- [ ] 2.8 Docs. In `docs/backend/04-gateway-budget-energy.md`, remove the fallback model line and add `finish_reason` and `tokens_reasoning`. Amend `docs/requirements/07-nfr-risk-cost.md`: R-14's mitigation (C8) and R-13 ("a deterministic code fallback per question"). Verify the links. **Checkpoint.**

## 3. LLM parameters

- [ ] 3.1 Add `runtime.llm.calls` (C1's table) and the new `replyMaxTokens` (D14) to `runtime.config.ts`, then run `seed:build`. Parse them in `domain/runtime_config.py`: `LlmCalls` and `ReplyCaps.for_mode(mode, turn_length, deep=False)`. Update `tests/unit/test_runtime_config.py` to the new values. Verify that `seed:check` and the runtime-config tests pass.
- [ ] 3.2 Add the `llm_request(row, …)` helper (D13), the single builder of `ChatRequest`s for the naive engine, drafter and probe. Verify with unit tests:
  - `off` → `reasoning: {enabled: false}`;
  - `temperature: null` → field absent;
  - no `top_p` or penalties.
- [ ] 3.3 Choose the cap after the plan (D14): `reply_cap(rt, sctx, plan)` is called after retrieval in `sessions/turn.py` and in `sessions/prefetch.py`, and `TurnContext.max_tokens` becomes required. Update `tests/sessions/test_naive.py` (350 → 200). Verify that a group request has `max_tokens` 150, a prefetched short-debate opening 200, and a naive 1:1 with passages 200.
- [ ] 3.4 Write `naive-3` (D15): the tag line, the per-mode length line, and the debate cue without "few sentences". Update `tests/knowledge/test_naive_prompt.py`. Verify:
  - the exact wording per mode;
  - with nothing retrieved, two consecutive requests share their prefix byte for byte;
  - `PROMPT_VERSION == "naive-3"` in the stored trace.
- [ ] 3.5 Add stop sequences (D16), built from `render_history`'s names, deduplicated, never a bare `"\n["`, and asserting ≤ 16. Verify with a unit test for a 5-cast group (the exact list) and one for a session with host lines (`"\n[host line]"`).
- [ ] 3.6 Add the name-prefix buffer to `TagParser` (D16, first line only), with `speaker`. Add fixtures to `backend/tests/fixtures/tag_parser/` with `speaker` and `perLine: false`:
  - `Mei: <e:happy>Hi`;
  - `<e:happy>Mei: Hi`;
  - split across chunks;
  - case and spaces;
  - a name that only starts the same.

  Update the TS reference parser and `frontend/src/engine/tagParser.fixtures.test.ts`. Verify that both languages pass every fixture.
- [ ] 3.7 Add the empty-reply rules to `NaiveTurnEngine` (D17):
  - the trailing cue when the history ends on the speaker's own line;
  - the `Emotion` is held until the first `Token` or the end;
  - one silent retry (adding the cue);
  - `provider_error` on a second empty.

  Verify with canned SSE tests:
  - empty then `<e:happy>Hi` → one message, two `reply` rows;
  - empty twice → `error` event, no message, two rows;
  - the face is emitted once.
- [ ] 3.8 Add `ai/jsonrepair.py` (`repair_json_quotes`) and `complete_json` (D19). Use them in the naive drafter and field regenerate, with the single-quote line in the prompt. Change the job worker's `commit_with` to add `cost_usd`. Verify with tests:
  - A3's `"Loretta "Rhett" Kowalski"` repairs to valid JSON with no second call;
  - valid JSON is never altered;
  - an unrepairable answer then a valid retry → two rows and the task cost is the sum;
  - a timeout is never retried.
- [ ] 3.9 One chat-model source (D20). The drafter and the probe use `prices.chat.model`, and start-up logs an error when `settings.models.chat` differs. `probe_model` ignores overrides and uses the `probe` row. Update `test_settings_key.py` (`test_model_probe_echoes_the_override` → overrides are ignored) and `MockClient.testModel`. Verify with tests: the probe body has `reasoning: {enabled: false}`; an override is ignored; a mismatch logs an error and the backend starts.
- [ ] 3.10 Make Settings → Models a read-only "Models in use" panel (D20): slug, purpose, price from `pricing.config.ts`, Test, and the v2 line. Remove save and reset. Verify with a component test (no editable field; each role shows a price and Test) and with `npm test`.
- [ ] 3.11 Docs:
  - `docs/requirements/02-functional-requirements.md`: SET-05 is read-only in v1;
  - `docs/requirements/08`: OQ-AI-13 resolved;
  - `docs/requirements/09-decision-log.md`: D-93's "byte-identical" note is now true only until `naive-3`;
  - `docs/backend/05-ai-seams.md` §5: `naive-3`;
  - `openspec/specs/openrouter-key` via this change's delta.

  Verify the links. **Checkpoint.**

## 4. Bubbles and demo parity

- [ ] 4.1 Add `splitBubbles(text)` (D21) in `frontend/src/features/session/`. Verify with unit tests:
  - line split;
  - blank lines collapsing;
  - the 4-bubble cap joining into the 4th;
  - no split inside a fenced block or a list;
  - Chinese `。` text with line breaks.
- [ ] 4.2 Render bubbles in `MessageRow.tsx`: 1:1 and group as bubbles, watch as script lines under one name tape, debate, host and user messages unsplit, citation chips under the last bubble. Change `sessionContext.ts` so auto-Readable applies per bubble over 600 characters. Verify with component tests for each mode, the streaming re-split, and the 700-character three-bubble reply staying bubbles.
- [ ] 4.3 Add line breaks to the 1:1, group and watch character lines in `seed-build/screenplays/seed.ts`, `mock.ts`, `frontend/src/mock/banks/*` and the scripted engine's lines (D22), leaving debate untouched. Run `npm run seed:build` and `npm run fixtures:build`. Verify:
  - `seed:check`, `fixtures:check` and the replay-equivalence and fork fixture tests pass in both languages;
  - a test asserts no debate message contains `\n`;
  - the Amara 1:1 seed has a multi-line reply.
- [ ] 4.4 Docs. Change D-46's wording in `docs/requirements/09-decision-log.md` to "one message, which chat modes may display as up to 4 bubbles". Verify the links. **Checkpoint.**

## 5. Contract rev 1.4 and System 1

- [ ] 5.1 Add `TurnTrace.system1` to `frontend/src/contract/types.ts` and `schemas.ts` (D23: strict, ≤ 64 rows, unit `p`/`confidence`), then run `npm run export-schema`. Verify:
  - `clientSchemas.test.ts` accepts a full W1 example and rejects 65 rows;
  - every rev 1.3 fixture still validates;
  - `export-schema:check` passes.
- [ ] 5.2 Add the rev 1.4 note and the `system1` block to `docs/requirements/05-data-contract.md` (W1's shape, verbatim), and INS-01 AC2 if it isn't already worded. Verify the links.
- [ ] 5.3 Make `system1` a runtime-owned trace key (`OWNED_TRACE_KEYS`). Change `_project` so an all-`None` `TraceMeta` keeps the engine columns and `created_at` (D24). Verify with tests: an engine patch with `system1` is dropped and `context` kept; a second `insight` without meta keeps `naive`, `2` and the original `created_at`.
- [ ] 5.4 Add `sessions/system1.py` (`merge_rows`, `cut`) and `SessionActor.append_system1` (D24):
  - the regenerate guard;
  - the streaming guard (`info.system1`, merged by `finish()`);
  - the Forget guard as a writer `extra`.

  Verify the doc 13 §3 checks as tests:
  - (2) 70 rows → 64, `not_used` removed first;
  - (3) an append after Regenerate writes nothing;
  - an append queued before a Forget commit writes no `mem_` row and no recalled text;
  - an append during streaming lands in the final `insight` only.
- [ ] 5.5 Write naive `route` rows (D25) into every reply started by the decision: answer, `p`, confidence, result and action; on a fallback, no `p`. Verify with an integration test: a naive group message answered by two characters → both traces carry the same `route` row; a parked decision past its deadline → a `fallback` row.
- [ ] 5.6 Add the seed-build generator for `seed/system1.fixture.json`, reading `backend/horizon/ai/questions/*.json`, and add it to `seed:check`. Make the scripted runtime path and `frontend/src/mock/script/turnScript.ts` write `route` rows from the fixture, with `answer` filled from the actual routing. Verify:
  - `seed:check` fails after a label edit without a rebuild;
  - a scripted group turn and a mock group turn both produce a schema-valid row naming the speaker;
  - seed session traces are unchanged.
- [ ] 5.7 Add the second-`insight` reducer fixture with an appended `system1` row (D40). Verify that both reducers' fixture tests pass.
- [ ] 5.8 Add the "System 1 · Jev" section to `InsightDrawer.tsx` (D26): after Emotion, grouped with latency or "fallback", rows with band and comparisons, `not_used` folded, IDs resolved, hidden when empty, absent in Compact. Verify with component tests: no rows → no section; a route row shows the name and `p` with its band; compact → absent; folding.
- [ ] 5.9 Set W7's tooltip on the session cost counter in `SessionScreen.tsx`: "Reply cost only. Planning, checks, summaries and memory count toward the daily cap: see Settings → Cost." Verify with a component test. **Checkpoint.**

## 6. Capture, purge hooks and tracing

- [ ] 6.1 Add `services/capture.py` (D27):
  - a bounded deque (2,000);
  - `CallBody` built only when enabled;
  - the flush task via `rt.spawn` every 2 s of clock time or 200 rows;
  - `dropped_before`;
  - retention at start-up and hourly (7 days, then 20,000).

  Extend the gateway's `on_call` to pass the redacted bodies when capture is on (chat messages and text, Jev state, questions and answers; never embeddings, images or audio). Verify with tests:
  - capture off → no body built, no rows;
  - on → call rows for `route` and `reply`, and a turn row, all with the message ID;
  - 2,500 rapid calls → every call completes and the drop count is recorded;
  - retention deletes 8-day-old rows;
  - an embedding row has no texts.
- [ ] 6.2 Write the turn row from `TurnRunner.finish()`: the frozen `TurnContext` and the routing and Decider fallback flags. Verify with an integration test: the turn row's request round-trips into a `TurnContext`.
- [ ] 6.3 Handle Forget and capture (D28): set the forget marks, then delete `ai_calls` (the character's rows, and the world's rows with no character) inside Forget's transaction; the flush drops marked rows. Run the existing byte-level Forget test with capture on. Verify with tests: a queued row created before Forget never lands, and the byte-level test passes.
- [ ] 6.4 Add the first real `AiStateHooks` (D29): `CompositeHooks([CaptureHooks])` wired into `PurgeWorker`. Verify with tests: deleting a character and delivering the hook twice → no rows and both succeed; a message delete removes its rows; the session and world deletes stay idempotent.
- [ ] 6.5 Add `horizon/tracing.py` (D30): `guard_env()` as the first statement in `cli.main`, `main.create_app` and `tests/conftest.py`; the opt-in check; the start-up warning or error; `no_trace()`; `traceable` around `Gateway.paid` and `chat_stream` when on. Add the optional `tracing` group (`langsmith`) to `pyproject.toml` without installing it. Verify with tests:
  - a stray `LANGCHAIN_TRACING_V2=true` reads `false` after the guard;
  - opt-in without the package logs an error and runs untraced;
  - with a stub client, traced inputs contain no key or `Authorization`.
- [ ] 6.6 Add `HORIZON_CAPTURE_AI_CALLS`, `HORIZON_LANGSMITH` and `LANGSMITH_API_KEY` to `KNOWN_VARS` and `.env.example` (with comments), and log a start-up line for capture and tracing. Change the provider-gateway lint exception list (D30) if the lint rule names modules. Verify: a config test reads them from `.env`; the leak sweep in `local-backend` still passes with capture on.
- [ ] 6.7 Docs:
  - `docs/requirements/07-nfr-risk-cost.md`: the NFR-13 note on LangSmith;
  - `docs/requirements/09-decision-log.md`: D-94 also covers `ai_calls`;
  - `docs/backend/05-ai-seams.md` §4 and §6: `ai_calls` built;
  - a README Privacy line for capture and tracing.

  Verify the links. **Checkpoint.**

## 7. Response store and the evaluation harness

- [ ] 7.1 Add `horizon/evals/store.py` (D31): group A's `canonical()` and key rule per kind, atomic writes, first write wins, the eval view and the seed view. Verify with tests:
  - a key computed for a recorded group A Jev request (fingerprint `None`) equals its group A filename;
  - a hit sends nothing and writes no row;
  - a different fingerprint misses.
- [ ] 7.2 Wire the seed view: `store_ok=True` only on seed knowledge indexing (`is_seed`) and seed memory embedding (and later corpus pieces); user paths pass nothing. Verify with an integration test using a temp store in test mode: index seed knowledge, Reset demo, index again → the second pass sends no embedding request and writes no embedding row; a user document is never stored.
- [ ] 7.3 Add `horizon/evals/` runner and CLI (D33):
  - `horizon eval <suite>` with `--profile`, `--limit`, `--max-usd`, `--yes`, `--allow-peak`;
  - plan and estimate; the off-peak check; the y/N prompt;
  - isolated copies under `data/evals/<run-id>/<profile>/`, with env overrides ignored and the key in memory only;
  - self-stop; `incomplete` on a budget refusal;
  - `report.md`, `results.jsonl`, `spend.jsonl`, pruning to 20.

  Verify with tests in test mode:
  - a declined prompt sends nothing and keeps no folder;
  - the user database is untouched by a run;
  - a paid suite refuses in test mode;
  - a forced cap gives `incomplete`;
  - the 21st run prunes the oldest;
  - the report lists resolved ports for `--profile agent`.
- [ ] 7.4 Add `horizon/evals/metrics.py`: Wilson, exact McNemar, bootstrap over groups, order-statistic percentile intervals, Recall@k, MRR, nDCG. Verify with unit tests against hand-worked answers recorded in the test file.
- [ ] 7.5 Add the canary suite (D32, D34):
  - `evals/canary.json` is a byte copy of group A's file;
  - the fingerprint is verified on load;
  - the pass rule;
  - the model id is recorded;
  - the store is bypassed;
  - `--accept`.

  Verify with tests using canned fake answers: identical → pass; one choice flipped → drift names the item; a p moved 0.11 → drift; a hand-edited baseline → refused; the copy's bytes equal the source.
- [ ] 7.6 Add the decisions suite (D34): the dataset loader with schema, building from the bank with the deadline off, policy accuracy, calibration, order bias in both orders, re-run only changed versions. Add `evals/datasets/_smoke/route.jsonl` (6 items, `smoke_only`). Verify with test-mode tests: a second run with no bank change sends nothing; order bias is computed from both orders; smoke-only items are never reported as a measurement.
- [ ] 7.7 Add the smoke suite (D34): `decisions --limit` over changed versions, one scripted conversation per mode from `evals/smoke/<mode>.json`, the bank wire-schema check, the dataset load, the report render. Verify that `HORIZON_TEST=1 uv run horizon eval smoke --limit 5 --yes` exits 0 with the socket guard on.
- [ ] 7.8 Add `horizon eval capture <messageId>` and `horizon stats [--days N]` (D36). Verify with tests: capture with rows writes a case file, and without rows exits non-zero; stats on a fresh install says there is no live data; stats on a seeded test database prints p50/p90, cost by purpose and late rates, and leaves the file's bytes unchanged.
- [ ] 7.9 Add the data checks (D37):
  - the split rule and the "split never changes" check (against `git show HEAD:` for existing items);
  - `horizon eval overlap` (6-word shingles);
  - `horizon eval review <set>` (seeded sample, `evals/reviews/<set>.json`, two disagreements → relabel).

  Verify with unit tests for each, including a copied bank example failing overlap.
- [ ] 7.10 Add the smoke, `eval overlap` and `eval corpus-check` steps to `.github/workflows/ci.yml` (D38). Verify by running the three commands locally with `HORIZON_TEST=1` and no key: each exits 0, and together they take < 1 min.
- [ ] 7.11 Docs:
  - `docs/requirements/08-open-questions-handoff.md`: OQ-AI-15 and OQ-AI-08's evaluation half resolved;
  - `docs/backend/05-ai-seams.md` §6: the harness is built;
  - `evals/README.md` covering the folder layout, the split rule, how to run each command, and the store rules.

  Verify the links. **Checkpoint.**

## 8. Corpus and remaining docs

- [ ] 8.1 **Ask the user** before downloading. Then fetch 3–5 public-domain US federal documents per knowledge-holding seed character (D37), as Markdown text only, into `evals/corpus/<character>/`, about 1 MB in all:
  - Amara: NIOSH shift work;
  - Mei: OPM work schedules;
  - Victor: the Federal Rules of Evidence;
  - Hana: USDA-staff recipes.

  Write `SOURCES.md` (URL, retrieval date) and `LICENSE`, and read each page for an outside credit. Verify that `horizon eval corpus-check` passes (doc 02 check 2), and that no figure, image or logo is committed.
- [ ] 8.2 Add the `agent` profile's docs: `docs/backend/05-ai-seams.md` §1 (opt-in until M15, resolves to naive per port) and the README's profile section, left as "experimental, opt-in". Verify the links.
- [ ] 8.3 Mark this change's resolved items in docs/ai with a pointer to it:
  - doc 13 §3 checks 1–3;
  - doc 02 §7's M7 rows;
  - doc 03 §6's rows;
  - doc 01 A12's opt-in note.

  Verify that the link scan over `docs/` reports 0 problems. **Checkpoint.**

## 9. Integration and M7's evaluation

- [ ] 9.1 Run a full offline integration pass:
  - every gate from the constraints block;
  - the E2E suite on both clients (`npm run e2e` or the CI equivalent);
  - `HORIZON_TEST=1 horizon eval smoke`.

  Verify that all are green and that `git status` shows only intended files.
- [ ] 9.2 Run a reviewer pass over the whole diff, per phase, for:
  - contract drift beyond rev 1.4;
  - key leaks;
  - hot-path latency added on our side;
  - tasks started outside `rt.spawn`;
  - store injection outside the allowed paths.

  Fix the findings and re-run 9.1. Verify that the review notes are recorded in the final commit message.
- [ ] 9.3 **Ask the user** to approve the canary (< $0.001, off-peak). Then run `horizon eval canary` with the real key from `.env`. Verify that the report passes or names drift; record the model id and the result in `docs/ai/checks/group-a.md`'s follow-up line (or a new `docs/ai/checks/m7.md`); and keep the spend in `data/evals/spend.jsonl`.
- [ ] 9.4 Run `openspec validate ai-foundation --strict`, then hand over for archive and the squash merge into `dev` (which needs the user's go-ahead). Verify that validation passes.

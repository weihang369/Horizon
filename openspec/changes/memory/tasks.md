# Tasks

> **Constraints for every task:**
> - **Tests are offline.** No network in automated tests: the socket guard stays on, and only the in-process fake
>   provider and obviously fake `sk-or-test-…` keys are used.
> - **The key stays private.** The real key is never printed, logged or put in fixtures.
> - **Contract.** M13 changes none (design D4). If any contract method, wire field, event or UI entry point turns out
>   to be needed, **stop and ask the user** before changing it.
> - **Background work and waits.**
>   - New background work starts only through `rt.spawn` or `actor.background`. Pause runs are runtime-level
>     (`rt.spawn`), never actor tasks (D8).
>   - New waits use the runtime clock (or `vclock.join` / `wait_handoff`), so `/_test/clock` settles.
> - **Our side stays fast.**
>   - Nothing on the reply path waits for memory writing.
>   - Recall's search is a few milliseconds.
>   - A quick `agent` turn costs and waits what it does today, plus the cached memory block.
> - **Scope.** Nothing from M14–M15:
>   - no unsafe-request or at-risk nouls, no output check, no `message_ai_meta.safety`;
>   - no S6 instruction noul or S7 code filter (D38; U4: M14 owns both);
>   - no conversations, `naive` memory arm or `agent` default.
> - **`scripted` keeps the mock's behaviour.** The mock never writes memories, and the 5 seed memories stay.
> - **No user text in the response store.** The user's documents, memories and messages (and message vectors) never
>   enter it (W10). The memory suite is synthetic.
> - **Commits and pushes.** Commit at each phase's green checkpoint, without Claude attribution. Push nothing unless
>   the user asks, and never commit `6 RAG.pdf`.
> - **Ask the user first** before:
>   - any paid run (phase 10, each with its own estimate, off-peak: not 09:00–12:00 or 14:00–18:00 KL; the overrun
>     cap is max(1.5 × estimate, $0.01));
>   - any download;
>   - spawning subagents;
>   - any prompt, wording, threshold, deadline or setting change a finding suggests (as choices).
> - **Gate eval commands run with `HORIZON_TEST=1`.**
> - **Before any paid batch,** check that no earlier batch script or process is still alive (`ps`), since M12 paid
>   twice for one batch.
>
> **Every phase ends with these gates green:**
> - `uv run pytest`, `uv run ruff check`, `uv run mypy horizon`;
> - `npm run typecheck`, `npm run lint`, `npm test`, `npm run test:http`;
> - `npm run seed:check`, `npm run fixtures:check`, `npm run export-schema:check`;
> - `HORIZON_TEST=1 uv run horizon eval smoke --limit 5 --yes`.
>
> **Checkpoint:** commit the phase.

## 0. The base and the storms (design D2)

- [ ] 0.1 Confirm M12's gates on 6ceb366:
  - in the gate worktree: backend pytest 1841 passed, noting the load-sensitive
    `test_search_on_a_loaded_database_is_fast`, plus ruff and mypy;
  - frontend 542 / http 62;
  - e2e 66.

  Record them in a new `docs/ai/checks/m13.md` §0.
- [x] 0.2 Add a storm test placeholder per new cancel path to the cancel-storm suite, marked `xfail(strict=True)` with
  its phase:
  - a run cut at each step;
  - Forget during a run;
  - a regenerate during a run;
  - the window-drop indexing;
  - recall on Stop;
  - the block refresh;
  - shutdown with runs pending.

  Each phase that builds the path flips its test to passing. Verify: the suite runs, and the placeholders report
  xfail.

## 1. Storage (D5, D6)

- [x] 1.1 Add migration `0005_memory`:
  - `sessions.memory_seq` (upgraded to each session's `MAX(messages.seq)`), `memory_reread`, `memory_tries`;
  - `message_index` with an integer `rid`, a `message_id` foreign key that cascades, `session_id`, `seq`, `author`,
    `text`, `created_at`, and the `(session_id, seq)` index;
  - `message_fts` and its three triggers, added to `FTS_DDL` / `FTS_DROP`.

  Verify: a migration test runs up to 0005 and down to 0004, with the checkpoint upgraded from a fixture session of
  57 messages to 57, and every other table unchanged.
- [x] 1.2 Have the SpaceManager create `message_vec__{space}` (vec0, `rid`, partition `session_id`, cosine) and its
  `AFTER DELETE` trigger on `message_index`, for the active and building spaces; add it to `vec_tables`. Verify: a
  startup test on a fresh and an upgraded database finds the table empty, and a restart leaves it intact.
- [x] 1.3 Make `Reinforce` also set `last_recalled_at = now`. Verify: a store test.
- [x] 1.4 Add `message` to `build_space`'s `KINDS`:
  - copy the vectors when the model and dimensions are unchanged, else re-embed;
  - count the lines in `plan_build`'s estimate and in `horizon space build`'s listing;
  - never go through the store.

  Verify: build tests for copy and re-embed, and an estimate test.
- [x] 1.5 Add the `message` kind to the embedder's `request_text` (no header). Verify: a unit test shows a message
  text is embedded unchanged under the header space.

## 2. The pause run without a writer (D7–D11)

- [x] 2.1 Add an `on_drained` hook to `EventBus`. The runtime registers it for session channels: a grace timer of
  `memory.leaveGraceMs` on the runtime clock, cancelled by a new subscribe. Verify, on the virtual clock:
  - two subscribers, one leaves: no timer;
  - the last one leaves: the timer starts;
  - a reconnect at 5 s: no run.
- [x] 2.2 Add `memory.*` to `runtime_config.py` and `runtime.config.ts` (D42), then rebuild the seed. Verify:
  `seed:check`, and a config test reading every knob.
- [x] 2.3 Build `MemoryRuns` (D8):
  - high and normal queues, `maxConcurrent` 2, one run per session with merge and `again`;
  - registration by session, character and world, with cancel APIs, and `drain()` for tests.

  Verify, with unit tests on the virtual clock:
  - three requests run two at a time;
  - a request during a run queues exactly one more;
  - high priority goes first.
- [x] 2.4 Wire the triggers (D7):
  - `leave`, `end`, the debate verdict, watch's `turn_cap`;
  - the re-request at a kept turn's `turn.end`;
  - trigger 5 at create and actor start (other sessions sharing a participant with unread lines, at high priority);
  - the start-up sweep after `close_interrupted_streams`;
  - the idle release.

  Remove `_remember` and its call. Verify: one test per trigger that a run is requested, and a test that ten
  completed replies in an open session make no memory call.
- [x] 2.5 Add the start checks (D8):
  - seed sessions skip;
  - an explicitly `scripted` profile advances the checkpoint with no call;
  - with no usable key the run is deferred (no move, no try), with "falls back for lack of a key" told apart through
    `profile.choose`.

  Verify: tests for each.
- [x] 2.6 Write `build_stretch` (D9):
  - the settled bound, kinds and labels, the debate and watch header;
  - 6 context lines, re-reads with their two context lines;
  - who is present, numbering, 8,000-token pieces;
  - the minimum rule (an ended session advances anyway).

  Verify with unit tests:
  - a user line sent during a stream stops the bound before the streaming reply;
  - a director's note is excluded;
  - debate moderator lines are labelled;
  - a 20,000-token stretch makes three pieces;
  - 2 character lines make no call.
- [x] 2.7 Write `MemoryStore.apply_run` (D10):
  - sorted run locks held from the list read to the commit;
  - one transaction with the compare-and-set, the re-read update and `memory_tries = 0`;
  - the variant check, the Forget-race drop, and Touch of recall-used memories;
  - `entity.changed` per character and the live-actor refresh post (a no-op until phase 5).

  Verify with tests:
  - two runs from the same checkpoint: one commits;
  - Forget of a target mid-run: the change is dropped and the rest commits;
  - a regenerated source variant: the draft is dropped;
  - two sessions sharing a character serialise.
- [x] 2.8 Add the failure path:
  - a failed call counts a try and keeps the checkpoint;
  - 3 tries skip the piece with a warning;
  - a failed commit retries once with no second call;
  - a cap refusal is not a try.

  Verify: tests for each, with a writer stub.
- [x] 2.9 Add `CallContext.pauses_sessions` (D11):
  - runs and window-drop indexing set `False`;
  - `_preflight` publishes with `sessions=False` for them;
  - `on_spend` skips `pause_all_for_cap()` for them.

  Verify: a run's call crossing the cap leaves an active session active, and a reply's crossing still pauses it.
  Spec: session-runtime "Daily cap pauses live sessions".
- [x] 2.10 Flip phase 2's storm tests to passing:
  - delete, character delete, world delete and Reset demo, each during a stubbed writer call and inside
    `apply_run`;
  - shutdown with runs pending, then a restart sweep reads the same lines.

  Verify: the storm suite is green, and the writer is free after each.

## 3. The writer (D12–D19)

- [x] 3.1 Replace `MemoryWriter.after_turn` with `on_stretch(stretch, ctx) → WriterResult`. Add the types (D12), delete
  `NoMemoryWriter.after_turn`, and add `memory_writer` to `NAIVE_PORTS` and `AGENT_PORTS`. Verify: mypy and a
  port-resolution test per profile, with no key, with a key and in test mode.
- [x] 3.2 Write the `memory-1` prompt and its parser (D13):
  - the fixed system message and the user-message layout;
  - `max_tokens` = 300 × present + 200 (≤ 3,000), and the split on `length`;
  - one retry on a parse or schema failure;
  - the code checks (drops are logged), and drafts with every source field.

  Verify with unit tests:
  - an unknown target, a bad `for`, a 45-word text and 7 changes for one character are each handled as D13 says;
  - a `length` answer splits;
  - the prompt bytes match a committed fixture.
- [x] 3.3 Add the bank entries `importance` and `memory_guard` (D14, D15), with their wordings, levels, state
  templates, versions and lock. Add `memory_guard` to `PURPOSE_CATEGORY`, and add `timeoutsMs.decision.importance` /
  `memory_guard` (30,000) to pricing and its mirror. Verify: bank load and lock tests, a `unit` test (level 4 →
  0.75), and `seed:check`.
- [x] 3.4 Build the importance request with `extra_questions` (D14's M14 seam):
  - the fallback from the weight hint;
  - `minImportance`, the higher-of rule on rewrites, and confirm → Reinforce +0.05.

  Verify: `DeciderFixtures` tests for each rule, plus an extra-question test showing `importance` keeps its version.
- [x] 3.5 Build the guard (D15): one request per rewrite, Supersede at or above `t_keep`, else Insert beside, and
  fallback → keep both. Verify: fixture tests for yes, no, late (`park_decision`) and a 429 retried once.
- [x] 3.6 Build the duplicate check (D16):
  - case-fold equality first, then embed once and KNN top 1 in the character's partition against current memories;
  - the vectors are handed to `apply_run`, so each text is embedded once per space.

  Verify with tests:
  - a near-duplicate above `dupCosine` reinforces;
  - exactly one embedding request carries a new add's text (embedding-spaces "Memory work embeds each new text
    once").
- [x] 3.7 Assemble the `agent` memory graph (D17): LangGraph, no checkpointer, a per-run semaphore of 10 Jev
  requests, cancellation through the run. Verify: a graph test over a two-character stretch with canned answers, and
  a storm test cancelling it mid-graph.
- [x] 3.8 Build the `naive` writer (D18): the same call, importance from the hint, Supersede with no guard, and the
  exact-duplicate skip. Verify: a test where a `naive` run makes exactly one `memory` call and no Jev request.
- [x] 3.9 Add canned memory responses to `FakeOpenRouter` (D19): purpose `memory` via `X-Horizon-Purpose`, a
  test-control route, and the defaults (empty, and add + rewrite + confirm). In test mode, use the `agent` writer
  unless the profile is `scripted`. Verify: an end-to-end backend test in which a 1:1 session pauses, writes the
  canned memories, and the Memory list shows them.
- [x] 3.10 Run the writer storms: cancel during the rewrite call, the Jev requests and the embeddings. Verify: the
  storm suite is green.

## 4. The undo and Forget (D20, D21)

- [ ] 4.1 Add the undo at Regenerate and Continue (D20), before streaming, for messages with `seq ≤ memory_seq`:
  - remove still-current derived memories through the Forget path;
  - restore their predecessors;
  - add the message to `memory_reread`.

  Verify with tests:
  - B replaced A, regenerate: B is gone and A is current;
  - the next run reads the new variant;
  - the checkpoint is unmoved.
- [ ] 4.2 Switch `_forget_derived` to the undo. Verify: session-runtime's "Blocked regenerate keeps older memories"
  scenario, with a forced block.
- [ ] 4.3 Make Forget clear the character's stored rewrites in the world (D21), in the same transaction, for a user
  Forget, the undo and the blocked-reply undo. Verify with tests: no `rewrites[characterId]` remains in that world
  after a Forget, and a regenerate then makes a new `query_rewrite` call.
- [ ] 4.4 Run the undo storms: a regenerate during a run, and Forget during a run. Verify: green.

## 5. The memory list and the greeting (D22–D25)

- [ ] 5.1 Build the block reader (D22):
  - current memories ranked importance × recency × mode weight, filled to 1,000 tokens;
  - each line cut at 40 words and newline-collapsed, with ties by newer then id;
  - an overflow flag.

  Add `CharacterView.memories`, filled by the runtime for `agent` speakers. Verify: ranking, budget, tie and collapse
  unit tests.
- [ ] 5.2 Put "# What you remember" between the world and session blocks in `compile_persona`. Add `memories` to the
  TS twin and new shared persona fixtures (a block, empty, the 40-word cut, a newline). Verify: the fixtures pass
  byte for byte in both languages; with no memories the bytes equal today's; the wizard preview passes none.
- [ ] 5.3 Freeze the block per sitting (D23): `actor.memory_blocks`, dropped by Forget's actor scrub and by
  `apply_run`'s post to live actors sharing the character. Verify the D23 proof test: 5 turns are byte-identical;
  after a Forget the next turn lacks the line; the turn after is identical again. A second-tab test covers a commit.
- [ ] 5.4 Put the block in the trace and the budget (D24):
  - `memory.recalled` without a score, plus `trace_memory_refs`;
  - `context.used.memory` from the compile;
  - `planned_input` gains `memory.blockTokens`.

  Verify: a trace test, and a Forget test that scrubs a block line from a stored trace.
- [ ] 5.5 Build the greeting (D25): a generated 1:1 greeting's tail gains ≤ 2 newest memories from the last 1:1
  session and the cue sentence, with no wait; the first chat is unchanged. Verify: persona-prompt's "Second chat"
  scenario, and a first-chat test.
- [ ] 5.6 Run the block-refresh storm: a Forget refresh posted while a turn builds its view. Verify: green, and no
  half-built block.

## 6. Recall's indexing (D29)

- [ ] 6.1 Hook `SummaryTask._write` (the DeepSeek summary and the fallback) to index the newly dropped user and
  character lines (active, complete) as `message_index` rows with `"Name: text"`. Verify: session-recall's "A drop is
  indexed once" scenario, with notes and directions excluded.
- [ ] 6.2 Add the batch embedding of a drop:
  - one call, active space, `embed_doc`, `pauses_sessions=False`, never stored, key only;
  - it runs as the summary task's continuation.

  Verify with tests:
  - one embedding call per drop;
  - no store entry;
  - with no key the lines are keyword-only;
  - Stop doesn't cancel it, and a delete does.
- [ ] 6.3 Make indexed lines follow their messages:
  - regenerate updates the row's text and re-embeds;
  - a blocked scrub zeroes, then deletes;
  - a session delete zeroes the session's vectors, then the cascade deletes;
  - fork copies rows and vectors under new ids and sets `memory_seq` to the copied max.

  Verify: the session-recall, session-lifecycle and data-storage scenarios, including "Fork copies without paying".
- [ ] 6.4 Run the indexing storm: cancel mid-write of the rows and vectors. Verify: green, with no partial rows.

## 7. Recall (D26–D36)

- [ ] 7.1 Add bank entries `earlier` and `recall` (D26, D33), with their wordings, state templates, thresholds and
  fallbacks. Add `retrieval.agent.recall` knobs (D42) in both config sources, then rebuild the seed. Verify: bank and
  config tests, `seed:check`.
- [ ] 7.2 Generalise `retrieval.search` over a `Corpus` (D30), with `ScopedIndex.knowledge()` for documents. Verify:
  M12's retrieval tests and committed fixture outputs are unchanged, byte for byte (retrieval "Documents unchanged").
- [ ] 7.3 Write the corpora `SessionLines(session, upto_seq)` and `Overflow(character, exclude_ids)`, world-bound.
  Verify: scope tests (another session's line and another world's memory never appear; a listed memory is never a
  candidate).
- [ ] 7.4 Ask the `earlier` gate in every plan (D26, D27):
  - the 1:1 plan, the cast plan, the follow plan, the debate plan and watch's plan-ahead;
  - asked only with something to search;
  - X9's dropped gates drop it too;
  - `TurnPlan.recall_gate` and the deep branch on either gate.

  Verify:
  - turn-plan, follow-plan, debate-plan and watch-direction scenario tests;
  - an offline size test that records each grown request's bytes and build time against M12's (D27) in m13.md.
- [ ] 7.4a Make X9 cut debate arguments before gates (D28, U2): after the existing steps, a debate state cuts
  `latest_by_candidate` to 30 words, then `last_opposing` to 120 tokens, and only then drops gates. Verify:
  - the debate-plan scenarios, run on M11's committed long debate states (how many gates survive, before and after,
    recorded in m13.md);
  - a short debate's state bytes are unchanged.
- [ ] 7.5 Widen the early embedding (D32): it starts when the session has indexed lines or a candidate has an
  overflow with vectors; recall-only turns use the message and its earlier lines with no rewrite; BM25 only without a
  vector. Verify: the deep-turn "Recall-only speaker" scenario, and session-recall's "Recall only" and "No vector".
- [ ] 7.6 Build recall's search (D31): per-corpus fused order, overflow weighting, the merge (≤ 5 each, lines first on
  ties), MMR with composite keys. Verify: unit tests for weighting, the merge, the cap and MMR over mixed keys.
- [ ] 7.7 Build recall's Jev call 2 (D33):
  - one request per candidate, all at once, read by `recall.checkMs`;
  - 429 → fallback;
  - keep ≤ 3 at or above `t_recall`;
  - the all-missing fallback (top 2, no score) and partial answers deciding alone.

  Verify: session-recall's "Two kept" and "Every answer late", plus a partial test with `park_decision`.
- [ ] 7.8 Add recall to the deep graph (D34):
  - the parallel recall branch, and the `DeepRequest` / `DeepResult` fields;
  - each mode starts where M12 does;
  - each part has its own fallback, and both cancel together;
  - replay with no calls.

  Verify: deep-turn's "Both in parallel" and "Stop during both", and a replay test.
- [ ] 7.9 Build the tail, the trace and System 1 (D35):
  - the two headings after the documents block, ≤ 400 tokens, 60-word lines, newline collapse;
  - `contextInSession` and scored `memory.recalled`, plus `trace_memory_refs`;
  - `earlier` and `recall` rows, and `System1Section`'s "earlier lines" mapping and id resolution.

  Verify: session-recall's tail and trace scenarios, system1-trace's scenarios, and a frontend test resolving a
  `mem_` row.
- [ ] 7.10 Add Touch at the next pause: the run reads the stretch's traces and Touches scored, still-current recalled
  memories, never block lines. Verify: session-recall's "Overflow memory used".
- [ ] 7.11 Regenerate `system1.fixture.json` for scripted and the mock if any row shape changed. Verify:
  `fixtures:check` and `export-schema:check`.
- [ ] 7.12 Run the recall storm: Stop during 8 passage checks and 6 recall checks. Verify: all recorded `cancelled`,
  no reply, writer free.

## 8. The Memory tab (D37)

- [ ] 8.1 Make `reads.character_memory` left-join `sessions` and drop a dangling `sourceSessionId`, and make the
  MockClient do the same. Add the case to the portable contract suite. Verify: http-api and client-contract
  scenarios, with `npm run test:http` and `npm test`.
- [ ] 8.2 Add Memory tab pagination (50 + "Show more (n)") and remove the "Preview" ribbon. Verify: a component test
  with 120 memories, and the e2e profile spec updated if it pins the ribbon.

## 9. The evaluation, offline (D40)

- [ ] 9.1 Build the `decisions` slices: `importance` (100), `memory_guard` (~120), `earlier` (~120), `recall`
  (~120). Synthetic, split at creation, no bank overlap. The threshold rules are D40's. Verify: dataset checks, and
  test-mode runs on fixtures.
- [ ] 9.2 Build the `memory` suite:
  - rewrite (24 stretches with planted lists, 6 secrets, 6 small-talk);
  - in-session (60 over `evals/long`) and overflow (40) recall probes, with the three arms;
  - layer 3 (20 pairs, `agent` writer and recall).

  Wilson intervals throughout. Verify: `HORIZON_TEST=1 horizon eval memory --limit 3 --yes` runs on the fake.
- [ ] 9.3 Add the judge rows "Memory rewrite" (covered · supported · lost a fact) and "Over-mention", with planted
  validation sets; an unvalidated judge reports "not counted". Add the "memory for an absent character" unit test.
  Verify: judge tests.
- [ ] 9.4 Build the comparisons:
  - the query instruction on the recall dev split;
  - the `dupCosine` sweep on planted duplicates;
  - recall's λ;
  - `recall.checkMs` from a measured tail (the `latency` suite, store-bypassed).

  Verify: test-mode runs.
- [ ] 9.5 Labels (U1: delegated to the team): record the review pass in `evals/reviews/m13-review.md`. Verify: the file exists, and
  the held-out test split is untouched.

## 10. The paid runs (D41; each asked for separately)

- [ ] 10.1 Ask the user for each run with its estimate (D41), off-peak, through the store where W10 allows. Mark every
  paid run folder `.keep`, and check `ps` for leftover batches first. Verify: the user's OK is recorded per run in
  m13.md.
- [ ] 10.2 Run the decisions slices, then choose `t_keep`, the earlier `t_gate` and `t_recall` on dev, and confirm
  once on test. Verify: the per-item results go in `docs/ai/checks/m13/`, and any threshold change goes to the user as
  a choice.
- [ ] 10.3 Run the rewrite suite (check 1's 6 calls among them) and the `dupCosine` sweep. Verify: per-item results,
  targets with intervals, and every failure read.
- [ ] 10.4 Run the recall probes, the arms and the comparisons (instruction, λ). Verify: per-item results; a change to
  the instruction or λ goes to the user as a choice.
- [ ] 10.5 Run layer 3 (20 pairs). Verify: probe use and over-mention with intervals; a miss goes to the user as a
  prompt choice.
- [ ] 10.6 Run check 2 (10 pause runs, timed, store-bypassed) and check 4 with D33's timing (50 deep turns with both
  gates: slowest-of-14 vs slowest-of-8, 429s, first word). Verify: the results are in m13.md; any deadline change, or
  a tail over 200 ms at p90, goes to the user as a choice.
- [ ] 10.7 Run the embedding provider probe (U3 approved): 20 queries, store-bypassed, off-peak. Verify: the result is in m13.md; a space switch goes
  only with the user's OK.
- [ ] 10.8 Record the spend in m13.md against D41's ≈ $0.27. Verify: the spend table matches the ledger.

## 11. Docs (D43)

- [ ] 11.1 Amend everything doc 09 §6 lists:
  - doc 01 A4, A7, A9, A13, §9;
  - doc 02 B2, B4, B7, §8;
  - doc 03 C1, §7;
  - doc 04 P9, §7;
  - doc 05 X1, X7, X9, §7;
  - 05-ai-seams §2.2, §4, §6;
  - 02-storage §3.7 and its job kinds.

  Verify: the docs link check reports 0 broken.
- [ ] 11.2 Add built notes to doc 09 (with D3's corrections), and update doc 13 W6's M13 row (spend) and W12's rows
  (knobs found). Verify: the link check.
- [ ] 11.3 Write m13.md's "What M13 found" and "What M14 inherits":
  - the importance seam and S7's filter;
  - the over-mention result;
  - any recall-latency choice.

  Verify: the file is complete.

## 12. The final gates and the merge

- [ ] 12.1 Run every gate on the final commit:
  - backend pytest (gate worktree), ruff, mypy;
  - frontend lint, typecheck, test, test:http;
  - `seed:check`, `fixtures:check`, `export-schema:check`;
  - smoke;
  - e2e;
  - `openspec validate memory --strict`;
  - the docs link check.

  Verify: the table is in m13.md.
- [ ] 12.2 Ask the user how to finish (archive and squash into dev; no push unless asked). Verify: their answer is
  recorded in m13.md.

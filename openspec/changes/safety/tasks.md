# Tasks

> **Constraints for every task:**
> - **Tests are offline.** No network in automated tests: the socket guard stays on, and only the in-process fake
>   provider and obviously fake `sk-or-test-…` keys are used.
> - **The key stays private.** The real key is never printed, logged or put in fixtures.
> - **Contract.** M14 changes none (design D18). If any contract method, wire field, enum value, event or UI entry
>   point turns out to be needed, **stop and ask the user** before changing it.
> - **Background work and waits.**
>   - New background work starts only through `rt.spawn`, `actor.background` or a named after-turn task.
>   - New waits use the runtime clock, so `/_test/clock` settles.
> - **Our side stays fast.**
>   - The nouls ride requests already sent.
>   - The output check is the only new wait before `turn.end`, and the first word is unchanged (NFR-01).
> - **Nothing tuned is re-versioned.** No existing bank entry, `_conventions.json`, system message 1 or `memory-2`
>   changes (design D1, D3, D6).
> - **Scope.** Nothing from M15:
>   - no compiler v3, song prompt or `ASSETS.md`;
>   - no conversations, `naive` arms, blended latency run or `agent` default.
> - **Private items.**
>   - Nothing under `private/` is ever committed, and no item holds a real harmful instruction (D22).
>   - `git status` shows nothing from `private/` before every commit.
> - **No user text in the shared response store** (W10). The private safety items use their own store under
>   `private/evals/` (D23).
> - **Commits and pushes.** Commit at each phase's green checkpoint, without Claude attribution. Push nothing unless
>   the user asks, and never commit `6 RAG.pdf`.
> - **Ask the user first** before:
>   - any paid run (phase 8, each with its own estimate, off-peak: not 09:00–12:00 or 14:00–18:00 KL; the overrun
>     cap is max(1.5 × estimate, $0.01));
>   - any download;
>   - spawning subagents;
>   - any prompt, wording, threshold, deadline or setting change a finding suggests (as choices).
> - **Gate eval commands run with `HORIZON_TEST=1`.**
> - **Before any paid batch,** check that no earlier batch script or process is still alive (`ps`).
>
> **Every phase ends with these gates green:**
> - `uv run pytest`, `uv run ruff check`, `uv run mypy horizon`;
> - `npm run typecheck`, `npm run lint`, `npm test`, `npm run test:http`;
> - `npm run seed:check`, `npm run fixtures:check`, `npm run export-schema:check`;
> - `HORIZON_TEST=1 uv run horizon eval smoke --limit 5 --yes`.
>
> **Checkpoint:** commit the phase.

## 0. The base and the storms (design D2)

- [ ] 0.1 Confirm M13's gates on 4f696ad in the gate worktree:
  - backend pytest (2009 + the absent-character test fixed in f892374, 10 deselected), ruff, mypy;
  - frontend 550 / http 63;
  - e2e 66 (2 skipped);
  - `openspec validate safety --strict`.

  Record them in a new `docs/ai/checks/m14.md` §0.
- [x] 0.2 Add one storm test per new cancel path in D2's table to the cancel-storm suite (`tests/helpers/storm.py`),
  marked `xfail(strict=True)` with the phase that makes it pass. Verify: pytest collects them and they xfail.

## 1. The bank, the flags and the fake (design D3, D5, D13)

- [x] 1.1 Add the ten bank entries at version 1 with D3's wordings, `true`/`false` text, examples, declared states,
  thresholds, fallbacks and labels, then run `horizon eval bank-lock`. Verify:
  - `check_lock()` passes;
  - every M7–M13 entry keeps its version and hash;
  - the compiled golden fixture gains only the new entries.
- [x] 1.2 Add the loader rule that the content-rules text in `unsafe_request`, `output_rules` and `motion_rules` is
  identical, as `SHARED_KNOBS` does. Verify: a test edits one copy and the load fails naming the entries.
- [x] 1.3 **Bring the wordings and labels to the user** for review (W4) before anything asks them live. Record the
  answer in `docs/ai/checks/m14.md`.
- [x] 1.4 Add migration `0006_safety` (`message_ai_meta.safety` JSON, nullable) and the column in `db/tables.py`.
  Verify: up and down migration tests; old rows read NULL.
- [x] 1.5 Add `stored_safety` / `store_safety` to `services/ai_meta.py` with D5's value. Only Jev answers are written,
  nothing is written for a missing message, and a fork copies the column. Verify unit tests:
  - write, then read;
  - a missing message writes nothing;
  - a fallback writes nothing;
  - the fork copies;
  - a delete cascades.
- [x] 1.6 Add the session-event-sourcing exemption to the safety flags. Verify: rebuilding a session from its events
  neither needs nor recreates them.
- [x] 1.7 The fake answers the eleven safety question ids p 0.02 by default (D13), below any answer set with
  `answer_question`, `park_question(s)` or `refuse_question`. Verify:
  - a fake test;
  - the full backend suite is unchanged in outcome.
- [ ] 1.8 Phase 1 gates green. Checkpoint commit.

## 2. Input and care in every plan (design D4, D6, D7, D8)

- [ ] 2.1 New `ai/agent/safety.py`:
  - the questions for a line;
  - reading the answers (p, or fallback and why);
  - the cue decision from stored flags, with D7's stay rule over the last 3 user lines;
  - the System 1 rows (D19);
  - `SafetyCue` on `TurnPlan`.

  Verify unit tests for each rule (steer at ≥ `tSteer`, care at ≥ `tCare`, the stay, missing rows as no).
- [ ] 2.2 Ride the nouls in Jev call 1 (1:1), and write the flags right after the plan returns. Verify:
  - a 1:1 test: the request holds `unsafe_request` and `at_risk`;
  - a regenerate's request holds neither and uses the stored answer;
  - a failed plan stores nothing and the next plan asks again.
- [ ] 2.3 Ride them in the cast plan for `group_first`, `group_mentioned`, `everyone`, Everyone answer and Next
  speaker (only without stored flags), and `step_in` (input + care: U1). Add the per-actor in-flight set. Verify:
  - group and Step in tests;
  - two parallel plans ask once.
- [ ] 2.4 Ride `unsafe_request` alone:
  - in the `debate_ask` face plan, with the Ask as `quoted_latest` (U3);
  - `unsafe_note` (U4) in the next debate plan, or the opening's face plan, for an unchecked Interject;
  - `unsafe_note` in watch's `scene` plan and the plan made ahead for an unchecked director's note.

  Keep the moderator line through X9's cap, cutting arguments first. Verify:
  - debate and watch tests;
  - the over-cap debate test keeps the line and the noul.
- [ ] 2.5 Time the grown requests with the fake and pin D4's question counts per request kind. Record sizes and build
  times in `m14.md`. Verify: the pinning test.
- [ ] 2.6 Add the cue sentences (S3 chat and note wordings, S4's care paragraph) to `ai/agent/persona.py` and the
  agent engine's `cue()`:
  - before every other cue line;
  - care replacing G3's "next" and watch-steer sentences;
  - the labels `+care-1` / `+steer-1`.

  Add the TS twin's table with shared fixtures. Verify:
  - the cue fixtures in Python and TS;
  - a byte-identical system message for a steered and an unsteered request;
  - label tests.
- [ ] 2.7 One voice (D7) in group (every policy, Everyone answer) and Step in: cut to one speaker after the plan, skip
  the follow plan, discard started prefetches, and set `routing.reason`. Verify group tests for each row of D7's table.
- [ ] 2.8 The care face map after every face path, with the emotion row's action, and no reactions task on a care
  reply (D8). Verify:
  - speaker-emotion tests (Jev's pick, kept face, Jev failed);
  - a listener-reactions test (no `reaction` request).
- [ ] 2.9 Turn the storm tests for the plan paths from 0.2 green: the nouls on Stop and a superseding send, and the
  safety write on a cancelled turn, a fork and a regenerate.
- [ ] 2.10 Update `docs/ai/01` A4 (the questions and the fallback row), `docs/ai/06` E3 and E5, and `docs/ai/07` G2's
  one-voice note. Verify: the docs link check.
- [ ] 2.11 Phase 2 gates green. Checkpoint commit.

## 3. The output check (design D9–D12, D19)

- [ ] 3.1 New `AgentGuardrail` (`ai/agent/guardrail.py`):
  - D9's state (name, role, care, `quoted_message` cut from its start, `quoted_reply` never cut, ≤ 1,500 tokens);
  - `output_rules`;
  - outcomes at `tFlag` / `tBlock`, failing open with a flag and no `p`;
  - the hot-path 429 policy.

  Wire it to `agent` in `ai/profile.py`. Verify unit tests for each outcome, the cut, and the size cap.
- [ ] 3.2 `finish()`:
  - carry the `input` and `care` checks on every reply's turn spec;
  - merge `guardrail.checks` by name;
  - emit `insight` for a blocked reply;
  - write the `output_rules` row.

  Verify: a blocked-reply test showing all three checks and the block's `p`; the turn event order test.
- [ ] 3.3 Doc 11 check 3 offline: a group turn with a forced block and `DeciderFixtures`, the follow plan's pick
  landing before the block. Verify: no second reply and no `turn.next` for it.
- [ ] 3.4 Prefetches: check a finished prefetch before release (in parallel with its wait), discard it on a block,
  carry the result into `finish()` so it isn't checked twice; a prefetch still streaming at its slot is checked as
  live. Verify:
  - an Everyone test and a debate-opening test;
  - one `guardrail` row per reply.
- [ ] 3.5 Host lines inside the `host_line` task and verdict prose inside the `verdict` work, with their existing
  fallbacks on a block. Verify: a debate-host test (the fixed line) and a debate-verdict test (the failed-prose
  fallback).
- [ ] 3.6 The after-the-fact check:
  - `close_interrupted` keeps `info.ctx`;
  - a named after-turn task `output_check` reuses an in-flight `DecisionCall` through `final()`;
  - it survives Stop, End, a cap pause and leave, and is cancelled by deletes, Reset demo and shutdown;
  - a block scrubs and sets status `error` (U2).

  Verify:
  - a Stop-during-check test with one ledger row;
  - a delete-cancels test;
  - the storm tests from 0.2.
- [ ] 3.7 The waits after a turn count from the stream's end (D10). Verify:
  - a watch `paceMs` test and a debate `pauseMs` test, with a 500 ms check hidden;
  - the follow and debate member deadlines still count from `turn.end`.
- [ ] 3.8 The reducer rule in both languages (D11): an `error` with `content_refused` and a `messageId` empties the
  message or variant and sets status `error`, with no cost change. Clear the StreamingText buffer in the TS client.
  Verify:
  - shared reducer fixtures (live block, after the fact, blocked variant);
  - the served message equals the reduced one.
- [ ] 3.9 `NaiveGuardrail` (pass, no checks; `guardrail` joins `NAIVE_PORTS`), and the scripted guardrail and trace
  with one `output: pass` check in `ai/scripted/ports.py` and `mock/script/turnScript.ts`. Rebuild with
  `npm run seed:build` and `npm run fixtures:build`, and regenerate `rev12/messages.json` and
  `reducer/seed-dinner-seq25.json`. Verify:
  - `seed:check` and `fixtures:check`;
  - a diff showing only guardrail checks changed;
  - the profile-selection test.
- [ ] 3.10 Update `docs/ai/01` A13 and the risk table, `docs/ai/07` G2 (the follow plan beside the check), and
  `docs/backend/05-ai-seams.md`'s guardrail section. Verify: the docs link check.
- [ ] 3.11 Phase 3 gates green, plus `npm run e2e`. Checkpoint commit.

## 4. The motion and premise check (design D14)

- [ ] 4.1 In `sessions/lifecycle.create` for debate and watch:
  - `motion_rules` at `guardrail_prompt`;
  - 451 `content_refused` with S3's message and no row;
  - the exact same-text skip within the world;
  - start on failure with a warning.

  Verify:
  - lifecycle tests (refused, rematch skipped, Jev down starts);
  - an HTTP test for the 451 envelope.
- [ ] 4.2 The setup screen keeps the typed text and shows the toast on 451. Verify: a frontend test with the HTTP
  client's error (no new UI).
- [ ] 4.3 The storm test for an abandoned creation request. Verify it passes.
- [ ] 4.4 Phase 4 gates green. Checkpoint commit.

## 5. Memory (design D15, D16)

- [ ] 5.1 Add `instruction:l{n}` to the importance request through `extra_questions`:
  - drop and log a line at or above `memory.tInstruction`;
  - a missing answer fails the piece as a try.

  Verify:
  - writer tests (dropped, kept preference);
  - the "Jev down" test is now a failed try, then a skip after 3;
  - `importance` keeps its version.
- [ ] 5.2 S7's code filter in `services/memory/stretch.py`: drop user lines whose cue was on (stored flags and the stay
  rule) and their reply lines, from numbered lines, context lines and re-reads. Count the minimum after the filter;
  keep lines without a row. Verify stretch tests:
  - a care talk writes nothing and moves the checkpoint;
  - a steered request and its reply are absent;
  - old sessions are unchanged.
- [ ] 5.3 Turn the failed-noul storm test from 0.2 green.
- [ ] 5.4 Update `docs/ai/09` M3 and M4 and doc 11 S6's built note. Verify: the docs link check.
- [ ] 5.5 Phase 5 gates green. Checkpoint commit.

## 6. Images, songs and the notice (design D17, D18)

- [ ] 6.1 `Guardrail.check_prompt(ctx, kind, text)`:
  - `agent`: four image nouls in one request, or `song_copy`, at `guardrail_prompt`, with the SHA-256 LRU cache (512)
    of Jev answers only;
  - `naive` and scripted pass with no call.

  Verify: unit tests (cache hit, fail-open not cached).
- [ ] 6.2 `JobScheduler.start`: compile and check after the active-job check and before the hold, with I3's two
  messages; start on failure with a log line. Verify:
  - jobs tests (tweak refused, base refused, edits not checked, Jev down starts, no hold or row on refusal);
  - an HTTP 451 test.
- [ ] 6.3 `call_song`: check the brief before `before_send`; on refusal return `SongFallback("brief_refused")`.
  `commit_song` picks the note by reason in `services/theme.py`. Verify song tests:
  - `brief_refused` makes no music request and uses its note;
  - a Lyria refusal gets its note;
  - other faults keep `FALLBACK_NOTE`;
  - the check's ledger row carries the job ID.
- [ ] 6.4 The storm tests for `check_prompt` at start and in the song task. Verify they pass.
- [ ] 6.5 S8's two notice lines in `features/settings/ConnectionTab.tsx` and `features/profile/tabs.tsx` (shared by
  both clients), and the README's privacy section (what is sent where, D-80, switching to `deny`). Verify:
  - a frontend render test in the mock and HTTP clients;
  - the README link check.
- [ ] 6.6 Record doc 12 check 4 as "open until the first real Seedream refusal" in `m14.md` (no image paid to provoke
  one).
- [ ] 6.7 Phase 6 gates green. Checkpoint commit.

## 7. The suite offline (design D21–D24)

- [ ] 7.1 `evals/safety_suite.py`:
  - every part of D21's table;
  - `--part`, counts with Wilson intervals;
  - DeepSeek refusals counted;
  - the cross-validation on the 0.1–0.9 grid (precision, recall, highest-that-meets);
  - `--recut <run>`.

  Add `safety` to the CLI's suites. Verify: unit tests on planted answers for each part, the cross-validation and the
  re-cut (no provider call).
- [ ] 7.2 The items. The team writes the private items by hand, following D22's rules: requests name the harm;
  rule-breaking replies use `[step redacted]` / `[dose redacted]`; no usable detail. They go in
  `private/evals/safety/`. Commit `evals/safety/manifest.json` with hashes, and the harmless items written by hand.
  **Ask before** the paid DeepSeek draft of the remaining harmless items. Verify:
  - the manifest check;
  - `git status` shows nothing under `private/`.
- [ ] 7.3 **The user reviews every private label by eye** (D24); the team records a B2 pass for the harmless items in
  `evals/reviews/`. Record both in `m14.md`.
- [ ] 7.4 The private store and run folders (D23): a `ResponseStore` rooted at `private/evals/cache/`; per-item
  answers saved in `private/evals/safety/runs/<run-id>/` with `.keep`; committed results with hashes in place of
  private text. Verify:
  - a test that a private run never touches `data/cache/`;
  - a results-writer test (no private text).
- [ ] 7.5 The six judge entries and their B4 validation sets (30 real + 30 planted each). Verify: the bank lock, and
  "unvalidated" shown until each passes.
- [ ] 7.6 `latency --part output` (50 hand-built states), with `--part follow` and `--part debate` timing those plans
  with the check in place, all store-bypassed. Verify offline with the fake.
- [ ] 7.7 Smoke and CI: the suite runs with `HORIZON_TEST=1` on the committed items, reporting the skipped private
  count; smoke covers a steered 1:1 turn, a care group turn, a blocked reply and a refused motion. Verify:
  `HORIZON_TEST=1 uv run horizon eval safety --yes` and the smoke gate.
- [ ] 7.8 Prove D6's claim offline: the M13 layer-3 items' `agent` request hashes with M14 equal M13's when no cue
  fires. Record it in `m14.md` (no layer-3 re-run needed).
- [ ] 7.9 Phase 7 gates green. Checkpoint commit.

## 8. The paid runs (design D20, D21, D25)

Each run is asked for separately with its estimate, off-peak, after a `ps` check, with its folder marked `.keep`.
- [ ] 8.1 The Jev parts: input, care, output, motion, image, song (≈ 390 requests, ≈ $0.008–0.016), through the
  private store. Verify: the report and the per-item results in `docs/ai/checks/m14/`.
- [ ] 8.2 Judge validation (≈ 360 requests, ≈ $0.008). Verify: each judge's B4 result recorded per version.
- [ ] 8.3 The end-to-end parts: care_method, injection, honesty, drafter, drift (≈ $0.045–0.06). Verify:
  - the report, with every failure read;
  - provider refusals counted.
- [ ] 8.4 Doc 11 check 2 (output timing, ≈ $0.0015), and the follow and debate re-measure (≈ $0.002), all
  store-bypassed. Verify: p50 and p90 against 700 / 483 / 651 recorded in `m14.md`.
- [ ] 8.5 **Bring the findings to the user as choices:**
  - threshold moves from W12's values;
  - any deadline change (output, follow, debate);
  - any wording change.

  Apply only what the user chooses, bumping versions and re-validating as needed.
- [ ] 8.6 Record the spend table against D25's estimate and `spend.jsonl` in `m14.md`.

## 9. Docs and the final gates (design D26)

- [ ] 9.1 Amend everything doc 11 §6 and doc 12 §5 list not already done in phases 2–6, plus doc 11's and doc 12's
  "Built in" notes and W6's and W12's M14 rows. Verify: the docs link check, with 0 broken.
- [ ] 9.2 Finish `docs/ai/checks/m14.md`: the runs, the findings, the user's choices, and "What M15 inherits"
  (deadlines, the late-check rate, the injection follow rate, the provider-refusal share). Verify: it is linked from
  doc 13.
- [ ] 9.3 Final gates on the gate worktree:
  - backend pytest, ruff, mypy;
  - frontend typecheck, lint, test, http;
  - `seed:check`, `fixtures:check`, `export-schema:check`;
  - smoke, e2e;
  - `openspec validate safety --strict`;
  - the docs link check;
  - `git status` clean of `private/`.

  Record them in `m14.md` §12.
- [ ] 9.4 Ask the user how M14 finishes (archive + squash into dev, as before). Do nothing further without the
  answer.

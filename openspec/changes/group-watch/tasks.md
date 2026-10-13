# Tasks

> **Constraints for every task:**
> - **Tests are offline.** No network in automated tests: the socket guard stays on, and only the in-process fake
>   provider and obviously fake `sk-or-test-…` keys are used.
> - **The key stays private.** The real key is never printed, logged or put in fixtures.
> - **Contract.** M10 changes none (design D26). If any contract method, wire field, skipped reason or UI entry point
>   turns out to be needed, **stop and ask the user** before changing it.
> - **Background work and waits.** New background work starts only through `rt.spawn` or `actor.background`, and new
>   waits use the runtime clock (or `vclock.join` / `wait_handoff` when waiting on a task or future), so `/_test/clock`
>   settles.
> - **Our side stays fast.** The follow plan replaces the turn gap and never adds to it. Watch's plan hides inside the
>   pace. Nothing else new waits before a `turn.next`.
> - **Scope.** Nothing from M11–M15: no debate plan, asleep-side pause, host lines or verdict; no gates, rewrite,
>   `deep_check` or passages; no memory list or writer; no safety nouls, care cue or output check. `agent` stays
>   opt-in.
> - **`scripted` and `naive` keep their picks** (G13), except G1 (`naive`'s first slot and the all-asleep rule for
>   everyone), G5 (every profile) and G10 (`naive`'s recap).
> - **Commits and pushes.** Commit at each phase's green checkpoint, without Claude attribution. Push nothing unless
>   the user asks, and never commit `6 RAG.pdf`.
> - **Ask the user first** before:
>   - any paid run (phase 10, each with its own estimate, off-peak: not 09:00–12:00 or 14:00–18:00 KL);
>   - any download;
>   - spawning subagents;
>   - any prompt, wording or setting change a finding suggests (as choices).
> - **Gate eval commands run with `HORIZON_TEST=1`.** Without it, `.env`'s key makes `smoke` paid.
>
> **Every phase ends with these gates green:**
> - `uv run pytest`, `uv run ruff check`, `uv run mypy horizon`;
> - `npm run typecheck`, `npm run lint`, `npm test`, `npm run test:http`;
> - `npm run seed:check`, `npm run fixtures:check`, `npm run export-schema:check`;
> - `HORIZON_TEST=1 uv run horizon eval smoke --limit 5 --yes`.
>
> **Checkpoint:** commit the phase.

## 0. The base: the Stop fix and the shared storm helper (design D2)

- [x] 0.1 Confirm the Stop fix: `git merge-base --is-ancestor 3488b14 dev` and `… HEAD` both succeed. Write the
  result into a new `docs/ai/checks/m10.md` ("Step 0"); if either fails, stop and tell the user.
- [x] 0.2 Move `_storm` from `tests/integration/test_cancel_writes.py` to `tests/helpers/storm.py` unchanged (its
  `perf_counter` spin and its comment), plus an `assert_writer_free(db)` helper: no checked-out connection, and a
  fresh write within 5 s. Verify the four existing storm tests import it and still pass.
- [x] 0.3 Add a `park_decision`-based helper that holds a Decider call open so a storm can land "during a plan".
  Verify it with a test on M9's 1:1 plan: a storm during the parked plan leaves the writer free and the `turn_plan`
  row `cancelled`.
- [x] 0.4 Gates green; commit "M10 phase 0".

## 1. The bank: the `none` switch, the label check on options, and the new entries (design D6, D7)

- [x] 1.1 Add `none: bool = True` to `QuestionBank.question()`, leaving out a dynamic choice's `none` option when
  false. Verify that every existing entry compiles byte-identically without the argument (a golden test over all
  entries), and that `questions.lock.json` is unchanged.
- [x] 1.2 Check dynamic option values against the label rule. A value over 40 characters or on two lines is cut with
  M8's `cut_tokens` before compiling. Verify with a 70-character role, and confirm the full role stays only in
  `quoted_cast`.
- [x] 1.3 Move `route` to v3 (D6's instructions and `none` text). `JevRouter` passes `none=bool(mentions)`, and the
  `len(options) <= 1` branch answers the single eligible character when nobody is mentioned. Verify with tests:
  - no `none` without a mention;
  - one eligible character answers with no request;
  - mentions keep `none`;
  - the naive fallback is unchanged.
- [x] 1.4 Write `who_first`, `who_second`, `who_next`, `who_scene`, `talk_finished`, `emotion_line` and
  `emotion_opening` with D7's exact wording, states, floors (0.6), `t_end` 0.8 and fallbacks. Record them with
  `horizon eval bank-lock`. Verify that `check_lock()` is clean and that each compiles (with `{name}` where it has
  one).
- [x] 1.5 Write `evals/reviews/m10-entries.md`: each new entry's full compiled text, for the user's wording review
  (proposal "Your time"). Verify that `horizon eval overlap` passes.
- [x] 1.6 Regenerate `seed/system1.fixture.json` from the bank (seed-build). Verify that `seed:check` and
  `fixtures:check` pass, and the scripted group trace still shows only the `route` row.
- [ ] 1.7 Gates green; commit "M10 phase 1".

## 2. The cast plan: port, types and graph (design D3, D4, D22)

- [x] 2.1 Add `CastRequest`, `CastPlan` (with `for_speaker`), `FollowRequest` and `FollowPlan` to `ai/contexts.py`,
  plus `TurnPlan.cue`, `TurnPlan.answered` and `TurnSpec.plan`. Add `plan_cast`, `start_follow` and
  `decides_retrieval` to the `TurnPlanner` protocol. Verify a JSON round trip test for each type.
- [x] 2.2 `NoPlanner` and `ScriptedTurnPlanner`: `plan_cast` and `start_follow` return `None`, and
  `decides_retrieval = False`. Verify that scripted and naive group sends make no `turn_plan` or `follow_plan` row
  (spec "Group and watch plans per profile").
- [x] 2.3 `ai/agent/cast_plan.py`: steps for `plan_cast` on the M9 graph builder:
  - `state` uses the X9 builder per D5/D11/D13's kinds;
  - `ask` makes one `turn_plan` request with the who question (unless forced or single) plus one emotion question
    per candidate, plus `talk_finished` for watch turns after the opening;
  - `decide` computes the who pick with G1's fallbacks, `decide_face` per candidate, the steer rule and the rows of
    D22;
  - `route` returns `quick`.

  Verify with fixture answers per kind: the keys asked, the rows, the `not_used` marks, the fallbacks (late, 429,
  invalid) and that row purposes equal the call's purpose.
- [x] 2.4 Pin G9 with a test: no call-1 state (any kind) holds an `energy` key or energy-derived value, and an
  exhausted character is never a candidate.
- [x] 2.5 Repeat M9's check 1 settle test for `plan_cast`: 100 group plans on the virtual clock with parked and
  released answers, two identical runs. Record the numbers in m10.md.
- [ ] 2.6 Gates green; commit "M10 phase 2".

## 3. Group Auto under `agent`, G1 in the shared runtime (design D5, D6, D18, D21)

- [x] 3.1 In `group.send`: when every mentioned character is asleep, post each one's asleep note, then return. Make
  no router or planner call, in every profile. Make the same change in `mock/engines/group.ts`. Parity is a portable
  contract test (milestone `M10`, run on the MockClient by `npm test` and on the backend by `npm run test:http`, now
  `supports: "M10"`), which is stronger than a shared fixture file: the same test runs against both clients. Verify
  both runs and the backend test.
- [x] 3.2 The group job calls `plan_cast` first. With a plan, `run_speakers` gets the plan's `order` and passes each
  speaker `TurnSpec.plan = for_speaker(…)`. Without one (`naive`, `scripted`), the router path runs unchanged. Verify
  every row of D5's table with fixture answers, including a single eligible character (emotion asked, no who
  question).
- [x] 3.3 `TurnRunner.run` uses `spec.plan` when set: no plan task, the plan's rows and calls, and no retrieval when
  `branch` is set. Verify a planned group reply's trace (routing question "who answers first?", a `turn_plan` call,
  rows), and that M9's 1:1 path is unchanged (the existing 1:1 tests pass).
- [x] 3.4 `start_query` returns at once when the resolved planner's `decides_retrieval` is true (D18). Verify with
  tests that `agent` 1:1 and group sends write no `query_embed` row even with vectors, and that `naive` still embeds.
- [x] 3.5 MANUAL in group: each candidate's base face is its last AI-chosen face. Verify that a MANUAL group reply's
  row action is "recorded (MANUAL)" and the shown face is unchanged.
- [x] 3.6 Storm tests (D2) for a cast plan cancelled during the user message's append and during the parked plan.
  Verify the writer is free, the log reduces, and the row is `cancelled`.
- [ ] 3.7 Gates green; commit "M10 phase 3".

## 4. The follow plan (design D4, D8, D9)

- [x] 4.1 `ai/agent/follow_plan.py`: the follow state template of D8 (the builder, then `quoted_message`, with the
  2,000-token cut order) and the graph steps. `start_follow` returns a `FollowCall` whose `by(deadline)` waits on the
  deadline future with `vclock.wait_handoff` and then on the Decider's `by`. Verify with tests: the state shape, the
  cut order, and a pick, `none`, below floor, late, failure and 429 each giving D8's outcome and row.
- [ ] 4.2 The runner side: a `TurnSpec.follow` hook called when a reply's stream ends without error (before
  `finish`). A blocked reply cancels the handle. The mode awaits `by(turn_end + follow_plan)` and emits the second
  reply's `turn.next` at once, with no turn gap. With no pick, it sleeps the rest of the gap. Verify timings on the
  virtual clock:
  - a pick 120 ms after `turn.end` emits `turn.next` at +120 ms;
  - with no pick, the next job starts at +400 ms.
- [x] 4.3 Where it runs and where it doesn't (D8's lists, spec "When the follow plan runs"). Verify each case.
- [x] 4.4 No pick: `append_system1(first_id, variant, rows, calls)`, with purpose `follow_plan`, "no second reply"
  and "(late)". Verify that a late follow plan's row lands on the first reply and that the late answer's ledger row
  is `late`.
- [x] 4.5 `PURPOSE_CATEGORY["follow_plan"] = "decision"`. A cap refusal publishes `budget.reached` without the pause
  hook (M9 D35's rule). Verify with a cap test that no `session.paused` comes from the follow plan.
- [ ] 4.6 Settle test: 100 group sends with parked and released follow answers, two identical runs (D4). Record in
  m10.md.
- [ ] 4.7 Measure `F` (the stream's end to `turn.end`) offline on Windows over 100 scripted group turns, p50 and p90,
  for D9's timing check. Record in m10.md.
- [ ] 4.8 Storm tests (D2) for a follow plan cut by Stop during the parked call and during the first reply's
  `turn.end` write. Verify the writer is free and the row is `cancelled`.
- [ ] 4.9 Gates green; commit "M10 phase 4".

## 5. G5's reply epoch, Next speaker, Everyone and Step in (design D11, D12)

- [ ] 5.1 `SessionActor.reply_epoch`, `supersede()` (bump plus the superseded event under the write lock, drop stale
  queued reply jobs, discard unreleased prefetches) and `TurnSpec.epoch`. `turn.next` goes through `emit_checked`
  with the epoch check, and a failed check returns outcome `superseded` with no event. Verify the spec's "Never
  between the check and the write" scenario: 1,000 virtual-clock races.
- [ ] 5.2 Cooperative ends: `run_speakers` checks the epoch before each speaker, and the follow wait and the gap
  sleep race the superseded event. Verify:
  - "Sent in the gap" (no second reply to A; B answered);
  - "Announced reply finishes";
  - a watch Step in during a scene turn's gap keeps its `turnsTaken` increment.
- [ ] 5.3 The mock: the epoch on `LiveSession`, the check where `speakThen` emits `turn.next`, and stale tasks
  skipped. Parity is a portable contract test (milestone `M10`, as in 3.1), run on the MockClient and on the backend.
  Verify both produce the same event types and speakers.
- [ ] 5.4 Next speaker under `agent`: `plan_cast(kind="next")` with `who_next` minus the last speaker, or the chosen
  character's emotion only, and cue `next`. Verify the spec scenario "Next speaker under agent", and that
  `naive`/`scripted` stay random.
- [ ] 5.5 Everyone and policy `everyone` under `agent`: one `plan_cast(kind="everyone")`, the order by probability,
  asleep notes kept, and `Prefetch.start` taking `plan=` and skipping retrieval when the plan has a branch. Verify:
  - the spec scenario "Everyone in Jev's order" (one request);
  - a prefetched reply's face is the plan's;
  - a Jev failure gives cast order with fallback faces.
- [ ] 5.6 Step in under `agent`: pause, the user's line, `plan_cast(kind="step_in")`, then the follow plan. Verify the
  spec scenario "Step in under agent", and that `naive`/`scripted` keep 2 random replies.
- [ ] 5.7 Storm tests (D2) for a superseding send landing in the user message's append and in the `turn.next` check,
  and for Step in's second reply cut during its follow plan. Verify the writer is free and the log reduces.
- [ ] 5.8 Gates green; commit "M10 phase 5".

## 6. Watch: the order, the guard, the steer and the plan-ahead (design D13–D15)

- [ ] 6.1 The guard as a pure function over the message log (scene start, round size, `2n`, silent-longest
  tie-break, the reason text). Verify with unit tests: never spoken, a woken character, Step in replies counted,
  director's notes not counted, and the release-survives scenario (it reads the stored log).
- [ ] 6.2 `watch.turn` under `agent`: nudge → guard → `plan_cast(kind="scene")` minus the last speaker, plus the one-
  and two-awake cases. Verify the spec scenarios "Never twice in a row" (30 turns), "The guard fires" and "Naive stays
  round-robin".
- [ ] 6.3 The "Auto" opening via `plan_cast(kind="opening")` (`who_scene` + `emotion_opening`, no `talk_finished`).
  Verify the spec scenario "Auto opening", and that a chosen opening speaker is forced.
- [ ] 6.4 The steer: D14's rule, with the cap read from the last 2 character messages' stored traces and the director's
  note check. The row and its actions, and `cue = "steer"` on the per-turn plan. Verify "Steer, then cap" and "No
  steer during a note".
- [ ] 6.5 The plan-ahead: start conditions, `actor.background("plan_ahead")` with `deadline_at` = the due time, the
  fingerprint of D15, the redo on mismatch, and `clear()` cancelling `"plan_ahead"`. Verify:
  - one test per fingerprint field (each change forces a redo; no change uses the stored plan with exactly one
    request);
  - "Hidden by the pace" (a 1.2 s answer at Normal pace is used);
  - "None at the limit";
  - Stop during the gap gives `cancelled` and no rows.
- [ ] 6.6 Storm tests (D2) for the plan-ahead cancelled by `clear()` and by a fingerprint change, during its parked
  call and during the turn's `turnsTaken` write. Verify the writer is free and the log reduces.
- [ ] 6.7 Gates green; commit "M10 phase 6".

## 7. The cue sentence and the prompt labels (design D10)

- [ ] 7.1 Before touching the engine: record an `agent-1` group first-reply request fixture and a watch scene request
  fixture (`backend/tests/fixtures/plan/agent1_group.json`, `agent1_scene.json`).
- [ ] 7.2 `TURN_CUE_SENTENCES` in `ai/agent/persona.py`. `AgentTurnEngine.cue()` appends the plan's sentence after
  naive's cue and any director's note. The prompt label follows D10's table. Verify:
  - a first reply equals the `agent-1` fixture byte for byte;
  - a second reply differs only in the tail's cue line and is labelled `agent-3`;
  - system message 1 and the summary message are identical in all four label cases;
  - "After the director's note".
- [ ] 7.3 The TS twin `turnCueSentence()` in `domain/personaPrompt.ts`, and the shared fixture
  `backend/tests/fixtures/turn_cue/cases.json` read by both suites. Verify both pass byte for byte.
- [ ] 7.4 "View as prompt": the fixed cue note under the preview, built from the twin (the persona-prompt delta),
  replacing the stale mood-line wording in the spec. Verify `PromptPreview.test.tsx` checks the note and its example.
- [ ] 7.5 Gates green; commit "M10 phase 7".

## 8. The episode recap (design D19, D20, D21)

- [ ] 8.1 Add `timeoutsMs.episode` = 30000 to `seed/pricing.json` and `pricing.config.ts`, and
  `PURPOSE_CATEGORY["episode_summary"] = "summary"`. Verify `seed:check` and the provider-gateway scenario "Recap
  limit".
- [ ] 8.2 `NaiveSummariser.episode`: D19's request (`episode-1`), the `episode` settings row, the 30 s limit, the
  120-word cut at a sentence end, and empty output treated as a failure. Verify with the fake provider's canned
  `episode_summary` response (`X-Horizon-Purpose`): the ledger row's purpose and category, no energy change, and an
  over-long output cut.
- [ ] 8.3 `watch.summarise` posts the failure note on any non-cap failure, and a cap refusal takes the existing pause.
  Verify the "Timeout" scenario and a cap test.
- [ ] 8.4 Scripted and the mock: the simulated call's purpose becomes `episode_summary`, and the canned text is
  unchanged. Verify the backend test and the mock test "Mock recap", plus the portable spend tests in both clients.
- [ ] 8.5 Gates green; commit "M10 phase 8".

## 9. Evaluation offline: datasets, policies, suites and smoke (design D16, D23)

- [ ] 9.1 Write the labelling rule `evals/reviews/m10-labels.md` (who-speaks sets, `none` items, talk finished, watch
  emotion, language split) and commit it before any label.
- [ ] 9.2 `horizon eval watch-history` (refuses to overwrite a committed history without `--force`; store on;
  `naive`). Verify with a test-mode run on the fake provider that it writes the transcript format the summary suite
  reads, and that it refuses a second run.
- [ ] 9.3 `evals/datasets/who_speaks/build.py` and its three files from the committed group transcripts, the long
  scripts' group pools and hand-written items (the watch part waits for the histories in 10.1, built in 10.2). Labels
  are written blind, with the language split of D23. Verify that `horizon eval corpus-check`, `overlap` and the
  dataset split rule pass.
- [ ] 9.4 `evals/datasets/talk_finished/` (about 120, at least 60 yes; goodbye and polite-agreement loops). Verify
  the same checks.
- [ ] 9.5 The 40-item watch slice in `evals/datasets/emotion/` (32 `emotion_line`, 8 `emotion_opening`; D27). Verify
  that its items are built with the live watch state and that the build is deterministic.
- [ ] 9.6 `evals/policies.py`:
  - the who-speaks policies (the live fallback rule, balanced accuracy, the baselines);
  - the exact paired tests (McNemar; the stratum-weighted sign test as a two-binomial convolution);
  - the floor grid and `floor.second`'s needless-reply bound;
  - the `t_end` precision rule.

  Verify with unit tests on constructed answers, including "Always none can't pass" and "Needless replies bound the
  floor".
- [ ] 9.7 The `summary` suite gains the 10 recap items (built from the histories once they exist, 10.2), the
  120-word check and the judge nouls. Verify on a test-mode run with canned recaps, including an over-limit failure
  being printed.
- [ ] 9.8 `horizon eval freerun --mode watch|group` (signals only; timeouts apart from `none`; steered lines
  printed). Verify on the fake provider with fixture answers.
- [ ] 9.9 `horizon eval latency --part follow` (`S`, `L` and the recorded `F`; the ≤ 10 % rule; spells) and
  `--part watch` (Fast pace; plan-ahead used / redone / fallback; spells; the 90 s watchdog kept), both
  store-bypassed. Verify on the fake provider with parked decisions that the miss arithmetic and the spell grouping
  are right.
- [ ] 9.10 `smoke` gains one planned group send with a follow plan, one planned watch turn, one recap, one
  follow-timing request and one free-run turn. Verify that `HORIZON_TEST=1 uv run horizon eval smoke --limit 5 --yes`
  passes with no socket opened.
- [ ] 9.11 The delegated label review (D27): the B2 sample (max(15, ⌈n/5⌉) per set) checked against the rule and
  recorded in `evals/reviews/m10-*.md` before any paid run.
- [ ] 9.12 Gates green; commit "M10 phase 9".

## 10. Paid runs (design D24; each asked for separately, off-peak, with its estimate)

- [ ] 10.1 Ask, then run `watch-history` for both histories (≈ $0.03). Read and commit them, and mark the run folder
  `.keep`.
- [ ] 10.2 Build the watch who-speaks part and the recap items from the histories (9.3, 9.7). Re-run the offline
  checks and commit.
- [ ] 10.3 Ask, then run `decisions --set who_speaks` (≈ $0.013): floors on dev, the test split once, the paired
  tests. Write the floors into the bank (a version bump and a re-lock) and record them in m10.md with the per-item
  results under `docs/ai/checks/m10/`.
- [ ] 10.4 Ask, then run `decisions --set talk_finished` (≈ $0.006): `t_end`, with recall reported. Write it into the
  bank and record it as in 10.3.
- [ ] 10.5 Ask, then run `decisions --set emotion` for the watch slice (≈ $0.002): the `emotion_line` and
  `emotion_opening` floors, recorded as in 10.3.
- [ ] 10.6 Ask, then run `summary` for the 10 recaps (≈ $0.012). Record the target result, with every failure quoted.
- [ ] 10.7 Ask, then run `latency --part follow` (≈ $0.004). Record the miss rate with and without spells.
  - If more than 10 % miss: apply G2's rule (D9, D27), setting `timeoutsMs.decision.follow_plan` from the measured
    p90 of `S + L − F` in `seed/pricing.json` and its mirror. Record the NFR-02 exception and the finding.
- [ ] 10.8 Ask, then run `latency --part watch` (≈ $0.03). Record against NFR-02's 3 s p50, with the plan-ahead
  used/redone/fallback counts and spells.
- [ ] 10.9 Ask, then run the free runs from the smoke allowance (≈ $0.06). Record the four signals and read the
  steered lines. Anything outside G11's expected ranges (second-reply rate outside 10–60 %, guard above 20 %) goes to
  the user as a choice.
- [ ] 10.10 Copy each run's per-item results to `docs/ai/checks/m10/` with a README (as M9 did), and add each run's
  spend to m10.md's spend table against D24. Verify that `data/evals/spend.jsonl` matches.
- [ ] 10.11 Gates green; commit "M10 phase 10".

## 11. Docs and the final gates (design D25)

- [ ] 11.1 Amend everything doc 07 §6 lists:
  - doc 01: A3 rule 5, A4 and §8;
  - doc 02: B2, B3, B5, B7 and B8;
  - doc 03: C1;
  - doc 04: §7;
  - doc 05: X3 and X9;
  - doc 06: E1.

  Add doc 07's built notes and D9's finding beside G2's A2 note, and doc 13 W12's found values. Verify that every
  link resolves (the docs link check).
- [ ] 11.2 Finish `docs/ai/checks/m10.md`: step 0, the settle checks, `F`, every run, the findings, and "What M11
  inherits".
- [ ] 11.3 Run every gate plus `npm run e2e`, and `openspec validate group-watch --strict`. Record the results in
  m10.md; the known flaky `live-and-session-tools.spec.ts:6` is reported as it falls.
- [ ] 11.4 Commit "M10 phase 11". Don't push, and ask the user about archiving and the squash into dev.

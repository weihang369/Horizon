# Tasks

> **Constraints for every task:**
> - **Tests are offline.** No network in automated tests: the socket guard stays on, and only the in-process fake
>   provider and obviously fake `sk-or-test-…` keys are used.
> - **The key stays private.** The real key is never printed, logged or put in fixtures. Live checks only test that a
>   key is present.
> - **Contract.** M9 changes none. If any contract method, wire field or UI entry point turns out to be needed,
>   **stop and ask the user** before changing it.
> - **Background work and waits.** New background work starts only through `rt.spawn`, and new waits use the runtime
>   clock, so `/_test/clock` settles.
> - **Our side stays fast.** Before the first word, only Jev call 1 is new, and it overlaps the thinking delay (D6).
>   Reactions and the face check run after `turn.end`.
> - **Scope.** Nothing from M10–M15:
>   - no follow plan, debate plan or watch guard;
>   - no gates, rewrite, `deep_check` or passages;
>   - no memory list or writer;
>   - no safety nouls or care cue;
>   - no Jev emotion outside `agent` 1:1 (D34).
> - **`naive` doesn't move** (D34), apart from D14's one-write grouping.
> - **Commits and pushes.** Commit at each phase's green checkpoint, without Claude attribution. Push nothing unless
>   the user asks, and never commit `6 RAG.pdf`.
> - **Ask the user first** before:
>   - any paid run (phase 9, each run with its own estimate, off-peak);
>   - any download (including `langgraph`);
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

## 1. The LangGraph gate: doc 01's checks 1 and 2 (design D1–D3, D8)

- [x] 1.1 Pick the `langgraph` version by D1's rule: the newest PyPI release at least two weeks old. Name it, with
  what it pulls in, and **wait for the user's OK**. Verify: the user's answer is recorded in `docs/ai/checks/m9.md`.
- [x] 1.2 Add it with `uv add langgraph==<version>`. Verify:
  - `uv.lock` pins it;
  - `uv run python -c "import langgraph"` works;
  - a new test asserts that compiling and running a one-node graph with LangSmith's flag unset opens no socket.
- [x] 1.3 Build the plan graph skeleton in `ai/agent/plan_graph.py` (D3): nodes `state → ask → decide → route`, with
  `route` returning `quick` and no checkpointer.
  - `ask` uses the `Decider` (`start` + `by`) with a stub question set.
  - The run returns its node path.
  - Verify a unit test: path `["state","ask","decide","route"]` with fixture answers, and the fallback path when the
    decision is parked past its deadline.
- [x] 1.4 Check 1, overhead (D2): `tests/integration/test_plan_graph_checks.py` runs the plan 200 times through the
  graph and 200 times as plain calls of the same node functions. Verify: the p95 real-time difference is < 50 ms on
  Windows; the numbers are printed and recorded.
- [x] 1.5 Check 1, settling (D2): 100 planned runs on the virtual clock, with decisions parked and released at set
  times, run twice. Verify: no `SettleTimeout`; identical outputs and event order across the two runs;
  `Activity.busy` is empty at the end.
- [x] 1.6 Check 2, Stop during a plan or a reply (D2, D8). This uses a minimal harness that runs the graph inside an
  `rt.spawn` task cancelled by `clear()`. The real wiring comes in phase 3, and its spec tests re-run there. Verify,
  for Stop, leave, a cap pause and end, each during a parked decision and during a streamed reply:
  - the work is gone within 500 ms of virtual time;
  - the clock settles;
  - no task remains after the decision is released;
  - the decision's ledger row has outcome `cancelled`.
- [x] 1.7 Write `docs/ai/checks/m9.md` § "Doc 01 checks 1 and 2" with the numbers. **If either check fails, stop**
  and give the user D2's choices before phase 2. Verify: the section exists, and states pass or fail with figures.
- [x] 1.8 Amend doc 01: A7's M9 shape note (D3), and §7 checks 1–2 marked done with a link to m9.md. Verify by
  reading.

## 2. Plan types, bank entries and the pure emotion rule (no runtime change; D4, D5, D10–D13)

- [x] 2.1 Add `TurnPlan`, `PlannedFace` and `PlanRequest` to `ai/contexts.py`, and `TurnContext.plan` (default
  `None`) (D4). Verify:
  - a round-trip test: `TurnContext` with a plan → JSON → equal object;
  - every existing context test passes unchanged.
- [x] 2.2 Add the `TurnPlanner` protocol to `ai/ports.py`. Add `planner` and `face_check` to `PORTS`, with env vars
  `HORIZON_AI_PLANNER` and `HORIZON_AI_FACE_CHECK`.
  - Implement D5's table: `NoPlanner`, `NoFaceCheck`, and `ScriptedReactions(simulate=…)` built per D5's rule.
  - `AGENT_PORTS` gains only the ports whose agent implementations exist by the end of each phase. Here that is
    none: `planner` is added in 3.1.
  - Verify `test_ai_profile` gains the spec's "Naive gets no planner and no check" and "Agent without a key"
    scenarios, and the start-up log lists the new ports.
- [x] 2.3 Add `turn_plan` and `face_check` to `PURPOSE_CATEGORY` as `decision`. Verify: `call_ctx("turn_plan")` and
  `call_ctx("face_check")` give category `decision`, and `drains` is false.
- [x] 2.4 The bank's `{name}` placeholder (D11): `question(…, name=…)` fills it under the label rule, and raises
  `BankError` when the name is missing or too long. Verify:
  - the spec's three scenarios;
  - `check_lock()` is clean for every existing entry with no re-lock.
- [x] 2.5 Write `emotion_reply.json` and `emotion_greeting.json` (D10): E1's `what` / `not_for`, D10's examples,
  floor 0.6, the deadline and the state fields. Then run `horizon eval bank-lock`. Verify:
  - `test_question_bank` loads them;
  - compiling about Amara gives D10's instructions plus the S6 sentence;
  - `horizon eval overlap` passes;
  - shuffling is stable for a seed.
- [x] 2.6 Add `emotion.fade` to `runtime.config.ts` → `seed/runtime.json` → `domain/runtime_config.py` (D13). Verify:
  `seed:check` and the runtime config test read `["surprised","embarrassed"]`.
- [x] 2.7 Write the pure `ai/agent/emotion.py`: `decide_face`, the D12 merge, the D13 rows and actions, and the top-3
  candidates. Verify the unit tests cover every row of D13's table, the spec's merge example (0.38 / 0.35 → `neutral`,
  compared 0.73), the fade on `none`, below-floor and fallback, MANUAL's action, and `none` left out of the
  candidates.
- [x] 2.8 Write `evals/reviews/m9-entries.md` listing the two entries' full wording for the user's review (B2). Verify:
  the file exists; the review is asked for at the phase checkpoint, and changes bump the version.

## 3. The planner in `agent` 1:1 (D3, D4, D6–D9, D14, D15)

- [x] 3.1 Write `JevTurnPlanner` on phase 1's graph:
  - `state` uses `build_turn_plan_state` with no document titles;
  - `ask` asks `emotion_reply` or `emotion_greeting` per candidate, keyed `{qid}:{characterId}`, with the derived
    seed;
  - `decide` calls `decide_face`.

  Add `planner` to `AGENT_PORTS`. Verify planner unit tests with `DeciderFixtures`: a confident pick, `none`, below
  the floor, a parked decision past the deadline (`late`), a 429, `too_large`, and cancellation, each with the
  expected `TurnPlan`.
- [x] 3.2 Wire `TurnRunner.run` (D6):
  - spawn the plan task before `turn.next`;
  - await it after `turn.thinking`, cancelling it if the worker is cancelled;
  - freeze `plan` into `TurnContext` with the quick cap;
  - set `base_face` per AUTO or MANUAL, and `kind` per line.

  Verify the turn-plan spec's scenarios: a 1:1 send is planned; the first-chat greeting asks nothing; group stays
  unplanned; `naive` asks nothing new; the overlap with the thinking delay; a late answer.
- [x] 3.3 Turn off retrieval for planned turns (D9): no `start_query` in `one_on_one.send` under `agent`, and no
  `retrieve()` when the turn has a plan. Verify the session-modes scenario "Agent 1:1 is quick" (no `query_embed`
  row, no `knowledge` section), and that `naive` 1:1 retrieval tests still pass.
- [x] 3.4 Stop during a plan (D8): re-run phase 1's check-2 cases through the real runtime. Verify the spec scenarios
  "Stop while Jev is thinking", "Nothing leaks" and session-runtime's "Stop during the plan".
- [x] 3.5 One write for `turn.start` and the first emotion (D14). Verify:
  - a test that both events are stored in one transaction with consecutive `seq`;
  - the session-runtime scenario "Nothing between the start and the face";
  - the stored-equals-streamed tests and the seed and naive event-order tests pass unchanged.
- [x] 3.6 The engine takes its face from the plan (D14): `AgentTagParser` uses `ctx.plan.emotion`, with
  `version = "2"`. Verify the ai-ports scenarios "Face from the plan" and "Face kept" (no plan), and "Refused reply"
  (no `turn.start`, no face change).
- [x] 3.7 The trace (D15, D4): add `emotion.candidates` from the plan, the plan's System 1 rows with `seed`, the
  `turn_plan` call in `calls`, and `graph.path`. The capture row gets the plan. Verify the speaker-emotion scenario
  "Candidates on a confident turn", the system1-trace "Confident row" and "MANUAL row", and the turn-plan scenario
  "Captured with the turn".
- [x] 3.8 Replay from JSON (D4). Verify the turn-plan scenario: a serialised planned context rebuilds a byte-identical
  request with no decision request.
- [x] 3.9 MANUAL (E2, D6). Verify the speaker-emotion scenario "Base face under MANUAL", and that no reactions or mood
  line apply.
- [x] 3.10 Amend doc 01 §8 (the `TurnPlanner` row and the 1:1 entry points built), A4's emotion fallback row (fade),
  A5 ("built in M9"), and resolve OQ-AI-07 in `docs/requirements/08`. Verify by reading.

## 4. The mood line and `agent-2` (D16, D17)

- [x] 4.1 **Before any engine change,** record an `agent-1` request fixture for a planned-shape 1:1 turn and a group
  turn: `backend/tests/fixtures/persona_prompt/request_agent1_*.json`. Verify: the fixture test passes on the current
  engine.
- [x] 4.2 Add `MOOD_PHRASES` and `mood_line()` to `persona.py`, and `moodLine()` to `personaPrompt.ts`, with shared
  `mood_line/cases.json` fixtures. Verify: the persona-prompt scenario "Phrase per face" passes in both languages.
- [x] 4.3 Put the mood line in the agent tail in D16's order, and bump `PROMPT_VERSION` to `agent-2`. Verify:
  - the "Prefix unchanged" scenario: the `neutral` request equals 4.1's fixture byte for byte, and the `happy` one
    differs only in the tail;
  - the "Mood line before the cue" scenario;
  - no line under MANUAL or without a plan.
- [x] 4.4 Add the "View as prompt" note (D17) under the system message in `PromptPreview.tsx`, from `moodLine("sad")`.
  Verify the "Mood note" scenario in `PromptPreview.test.tsx`: the text and token count are unchanged.
- [x] 4.5 Mark doc 06 §6's mood-line row built (D16, D17), and note the `agent-2` version and why in doc 04 P1's
  version list. Verify by reading.

## 5. After-turn tasks, listener reactions and the reducer guard (D18–D22)

- [x] 5.1 Give the actor named background tasks (D20): a registry by name, `cancel_background(*names)`, and `clear()`
  cancelling `reactions` and `face_check`. Verify the session-runtime scenario "Stop cancels reactions and the check"
  (the rolling summary's row is still written).
- [x] 5.2 Add `actor.emit_checked(event, check)` under the writer lock (D20). Verify: a unit test where a listener's
  `turn.start` is queued between the check and the append drops the reaction.
- [x] 5.3 Make `ReactionPredictor.predict` async with `ReactionRequest` (D18). Move the call into the reactions task
  in a new `sessions/after_turn.py`, with listeners read from the actor's state when the task runs. Verify the
  listener-reactions scenarios "Next speaker not delayed", "No reactions in 1:1" and "Muted after the reply".
- [x] 5.4 Make `ScriptedReactions` async with D21's `simulate` flag. Verify:
  - "Same reactions" (ai-ports);
  - "Naive group with a key" (no row);
  - "Scripted group" (one simulated `reaction` row);
  - existing reaction timing tests.
- [x] 5.5 Write the `reaction.json` bank entry (D18) and re-lock. Verify: the bank test loads it, it compiles about a
  named listener, and `overlap` passes.
- [x] 5.6 Write `JevReactions` (D18): the state, one question per listener, the merge, the keep rule, at most 2, the
  fades outside the cap, the seeded delays, and the 1.5 s deadline. Add `reactions` to `AGENT_PORTS`. Verify the
  listener-reactions scenarios:
  - "Two listeners", "Cap of two" and "Same face";
  - "Muted listener fades";
  - "Late answer" and "Budget refusal".
- [x] 5.7 The drop rules (D20): `on_user_message(actor)` in every mode's send path, MANUAL in `_emotion_mode`, and the
  per-listener locked re-check. Verify the scenarios "The next speaker's reaction", "A user message" and session-modes
  "MANUAL drops reactions".
- [x] 5.8 The reducer guard (D22) in `reducer.py` and `sessionReducer.ts`, with the four new shared fixtures including
  `seed-dinner-seq25`. Verify:
  - both languages pass every reducer fixture;
  - the session-event-sourcing scenarios "Speaker's face kept against a reaction" and "Seed sessions still reduce";
  - `seed:check`.
- [x] 5.9 The MockClient's reactions (D21): `turnScript.ts` charges a simulated `reaction` call and applies the drop
  rules. Verify: the portable suite's spend and cap tests pass on both clients (`npm run test:http`), and the
  demo-data scenario "Mock reactions dropped by a user message".
- [x] 5.10 Mark doc 06 §6's reaction, reactions-task, mock and E6 rows built. Verify by reading.

## 6. The face check (D23, D24)

- [x] 6.1 Write the `face_check.json` bank entry (D23), with `not_for` and examples written under the overlap rule,
  and re-lock. Verify: the bank test loads it, `overlap` passes, and its state declares only `quoted_reply`.
- [x] 6.2 Write `JevFaceCheck` (`ai/agent/face_check.py`): the state is the reply's last 600 tokens, and the row
  follows W2's format. Add `face_check` to `AGENT_PORTS`. Verify unit tests for `yes`, `clash` (happy against angry,
  and sad against happy) and `no (words read: thinking)`, with `p` as p(face shown).
- [x] 6.3 The face-check task in `sessions/after_turn.py` (D24): record `info.auto` and `info.face`, apply the start
  conditions, ask with deadline `face_check`, and call `append_system1`. Verify the face-check spec scenarios:
  - "Non-neutral AUTO reply", "Neutral reply" and "Switched to MANUAL mid-reply";
  - "A long reply", "Agreement" and "Clash";
  - "Failed check";
  - "Next turn does not cancel" and "Regenerated before the row";
  - system1-trace "Row after the reply";
  - decider "Turn plan and face check".
- [x] 6.4 `ScriptedFaceCheck` with `faceCheckMs` (300) in the timing table (`runtime.config.ts` → `seed/runtime.json`
  → `runtime_config.py`). Verify the face-check scenario "Scripted check".
- [x] 6.5 Add `face_check` to ENG-02 AC2's list in the requirements doc (W2). Verify by reading.

## 7. Scripted and mock parity, the System 1 fixture and Insight (D15, D25)

- [x] 7.1 Regenerate `seed/system1.fixture.json`. The seed-build generator `system1.ts` emits `emotion_reply`,
  `emotion_greeting` and `face_check`, and skips `reaction` and every judge. Verify the demo-data scenarios "Emotion
  and face-check rows" and "Judges are not turn rows", and `seed:check`.
- [x] 7.2 `ScriptedTurnPlanner` (D25): a simulated `turn_plan` call, plus the fixture row with its answer filled at
  `finish` from the face shown. Verify the turn-plan scenarios "Scripted 1:1 turn" and "Naive with a key", and
  system1-trace "Scripted 1:1 rows shown".
- [x] 7.3 The MockClient's 1:1 engine charges `turn_plan`, adds the emotion row, and runs the mock face check. Verify
  the demo-data scenario "Mock 1:1 turn" on the MockClient. The portable suite passes on both clients with the same
  spend.
- [x] 7.4 Insight's "kept" chip (D15) in `InsightDrawer.tsx`. Verify the speaker-emotion scenario "Kept face in
  Insight" in a component test. A face with no candidates keeps its source label, and system1-trace "No rows" (`naive`
  1:1) still holds.
- [x] 7.5 Update the E2E expectations that count simulated 1:1 spend or System 1 rows. Verify:
  `npm run e2e` passes on the mock and HTTP projects.

## 8. Evaluation tooling, offline (D26–D31)

- [x] 8.1 Write `evals/policies.py` (D26): the emotion and reaction policies on `decide_face` and the keep rule, their
  baselines, and floor selection on dev from the seeded order. Verify the evaluation-harness scenarios "Emotion item
  with a kept face" and "Floor chosen on dev" on fixture answers.
- [x] 8.2 Extend the `decisions` report (D26): the baseline difference with McNemar, coverage, the merge rate, and the
  reaction share. Verify a report test on fixture answers.
- [x] 8.3 Write the labelling rule in `evals/reviews/m9-labels.md` (D27) **before** any item is labelled. Verify the
  file is committed first: its commit precedes the dataset commit.
- [x] 8.4 Build `evals/datasets/emotion/` (100 items) with a builder that takes contexts from the transcripts and the
  long scripts plus written lines, labelled blind (D27). Verify:
  - `smoke` loads it;
  - the split rule test;
  - `overlap` passes;
  - the keep cap is 20–30;
  - the spread matches D27's table.
- [x] 8.5 Build `evals/datasets/reactions/` (90 items), the same way (D27). Verify the same checks, with at most 27
  `none`-acceptable items.
- [x] 8.6 Write the judge entries (D28, D29): `judge_names_feeling` (noul) and `judge_pairwise` (choice, no shuffle),
  and re-lock. Verify the question-bank scenarios "Pairwise judge" and "Shared face check", and that "Never live"
  still holds.
- [x] 8.7 Build the validation sets (D28, D29): `judge_names_feeling.jsonl` (30 real with the found "yes" lines, 30
  planted) and `judge_pairwise.jsonl` (30 known-winner pairs from the `CLASH` map and mismatched lines). Extend B4
  scoring with the false-alarm rule and the pairwise both-orders rule. Verify the "Too many false alarms" scenario
  and a pairwise scoring test.
- [x] 8.8 Write the `moodline` suite (D30): item selection by plan, both arms, the three checks, the block bootstrap
  (seeded, 2,000 resamples) and E8's verdict text. Verify, offline on fixture answers and canned replies:
  - "Same history in both arms";
  - "Replay from the store";
  - "Verdict is advice";
  - a bootstrap unit test on a known split.
- [x] 8.9 Write the `latency` suite (D31): API-driven sends, Stop at the first token, store bypass, and the
  order-statistic intervals. Verify on the fake provider: "Never from the store" and "Stopped at the first word";
  the report renders the p50 and p90 rows.
- [x] 8.10 Widen `smoke` and the suite list (evaluation-harness "Suites and options" and "Smoke runs in test mode"):
  one planned `agent` 1:1 turn, the first `moodline` item, and one `latency` turn. Verify: the CI smoke command exits
  zero with no socket.
- [x] 8.11 Prepare B2's review sample of both decision sets and both judge sets in `evals/reviews/m9-*.md`, and ask
  the user to review them (or delegate, as in M8). Verify: the review is recorded, with disagreements, before phase
  9.
- [x] 8.12 Amend doc 02: B2's emotion and reaction rows (D27), B4's pairwise entry and the "names the feeling" mix
  (D28, D29), and B7's `moodline` and `latency` commands. Update `evals/README.md`'s command table. Verify by reading.

## 9. Paid runs (each asked for, off-peak, through the store except latency; D32)

- [x] 9.1 `decisions --set emotion`: ask with its estimate (≈ $0.009), run it, choose the floor on dev, and report the
  test split once. If no floor meets E8's target, stop and give the user choices (reword, or grow the set by 40).
  Verify: the report and the chosen floor are in m9.md.
- [x] 9.2 `decisions --set reactions`: the same (≈ $0.008). Verify likewise.
- [x] 9.3 Write the chosen floors into the bank (version bump, re-lock), then re-run the offline gates. Verify:
  `check_lock()` is clean, and m9.md records each floor with its version.
- [x] 9.4 Judge validation for `judge_names_feeling` and `judge_pairwise` (≈ $0.003). A failing judge gets the user's
  choice before any rewording. Verify: the results per question and version are in `evals/baselines/judges.json` and
  m9.md.
- [x] 9.5 `moodline`: ask with both options (100 ≈ $0.11, 60 ≈ $0.07), then run the chosen one. Verify: m9.md holds
  the exact-match difference, the pairwise result, the "names the feeling" pass rate, the clash rate and the verdict.
  Any rewording or dropping goes to the user first.
- [x] 9.6 `latency` (≈ $0.03, store bypassed). Verify: m9.md holds the face and first-word p50/p90 against NFR-01,
  Jev's distribution and the deadline-fired rate.
- [x] 9.7 Update doc 02 B5 (the floors found) and B8 (the 1:1 timing figures), and record the spend table against
  D32. Verify by reading; the spend log matches `spend.jsonl`.

## 10. Integration and close

- [x] 10.1 Run every gate on a clean tree, plus `npm run e2e`. Verify: all pass, and the counts are recorded in
  m9.md.
- [x] 10.2 Run `openspec validate turn-plan-emotion --strict`. Verify: it reports valid.
- [x] 10.3 Write m9.md's summary: what M9 found, the spend against D32, and what M10 inherits (group emotion via the
  follow plan, the floors to reuse, the latency baseline). Verify by reading.

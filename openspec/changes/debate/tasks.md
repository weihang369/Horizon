# Tasks

> **Constraints for every task:**
> - **Tests are offline.** No network in automated tests: the socket guard stays on, and only the in-process fake
>   provider and obviously fake `sk-or-test-…` keys are used.
> - **The key stays private.** The real key is never printed, logged or put in fixtures.
> - **Contract.** M11 changes none (design D24). If any contract method, wire field, pause or skipped reason, event or
>   UI entry point turns out to be needed, **stop and ask the user** before changing it.
> - **Background work and waits.** New background work starts only through `rt.spawn` or `actor.background`, and new
>   waits use the runtime clock (or `vclock.join` / `wait_handoff`), so `/_test/clock` settles.
> - **Our side stays fast.** The debate plan replaces the turn gap and never adds to it. Host lines and the verdict
>   work hide in the pause, the banners and the existing delays. The pick never waits in the inbox.
> - **Scope.** Nothing from M12–M15:
>   - no retrieval, gates, rewrite or passages in debate;
>   - no memory list or writer;
>   - no safety nouls, motion check or output check;
>   - no `naive` verdict arm or layer-3 conversations (M15).
>   `agent` stays opt-in.
> - **`scripted` and `naive` keep fixed order** (V12), except the shared rules: D3's slots, D4's pause, the teammate
>   fix, the resume rule, and `naive`'s DeepSeek host and verdict.
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

## 0. The base (design D2)

- [x] 0.1 Confirm the base. `git diff --stat ef94298 c8cdb54 -- backend frontend seed evals` must show no code
  change (M10's gates ran on `ef94298`). Re-run the backend gate in the gate worktree on c8cdb54, plus the frontend
  gates and `npm run e2e`. Write the results into a new `docs/ai/checks/m11.md` ("Step 0"). If any gate differs from
  M10's (1451 / 507 / 61 / 66 + 2 skipped), stop and tell the user.
- [x] 0.2 Add `storm_during_write` and `storm_during_call` helpers on top of `tests/helpers/storm.py` (unchanged).
  The second parks a Decider call (`park_decision`) or a canned chat response. Each asserts the D2 checks: no
  checked-out connection, a fresh write within 5 s, `assert_reduces`, the clock settles.
  Verify: a test applies both helpers to an existing M10 path (the plan-ahead cancelled by `clear()`) and passes.

## 1. The bank and the loader (design D6, D7, D12, D17–D19, D21)

- [x] 1.1 The loader:
  - `{side}` / `{other}` placeholders, values checked against {"Proposition", "Opposition"};
  - `{n}` for score entries, a whole number 1–6;
  - a missing or other value raises a bank error.
  Verify: tests for each placeholder, a refused "Team Blue", and an unchanged lock hash for every existing entry.
- [x] 1.2 The loader checks the shared knobs: the three `member_*` floors must be equal, and the five `rubric_*`
  `thresholds.margin` must be equal (`floor.member`, `verdict.margin`).
  Verify: a test with one drifted value fails to load, naming the knob.
- [x] 1.3 Write `member_rebuttal`, `member_closing` and `member_panel` with D7's exact wording: purpose
  `debate_plan`, no `none`, `describe`, the state, floor 0.6, fallback `next_in_order`.
  Verify: compiled-text tests for both sides and the panel.
- [x] 1.4 Write `emotion_debate_opening` with D7's wording (E1's 8 options, `emotion_line` v2's `what`, `not_for` and
  examples) at floor 0.6.
  Verify: the compiled text and an overlap check against the bank's other emotion examples.
- [x] 1.5 Write the five `rubric_*` score entries with D12's instructions and levels: 5 levels, `shuffle: false`,
  `thresholds.margin` 0.5; `rubric_generic` uses `quoted_criteria` and `{n}`.
  Verify: compiled-text tests, including a generic criterion whose label appears only in the state.
- [x] 1.6 Add the builder switch `last_spoke: bool = True` to `build_turn_plan_state` (D6).
  Verify:
  - with `False`, no `quoted_cast` entry has `last_spoke`;
  - with the default, every existing state is byte-identical (golden fixtures from M8–M10).
- [x] 1.7 Move `who_scene` and `who_next` to version 3, built with `last_spoke=False` everywhere they are asked (cast
  plan, plan-ahead, the decisions builders) (D17).
  Verify: a watch turn's and a Next speaker's state carry no `last_spoke`, and a test pins that the guard still forces
  a character silent for two rounds.
- [x] 1.8 Write the judges:
  - `judge_keeps_side` and `judge_engages` (D21);
  - `judge_starts_new` (D18);
  - `judge_summary_unsupported` v2 with the optional `quoted_premise` (D19).
  Verify: compiled-text tests, with v2 compiling without a premise for a rolling-summary item.
- [x] 1.9 Run `horizon eval bank-lock` and rebuild the seed (`npm run seed:build`), so `system1.fixture.json` gains
  the new labels; then `horizon eval overlap`.
  Verify: `seed:check` passes; the lock lists 12 new entries at v1, `who_scene` / `who_next` at v3 and
  `judge_summary_unsupported` at v2; the overlap check reports 0 problems.

## 2. The slots and the asleep side, every profile (design D3, D4)

- [x] 2.1 Replace `phase_order` with `phase_slots(cfg)` (sides per slot). `step` fills each slot when it comes up with
  the first eligible member in fixed order (no planner yet).
  Verify:
  - a scripted 2 v 2 Standard debate's speakers are prop[0], opp[0], prop[1], opp[1] per phase, as before;
  - a 2 v 1 runs P, O, P;
  - a panel follows cast order.
- [x] 2.2 V3's skip rule: a slot whose side has nobody eligible but someone awake is used, with "{name} is asleep,
  skipping." for the first asleep member not yet heard. The skip note carries the existing `debate` tag.
  Verify: the session-modes scenario "A side heard already skips the slot".
- [x] 2.3 Rebuild the cursor from the log: since the phase's banner, arguments and skip notes each use one slot, and
  "heard" is the set of argument authors. A still-eligible `state.nextSpeakerId` fills the next slot.
  Verify: the scenario "The cursor survives an idle release", plus a fork mid-phase.
- [x] 2.4 Energy at turn start: an announced member asleep at their turn gives way to the next eligible teammate with
  a fresh `turn.next`. Asleep members are listed in `routing.skipped` with reason `exhausted`.
  Verify: the debate-plan scenario "Asleep after the announcement", under `scripted`.
- [x] 2.5 V5's pause (D4): when nobody on a slot's side is awake:
  - each asleep member's note with `energy_exhausted`;
  - the side's system note;
  - `session.paused` reason `user`, `actor.held`;
  - the slot kept.
  ▶ or Next turn re-runs the slot.
  Verify: the three session-modes pause scenarios.
- [x] 2.6 The missed-turn facts for the verdict, computed from the log (D4): per side, the slots of every reached
  phase-iteration minus its arguments, with the reason "asleep" or "the debate ended early".
  Verify: unit tests for a side asleep through a round, and for an early End.
- [x] 2.7 The mock: `mock/engines/debate.ts` gets the same slots, cursor, skip rule, energy re-check and pause. (Its
  fixed verdict lead-in moved to 6.2, with the scripted host's.)
  Verify: the mock's unit tests mirror 2.1–2.5.
- [x] 2.8 The portable parity test (milestone `M11`): a scripted 2 v 1 Quick debate whose whole Opposition is asleep
  (a seed world has three characters), then a top-up and ▶. Run it on the MockClient (`npm test`) and on the backend (`test:http`).
  Verify: both produce the same event types, notes, speakers and pause.
- [x] 2.9 `naive`'s teammate fix (D10): the debate line names the side and teammates apart from the opponents, and a
  panel's others. `naive`'s debate requests take the label `naive-6` through the per-request label hook; every other
  `naive` request keeps `naive-5`.
  Verify: the ai-ports scenario "A teammate is not an opponent", and label tests for a debate and a 1:1 request.
- [x] 2.10 Storms (D2) on the pause path: a storm during the asleep notes' write and during `session.paused` leaves
  the writer free.
  Verify: the D2 checks pass.

## 3. The debate plan (design D5, D6, D8, D9, D25, D27)

- [x] 3.1 Add `debate_plan` to `PURPOSE_CATEGORY` (`decision`), and a refused debate plan publishes `budget.reached`
  without pausing (M9 D35's rule).
  Verify: the provider-gateway scenario "Cap reached at the debate plan".
- [x] 3.2 The types: `DebateRequest`, `DebatePlan`, and the `DebateCall` protocol with `member(deadline)`,
  `faces(until)` and `cancel()`. `TurnPlanner.start_debate` returns `None` from `NoPlanner` and
  `ScriptedTurnPlanner`.
  Verify: type checks, and a test that `naive` and `scripted` debates make no `debate_plan` request.
- [x] 3.3 `ai/agent/debate_plan.py`: the state per D6 (the builder with `last_spoke=False`, `last_opposing` per the
  side and panel rules, `latest_by_candidate` at 60 words), the questions (member question when ≥ 2 candidates,
  `emotion_line` per candidate) and the decide step (`floor.member`, fixed-order fallback), on the plan graph's shape
  with one Decider `start(...)` behind `member` and `faces` (W11).
  Verify: unit tests for each outcome row of D8's table, and the debate-plan scenarios "The rebuttal state" and
  "Uneven sides never quote a teammate".
- [x] 3.4 The runtime timeline (`sessions/debate_plan.py`, D8):
  - start at `turn.end` for the next same-phase slot;
  - with a member question, emit `turn.next` when `member()` returns, with no turn gap; with one member, the gap as
    today;
  - store `(fingerprint, slot, call)` as `actor.background("debate_plan")`;
  - at turn start, use `faces(now)`.
  Verify: the scenarios "A quick pick", "A late answer", "Unsure", "A late member, an on-time face" and "Too late for
  the face", all on the virtual clock with `park_decision`.
- [x] 3.5 The fingerprint: M10 D15's function, with the seq of the last character or user message, plus the target
  (phase, iteration). A mismatch at turn start keeps the announced member and asks the faces again (`debate_ask`'s
  machinery, `turn_plan` deadline). Pause drops the stored faces.
  Verify:
  - one test per fingerprint part;
  - "A banner doesn't spoil the plan";
  - "An Ask in the pause".
- [x] 3.6 The phase-boundary plan: at a phase's last `turn.end` (not before the verdict), stored with its target, and
  its member deadline is that slot's turn start. `begin_phase` uses it only on a matching target and fingerprint;
  Extend and Skip discard it.
  Verify: the scenario "Extend discards the plan", and a test that the closing's first slot uses a stored plan after
  the bridge.
- [x] 3.7 The trace:
  - `routing.question`, `candidates`, `selected`, `forcedBy: "round_order"`;
  - `routing.reason` "Side by the debate order; speaker chosen by Jev" (and its fallbacks);
  - the rows of D27, with late answers written through `append_system1` as `fallback` rows carrying Jev's answer.
  Verify: the system1-trace scenarios "A confident pick", "A late answer during the argument" and "Faces asked again
  after an Ask".
- [x] 3.8 `clear()` adds `"debate_plan"` to the names it cancels.
  Verify: the debate-plan scenario "Ending during a plan", with the call recorded `cancelled`.
- [x] 3.9 Settling (M9 check 1's test, repeated for debate): 50 `agent` debate slots with parked and released
  answers, run twice.
  Verify: the virtual clock settles, and the two runs' event logs are identical.
- [x] 3.10 Storms (D2) on a stored debate plan: cut by `clear()` during the `turn.next` write and during the parked
  call, and cut by a fingerprint change.
  Verify: the D2 checks pass.

## 4. Faces in debate (design D7, D8)

- [x] 4.1 Add the `CastKind` values `debate_opening` (`emotion_debate_opening`, forced speaker) and `debate_ask`
  (`emotion_reply`) to `plan_cast`.
  Verify: unit tests of each request's keys and state.
- [x] 4.2 The first opening's plan starts at Start, during `debateStartMs`, and is stored with the fingerprint; its
  deadline is the first opening's turn start.
  Verify: the turn-plan scenario "The first opening's face is ready at its start".
- [x] 4.3 Each prefetched opening runs its own `plan_cast(debate_opening)` when its prefetch starts, and
  `Prefetch.start` passes the plan into its context (M10 D11's path). An opening with no prefetch plans at turn start.
  Verify: the scenario "A prefetched opening keeps its own plan", and that a prefetch discarded by Extend is recorded
  `cancelled`.
- [x] 4.4 Ask answers plan at turn start with `plan_cast(debate_ask)`.
  Verify: the scenario "Ask answers are planned".
- [x] 4.5 The face rule in debate is M9's `decide_face` (floor, keep, fade, the merge). `AgentTurnEngine` no longer
  holds M8's face for a planned debate turn.
  Verify: the speaker-emotion scenarios "A rebuttal reacts to the argument it answers" and "A late face is a kept
  face", and the updated ai-ports scenario "Face kept".

## 5. The debate cue, the steer reword and the prompt labels (design D10)

- [x] 5.1 First, before the engine changes: record an `agent-1` debate request fixture beside M9's and M10's in
  `backend/tests/fixtures/agent_request/`.
  Verify: the fixture is committed and a test loads it.
- [x] 5.2 `DebateMeta` gains `teammates_heard`, `after_interject` and `panel`, computed by the runtime from the log
  when it builds the spec.
  Verify: unit tests for a teammate heard, an Interject before and after the last argument, and an extended round.
- [x] 5.3 `DEBATE_CUES` and the debate branch of `AgentTurnEngine.cue()`: the phase line, then the extended,
  teammate and moderator sentences in D10's order. Ask keeps `naive`'s cue.
  Verify: the persona-prompt scenarios "A rebuttal after a teammate", "An extended rebuttal after an Interject" and
  session-modes' "Interject reaches the next argument once".
- [x] 5.4 The TS twin `debateCue()` in `domain/personaPrompt.ts`, plus the shared fixture
  `backend/tests/fixtures/debate_cue/cases.json` read by both suites.
  Verify: the scenario "Same table in both languages".
- [x] 5.5 Replace the steer sentence in `TURN_CUE_SENTENCES` and `turnCueSentence()` with D10's wording, with
  `{user}` filled from the You card, and update the turn-cue fixtures.
  Verify: the persona-prompt scenario "The steer names the watcher".
- [x] 5.6 The labels: `prompt_version_for` gives `agent-5` / `agent-6` for the steer sentence and `agent-7` /
  `agent-8` for a debate argument with the cue. `agent-1` … `agent-4` are unchanged.
  Verify: the ai-ports scenarios "Label follows the bytes" and "Steer and debate labels".
- [x] 5.7 The prefix proof:
  - a V4 debate request differs from 5.1's fixture only in the tail's cue line;
  - system message 1 is byte-identical across one debate's turns;
  - every M9 and M10 request fixture is unchanged.
  Verify: the persona-prompt scenario "Two rounds, one prefix", plus the existing fixture tests.
- [x] 5.8 "View as prompt" gains the fixed debate note, built from `debateCue("rebuttal")`.
  Verify: the persona-prompt scenario "The note is the table's", as a frontend unit test.

## 6. The host (design D11, D25)

- [x] 6.1 `seed/runtime.json` (from `scripts/seed-build/runtime.config.ts`) gains `debate.hostWelcomeWaitMs` 3,000 and
  `debate.hostBannerWaitMs` 1,500; `domain/runtime_config.py` reads them, and the mock's timing config mirrors them.
  (Built: the knobs sit under `runtime.debate`; the mock's host lines are fixed and instant, so it has no wait to
  mirror.)
  Verify: `seed:check` passes, and a config test reads both values.
- [x] 6.2 The port: `DebateHost` gains `fixed_line(key, by)`, `async narration(ctx, key)`, `async assess(ctx, by)`
  and `deliver(assessment, picked)`. `host` joins `NAIVE_PORTS` and `AGENT_PORTS`. `ScriptedDebateHost` returns its
  fixed lines and the three fixed lead-ins, and the mock's `debate.ts` shows the same lead-in after the VERDICT
  banner with Auto host.
  Verify: the ai-ports scenario "Profile selection", and the debate-host scenario "Scripted stays free".
- [x] 6.3 `ai/naive/host.py` (prompt `host-1`):
  - V6's instruction verbatim, the S6 transcript sentence, the per-kind content, the explicit language last line;
  - `runtime.llm.calls.host`, purpose `host`;
  - validation: quotes and "Host:" stripped; empty or over 60 words → `None`.
  Verify: request-shape tests with canned responses, and the scenario "Too long".
- [x] 6.4 The runtime: each line is requested ahead by `HostKey` as `actor.background("host_line")` at D11's moments,
  and shown after its banner when ready, or replaced by the fixed line at its deadline (the late answer dropped). A
  key that no longer matches is cancelled. `clear()` adds `"host_line"`. A cap refusal shows the fixed line and takes
  the existing pause path.
  Verify: the debate-host scenarios "A Standard debate's lines", "A late bridge", "A bridge made for something else",
  "No host" and "The ledger".
- [x] 6.5 Storms (D2): a host line cut by Extend, Skip and `clear()` during its write and during a parked chat
  response.
  Verify: the D2 checks pass.

## 7. The verdict (design D12–D16, D25)

- [x] 7.1 `seed/pricing.json` and `pricing.config.ts` gain `timeoutsMs.verdict` 30,000 and
  `timeoutsMs.decision.rubric` 10,000. A rubric 429 is retried once after 1 s inside the deadline.
  Verify: the provider-gateway scenarios "A rubric 429" and "Seed check".
- [x] 7.2 `ai/agent/rubric.py`:
  - the state per D12 (`quoted_sides` as an ordered list, missed turns, moderator notes apart);
  - the 24,000-token budget with its cut order;
  - one score question per side per criterion, generic by position;
  - bars = unit × 10;
  - the winner by mean and margin.
  Verify:
  - the debate-verdict scenarios "The default rubric", "An unknown criterion" and "A near tie";
  - the worst-case size test;
  - "A swapped order is a different request" (the store keys differ).
- [x] 7.3 The prose (`ai/naive/verdict.py`, prompt `verdict-1`):
  - V8's instruction, the S6 sentence, the single-quotes line, one example output, the subject mapping, the result,
    and the language last line;
  - `runtime.llm.calls.verdict`, `timeoutsMs.verdict`;
  - validation, local repair, one retry.
  Verify: request-shape and validation tests with canned JSON, and the scenarios "You decide" and "Too many points".
- [x] 7.4 The failure table (D13): prose only, scores under Arbiter, scores under You decide, both, and a cap refusal,
  each with its note.
  Verify: one test per row, including "Scores fail under Arbiter".
- [x] 7.5 The agent host's `assess`: the Jev scores then the prose told the result. `deliver` applies a pick.
  Verify: a test of a whole `agent` Arbiter verdict from fixture answers and canned prose.
- [x] 7.6 `naive`'s single-call verdict (D15): its schema, its validation (every criterion for both sides in 0–10),
  its stronger case used as written, and panel names mapped to IDs.
  Verify: the scenario "The yardstick's verdict", and a panel test.
- [x] 7.7 When the work runs (D14):
  - `actor.background("verdict")` from the last closing's `turn.end` unless Extend is set, stored with the transcript
    fingerprint;
  - Extend and Skip discard it;
  - End with verdict takes it out before `clear(keep_current=True)` and reuses a match;
  - End without verdict cancels it.
  Verify: the scenario "End right after the last closing" (one `rubric` and one `verdict` request), and discard
  tests.
- [x] 7.8 The non-blocking pick: `debate.pick` records `ModeState.picked` and returns. Delivery runs as an actor job
  when the work finishes, at once if it's done, or by starting the work if there is none.
  Verify: the scenario "A click before the work is done", with the HTTP route answering 202 before the parked rubric
  is released, and Pause handled meanwhile.
- [x] 7.9 The resume rule: a debate in the verdict phase with no verdict runs the work again on `debate.resume`, on
  the cap-resume path, and on the actor's first command after a load.
  Verify: the scenario "The cap-refusal hang is gone", end to end on the fake with a cap set and raised.
- [x] 7.10 `scripted`: `assess` / `deliver` wrap `make_verdict` and its simulated call (none for a pick). The mock's
  verdict charge moves to category `chat`, purpose `verdict`.
  Verify: the debate-verdict scenario "Same cost category in both clients", and the demo-data scenario "Mock verdict".
- [x] 7.11 `EndDebate.tsx`'s estimate from `PRICING` and `status.pricing.period` (D16): Jev's ≈ 6,000 tokens plus the
  prose's ≈ 6,000 in and 300 out, the peak multiplier on the DeepSeek part only.
  Verify: the scenario "Peak prices the prose higher", as a frontend unit test.
- [x] 7.12 Storms (D2): the assess work cut by Extend, Skip and End without verdict during a parked rubric call; End
  with verdict during the current argument's `turn.end` write; a resume during the re-run's first write.
  Verify: the D2 checks pass.

## 8. M10's carry-overs, offline (design D17–D20)

- [x] 8.1 The `who_next` set: 40 group items from the frozen group transcripts, cut at character lines that ask
  nobody directly, built by the existing who-speaks builder with `last_spoke=False`, labelled blind under
  `evals/reviews/m10-labels.md`'s rule, with M9's hash split (≥ 20 test).
  Verify: `corpus-check`, `overlap`, and a deterministic-builder test.
- [x] 8.2 The decisions suite scores `who_scene` and `who_next` v3 with the same G11 policies, plus a "fresh cuts"
  file whose items are all test.
  Verify: a test on fixture answers that the floor is chosen on the 100 existing items only, and the fresh cuts are
  scored once.
- [x] 8.3 The `judge_starts_new` validation set: 30 real items (M10's free-run lines, including its 7 steered lines,
  labelled blind) and 30 planted. Plus a free-run report that judges and prints every steered line, against M10's 0
  of 7.
  Verify: the evaluation-harness scenario "Steered lines are listed", on fixture answers.
- [x] 8.4 The recap check gives `judge_summary_unsupported` v2 the premise.
  Verify: the scenario "A detail from the premise", with the M10 recap item `recap-sunnyhollow-010`.
- [x] 8.5 The watch-faces comparison: the emotion policy scores `emotion_line` under both rules (merge, no merge)
  over the same floor grid. The growth file `emotion_watch_2.jsonl` is built in phase 10, from the free runs.
  Verify: the scenario "Both policies reported", on fixture answers.

## 9. The debate evaluation, offline (design D21, D22)

- [x] 9.1 `horizon eval debate-history`:
  - scripts in `evals/debates/scripts/` (13: D21's mix, both worlds, 12 motions plus the panel's, casts chosen so a
    side's members differ in field);
  - generation through the live runtime under `naive` with the store;
  - output `evals/debates/<id>.json`;
  - refused without `--force`.
  Verify: the scenario "Refused regeneration", and a test-mode run of one script on the fake.
- [x] 9.2 `horizon eval debate-plant`: D21's alternating weak side, the rewrite prompt, and the output
  `evals/debates/planted/<id>.json`.
  Verify: the scenario "Which side is weak", on a fixture history with canned rewrites.
- [x] 9.3 The member slice builder (`evals/datasets/debate_member/`):
  - natural slots from the histories (2–3 eligible), cut with the live state builder;
  - written variants;
  - the `single` flag, the fixed-order answer and the language split;
  - M9's hash split with M10's prefix search, ≥ 30 test;
  - the label rule written first in `evals/reviews/m11-labels.md`.
  Verify: `corpus-check`, `overlap`, and a builder test on fixture histories.
- [x] 9.4 The member policy (`evals/who_policies.py`): accuracy in the set, the single-answer lift over fixed order
  with the exact McNemar test, the random-pick baseline, and the floor chosen on dev.
  Verify: the scenario "A pass needs both measures", on fixture answers.
- [x] 9.5 The debate emotion slice builder (D29.1): 30 rebuttal or closing lines for `emotion_line` and 10 openings,
  from the histories, as `evals/datasets/emotion/emotion_debate.jsonl`, with its own split.
  Verify: the evaluation-harness scenario "The slice is scored alone", on fixture answers.
- [x] 9.6 The debate-quality judge sets: 30 real + 30 planted each for `judge_keeps_side` and `judge_engages`, with
  B4 validation through the existing judge-validation path. A run over histories and free runs reports both columns.
  Verify: the scenario "An unvalidated judge doesn't count".
- [x] 9.7 `horizon eval debate`:
  - items from the histories and plants, balanced and planted, each also swapped;
  - the split by debate (4 dev / 8 test);
  - margin tuning on dev per D21's rule;
  - the test measures, flips and too-close changes reported apart;
  - the prose and host checks printing every item.
  Verify: the scenarios "Swap flips are counted apart from ties", "The margin is tuned on dev only" and "Every item
  is printed", on fixture answers.
- [x] 9.8 `latency --part debate`: D9's `S + L` for 30 states from the member slice's dev items, the 10 bridges and 5
  verdicts timed from `turn.end`, spells apart, the 90 s watchdog. Bridges and verdicts are saved to the store after
  timing.
  Verify: the scenarios "A slow API is kept" and "Bridges are kept", on the fake with parked answers.
- [x] 9.9 `freerun --mode debate`: the two D22 runs and their report (member sources, host on time, pauses, verdict,
  debate-quality rates).
  Verify: the scenario "A member choice report", on the fake.
- [x] 9.10 `smoke`: one Quick 2 v 2 `agent` debate with Auto host and Arbiter, one debate-plan timing request and one
  rubric request, from fixture answers. Synthetic canned `host` and `verdict` responses (W14) stand until 10.x
  records real ones.
  Verify: the scenario "Smoke in CI" (`HORIZON_TEST=1 … smoke`, no socket).

## 10. The paid runs (design D23; each asked for with its estimate, off-peak, through the store)

- [x] 10.1 `debate-history` (13 debates, ≈ $0.10). Read and review every history, then commit them (`.keep` on the
  run folder).
  Verify: 13 files in `evals/debates/`, the review recorded in `evals/reviews/m11-histories.md`.
- [x] 10.2 `debate-plant` (≈ $0.03). Review and commit.
  Verify: 12 planted files; each rewritten argument read; the review recorded.
- [x] 10.3 Build the member slice, the debate emotion slice and the debate-quality real items from the committed
  histories. Do the delegated B2 review (D29.2) as a recorded pass in `evals/reviews/m11-review.md`.
  Verify: `corpus-check`, `overlap`, and the builders' tests pass on the real files.
- [x] 10.4 Judge validations: `judge_keeps_side`, `judge_engages`, `judge_starts_new` and
  `judge_summary_unsupported` v2 (≈ $0.015).
  Verify: each clears B4's bar, recorded in m11.md. A failing judge is reported to the user as a choice.
- [x] 10.5 `decisions --set debate_member` (≈ $0.010), then write `floor.member` into the three entries (version 2,
  `bank-lock`, seed rebuilt).
  Verify: m11.md has the dev grid, the test result, the paired test and the baseline.
- [x] 10.6 `decisions --set emotion` for the debate slice (≈ $0.002), then write the debate faces' floors.
  Verify: m11.md has the slice's report.
- [x] 10.7 `latency --part debate` (≈ $0.015). Apply D9's rule and D29.3 if more than 10 % miss: set the
  `debate_plan` deadline from the measured p90 in `seed/pricing.json` and the mock, and record the NFR-02 exception.
  Record the canned `host` and `verdict` responses for the fake (W14).
  Verify: m11.md has `S`, `L`, the miss rate, the bridges on time and the verdict waits; `smoke` uses the recorded
  responses.
- [x] 10.8 `debate` suite (≈ $0.025): margin tuned on dev, the test measures, the prose and host checks read in full.
  Write `verdict.margin` if it moved.
  Verify: m11.md has every measure, and each failure read.
- [x] 10.9 Debate-quality over the 13 histories (≈ $0.012).
  Verify: m11.md has the `naive` column.
- [x] 10.10 Free runs from the smoke allowance (≈ $0.05): 2 `agent` debates and 3 `agent` watch runs of 30 turns.
  Verify: m11.md has the debate report (with the `agent` debate-quality column) and the steer report against M10's 0
  of 7. The steer rule (D18) goes to the user if fewer than half the steered lines start something new.
- [x] 10.11 The carry-over re-tests (≈ $0.011):
  - cut 40 fresh `who_scene` items and 40 watch emotion growth items from the 10.10 watch runs, labelled blind before
    any v3 answer is seen;
  - run `who_scene` (140) and `who_next` (40);
  - run the watch emotion growth;
  - re-score the 10 recaps.
  Write the floors found.
  Verify: m11.md has each result against its bar. D20's watch-faces comparison goes to the user as a choice, and is
  applied as chosen.
- [x] 10.12 Spend against D23: every run's per-item results under `docs/ai/checks/m11/`, checked line by line against
  `data/evals/spend.jsonl`.
  Verify: m11.md's spend table matches the log.

## 11. Docs (design D28)

- [ ] 11.1 Amend everything doc 08 §6 lists:
  - doc 01: A7, A14, §6, §8, §9;
  - doc 02: B2, B4, B5, B7, B8, §8;
  - doc 03: C1 and §7;
  - doc 04: P5 and §7;
  - doc 05: X9 and §7;
  - doc 06: §7;
  - doc 07: §7, and the cost pointers in docs 05–07.
  Then add doc 08's built notes per V, doc 07 G3's steer note, and doc 13's W12 and W6 rows.
  Verify: the docs link check reports 0 broken links in `docs/ai`.
- [ ] 11.2 Finish `docs/ai/checks/m11.md`: step 0, every run, "What M11 found" and "What M12 inherits".
  Verify: every number in it traces to a run folder or a committed file.

## 12. The final gates

- [ ] 12.1 Run every gate:
  - the backend `pytest` in the gate worktree, `ruff`, `mypy`;
  - the frontend `lint`, `typecheck`, `npm test`, `test:http`;
  - `seed:check`, `fixtures:check`, `export-schema:check`;
  - `HORIZON_TEST=1 … smoke`;
  - `npm run e2e`;
  - `openspec validate debate --strict`.
  Verify: all green, recorded in m11.md's final gates table.
- [ ] 12.2 Tell the user M11 is ready to archive and squash into dev. Push nothing unless asked.
  Verify: the user's answer is recorded.

# Proposal: debate (M11)

## Why

A debate is the most structured mode, and today nothing in it reads what was said. Doc 08 found five faults:
- a side whose members are all asleep turns the debate one-sided without telling anyone;
- the `naive` prompt tells teammates they are opponents;
- nothing keeps the sides from drifting into agreement;
- the host never mentions an argument, and the verdict is random in every profile, including the ones that pay for
  real arguments;
- "You decide" builds the verdict only after the click, so a real verdict would stall the reveal.

Doc 13 W4 makes M11 the change that fixes them, under five headings:
- **the debate plan:** Jev picks which member of a side speaks;
- **the asleep-side pause;**
- **host lines** written by DeepSeek;
- **the rubric verdict:** Jev scores, code decides, DeepSeek writes the prose;
- **M10's carry-overs**, which the user chose to fix here: who-speaks without `last_spoke`, the steer's wording, the
  recap judge's premise, and the watch-faces choice.

**Why now:** M10 built every pattern the debate plan needs:
- a plan whose deadline counts from `turn.end` and replaces the turn gap (the follow plan);
- a plan stored with an input fingerprint (the watch plan-ahead);
- the cancel-storm helper.

M12–M14 then add their questions (gates, input safety) to the debate plan built here.

**It lands as one change.** The debate work shares one runtime seam: the phase machine's slots. The plan fills them,
V5 pauses on them, the host bridges them and the verdict reads them. Split, it would be built twice.

The M10 carry-overs are small and mostly independent. One of them is on the debate plan's own path: the plan state
without `last_spoke` that `who_scene` needs is the same builder switch the member question uses (design D6). They come
last among the offline phases, so they can't block the debate work.

## What Changes

**Phase 0: the base (design D2)**
- M10's gates are confirmed on c8cdb54. M11 then adds offline storm tests for each new cancel path:
  - a stored debate plan;
  - a host line requested ahead;
  - the verdict's assess work;
  - End's keep-current;
  - the Extend and Skip discards;
  - the resume in the verdict phase.

**The debate's slots and the asleep side (doc 08 V1, V3, V5; design D3, D4)**
- **Every profile:** a phase becomes an ordered list of side slots (two-sided) or panel slots, filled when each
  slot comes up.
- **Who fills a slot:** without a planner, the next eligible member in today's fixed order. So `scripted` and `naive`
  speak exactly as today while everyone is awake.
- **A side with nobody awake pauses the debate:**
  - every asleep member gets a note with Top up;
  - a system note says which side is asleep;
  - `session.paused` has reason `user`, and the slot is kept;
  - the rule is in the shared runtime **and the mock's debate engine**, with a parity test.
- **Missed turns** (asleep, or the debate ended early) are computed from the log and given to the verdict.

**The debate plan (V2, V3; W5 row 11; design D5–D9)**
- **New purpose:** `debate_plan`.
- **When it runs:** at each `turn.end`, for the next rebuttal, closing or panel slot that has two or more eligible
  members.
- **What it asks, in one request:**
  - which member speaks: one of three new member questions (rebuttal, closing, panel), with no `none`, at
    `floor.member`;
  - each candidate's emotion, on `emotion_line`.
- **The deadline:**
  - the member is fixed by `turn.end` + 500 ms (`timeoutsMs.decision.debate_plan`), which replaces the turn gap;
  - the faces are used if they land before the turn starts;
  - late, unsure or failed means the next member in fixed order.
- **Stored with M10's fingerprint,** using V2's seq rule (banners, round notes and host lines don't count). A plan for
  the next phase's first slot carries its (phase, iteration) target. Extend, Skip and `clear()` drop it.
- **Faces in debate come from the plan** under `agent`, which ends M9 D34's held face:
  - rebuttals and closings use `emotion_line` (E1 gives watch and debate the same question);
  - openings use a new `emotion_debate_opening`, planned at Start for the first opening and at prefetch start for the
    others;
  - Ask answers use `emotion_reply`.
- **Reactions** are unchanged: M9 already gives each debate listener a side label.

**The debate prompt (V4; design D10)**
- The `agent` compiler already has V4's session block and reply rules (M8). M11 adds **V4's per-phase cue**:
  - the teammate sentence;
  - the moderator sentence after an Interject;
  - the extended-round line.
  They go into the TS twin with shared fixtures, and "View as prompt" gets one fixed note.
- **The label:** debate requests become `agent-7` (`agent-8` with the mood line on). The cached prefix stays
  byte-identical.
- **Bug fix:** `naive` names teammates as teammates.

**The host (V6; design D11)**
- `DebateHost.narration` becomes async.
- `naive` and `agent` share a DeepSeek host. It writes:
  - the welcome;
  - the round bridges;
  - the Extend and Skip lines;
  - the verdict lead-in.
- Each line is requested ahead, keyed by (phase, iteration), and shown whole. It waits at most until Start + 3 s, or
  1.5 s after its banner; otherwise today's fixed sentence shows.
- A host line is told the motion's language explicitly (M10's recap finding).
- `scripted` keeps its fixed lines.

**The verdict (V7–V9, V12; design D12–D16)**
- **`agent` scores with Jev:** `rubric`, one score question per side per criterion, from 4 new criterion entries plus
  a generic one. Levels 2–4 are written here.
  - The state is two side blocks **in a list**, so a side-order swap changes the request and isn't served from the
    store (M9 D38's trap).
  - It has a 24,000-token budget, a cut order and a worst-case test.
- **Code decides the winner:** bars = unit × 10, and `verdict.margin` 0.5 decides between a winner and "too close".
- **DeepSeek writes the prose** as JSON, told the result. It is validated, retried once, and falls back by V8's
  failure table.
- **The work starts at the last closing's `turn.end`,** also for You decide, and is stored with a transcript
  fingerprint:
  - End reuses matching work instead of paying twice;
  - Extend and Skip discard it.
- **`debate.pick` no longer waits for the verdict:** it records the side, and the verdict is delivered when the work
  finishes.
- **Today's cap-refusal hang is fixed:** resuming in the verdict phase with no verdict runs the work again.
- **`naive`'s single-call verdict:** one DeepSeek JSON call writes the scores, the winner and the prose (the M15
  baseline).
- **`scripted`** keeps the mock's random verdict. The mock's verdict charge moves from category `decision` to `chat`,
  to match the backend (a parity bug found here).
- **"Go to verdict now (≈ $x)"** becomes an estimate from the shared price table and the current price period (design
  D16 explains why it isn't per profile).

**M10's carry-overs (the maintainer's choices of 2026-10-13; design D17–D20)**
- **`who_scene` v3 and `who_next` v3 without `last_spoke`:** the guard still reads it in code. Both are measured
  again:
  - `who_scene` on 40 fresh held-out cuts;
  - `who_next` on a new 40-item group set.
- **The steer reworded** so it brings something new instead of closing the scene. It is measured with a validated
  "does this line start something new?" judge on 3 fresh watch free runs, against M10's 0 of 7.
- **The recap judge** (`judge_summary_unsupported` v2) gets the premise. Its validation runs again, then the 10 stored
  recaps are re-scored.
- **The watch faces:** a 40-item growth of the watch emotion slice, with both neutral + none policies scored, and
  then **a choice for the user**.

**Evaluation (V11; W6's M11 row; doc 08 §5; design D21–D23)**
- **No frozen debate transcripts exist** (`evals/transcripts/` holds 1:1 and group only). So `horizon eval
  debate-history` generates them once with `naive`:
  - the 12 two-sided suite debates;
  - one panel.
  `debate-plant` writes the weak-side rewrites. Both are reviewed and committed.
- **The member slice:** 90 items (≥ 45 with a single acceptable member, English 80). The targets are ≥ 80 % inside
  the set, and ≥ 15 points above fixed order on the single-answer items (exact paired test).
- **The debate-quality judge** ("keeps its side", "engages") is validated 30 real + 30 planted each. It runs on the
  `naive` histories now and on the `agent` free runs; the formal targets stay with M15's conversations.
- **The `debate` suite, `agent` part:**
  - 12 debates, balanced and planted, split 4 dev / 8 test;
  - the margin is tuned on dev;
  - targets: the strong side wins ≥ 7 of 8, Rebuttal is higher on ≥ 7 of 8, and the side swap flips at most 1 of 16;
  - prose and host checks;
  - the `naive` arm waits for M15.
- **Timing:**
  - 30 debate-plan requests (≤ 10 % miss the 500 ms deadline, state assembly included; otherwise V2's rule applies);
  - 10 host bridges and 5 verdicts, timed and kept as suite items.
- **2 `agent` free runs:** a Standard 2 v 2 and a panel of 4.
- **Offline:** everything runs in `smoke`, CI and tests.

## Capabilities

### New Capabilities
- `debate-plan`: who fills a rebuttal, closing or panel slot. Covers when the plan starts, its deadline from
  `turn.end`, its questions and state, the fallbacks, the stored plan with its fingerprint and phase target, the trace
  rows, what cancels it, and its timing check.
- `debate-host`: the Auto host's lines. Covers which lines, when each is requested and shown, the call's settings and
  purpose, the fallbacks, and the profiles.
- `debate-verdict`: the verdict. Covers the Jev rubric and the code winner, the side blocks and size budget, the prose
  and its failure table, the early start and reuse, the non-blocking pick, the resume rule, `naive`'s single-call
  verdict, `scripted`'s, and the early-end estimate.

### Modified Capabilities
- `session-modes`: debate phases become slots filled when they come up; a side with nobody awake pauses; Ask and
  Interject feed the plan and the cue; the verdict phase follows `debate-verdict`.
- `turn-plan`: the planner plans debate slots, openings and Ask answers; `naive` and `scripted` keep fixed order.
- `ai-ports`: `DebateHost` becomes async with `assess` / `deliver`; `host` gets `naive` and `agent` implementations;
  the agent reply engine's debate cue; `naive`'s teammates.
- `persona-prompt`: the debate cue and its sentences, the reworded steer sentence, and the prompt labels.
- `speaker-emotion`: faces in debate come from the plan.
- `system1-trace`: member rows, late answers, and which trace a debate plan writes to.
- `question-bank`: the member, opening-emotion, rubric and judge entries, the `{side}` placeholder, the shared
  `floor.member` and `margin`, and the who-speaks v3 entries.
- `watch-direction`: the scene question no longer shows `last_spoke`.
- `provider-gateway`: `debate_plan`, the `rubric` deadline and retry, `timeoutsMs.verdict`, and the host and verdict
  calls labelled at the source.
- `evaluation-harness`: debate histories and plants, the member slice, the `debate` suite, the debate-quality and
  steer judges, the debate timing and free runs, the who-speaks re-test, and the recap re-score.
- `demo-data`: the mock's debate engine follows the slot and asleep-side rules, and its verdict charge category.

No `client-contract` or `http-api` delta (design D24):
- `debate.pick` already answers 202 with an empty body, and the verdict arrives on the existing `session.state`;
- `routing.skipped` with reason `exhausted`, `forcedBy: "round_order"`, pause reason `user`, `energy_exhausted`,
  host `narration` notes and `Verdict.decidedBy: "none"` all exist.

If implementation finds a contract need, it stops and asks.

## Impact

- **Backend:**
  - new:
    - `ai/agent/{debate_plan,rubric}.py`;
    - `ai/naive/{host,verdict}.py`;
    - `ai/questions/{member_rebuttal,member_closing,member_panel,emotion_debate_opening,rubric_*,judge_keeps_side,
      judge_engages,judge_starts_new}.json`;
    - `sessions/{debate_slots,debate_plan,debate_verdict}.py`;
  - changed:
    - `ai/{ports,contexts,profile}.py`;
    - `ai/agent/{planner,plan_state,persona,turn}.py`;
    - `ai/naive/prompt.py`, `ai/scripted/ports.py`;
    - `sessions/modes/debate.py`, `sessions/actor.py`;
    - `gateway/context.py`, `domain/runtime_config.py`;
    - `evals/*`.
- **Frontend:**
  - `mock/engines/debate.ts`;
  - `domain/personaPrompt.ts` (the debate cue twin);
  - `features/ensemble/EndDebate.tsx`, `features/wizard/steps/PromptPreview.tsx`;
  - `runtime.config.ts`, `pricing.config.ts`.
- **Data:**
  - `seed/{pricing,runtime,system1.fixture}.json`;
  - `evals/debates/` (histories, plants, scripts);
  - `evals/datasets/{debate_member,judges}/`;
  - `evals/reviews/m11-*`.
- **No contract change, no new UI entry point, no migration.**
- **Docs:**
  - everything doc 08 §6 lists;
  - doc 07 G3's steer and the M10 carry-overs' built notes;
  - the new `docs/ai/checks/m11.md`.
- **Spend:** about **$0.24** of paid runs, plus about $0.05 of free runs from the smoke allowance (design D23). W6
  said $0.14. The difference, all named in D23:
  - generating 13 debates instead of 8 (no frozen debate transcripts exist);
  - the measured DeepSeek cache share (M10: estimates about 2× low);
  - three judge validations W6 didn't price;
  - the M10 carry-overs (≈ $0.04).
  Each run is asked for when it comes, with its estimate. All of them run off-peak and through the store, except the
  timing runs, and every output is saved.
- **Your time:**
  - review the new bank entries' wording: 3 member questions, 1 opening emotion, 5 rubric entries with their levels,
    3 judges, the reworded steer, and `who_scene` / `who_next` v3;
  - four choices, all made at the proposal (design D29):
    - the 40-item debate emotion slice;
    - the B2 label review delegated;
    - merging with the debate plan's measured deadline if it must change;
    - the carry-overs inside M11;
  - one later choice, D20's watch-faces rule, which comes with its measurement.

# Proposal: group-watch (M10)

## Why

After M9, `agent` plans only 1:1 turns. In group and watch it still runs `naive`'s routing: an up-front pick of two
speakers, random Next speaker and Step in, round-robin watch. Its faces there are M8's held face (M9 D34), and Summarise
returns a canned sentence. Doc 07 found five faults in that behaviour:
- Auto can answer a user's message with silence (Jev picks `none`);
- the second replier is chosen blind, before the first reply exists;
- a message sent between two replies is answered late by a reply to the older message;
- "is the talk finished?" has no outcome;
- energy sat in Jev's state, mixing a budget into a story decision.

Doc 13 W4 makes M10 the change that moves group and watch onto the planner: the follow plan, Next speaker and Step in,
the watch guard, steer and plan-ahead, and the episode recap.

**Why now:** M11 (debate) reuses this change's cast plan, its deadline-from-`turn.end` pattern and its cancel rules.
M12–M14 then add their questions to every plan built here. The Stop fix (3488b14) is on dev, so the new cancel paths
build on a writer that survives any number of cancels.

**It lands as one change.** It is larger than M9 in runtime work and smaller in evaluation. Three shared seams would be
built twice if it were split:
- **the cast plan:** one Jev call 1 for group first slots, Everyone, Next speaker, Step in and every watch turn;
- **the follow plan's handle:** it starts at the stream's end and its deadline counts from `turn.end`. Group Auto and
  Step in share it, and M11's debate plan reuses the pattern;
- **the reply epoch:** G5's cancel, which group sends, Step in, Everyone runs and prefetches all obey.

Each phase ends green, so it can be committed alone. **Phase 0 comes first:** it confirms the Stop fix and adds the
shared cancel-storm test helper. Every later phase adds its own cancel-in-a-write and cancel-in-a-plan tests to it.

## What Changes

**Phase 0: the base (design D2)**
- **The Stop fix is on dev and on this branch** (3488b14, checked: both contain it).
- **The shared storm helper:** `test_cancel_writes.py`'s storm moves into a shared test helper. Each new cancel path
  (G5's cut, the plan-ahead, Step in, a follow plan cut by a new message) gets an offline test that storms it during
  a write and during a plan, then shows the writer is free.

**The cast plan and group Auto (doc 07 G1, G3, G9; doc 01 A3, A4; design D3–D7, D16)**
- **The port:** the `TurnPlanner` port gains `plan_cast` (who speaks, and every candidate's emotion, in one
  `turn_plan` request) and `start_follow` (the follow plan's handle). Each returns `None` when the profile has no
  planner, and the mode then keeps its own pick, so `scripted` and `naive` keep their routing (G13).
- **Group Auto under `agent`:**
  - with no mention, the first slot has no `none`. One eligible character answers with no who-speaks question, but its
    emotion is still asked;
  - mentions answer first;
  - when every mentioned character is asleep, nobody else answers. This lives in the shared runtime, so it applies to
    every profile, with a mock parity fixture.
- **`naive` gets G1's fix:** no `none` when nobody is mentioned, and a single eligible character answers. This also
  closes a bug the fix would expose: with `none` gone, today's "one option or fewer" check would answer with nobody
  (D6). The `route` entry moves to v3, with an additive `none` switch in the bank loader.
- **Energy stays out of Jev's state** (G9). It was already removed by M8's state builder; a test pins it.
- **Faces in group come from Jev** (E1): `emotion_reply` v2 at floor 0.2 per candidate. This ends M9 D34's held face
  for group and watch.
- **The turn cue's one sentence** (G3) goes into the `agent` compiler, driven by fields in the frozen plan, with a TS
  twin table and shared fixtures. "View as prompt" gets one fixed note. The cached prefix stays byte-identical. The
  prompt label follows the bytes: `agent-3` when a sentence is sent (`agent-4` with the mood line on).

**The follow plan (doc 07 G2; doc 11 S5; W1; W5 row 10; design D8, D9)**
- **When:** it starts at the first reply's stream end. Its deadline is `turn.end` + 400 ms
  (`timeoutsMs.decision.follow_plan`), and it replaces the turn gap for that step.
- **What it asks:** "who speaks up now?" (a choice with `none`) and `emotion_reply` per candidate.
- **The outcome:** a pick at or above `floor.second` gives a second reply, with G3's sentence. `none`, unsure, late or
  failed means no second reply. It replaces doc 01 A4's re-plan, and MULTI-03's cap of 2 stays.
- **New purpose:** `follow_plan` in `PURPOSE_CATEGORY`.
- **System 1 rows follow W1:** a follow plan that picked nobody writes to the first reply's trace through
  `append_system1`.
- **A finding that decides the deadline (D9):** group A's "about 800 ms" budget assumed M14's output check runs between
  the stream's end and `turn.end`. Until M14 there is nothing there, so the follow plan gets about 400 ms against Jev's
  measured 420–530 ms p50. Most follow plans will likely be late, so there would be no second reply. The paid timing
  check measures this, and G2's rule (keep Jev, deadline from the measured p90, record an NFR-02 exception) applies.
  Whether M10 merges with that exception is the user's choice.

**Next speaker, Everyone and Step in (G4), and the cancel rule (G5) (design D11, D12)**
- **Next speaker** asks "who speaks next?" with no `none` and without the last speaker. Its cue gets G3's "Nobody asked
  you directly" sentence.
- **Everyone** gets its speaking order and every speaker's emotion from one call 1. Prefetch is unchanged, and the
  asleep notes stay.
- **Step in** follows group Auto: the first slot with no `none`, then an optional follow plan.
- **A user message cancels the previous message's replies that have no `turn.next` yet.** That covers a follow plan in
  flight, the rest of an Everyone run, unreleased prefetches and Step in's second reply.
  - It is built as a reply epoch, checked under the writer lock when `turn.next` is appended. Jobs end cooperatively at
    their boundaries; the worker is never killed, so the watch turn count can't be lost.
  - It applies to every profile, and to the mock's group engine, with a parity fixture.

**Watch (G6, G7, G8; design D13–D15)**
- **Who speaks next, in this order:**
  1. a Speak next nudge;
  2. the nobody-left-out guard: anyone silent for 2 full rounds, counted from the message log since the premise
     (`forcedBy: "round_order"`, the reason "{name} hadn't spoken for {n} turns.");
  3. otherwise Jev's "who speaks next?" without the last speaker.
  The "Auto" opening goes through the planner. All of this is `agent` only.
- **Faces:** two new emotion entries with E1's wording, `emotion_scene` and `emotion_opening`.
- **Steer:** the "is the talk finished?" noul (`t_end`, starting at 0.8) adds G7's cue sentence, at most once every 3
  turns, counted from the stored traces, and never while a director's note is active.
- **Plan-ahead:** at each `turn.end` the next plan starts during the turn gap and the pace. It is stored with its input
  fingerprint and redone when the fingerprint changes. `clear()` cancels it, and none starts at the turn limit or while
  paused. Its deadline is the moment the next turn is due, so a slow Jev is hidden by the pace.

**The episode recap (G10; doc 05 X3; design D19)**
- **The call:** `Summariser.episode` becomes one DeepSeek call for `naive` and `agent` (the `episode` settings row
  already exists).
- **New config:** `timeoutsMs.episode` = 30 s, and the purpose `episode_summary` (category `summary`).
- **On failure:** a plain system note, never a fake recap.
- **`scripted`** keeps its canned text, and its simulated call now uses the purpose `episode_summary`, as does the
  mock's.
- **This closes M9 D5's open trap:** under `naive` with a key, the canned recap billed a simulated row to the real
  ledger.

**Smaller findings, each decided in design.md**
- **Doc 07 G1's option text breaks doc 11 S6:** it puts `about`, which the user writes, into an option. It stays in
  `quoted_cast` instead (D7).
- **G1's "no Jev call" vs E1:** a single eligible speaker still needs its emotion asked (D5).
- **M9 D9's "no query embedding at send" was never built:** `agent` 1:1 still pays for an embedding it never uses. It
  is gated by a planner capability flag for 1:1, group and watch (D18).
- **No frozen watch transcripts exist** for G11's "8 recaps from the frozen watch transcripts". So two watch histories
  are generated once by `naive` (D23).
- **G6's guard and G7's steer cap** would reset on an idle release if they were kept in memory. Both are counted from
  stored messages and traces (D13, D14).

**Evaluation (G11; W6's M10 row; doc 07 §5; design D23, D24)**
- **The who-speaks slice, about 210 items, English first:**
  - group first slot: 60 items;
  - group second slot: 90 items, about 65 % with `none` right, scored on balanced accuracy;
  - watch next speaker: 60 items, each with at least 3 awake characters.
  Each part must beat its baseline by ≥ 15 points on an exact paired test: least recently spoken, or round-robin for
  watch. Floors are chosen on dev, over a grid that includes 0.2–0.4.
- **"Is the talk finished?":** about 120 nouls (at least 60 "yes"), including goodbye loops and polite-agreement loops.
  `t_end` is the lowest threshold with precision ≥ 90 %.
- **A 40-item watch slice for the two new emotion entries** (the user's choice, D27).
- **The episode recaps:** 10 in the `summary` suite, from two watch histories generated once. One of them has about
  100 turns.
- **The timing checks:**
  - 50 follow-plan requests from hand-built states, with state assembly and the measured `finish` time counted;
  - watch at Fast pace with the plan-ahead, against NFR-02's 3 s p50;
  - Jev's slow spells reported apart from our own latency.
- **Free runs:** 3 watch runs of 30 turns and 3 group runs of 12 messages, `agent` only, from the smoke allowance
  (≈ $0.06).
- **Offline:** everything runs in `smoke`, CI and tests.

## Capabilities

### New Capabilities
- `follow-plan`: the second-slot decision in group Auto and Step in: when it starts, its deadline from `turn.end`, its
  question and state, its outcomes and trace rows, what cancels it, and its timing check.
- `watch-direction`: who speaks next in a watch (nudge, the nobody-left-out guard, Jev's pick), the steer, and the
  plan-ahead with its fingerprint.
- `episode-recap`: watch's Summarise as a real recap: the call, its settings and purpose, the failure note, and the
  scripted twin.

### Modified Capabilities
- `turn-plan`: the planner also plans group and watch turns (`plan_cast`), and the follow plan's handle. Group stays
  unplanned under `naive` and `scripted`.
- `session-modes`:
  - group Auto's first slot, mentions and all-asleep mentions;
  - Next speaker, Everyone and Step in under `agent`;
  - watch speaker order;
  - G5's cancel;
  - no retrieval in `agent` group and watch.
- `session-runtime`: `turn.next` is announced under the reply epoch, and the follow plan replaces the turn gap. A plan
  can arrive in the `TurnSpec`.
- `ai-ports`:
  - the Jev router's G1 fix;
  - `Summariser.episode` becomes real in `naive` and `agent`;
  - the agent engine's cue sentence and its prompt labels.
- `speaker-emotion`: faces in group and watch come from the plan, through two new entries and per-candidate
  `not_used` rows.
- `system1-trace`: who-speaks, follow-plan, talk-finished and per-candidate rows, and where an Everyone or follow plan
  writes.
- `question-bank`: the `none` switch for dynamic choices, and the new entries.
- `persona-prompt`: the G3 sentence and its "View as prompt" note.
- `provider-gateway`: `follow_plan` and `episode_summary`, and `timeoutsMs.episode`.
- `evaluation-harness`:
  - the who-speaks and talk-finished policies;
  - the watch emotion slice;
  - recaps in `summary`;
  - free runs;
  - `latency`'s follow-plan and watch parts;
  - a wider `smoke`.
- `demo-data`: the mock's group engine follows G1's all-asleep rule and G5's cancel. Its recap call uses
  `episode_summary`.

No `client-contract` delta. `routing.question`, `routing.reason`, `forcedBy: "round_order"`, the `system1` rows and
`note` messages of kind `summary` and `system_note` already exist (design D26). If implementation finds a wire field,
skipped reason or UI entry point it needs, it stops and asks.

## Impact

- **Backend:**
  - new:
    - `ai/agent/{cast_plan,follow_plan,watch}.py`;
    - `ai/questions/{who_first,who_second,who_next,who_scene,talk_finished,emotion_scene,emotion_opening}.json`;
    - `sessions/epoch.py`;
  - changed:
    - `ai/{ports,contexts,profile}.py` and `ai/agent/{planner,plan_graph,turn}.py`;
    - `ai/naive/{router,summary,prompt}.py`, `ai/scripted/ports.py`, `ai/questions/{__init__,route}.json`;
    - `sessions/{turn,actor,retrieve}.py` and `sessions/modes/{group,watch,common}.py`;
    - `gateway/context.py`, `domain/runtime_config.py`, `evals/*`.
- **Frontend:**
  - `mock/engines/{group,watch,host}.ts` and `features/wizard/steps/PromptPreview.tsx`;
  - `domain/personaPrompt.ts` (the cue table twin);
  - seed-build: `pricing.config.ts` and `system1.ts`.
- **Data:**
  - `seed/{pricing.json,system1.fixture.json}`;
  - `backend/tests/fixtures/{turn_cue,group_parity,plan}/`;
  - `evals/datasets/{who_speaks,talk_finished,emotion}/`, `evals/watch/` (the two histories) and `evals/reviews/`.
- **No contract change, no new UI entry point, no migration.**
- **Docs:**
  - everything doc 07 §6 lists: doc 01 A3 rule 5, A4 and §8; doc 02 B2, B3, B5, B7 and B8; doc 03 C1; doc 04 §7;
    doc 05 X3 and X9; doc 06 E1;
  - the new `docs/ai/checks/m10.md`.
- **Spend:** about **$0.10** of paid runs plus the free runs from the smoke allowance (≈ $0.06, within its $0.10).
  W6 said $0.07. The difference is the second watch history, the 40-item watch emotion slice and the timed watch run
  (design D24). Each run is asked for when it comes, with its estimate. All of them run off-peak and through the
  store (except the timing runs, which W10 keeps out of it), and every output is saved.
- **Your time:**
  - review the 7 new bank entries' wording and the `route` v3 change;
  - the labels of the three who-speaks parts, the talk-finished set and the watch emotion slice: the B2 review is
    delegated to me (D27);
  - four choices, all made at the proposal (design D27): merge with the follow plan's measured deadline if it
    must change; the 40-item watch emotion slice; keep reactions; the label review delegated.

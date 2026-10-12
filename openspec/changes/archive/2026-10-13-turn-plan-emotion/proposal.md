# Proposal: turn-plan-emotion (M9)

## Why

After M8, `agent` has a real persona prompt but no System 1: its face is whatever it was before (design D4 of
`persona-context`), listeners react at random, and nobody checks that the face fits the words. M8 also measured why
the face has to come off the model: DeepSeek writes a valid emotion tag only 5–8 % of the time, and 33 % of
Meridian's `naive` replies open with the emotion as a word ("Sad — …").

Doc 13 W4 makes M9 the first change where Jev decides something inside a turn:
- doc 01's `TurnPlanner`, with Jev call 1 in 1:1;
- doc 06: the emotion, the mood line and listener reactions;
- W2's live face check.

**Why now:** every later change (M10 group, M11 debate, M12 documents, M13 memory, M14 safety) adds questions to this
planner. Its two offline checks, graph overhead and Stop during a plan, decide whether LangGraph stays. They must
come first, before anything is built on the graph.

**It lands as one change.** It is about M8's size, and its parts meet in two shared seams that would otherwise be
built twice:
- **the frozen plan in `TurnContext`:** the face, the mood line, the System 1 rows and replay;
- **the actor's named after-turn tasks:** reactions and the face check share the cancel rules in `clear()`.

The phases end green, so each can be committed alone. **Phase 1 is a gate:** if doc 01's check 1 or 2 fails, the
work stops and the user chooses a path (design D2) before phase 2 starts.

## What Changes

**First: doc 01's checks 1 and 2 ($0, design D1–D3)**
- **The dependency:** `langgraph` is added, pinned to a release the user approves before `uv add`. No LangChain model
  classes are used (A8), there is no checkpointer (A9), and LangSmith stays off (B11).
- **Check 1:** the graph's overhead is under 50 ms, and its runs settle on the virtual clock with every task visible to
  `rt.spawn`.
- **Check 2:** Stop or pause during a plan or a reply leaves nothing running except the allowed late Jev call, and
  lands within 500 ms.
- Results go in `docs/ai/checks/m9.md`.

**The turn planner (doc 01 A4, A5, A9, A11, A13; D-92; design D4–D9)**
- **The port:** a `TurnPlanner` port with a frozen `TurnPlan` type. `TurnContext.plan` holds the plan, so a turn can be
  replayed from JSON (W4's hand-off).
- **The graph:** the plan graph is LangGraph, with M12's quick/deep branch point already in place. In M9 it always
  takes the quick branch.
- **Where it runs:** in `agent` 1:1 only, on send, regenerate and a generated greeting. Jev call 1 asks only the
  emotion: no gates, no safety (W4's table).
- **Timing:**
  - the call starts before `turn.next`;
  - it has the 700 ms `turn_plan` deadline;
  - a late answer is billed and discarded (W11).
- **Agent 1:1 does no retrieval in M9,** and no query embedding at send (W4: "none in agent 1:1"; D-100).
- **Profiles:**
  - `naive` resolves to no planner;
  - `scripted` simulates the call (D-81) and shows the emotion row from the System 1 fixture;
  - the MockClient does the same.
- **The new purposes** `turn_plan` and `face_check` are added to `PURPOSE_CATEGORY`. Their deadlines already exist.

**Emotion (doc 06 E1–E3, E6; design D10–D15)**
- **The question:** one choice per candidate, with E1's options, `what` / `not_for` / examples, and `none`. It has:
  - the `neutral` + `none` merge;
  - per-question seeds derived from `system1.seed`;
  - the 0.6 floor (W12).
- **The bank:** two entries, `emotion_reply` (answering the user) and `emotion_greeting` (meeting the user again).
  Each names its candidate through a new, additive `{name}` placeholder.
- **The face reaches the screen:**
  - the `agent` engine yields the planned face on DeepSeek's first chunk;
  - the runtime appends `turn.start` and `emotion` in one write;
  - the source is `classifier`, or `default` when the face is kept or faded;
  - MANUAL still asks: the pick is recorded, never shown, and its base is the last AI-chosen face;
  - `TurnTrace.emotion` carries the top 3 candidates.
- **The fade:** short faces fade (`emotion.fade` in the runtime config).
- **Insight:** a "kept" chip replaces the band when the face shown is not Jev's top pick (display only).
- **The reducers:** both stop applying a reaction's face to the character who is streaming (E6). Shared fixtures,
  including `ses_seedDinner` seq 25.

**The mood line (doc 06 E4; design D16, D17)**
- **The line:** E4's line and phrase table. It is in the dynamic tail, never for neutral or MANUAL, and lives in
  `persona.py` and its TS twin with shared fixtures.
- **The version:** the prompt becomes **`agent-2`**. The cached prefix is byte-identical to `agent-1`'s, and so is the
  whole request on neutral and MANUAL turns. A fixture proves both.
- **"View as prompt":** one fixed line notes the mood line.

**Listener reactions (doc 06 E5; design D18–D22)**
- **The predictor:** `JevReactions` in `ai/agent/reactions.py`, with an async `ReactionPredictor.predict` called
  inside the reactions task:
  - listeners are read from the actor's state when the task runs;
  - at most 2 confident changes are kept, plus fades;
  - the timeout is 1.5 s.
- **Where it runs:** `agent` in group, debate and watch. Routing there stays `naive`'s.
- **Cancelling them:**
  - the actor's background tasks become cancellable by name;
  - `clear()` cancels reactions and the face check;
  - a new user message or MANUAL drops every pending reaction;
  - each append re-checks under the writer lock, so a reaction can't land on a speaker whose turn just started.
- **Spend:** scripted reactions become async and bill a simulated call, **only under the `scripted` profile** (design
  D21: `naive` also resolves to them, and must never record a fake charge). The MockClient charges the same and
  applies the same drops.

**The face check (W2; design D23–D25)**
- **The call:** one Jev call in a named task after `turn.end`, for AUTO replies whose face isn't neutral, with W2's
  skips.
- **The row:** "face and words agree?", with answer `yes`, `clash` or "no (words read: …)", written with
  `append_system1`.
- **Rules:**
  - it never changes the face;
  - a late or failed call adds nothing;
  - it never triggers the cap pause.
- **Profiles:** `scripted` and the MockClient write the fixture row with a simulated call; `naive` has no check.

**Evaluation (doc 06 E8; W6's M9 row; design D26–D32)**
- **The `decisions` slice:**
  - emotion: about 100 items, English-weighted (design D27);
  - reactions: 90 items;
  - each with E8's cap on "keep" or `none`, and the trivial baseline;
  - floors tuned on one seeded order, on dev.
- **Two new judges, validated (B4):**
  - "names the feeling?", with at most 1 false alarm on the clean real replies;
  - the pairwise "which reply is better?". E8's on/off rule needs it, and the bank so far allows only noul judges
    (design D29).
- **The mood line on vs off, once:**
  - up to 100 non-neutral turns of M8's frozen transcripts, each re-replied as a single call;
  - compared with a paired bootstrap over 10-turn blocks, because four transcripts are too few to resample whole
    conversations (design D30).
- **The 1:1 quick-turn timing against NFR-01:** a new, minimal `horizon eval latency` that bypasses the store
  (design D31).
- **Offline:** everything runs in `smoke`, CI and tests, including every E8 offline item.

**Findings from reading the code and docs**, each decided in design.md:
- The port fallback chain would give `naive` the scripted planner, face check and reaction charge. All three would
  record fake spend in a real ledger (D5, D21, D24).
- E1's wording names the candidate, but the bank has no way to put a name in the instructions (D11).
- E1's merge rule compares a summed probability against a floor that's meant for Jev's confidence (D12).
- `clear()` never cancels background work, so today a late reaction can flip a speaker's face (D20).
- A reaction's re-check outside the writer lock can race the next `turn.start` (D20).
- By A7's own rule, M9's plan is a single call and shouldn't be a graph (D3).
- E4's "View as prompt shows it" conflicts with P10, which shows system message 1 only (D17).
- E8's per-conversation bootstrap has only 4 conversations (D30).
- The question bank allows only noul judges (D29).
- W6's M9 estimate assumed an 80 % cache hit (D32).

## Capabilities

### New Capabilities
- `turn-plan`: the `TurnPlanner` port, the plan graph, `TurnPlan` and its place in `TurnContext`, Jev call 1 in
  `agent` 1:1, deadlines and late answers, Stop during a plan, and profile resolution.
- `speaker-emotion`: the emotion question and its bank entries, the merge, floor, keep and fade, the face's source and
  timing, MANUAL, the trace candidates and Insight's "kept" chip, and the mood line's choice of face.
- `listener-reactions`: `JevReactions`, the reactions task (when it runs, who listens, the keep rule, timing, drops),
  scripted and mock reactions, and the reducers' guard for a speaker's face.
- `face-check`: W2's live check: when it runs, its state and row, cancellation, spend, and profiles.

### Modified Capabilities
- `ai-ports`:
  - profile selection: `agent` gains the planner, reactions and the face check; `naive` resolves to none of the new
    ones;
  - the agent reply engine moves to `agent-2` and takes its face from the plan;
  - the scripted reaction predictor becomes async.
- `session-runtime`:
  - the turn sequence: `turn.start` and the first `emotion` go in one write;
  - Stop during a plan;
  - `clear()` cancels named after-turn tasks;
  - the reply cap with a planned turn.
- `session-event-sourcing`: both reducers keep a streaming speaker's face against reactions, with shared fixtures.
- `session-modes`: `agent` 1:1 turns retrieve nothing in M9; switching to MANUAL drops pending reactions.
- `persona-prompt`: the mood line in the dynamic tail, and its note in "View as prompt".
- `system1-trace`: the emotion and face-check rows; the scripted 1:1 Insight now shows the section.
- `decider`: `turn_plan` and `face_check` are decision spend.
- `question-bank`: an additive `{name}` placeholder in instructions; a pairwise judge entry of type `choice`; the
  face-check entry is shared with the evaluation.
- `evaluation-harness`:
  - the emotion and reaction policies in `decisions`;
  - choice judges;
  - the mood-line on/off run;
  - the `latency` suite;
  - a wider `smoke`.
- `demo-data`: the System 1 fixture gains the emotion and face-check rows; the MockClient plans, reacts and checks
  like the scripted profile.
- `opt-in-tracing`: the tracing package now ships with the backend (`langgraph` depends on it); opting in still needs
  the flag and the key (found in phase 1, design D1).

No `client-contract` delta. W4 lists it among the specs M9 touches, but every field used already exists:
`turn.start`, `emotion`, `reaction` with `p`, `TurnTrace.emotion.candidates`, `system1` and `graph.path`. If
implementation finds a wire change, it stops and asks.

## Impact

- **Backend:**
  - new: `ai/agent/{planner,plan_graph,emotion,reactions,face_check}.py`, `ai/questions/{emotion_reply,
    emotion_greeting,reaction,face_check,judge_names_feeling,judge_pairwise}.json`, `sessions/after_turn.py`;
  - changed:
    - `ai/{ports,contexts,profile}.py`, `ai/agent/{turn,persona}.py`, `ai/questions/__init__.py`,
      `ai/scripted/ports.py`;
    - `sessions/{turn,actor,commands}.py` and `sessions/modes/{one_on_one,common}.py`;
    - `services/runtime/reducer.py`, `gateway/context.py`, `domain/runtime_config.py`, `evals/*`;
  - `pyproject.toml` / `uv.lock` gain `langgraph`, pinned.
- **Frontend:**
  - `engine/sessionReducer.ts`, `domain/personaPrompt.ts`, `features/insight/InsightDrawer.tsx`,
    `features/wizard/steps/PromptPreview.tsx`;
  - `mock/script/turnScript.ts`, `mock/engines/{oneOnOne,group,debate,watch}.ts`;
  - seed-build: `runtime.config.ts` and `system1.ts`.
- **Data:**
  - `seed/{runtime.json,system1.fixture.json}`;
  - `backend/tests/fixtures/{reducer,persona_prompt,plan,reactions}/`;
  - `evals/datasets/{emotion,reactions,judges}/` and `evals/reviews/`.
- **No contract change, no new UI entry point, no migration.**
- **Docs:**
  - docs 06 §6 and 01 §8 (the built rows); doc 01 A4/A5/A7; doc 02 B2/B4/B5/B7/B8;
  - OQ-AI-07 resolved;
  - the new `docs/ai/checks/m9.md`.
- **Spend:** about $0.16 of paid runs (W6 said $0.10; M8's measured cache hit roughly doubles the reply part, and the
  pairwise judge wasn't counted, design D32), plus at most $0.10 of smoke. Each run is asked for when it comes, with its estimate; every output is saved.
- **Your time:**
  - review the 6 new bank entries' wording and labels;
  - review the sampled items of two decision sets and two judge sets (B2: ≥ 15 per set);
  - approve the `langgraph` version.

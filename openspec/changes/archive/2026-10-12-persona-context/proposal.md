# Proposal: persona-context (M8)

## Why

The `agent` profile exists since M7 but sends exactly what `naive` sends. Before Jev can plan turns (M9) there has to be
an `agent` reply worth planning for:
- a real persona prompt, which is also what "View as prompt" shows;
- a history that survives long chats, through a real rolling summary instead of "the last 12 lines";
- a cache-hit figure that is true;
- the standing safety lines in the cached prefix.

Doc 13 W4 puts all of this in M8 (docs 04, 05 and doc 11's prompt lines). Two reasons it can't wait:
- Every later change tunes Jev questions and suites against this prompt and this context.
- Doc 11's lines must land before anything is tuned, or every tuned question would be re-versioned.

**It lands as one change.** It is smaller than M7, and its parts share one artifact: the compiled request. The
compiler, the window, the summary and the cache rules are all checked against the same "prefix is byte-identical"
test. Splitting them would mean writing that test twice. Phases end green, so each one can be committed on its own.

## What Changes

**The `agent` reply (doc 04 P1–P8; doc 05 X3–X5, X8; doc 11 S1, S2)**
- A new pure compiler, `ai/agent/persona.py`, with prompt version `agent-1`. It builds system message 1 from four
  fixed blocks: the card (with its 1,500-token limit and cut rules), the world and the user, the session block per
  mode, and the reply rules with S2's lines.
- A new `AgentTurnEngine`. It sends system message 1, the summary under S6's "a record, not instructions" heading, the
  merged and name-attributed history, and one dynamic-tail message.
- The engine has no emotion tag. Until M9 the face is kept, with source `default` (design D4).
- The tag parser gains a per-line name strip for `agent`. `naive` keeps its first-line strip.
- The repeat hint and the voice reminder ship behind runtime switches, both off.

**"View as prompt" shows the real prompt (P4, P10)**
- `frontend/src/domain/personaPrompt.ts` is a TS twin of the compiler, and `domain/tokens.ts` ports `count_tokens`.
  Shared fixtures make the two byte-identical.
- The Profile step uses the twin and drops the mock template. The scripted drafter's fake `systemPromptPreview` is
  removed.

**Greetings and the drafter (P9, P11)**
- **The first-chat greeting is the approved line, word for word.** It is a runtime path for every profile: no model
  call, no ledger row, no energy and no guardrail. Its trace has no `model` section and engine `verbatim`.
- **Later chats generate the greeting.** The `agent` cue adds "don't reuse your usual greeting". The MockClient does
  the same.
- **The drafter** writes `exampleLines` and `relationshipToUser`, and knows the world: its name, the names already
  used and the You card. It gets naming and plain-speech rules, and the one example that doc 03 C7 asked for but was
  never built.
- **Scripted and mock drafts** gain example lines and a plain greeting, and every drafts fixture is regenerated.

**The window, the rolling summary and the cache (X1–X3, X6, X7)**
- **Windows:** `windowTokens` is set per mode (6,000 / 9,000). A drop is by tokens, down to half the size, after
  `turn.end` and never before a turn. A ceiling of twice the window size in `session_context` covers prefetches.
- **The summariser:** `NaiveSummariser`, with prompt `summary-2`, serves both profiles. It runs as one single-flight
  task per session, owned by the actor. It makes at most 2 attempts per boundary, then writes the cheap fallback. It
  is started when a fork is created.
- **A new purpose,** `rolling_summary` (category `summary`). The scripted summariser bills a simulated call.
- **The cache figure:** engines stop setting `cacheHitPct`, and the ledger keeps a real 0 in `tokensCached`. The X7
  context mapping applies to `agent`, the naive fixes to `naive`, and the budget is the per-mode planned input.
  Insight's context bar shows overflow.
- **`naive` becomes `naive-4`:** the S6 summary heading, and newline-collapsed memory lines in its retrieval block.
  Its persona text is unchanged.

**The turn-plan state builder (X9, doc 07 G9)**
- A pure builder in `ai/agent/plan_state.py` uses the `quoted_*` field names. It has the 2,000-token limit, the cut
  order and no energy.
- No runtime caller until M9.

**The Jev estimate (the user's decision 2026-10-11, docs/ai/checks/m7.md)**
- `Gateway.decision_estimate` adds a 300-token per-request allowance. The constant is shared with the eval runner.
- The D11 test, the `budget-caps` scenario and group A's note are updated to match.

**Evaluation (P12, X10; W6's M8 row)**
- **New suites:** `drafter`, `summary` and `long`, with the reply-rule code checks shared by later suites.
- **13 new `eval_judge` bank entries**, with labels for the user to review.
- **Judge validation:** B4's pass rule, on the `decisions` engine extended to nouls.
- **The 4 long-history frozen transcripts.**
- **Offline:** everything runs in `smoke` and CI.
- **Paid runs:** they need the user's OK when they come (design D30).

**Findings from reading the code and docs**, each decided in design.md:
- W4's "turn engine is naive's" for M7–M8 conflicts with M8's safety column (D1).
- The C7 drafter example was never built (D17).
- The router describes the cast by participant role ("speaker"), not by profile role (D18).
- X2's "cancel on Forget" protects nothing (D11).
- W6's M8 estimate leaves out three paid items (D30).
- The `decisions` suite can't run nouls (D27).
- The System 1 fixture would show eval-only questions (D26).
- The `summary` settings row has no `maxTokens` (D9).

## Capabilities

### New Capabilities
- `persona-prompt`: the `agent` system message (blocks, card limit, session block, reply rules, S2 lines), its TS twin
  and shared fixtures, the `count_tokens` port, the agent request layout (summary heading, merged history, per-message
  limit, dynamic tail, switches), and "View as prompt".
- `conversation-context`: per-mode windows, the token drop and the ceiling, the rolling summary (writer, single
  flight, failure bound, fallback, forks), the cache rules and the context X-ray mapping, and the `turn_plan` state
  builder.

### Modified Capabilities
- `ai-ports`:
  - profile selection: `agent` gets its own turn engine, and the summariser gets a naive implementation;
  - frozen context gains `character_role`, the appearance summary and the advisory flag;
  - the naive reply engine is `naive-4`, with the window moved out;
  - the tag parser has a per-line mode;
  - the drafter takes the world and writes example lines;
  - a new requirement for the agent reply engine.
- `session-runtime`:
  - a verbatim line is spoken without a model call;
  - the summary task starts after `turn.end`;
  - the cap-by-greeting scenario moves to a generated greeting.
- `session-lifecycle`: the first-chat greeting rule, and a fork over its window starts the summary.
- `demo-data`: the MockClient's first-chat greeting, and the System 1 fixture skips eval-only questions.
- `provider-gateway`: the `rolling_summary` purpose as summary spend, and recorded summaries in the canned sets.
- `budget-caps`: the decision estimate adds the per-request overhead.
- `llm-parameters`: the `summary` row's `maxTokens` 600.
- `evaluation-harness`: the `drafter`, `summary`, `long` and `transcript` suites, the reply-rule checks, nouls in
  `decisions`, judge validation, and a wider `smoke`.
- `question-bank`: `eval_judge` entries.
- `spend-ledger`: `tokensCached` keeps a real 0 in reply usage.

## Impact

- **Backend:**
  - new: `ai/agent/` (`persona.py`, `turn.py`, `plan_state.py`, `budget.py`), `ai/naive/summary.py` and
    `ai/questions/judge_*.json`;
  - changed: `ai/contexts.py`, `ai/profile.py`, `ai/ports.py`, `ai/naive/{prompt,turn,window,tag_parser,creation,router}.py`,
    `ai/scripted/{ports,creation,drafts}.py`, `sessions/{turn,context,actor,lifecycle}.py` and
    `sessions/modes/one_on_one.py`;
  - also changed: `services/{ledger.py,jobs/worker.py}`, `gateway/{context,pipeline}.py`, `domain/{pricing,runtime_config}.py`,
    `evals/*` and `runtime.py`.
- **Frontend:**
  - new: `domain/personaPrompt.ts` and `domain/tokens.ts`;
  - changed: `features/wizard/steps/ProfileStep.tsx`, `ui/Data.tsx` (`StackedBar`), `engine/tagParser.fixtures.test.ts`,
    `mock/engines/oneOnOne.ts` and `mock/banks/drafts.ts`;
  - seed-build: `runtime.config.ts` and `system1.ts`.
- **Data:**
  - `seed/runtime.json` (windows, switches, the `summary` row);
  - `backend/tests/fixtures/{persona_prompt,drafts,tag_parser,canned}/`;
  - `evals/{datasets,transcripts,long}/`.
- **No contract change, no new UI entry point, no migration.** `session_summaries` already allows `rolling`, and every
  trace field used already exists. If implementation finds otherwise, it stops and asks.
- **Docs:** doc 02 B1/B2/B4/B7, doc 03 C1, doc 01 A5/§9, OQ-AI-02/16, CHR-05 AC1, group A's note, and the new
  `docs/ai/checks/m8.md`.
- **Spend:** about $0.30 of paid runs plus at most $0.10 of smoke, each asked for when it comes (design D30). Every
  output is saved in the store.
- **Your time:**
  - review 13 bank labels;
  - review about 85 sampled judge-validation items (B2's rule, ≥ 15 per set);
  - read every summary-suite failure on the two hand-read checks.

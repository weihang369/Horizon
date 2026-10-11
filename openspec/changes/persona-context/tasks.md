# Tasks

> **Constraints for every task:**
> - **Tests are offline.** No network in automated tests: the socket guard stays on, and only the in-process fake
>   provider and obviously fake `sk-or-test-…` keys are used.
> - **The key stays private.** The real key is never printed, logged or put in fixtures. Live checks only test that a
>   key is present.
> - **Contract.** M8 changes none. If any contract method, wire field or UI entry point turns out to be needed,
>   **stop and ask the user** before changing it.
> - **Background work and waits.** New background work starts only through `rt.spawn`, and new waits use the runtime
>   clock, so `/_test/clock` settles.
> - **Our side stays fast.** Nothing new runs between a request and its first token. The summary runs after
>   `turn.end`, and the X9 builder has no caller.
> - **Scope.** Nothing from M9–M15: no planner call, no emotion choice, no G3 or V4 cues, no passage tags, no memory
>   list, no safety nouls.
> - **Commits and pushes.** Commit at each phase's green checkpoint, without Claude attribution. Push nothing unless
>   the user asks, and never commit `6 RAG.pdf`.
> - **Ask the user first** before any paid run (phase 10, each run with its own estimate), any network download, and
>   spawning subagents.
>
> **Every phase ends with these gates green:**
> - `uv run pytest`, `uv run ruff check`, `uv run mypy horizon`;
> - `npm run typecheck`, `npm run lint`, `npm test`, `npm run test:http`;
> - `npm run seed:check`, `npm run fixtures:check`, `npm run export-schema:check`;
> - `HORIZON_TEST=1 uv run horizon eval smoke --limit 5 --yes`.
>
> **Checkpoint:** commit the phase.

## 1. Foundations with no reply change

- [x] 1.1 Move `JEV_REQUEST_OVERHEAD_TOKENS = 300` into `domain/pricing.py`, and add `estimate_decision_request(prices, state, questions)` (design D23).
  - `Gateway.decision_estimate` and `evals/runner.decision_estimate` both call it.
  - Verify:
    - `test_decision_estimate_counts_the_state_once` keeps its 7 × per-question difference and gains the constant in the absolute value;
    - a unit test gives $0.0004326 for 10,000 tokens;
    - `test_eval_runner`'s estimate test still passes.
- [x] 1.2 Update the docs for the Jev allowance: a note under group A's billing row in `docs/ai/checks/group-a.md`, and `docs/ai/checks/m7.md` "Not changed in M7" → "fixed in M8 (persona-context)". Verify by reading both.
- [x] 1.3 Add the new context fields (design D18).
  - `ParticipantView.character_role` (default `""`), filled from the profile role in `session_context`.
  - `CharacterView.appearance_summary` and `CharacterView.advisory`, filled by `character_view(row)`.
  - Verify with a unit test: a group context has `role == "speaker"` and `character_role == "barista"` for Hana, and the context round-trips through JSON.
  - Update the tests that build `ParticipantView` directly: `test_naive_prompt.py`, `test_turn_retrieval.py`, `test_ports.py`.
- [x] 1.4 Feed the profile role to the Jev router's cast options and `quoted_cast`, falling back to `role` when it is empty (design D18). Verify:
  - a router unit test sees "Hana (barista)" in the compiled option;
  - `route`'s bank version and lock are unchanged.
- [x] 1.5 Add `per_line: bool` to `TagParser` (design D18). Add shared fixtures with `perLine: true`: a second-line prefix, a prefix split across chunks after `\n`, and a lookalike name on a later line. Implement the same in the TS reference parser in `frontend/src/engine/tagParser.fixtures.test.ts`. Verify:
  - the Python and TS fixture tests both pass;
  - the existing `perLine: false` fixtures are unchanged.
- [x] 1.6 Refactor `NaiveTurnEngine.run` into the three seams `request()`, `parser()` and `trace_patch()` (design D2), with no behaviour change. Verify:
  - every naive test passes unchanged;
  - the naive request snapshot test passes byte for byte;
  - `fixtures:check` passes.
- [x] 1.7 Phase gates green → commit "M8 phase 1: foundations".

## 2. The `agent` persona compiler and its TS twin

- [x] 2.1 Write `ai/agent/persona.py`: `PersonaInput`, `PersonaPrompt` and `compile_persona` (design D3, D5, D7), with `PROMPT_VERSION = "agent-1"`. It builds:
  - P3's card;
  - P2's world block;
  - P5's session block for 1:1, group, watch, and two-sided and panel debate (V4's block text);
  - P6's rules with S2's lines, the advisory line and the emoji line;
  - V4's debate rules in place of P6's three chat lines.

  Verify with unit tests on Amara, Hana and a debate cast:
  - no `<e:` instruction and no mature line;
  - the relationship reaches the world block;
  - the tagline is absent;
  - "use rarely" and "style only" are present;
  - an advisory character gets the lower-cased role in the advisory line.
- [x] 2.2 Add the card limit (design D5): per-field caps, the shared sentence-end regex with the abbreviation list, the space and CJK fallbacks, step 2's drop order, and the cut report. Verify with unit tests:
  - a 5,000-word backstory;
  - "Dr." at the cut;
  - a CJK item with no sentence end;
  - an emoji at the cut;
  - a card that needs step 2 keeps every voice field.
- [x] 2.3 Write the shared fixtures in `backend/tests/fixtures/persona_prompt/` (`{input, expected}`): the six seed characters in their natural modes, every mode at least once, and the cut cases from 2.2. Add a Python fixture test. Verify that it passes, and that a one-character edit to any expected text fails it.
- [x] 2.4 Port the compiler to TypeScript: `frontend/src/domain/tokens.ts` (`countTokens`: UTF-8 bytes through `TextEncoder`, ÷ 3, rounded up) and `frontend/src/domain/personaPrompt.ts` (design D21). Add `personaPrompt.fixtures.test.ts`, running every fixture from 2.3. Verify that both languages pass the same fixtures.
- [x] 2.5 Make the Profile step use the twin (design D21).
  - Build a 1:1 `PersonaInput` from the wizard's character, its world's name and You card, and `appearanceSummary`.
  - Show the step-2 note and `≈ {countTokens} tokens · read-only`.
  - Delete `composePrompt` and the "mock template" label.
  - Verify with a component test: editing the backstory past 600 tokens updates the preview with the cut and the new count, and "mock template" is gone.
- [x] 2.6 Run doc 04 §5 check 1 offline as `docs/ai/checks/m8/prompt_sizes.py` (beside group A's scripts): compile the six seed characters in all four modes and record each system message's tokens per block. Verify:
  - the output table is in a new `docs/ai/checks/m8.md` ("Offline checks");
  - any card hitting step 2 is listed as a finding and reported to the user.
- [x] 2.7 Update the docs:
  - doc 01 A5 and its fallback table's emotion row (P7: keep the previous face on `agent`);
  - OQ-AI-16 marked resolved in `docs/requirements/08`;
  - CHR-05 AC1 drops "it's a mock in the UI phase" in `docs/requirements/02`.

  Verify by reading each edit.
- [x] 2.8 Phase gates green → commit "M8 phase 2: persona compiler and preview".

## 3. The `agent` reply engine

- [x] 3.1 Add the runtime switches `persona.repeatHint` and `context.voiceReminder` (both `false`) to `runtime.config.ts` → `seed/runtime.json` → `domain/runtime_config.py`. Verify:
  - `test_runtime_config` reads both as false;
  - `seed:check` passes after seed-build.
- [x] 3.2 Write `ai/agent/turn.py` `AgentTurnEngine`, overriding the three seams (design D2, D4, D6, D7).
  - The request: system message 1, the summary under S6's heading with leading `#`s stripped, the X4 merged and line-attributed history with the X8 clip, and one tail message with the retrieval block, the hint and reminder (when on), the cue or the trailing cue.
  - The parser in per-line mode.
  - The face kept, with source `default`.
  - Verify with unit tests:
    - a multi-line reply from another speaker becomes `Name: line` lines in one merged `user` message;
    - a user line containing `\n# How to reply` is prefixed on every line;
    - a 20,000-token message is clipped to 3,000 + `[…]` + 1,000;
    - a stray `<e:happy>` doesn't change the face;
    - the greeting cue quotes the stored greeting;
    - the hint and reminder appear only when on, and never in system message 1.
- [x] 3.3 Add `"turn"` to `AGENT_PORTS` and build `AgentTurnEngine` in `AiPorts._build` (design D1). Verify:
  - `resolved()` under `agent` with a key shows `turn: agent` and `router: naive`;
  - without a key everything is scripted;
  - a 1:1 integration turn under `agent` on the fake provider completes, with `prompt_version` `agent-1` in `turn_traces`.
- [x] 3.4 Add the agent X7 context mapping (design D16, agent part, using `ai/agent/budget.py`). Verify with an integration test:
  - `context.used.persona` equals the card's tokens;
  - `user` equals the latest user message's tokens;
  - `budget` is 11,680 in 1:1 and 14,680 in group;
  - there is no `cacheHitPct`.
- [x] 3.5 Add the prefix stability test (X6): two consecutive `agent` turns of a fixture group session with no drop. Verify that the second request's messages begin with exactly the first's.
- [x] 3.6 Phase gates green → commit "M8 phase 3: agent reply engine".

## 4. Windows and the rolling summary

- [x] 4.1 Set `windowTokens` per mode (`{one_on_one: 6000, group: 9000, watch: 9000, debate: 9000}`) and add `maxTokens: 600` to the `summary` row (design D8, D9). The loader also accepts the old int. Verify:
  - `test_runtime_config` covers both shapes;
  - `seed:check` passes;
  - the `llm-parameters` summary request test sees `max_tokens: 600`.
- [x] 4.2 Rewrite `plan_window` to drop by tokens down to half the size, keeping at least 2 messages (design D8). Verify with unit tests: a normal drop, a single huge message, a fork-sized history, and a no-op under the size.
- [x] 4.3 Add the ceiling to `session_context`: twice the mode's window of post-summary history, newest first, at least 2 (design D10). Verify:
  - a unit test on a 15,000-token 1:1 history gives at most 12,000;
  - a prefetch path test sees the ceiling.
- [x] 4.4 Write `ai/naive/summary.py` `NaiveSummariser` (design D9).
  - Prompt `summary-2`: X3's text plus S6's reported-speech line.
  - Input: speaker-prefixed lines with the X8 clip, folded in 6,000-token chunks.
  - Output: cut at a sentence end over 600 or on `length`; empty means failure.
  - `episode` delegates to the scripted one.

  Add `rolling_summary` to `PURPOSE_CATEGORY` (category `summary`), and `"summariser"` to `NAIVE_PORTS`. Verify with unit tests: the prompt text, chunking at 6,000, the sentence-end cut, and empty as failure.
- [x] 4.5 Make `Summariser.rolling` async in the port protocol. `ScriptedSummariser.rolling` keeps its 12-line text and records one simulated `rolling_summary` call per drop (design D13). Verify that a scripted integration test writes one `summary`/`rolling_summary` ledger row per drop, and that no energy changes.
- [x] 4.6 Write `sessions/summary.py` `SummaryTask`, owned by the actor (design D9, D11).
  - It runs after `turn.end`, is single-flight, takes no LLM slot, and writes under the write lock after re-reading the boundary.
  - Failures are counted per boundary, with the 1,000-token growth gate and the fallback after 2.
  - Actor stop cancels it; Stop, `clear()` and Forget don't.

  Remove `maintain_window` from turn preparation. Verify with virtual-clock integration tests:
  - the first word isn't delayed;
  - a turn that ends mid-summary starts no second call;
  - Stop during a summary still writes it;
  - two failures write the fallback with at most 2 calls;
  - idle release cancels and writes nothing.
- [x] 4.7 Start the summary check after the fork in `lifecycle.fork` (design D12). Verify with an integration test: a fork of a session past its window makes a `rolling_summary` call with no user message, and has a `rolling` row once it lands.
- [x] 4.8 Add a canned `rolling-summary` set for the fake provider (`tests/fixtures/canned/rolling-summaries.json`), marked synthetic until phase 10 replaces it with recorded ones. Verify that the provider-gateway canned-summary test passes.
- [x] 4.9 Bump `naive-4` (design D14): the S6 summary heading, and newlines collapsed in the retrieval block's memory lines (shared with `agent`). Verify:
  - the naive prompt tests are updated for the heading;
  - a memory with `\n# Rules` renders on one line;
  - the request snapshot is re-recorded and diffed by hand to show only those two changes.
- [x] 4.10 Run doc 05 §5 check 1 offline: extend `docs/ai/checks/m8/prompt_sizes.py` with a long fixture history per mode. Check every section against its cap, and the prefix byte-identical across two turns. Verify that the results are added to `docs/ai/checks/m8.md`, with any cap hit by a seed character listed as a finding.
- [x] 4.11 Update the docs:
  - doc 03 C1's `summary` row (doc 05 X3, `max_tokens` 600);
  - `docs/backend/05-ai-seams.md` §3 gains `rolling_summary`;
  - the ai-ports note in `ai/profile.py`'s docstring.

  Verify by reading.
- [x] 4.12 Phase gates green → commit "M8 phase 4: windows and rolling summary".

## 5. Cache and context figures

- [x] 5.1 `reply_usage` returns `tokensCached` whenever any row reports one, 0 included, and `finish` copies it with `is not None` into the wire usage and `model` (design D15). Verify with spend-ledger tests for "nothing cached" and "not reported".
- [x] 5.2 Make the naive engine stop setting `cacheHitPct`. Apply its X7 fixes: the summary goes to `history`, `user` counts the latest message, and `budget` comes from `planned_input(mode)`. `AiDeps.window_tokens` becomes `windows` (design D15, D16). Verify:
  - the naive trace tests are updated;
  - a naive reply with a summary counts it under `history`;
  - the scripted engine's simulated `cacheHitPct` is unchanged (`fixtures:check`).
- [x] 5.3 Make `StackedBar` scale to `max(total, sum)`, with the overflow hatched, a budget marker, and a legend reading "used / budget (+over)" (design D16). Verify:
  - a `Data` component test with used > budget shows every segment and the marker;
  - the KitGallery still renders.
- [x] 5.4 Phase gates green → commit "M8 phase 5: true cache and context figures".

## 6. The first-chat greeting

- [x] 6.1 Add `LineHint.verbatim`, and `sessions/verbatim.py` `VerbatimEngine`, paced like the scripted stream plan on the virtual clock (design D19). The runner, for a verbatim turn:
  - takes no LLM slot and runs no retrieval;
  - skips the guardrail, the memory writer and the capture row;
  - writes no `model` section, `calls: []`, engine `verbatim` and no prompt version.

  Verify with integration tests:
  - no ledger row, no `energy` event, no `usage`;
  - the trace shape;
  - Stop mid-greeting keeps the partial text at no cost;
  - regenerate produces a billed generated variant.
- [x] 6.2 Add `is_first_chat` and the new `one_on_one.greet` (design D20). Verify with integration tests:
  - a new character's first chat is verbatim;
  - seed sessions and a "Continue live" fork don't count;
  - an asleep-only first session doesn't count;
  - a second chat is generated (naive cue; agent cue with the stored greeting; scripted bank greeting, billed).
- [x] 6.3 Update the tests that assumed a billed greeting (P9): `tests/sessions/test_naive.py` (ledger row, cost, `emotionSource`, energy, the "greeting set the prefix" cases), `test_energy_caps.py` ("cap reached by the greeting", moved to a second session) and `test_core.py`. Verify that each passes, with the cases moved to a second 1:1 session where a billed greeting is the point.
- [x] 6.4 Give the MockClient the same rule in `mock/engines/oneOnOne.ts` (design D20): verbatim, no simulated cost or energy event, and no `model` trace on a first chat. Verify:
  - a mock engine test for first and second chats;
  - `npm run test:http` passes on both clients;
  - the E2E specs that read cost or energy after a greeting are updated, and `npm run e2e` passes.
- [x] 6.5 Phase gates green, plus `npm run e2e` → commit "M8 phase 6: approved greeting first".

## 7. The drafter

- [x] 7.1 Extend the draft schema with `exampleLines` (2–3) and `relationshipToUser` (an empty value dropped before validation) (design D17). Add `DraftWorld`, and the `world` argument to `ProfileDrafter.draft` on both drafters. The worker builds it from the world name, the world's character names (tombstones included) and the You card. Verify:
  - the schema test keeps every contract limit in step;
  - a worker test sees the world in the naive request;
  - the scripted drafter avoids a name already used.
- [x] 7.2 Add P11's rules and the one C7 example draft (a new invented companion, no seed or stock names) to the drafter system prompt, and the greeting rules to `regenerate_field` (design D17). Verify:
  - a test validates the example against the schema;
  - the system prompt holds the schema, the quote rule and the example in a fixed order, so the cached prefix is stable;
  - the canned `profile-drafts` drafts still validate.
- [x] 7.3 Update the scripted and mock drafts: 2–3 example lines from a shared bank, a plain greeting, no `systemPromptPreview`. Regenerate every `backend/tests/fixtures/drafts/*.json` in the same change. Verify:
  - the Python and TS draft fixture tests pass byte for byte;
  - no greeting contains `*` or "What can I do for you".
- [x] 7.4 Phase gates green → commit "M8 phase 7: drafter knows the world".

## 8. The turn-plan state builder

- [x] 8.1 Write `ai/agent/plan_state.py`: `PlanStateInput`, `build_turn_plan_state` and `eligible_candidates` (design D22). It has:
  - X9's fields with S6's `quoted_*` names;
  - labels for `last_spoke`;
  - the 2,000-token limit and the cut order;
  - `dropped_gates`;
  - no energy.

  Verify with unit tests:
  - every top-level text field is `quoted_*`;
  - labels fit `labelMaxChars`;
  - "not yet" and "2 turns ago";
  - an exhausted or muted character is excluded;
  - a 5-candidate state with long titles stays ≤ 2,000, keeps ≥ 3 recent lines and reports dropped gates;
  - watch uses 12 recent lines and the summary;
  - the debate fields are present.
- [x] 8.2 Update the docs: doc 01 §9's Jev-state item and OQ-AI-02 marked resolved (doc 05 X9, built in M8). Verify by reading.
- [x] 8.3 Phase gates green → commit "M8 phase 8: turn-plan state".

## 9. Evaluation, offline

- [x] 9.1 Write the 13 `eval_judge` bank entries (design D24): nouls, "yes" is the failure, `quoted_*` state, `deadline: "default"`, `thresholds: {"t": 0.5}`. Run `horizon eval bank-lock`. Verify:
  - `test_bank_lock` passes;
  - every entry compiles to a valid wire question in smoke;
  - a test asserts no live code path asks an `eval_judge` question.
- [x] 9.2 **Ask the user to review the 13 labels and wordings** (W4). Apply their edits, bump versions, re-lock. Verify that the user has approved them in chat.
- [x] 9.3 Make `system1.ts` skip `purpose: "eval_judge"` (design D26). Verify that seed-build regenerates the fixture with no judge rows, and that `seed:check` passes.
- [x] 9.4 Teach `decisions` to score nouls (asked once, `p ≥ t`, calibration on `p`), and add `--set NAME`. Add the B4 judge report, the `evals/baselines/judges.json` record, and "unvalidated" marking for figures from judges without a passing record (design D25, D27). Verify with unit tests:
  - a noul item is scored from one request;
  - the pass rule's three conditions;
  - a version bump makes a judge "unvalidated" again.
- [x] 9.5 Write `evals/reply_checks.py` (design D28): actions, stray tag or prefix, bubbles over target, emoji, question endings, the step-2 rate, repeated openers and catchphrases. Verify with unit tests per check on hand-made replies.
- [x] 9.6 Write the suite inputs, each line split by M7's hash rule:
  - `evals/drafter/seeds.jsonl`: 20 seeds, three intents, both worlds;
  - `evals/summary/items.jsonl`: 40 items in English, Malay, Chinese and mixed, with 3 planted facts, 1 promise and its maker each;
  - `evals/long/*.json`: three scripts to two drops + 20 turns, facts in turns 3–10, 5 late probes, ≥ 3 wrong claims;
  - `evals/transcripts/scripts/*.json`: 1:1 × 2, group × 2.

  Verify:
  - the data checks load them all;
  - the overlap check passes against the bank;
  - the split test pins every split.
- [x] 9.7 Implement the `drafter`, `summary`, `long` and `transcript` suites (design D28–D31). `long` and `transcript` use `drive()`, which waits on idle rather than sleeping. Write the planted-failure generators for the 13 judge sets. Verify:
  - each suite runs one item on the fake provider in test mode;
  - the planted generators produce 30 items per judge with known answers;
  - the transcript loader rejects a "long" transcript with no summary.
- [x] 9.8 Widen `smoke` (one drafter seed, one summary item, the first lines of each long script, reply checks on every smoke conversation) and update the CLI's suite list. Verify:
  - `HORIZON_TEST=1 uv run horizon eval smoke --limit 5 --yes` exits 0 with no socket opened;
  - `horizon eval conversations` lists the new suites.
- [x] 9.9 Update the docs: doc 02 B1 (suites), B2 (sizes, the judge sets), B4 (the 13 judges, "yes" is the failure), B7 (the suite list and cost line); `evals/README.md` (layout and commands). Verify by reading, and that every command in the README runs in test mode.
- [x] 9.10 Phase gates green → commit "M8 phase 9: evaluation suites offline".

## 10. Paid runs (each asked for separately)

- [ ] 10.1 **Ask the user**: the `drafter` run (≈ $0.025, off-peak, `--profile naive`, store on). After OK, run it with `--yes`. Verify:
  - the report and spend appear in `data/evals/`;
  - the code checks are summarised in `docs/ai/checks/m8.md`, with the judge figures marked "unvalidated".
- [ ] 10.2 **Ask the user**: the `summary` run (≈ $0.06). After OK, run it. Verify:
  - the code checks are in m8.md;
  - every failure on the two 20-item checks is printed for reading;
  - the recorded real summaries replace the synthetic canned set (4.8), and the canned-summary tests still pass.
- [ ] 10.3 **Ask the user**: the `long` run (≈ $0.12, `--profile agent`). After OK, run it. Verify that m8.md has recall, the cache-hit %, summary calls per 100 turns, the reply checks and the repetition rates, with judge figures marked "unvalidated".
- [ ] 10.4 **Ask the user**: the four long-history transcripts (≈ $0.06, `naive`). After OK, generate them, read each one, and commit them. Verify that the loader accepts all four and each is past one drop.
- [ ] 10.5 Label 30 real items per judge from 10.1–10.4's outputs and group A's drafts. Run `horizon eval review` per set, and **ask the user to review the samples** (about 85 items). Relabel any set with two or more disagreements. Verify that `evals/reviews/` records each review.
- [ ] 10.6 **Ask the user**: judge validation (≈ $0.03, `decisions --set judges`). After OK, run it. A failing judge is reworded on its items, re-versioned, re-locked, re-reviewed with the user, and re-run. Verify that `evals/baselines/judges.json` shows all 13 judges passing at their current versions.
- [ ] 10.7 Re-run `drafter`, `summary` and `long`, served from the store, paying only for re-versioned judges. Ask first if anything new will be paid. Verify:
  - m8.md reports validated figures against P12's and X10's targets;
  - X5's drift signal decides the voice-reminder switch;
  - P8's rates decide the repeat-hint switch;
  - a missed target is reported to the user with options before any prompt change.
- [ ] 10.8 Write `docs/ai/checks/m8.md`'s summary: the spend per run against the estimates (design D30), the findings, and what M9 inherits. Verify by reading. Phase gates green → commit "M8 phase 10: paid runs and results".

## 11. Integration and review

- [ ] 11.1 Run every gate on the final commit, plus `npm run e2e` and the three CI eval commands, in a clean worktree (`../Horizon-gate`, the main venv, `PYTHONPATH=.`). Verify that all pass, and record the counts in the commit message.
- [ ] 11.2 Run a scope and contract review against design.md:
  - no contract or schema diff (`export-schema:check`, `git diff` on `contract/`);
  - no runtime caller of the X9 builder;
  - no `eval_judge` question in live code;
  - nothing from M9–M15.

  Verify that the review notes are in the commit message, and that every task above is checked.
- [ ] 11.3 `openspec validate persona-context --strict` passes → commit "M8 phase 11: review", and tell the user that the change is ready to archive.

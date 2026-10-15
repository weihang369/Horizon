# Tasks

> **Constraints for every task:**
> - **Tests are offline.** No network in automated tests: the socket guard stays on, and only the in-process fake
>   provider and obviously fake `sk-or-test-…` keys are used.
> - **The key stays private.** The real key is never printed, logged or put in fixtures.
> - **Contract.** M12 changes none (design D25). If any contract method, wire field, event or UI entry point turns out
>   to be needed, **stop and ask the user** before changing it.
> - **Background work and waits.** New background work starts only through `rt.spawn` or `actor.background`, and new
>   waits use the runtime clock (or `vclock.join` / `wait_handoff`), so `/_test/clock` settles.
> - **Our side stays fast.**
>   - The deep work starts at the gate and runs ahead wherever the mode already waits (D15).
>   - Search, fusion and MMR stay a few milliseconds.
>   - A quick turn costs and waits what it does today.
> - **Scope.** Nothing from M13–M15:
>   - no recall, no "needs something from earlier?", no memory list or writer, no `dupCosine`;
>   - no safety nouls or output check;
>   - no conversations or `naive` arms.
>
>   `agent` stays opt-in.
> - **`scripted` keeps the mock's behaviour; `naive` changes only its slice** (K13, D18).
> - **The user's documents, memories and messages never enter the response store** (W10).
> - **Commits and pushes.** Commit at each phase's green checkpoint, without Claude attribution. Push nothing unless
>   the user asks, and never commit `6 RAG.pdf`.
> - **Ask the user first** before:
>   - any paid run (phase 11, each with its own estimate, off-peak: not 09:00–12:00 or 14:00–18:00 KL; the user's
>     small-overrun rule: a run may pass 1.5× its estimate without asking while it stays under $0.01 in all);
>   - any download (check 4's PDFs, D31.3);
>   - spawning subagents;
>   - any prompt, wording, threshold or setting change a finding suggests (as choices).
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

- [x] 0.1 Confirm the base. `git diff --stat cf157b9 a16a5ec -- backend frontend seed evals` must show no code
  change. Re-run the backend gate in the gate worktree and the frontend gates, and record them in a new
  `docs/ai/checks/m12.md` "Step 0" table.
  Verify: backend 1648, frontend 529 / http 62, e2e 66 + 2 skipped, or each difference explained there.
- [x] 0.2 Confirm the storm helper (`tests/helpers/storm.py`) and `park_decision` cover a held `deep_check` request
  and a held chat response. Add a test for each holding shape the later phases need (several parked decisions at
  once, released in any order).
  Verify: the new helper tests pass on the virtual clock.

## 1. `pack@2` and its mock twin (design D3; K1, K12)

- [x] 1.1 Write the shared chunker fixtures `tests/fixtures/chunker/*.json`. Each holds input Markdown and the expected
  pieces (text, locator, heading). The cases:
  - heading carry, including a heading at a page foot and two headings in a row;
  - merging to 300;
  - the 400 ceiling with sentence, line and word cuts;
  - `。！？` cuts;
  - a table split between rows with the header repeated;
  - a list kept with its lines;
  - a mid-sentence page break giving `pp. 3–4`;
  - a heading change that never crosses;
  - `¶ n` with no headings;
  - the Soups case.

  Verify: the files load in both languages' test runners.
- [x] 1.2 Implement `pack@2` in `ai/chunker.py`, with the offsets invariant in its docstring, sections kept for
  `naive`, and `CHUNKER_VERSION = "pack@2"` defined once and imported by `services/knowledge/sources.py`.
  Verify:
  - every fixture passes;
  - a property test checks the offsets invariant on every fixture (text minus a repeated header equals the
    collapsed source slice);
  - `grep CHUNKER_VERSION` finds one definition.
- [x] 1.3 Make the mock's `paragraphs()` (`mock/engines/knowledge.ts`) `pack@2`'s twin on Markdown and text, reading
  the same fixtures. Update `clientContract.portable.ts`'s chunking test (one Soups piece, `§ Soups`).
  Verify: `npm test` and `npm run test:http` pass with the same expectation on both clients.
- [x] 1.4 Reindex of a `para@1` source re-chunks from the `chunk` stage. Seed sources only re-embed, keeping their
  piece IDs. Startup never re-chunks.
  Verify:
  - a test reindexes a stored `para@1` source and finds new piece IDs, with an old citation showing the viewer's
    "re-indexed" path;
  - a seed source keeps its IDs;
  - a restart changes no piece.
- [x] 1.5 Note `pack@2` in doc 10 K1/K12 ("built in M12") and in `docs/backend/05-ai-seams.md` §3.
  Verify: the docs link check passes.

## 2. The header space and `horizon space build` (design D4, D5; K3)

- [x] 2.1 Add `SpaceSpec.doc_template`, persisted in `embedding_spaces.doc_template` (read and written by
  `ensure_active`, `create_building` and `spec_of`). Add the `knowledge` embedder kind and
  `request_text(text, kind, space, meta)`, where the header leaves the heading out when it equals the locator and
  strips the title's extension. Ingestion and `build_space` pass `(title, heading)` with each piece.
  Verify: unit tests for the four header cases (title + heading, seed row, no heading, memory plain).
- [x] 2.2 Key the LRU on the request text, and add in-flight de-duplication (a second miss for a key being embedded
  awaits the first call).
  Verify:
  - two concurrent embeds of one message make one gateway call and one ledger row;
  - a changed instruction misses the cache.
- [x] 2.3 Make `qwen3-emb-8b@1024+h` the new `DEFAULT_SPACE`, with the template and the new instruction. An existing
  install keeps its space.
  Verify:
  - a fresh data directory starts in the new space, with its vec tables;
  - a database whose active space is `qwen3-emb-8b@1024` keeps it after a restart;
  - seed indexing embeds with the header through the seed-only store view.
- [x] 2.4 `build_space` copies memory vectors when the model and dimensions match, and knowledge vectors only when the
  template also matches, inside the fill's write transaction with no ledger row. It takes the list of kinds to fill
  (the M13 seam, D27).
  Verify: a test builds the header space from the old one, copies 40 memory vectors (no ledger rows) and re-embeds
  the pieces (`embed_doc` rows).
- [x] 2.5 Add `horizon space build [--space ID] [--yes]`: it counts and estimates at today's price period, asks,
  refuses while the server holds the data directory, and with no confirmation spends nothing.
  Verify: CLI tests for declined, `--yes` on the fake provider, and server-running refusal.
- [x] 2.6 Note K3's built parts in doc 10 and the CLI in `docs/backend` (the local-backend command list).
  Verify: the docs link check passes.

## 3. The bank, the purposes and the knobs (design D7, D21, D26)

- [x] 3.1 Add the five bank entries at version 1, worded exactly as D7, with `what` / `not_for` examples:
  `docs`, `standalone`, `english`, `passage` (3 ordered levels, `shuffle: false`), `passage_set`. `docs` declares
  every plan state field (1:1, group, watch and debate). Run `uv run horizon eval bank-lock`.
  Verify:
  - `test_question_bank_m12.py` checks wording, types, thresholds (D7's starting values) and the declared fields;
  - a `docs` question is accepted in a debate plan state;
  - `passage`'s levels keep their order across seeds.
- [x] 3.2 Add `deep_check: decision` and `query_rewrite: chat` to `PURPOSE_CATEGORY`.
  Verify: `call_ctx` accepts both, an unknown purpose still raises, and neither drains energy.
- [x] 3.3 Add the `retrieval.agent` knobs to `runtime.config.ts` and `seed/runtime.json` (D26), and regenerate the
  seed. `naive` and `scripted` keep `knowledgeK`, `memoryK` and `queryEmbedWaitMs`.
  Verify:
  - `npm run seed:build` then `seed:check` pass;
  - the backend reads every knob in a config test.
- [x] 3.4 Regenerate `seed/system1.fixture.json` with rows for the five entries.
  Verify:
  - `seed:check` passes;
  - the demo-data test finds the five rows and no judge rows;
  - `System1Section`'s existing passage test still resolves a `kch_` id.

## 4. The gates in every plan (design D6, D8, D20)

- [x] 4.1 The runtime reads each candidate's searchable-source titles (`indexed` or `keyword_only`, extension stripped,
  newest first) through a world-bound read, and fills `PlanStateInput.documents` for gated candidates only.
  Verify:
  - a state for Amara (keyword-only seed sources) lists her titles;
  - a candidate with no source has none;
  - X9's cuts still keep the state ≤ 2,000 tokens, reporting `dropped_gates`.
- [x] 4.2 Add the gates to Jev call 1 in 1:1: `docs:{speaker}`, plus `standalone` and `english` when `docs` is asked.
  Decide the branch: `route` answers `deep` when p ≥ `t_gate`, and generated greetings ask no gate.
  Verify `test_gates_m12.py`:
  - one request holds the three questions;
  - p 0.8 → `deep`, p 0.1 → `quick`;
  - a late plan → quick with a `fallback` row;
  - a character without sources gets no gate.
- [x] 4.3 Add the gates to the cast plan:
  - `group_first`, `group_mentioned` and `everyone`: `docs` per gated candidate, plus `standalone` and `english` once;
  - `next` and `step_in`: `docs` only;
  - watch `scene` and `opening`: `docs` only;
  - `debate_opening` and `debate_ask`: `docs` for the speaker.

  `for_speaker` takes the speaker's own gate: their branch, abstain-allowed (D8) and rows.
  Verify:
  - per-kind request contents;
  - only the speaker's `docs` row is `used`;
  - `dropped_gates` candidates go quick.
- [x] 4.4 Add the gates to the follow plan: `docs` per candidate, reusing the cast plan's `standalone` and `english`
  for the same message, or asking them when it didn't.
  Verify: a follow request holds `docs` and no rewrite nouls when the cast plan asked them, and holds them when it
  didn't.
- [x] 4.5 Add the gate to the debate plan: `docs` per eligible member with titles, no rewrite nouls. The member's
  651 ms deadline is unchanged; the gate is used if back by the turn's start, else the turn is quick.
  Verify, on the virtual clock:
  - the member fixed at 651 ms is unaffected;
  - a gate landing after the deadline but before the turn's start is used;
  - one landing later gives a quick turn with a `fallback` row.
- [x] 4.6 Measure each grown request on the fake: the state and question tokens of 1:1, a group of 5 with 4 gated,
  watch, follow and a debate plan with 3 members. Record them in m12.md.
  Verify: every request is under the Decider's size check, and the table is in m12.md.
- [x] 4.7 Note the gates in doc 01 A4 and doc 05 X9 ("built in M12").
  Verify: the docs link check passes.

## 5. The query (design D10, D11, D19; K4; D-100)

- [x] 5.1 Extend `QueryBundle` to D10's fields, JSON round-trip, and build it per mode (1:1 and group message, the
  rewrite rows, debate's motion + argument, watch's two texts, Ask's question + motion).
  Verify: a test per mode checks `dense_texts`, `earlier`, `source` and `display` (≤ 120 characters), and that the
  bundle round-trips.
- [x] 5.2 Implement `agent_terms`: the committed stop list, rarity from scoped FTS5 counts (≤ 40 terms looked at),
  ≤ 16 terms, or ≤ 24 rewritten with the rewrite's terms first, still as quoted OR terms.
  Verify:
  - unit tests for stop words, rarity order on a fixture index, the 24-term case;
  - the existing "message full of syntax" scenario.
- [x] 5.3 Migration `0004_message_ai_meta` (D19), with upgrade and downgrade. Fork copies its rows in
  `sessions/lifecycle.py`, deleting a message cascades, and a factory reset removes it.
  Verify: migration up/down test; fork and cascade tests; `assert_reduces` unaffected.
- [x] 5.4 Implement the rewrite (`ai/agent/rewrite.py`):
  - the speaker's `agent` reply prefix byte for byte, plus K4's instruction;
  - `query_rewrite` with `runtime.llm.calls.query_rewrite`;
  - K4's output checks;
  - the `rewriteMs` deadline;
  - a returned accepted rewrite for the runtime to store per message and speaker;
  - reuse of a stored rewrite with no call.

  Add a canned rewrite set to the fake (W14).
  Verify:
  - the prefix equals the reply's prefix;
  - a two-line rewrite is rejected;
  - a held rewrite past 1,500 ms falls back to the message + earlier lines;
  - regenerate reuses the stored rewrite with no chat call;
  - a group's second speaker gets its own rewrite.
- [x] 5.5 Implement D11's embedding at the gate: started in parallel with BM25 and the rewrite, skipped without
  vectors, waited ≤ 400 ms, and the rewrite's embedding ≤ 400 ms. `start_query` stays off for `agent`.
  Verify:
  - one `query_embed` row for a group message both repliers searched;
  - none when the gate said no;
  - none for a keyword-only speaker;
  - a late embedding → keywords only, still recorded.
- [x] 5.6 Storms (D2): the rewrite cut by Stop, a new message and `clear()`; the embedding wait cut by Stop; the
  `message_ai_meta` write cut mid-transaction.
  Verify: each storm's asserts pass.

## 6. The shared search pipeline (design D12; K5)

- [x] 6.1 Add `ScopedIndex.vectors(rids)` reading the active space's `knowledge_vec` rows in the speaker's partition.
  Verify:
  - it returns stored vectors for indexed pieces and nothing for keyword-only ones;
  - another character's rid returns nothing.
- [x] 6.2 Implement `search(index, bundle, params)`:
  - BM25 + dense lists;
  - two-step RRF;
  - min–max normalisation (single-item and all-equal pools give 1.0);
  - MMR with cosine or the Jaccard fallback;
  - the deterministic tie order.

  The parameters come from the knobs, not code, so M13 passes recall's.
  Verify:
  - unit tests for fusion arithmetic, normalisation edge cases, MMR spreading near-copies, Jaccard with no vectors;
  - the same inputs always give the same 8.
- [x] 6.3 Time the pipeline on a fully loaded test database (every seed and corpus document, 3,000 pieces for one
  character).
  Verify: p99 of `search` under 50 ms in the test, recorded in m12.md.
- [x] 6.4 Storm (D2): a reindex and a space-build flip landing while a turn searches.
  Verify: the turn's candidates all come from its starting space, and the next turn uses the new one.
- [x] 6.5 Note K5 as built in doc 10, and doc 09 M9's "same pipeline" seam.
  Verify: the docs link check passes.

## 7. Jev call 2, the keep rule and the deep graph (design D13–D15)

- [x] 7.1 Implement Jev call 2 (`ai/agent/deep.py`'s check step):
  - one `deep_check` request per candidate, started together, each read by `deepCheckMs`;
  - a 429 falls back at once;
  - the set check when K6 says;
  - K6's missing-request rules.
  Verify on the virtual clock with parked decisions:
  - all back;
  - one 429;
  - two late with none found → fallback;
  - one late with one found → found;
  - the set check yes and no.
- [x] 7.2 Implement the keep rule (`ai/agent/keep.py`): usable, found, partly, not found, fallback; k per mode; the
  ordering; and the abstain rule (D8).
  Verify: a table test over outcomes × modes, including "debate never abstains" and "not found needs every answer".
- [x] 7.3 Build the deep graph (gather → search → check → keep), with `DeepRequest` and `DeepResult` frozen and JSON
  round-trip. A bug inside gives a quick turn with a logged error and a `fallback` row.
  Verify: graph path tests; a forced exception test; a settle test on the virtual clock (50 deep turns run twice give
  identical results).
- [x] 7.4 Wire 1:1. The plan graph's `route ──deep──▶ deep` edge returns the plan with its passages. `TurnPlan` gains:
  - `knowledge`;
  - `retrieved`;
  - `query`;
  - `knowledge_outcome`;
  - `abstain`.

  `deep` is true for found, partly and fallback, and `TurnRunner` fills `TurnContext.knowledge` and `query` from the
  plan.
  Verify:
  - a deep 1:1 turn's request holds the passages;
  - not found gets the quick cap;
  - replay from JSON makes no decision, embedding or chat request before the reply.
- [x] 7.5 Add `start_deep` to the planner port. `naive` and `scripted` return None. Wire group's first reply and
  Everyone (from the cast plan) and group's second reply (from the follow plan).
  Verify:
  - group first reply's `deep_check` requests are sent before its `turn.next`;
  - the second reply's deep work starts when the follow plan lands;
  - a new message cancels both, with every request `cancelled`.
- [x] 7.6 Wire watch. The plan made ahead starts the speaker's deep work and stores it with its fingerprint; a stale
  plan cancels both.
  Verify:
  - a pause longer than the deep work → the reply request goes out with no wait after `turn.next`;
  - a director's note mid-work → both discarded, with requests `cancelled`.
- [x] 7.7 Wire debate:
  - a rebuttal, closing or panel turn starts its deep work when the member is fixed and its gate is in;
  - an opening's starts with its prefetch;
  - an Ask's starts when its cast plan lands;
  - Extend, Skip, End and `clear()` cancel it.

  Verify on the virtual clock:
  - the member deadline is unchanged;
  - Skip during a prefetched opening's checks cancels them;
  - a debate turn never rewrites or abstains.
- [x] 7.8 Storms (D2): the 8 checks and the set check cut by Stop and by a superseding message, in each wired mode.
  Verify: each storm's asserts pass.
- [x] 7.9 Note K6, K7 and the deep graph in doc 10, doc 01 A6/A7 and the plan graph's docstring.
  Verify: the docs link check passes.

## 8. The reply (design D16–D18, D20)

- [x] 8.1 Build the `agent` documents block (K8 + S6 tags), the tag stripping, the 1,400-token guard, the partly line
  and the not-found block, and place them first in the tail (P2).
  Verify:
  - the block's exact text for two passages;
  - a planted `< /PASSAGE >` is removed;
  - partly and not-found texts;
  - a deep turn and a quick turn send byte-identical system message 1, summary and history.
- [x] 8.2 Add the prompt labels `+docs-1` and `+nodocs-1` (D16) to `prompt_version_for`.
  Verify: a label test per combination (1:1, cue, steer, debate, with and without the mood line).
- [x] 8.3 Citations: the numbering, `kept_citations`, the deterministic quote window (D17), `score` = `unit` or
  absent on a fallback.
  Verify:
  - unit tests for the quote window (fact in sentence four, CJK sentences, no overlap, a first sentence over 400);
  - an invented marker stays plain text;
  - a fallback citation has no score.
- [x] 8.4 Build the trace: `knowledge` with `query`, `trigger "gated"` and the 8 `retrieved` (score, cited, n);
  `context.used.knowledge`; the System 1 rows of D20, grouped under "passages".
  Verify:
  - a deep reply's trace round-trips through the contract schema (`export-schema:check`);
  - Insight resolves passage rows to titles in a frontend test;
  - a 5-candidate group deep turn stays ≤ 64 rows.
- [x] 8.5 `naive`'s next version: the centred 1,200-character slice, labelled `naive-7` (`naive-8` for debate). The
  rest is unchanged.
  Verify:
  - a hit 4,000 characters into its section is wholly in the request;
  - `naive` requests without passages keep `naive-5` and `naive-6`.
- [x] 8.6 Remove the Knowledge tab's "Preview" ribbon, keeping the Memory tab's.
  Verify: `npm test` and the e2e Knowledge tab test pass.
- [x] 8.7 Note K8, K9 and K13 as built in doc 10, doc 03 C1 and doc 11 S6.
  Verify: the docs link check passes.

## 9. The evaluation, offline (design D22–D24, D30)

- [x] 9.1 The runner marks every paid run's folder `.keep` when it finishes (D31.4).
  Verify: a test runs a paid-shaped run on the fake and finds `.keep`; a smoke run is still pruned past 20.
- [x] 9.2 Build `evals/datasets/retrieval/`: the question format, span labels with offsets, the hash split, and the
  corpus and seed loader into a run database as each character's sources. Check spans with `corpus-check`, and
  check against the bank with `overlap`.
  Verify:
  - the builder is deterministic;
  - every span resolves to its source text;
  - `overlap` reports 0 on a fixture set.
- [x] 9.3 Implement `horizon eval retrieval`:
  - D23's metrics;
  - the 80 % coverage rule;
  - K7's leave-one-out tuning and counts;
  - the set-check report;
  - seed and corpus apart.
  Verify: `HORIZON_TEST=1 horizon eval retrieval --limit 5 --yes` completes with fixture answers, and a report test
  checks every metric on a fixture run.
- [x] 9.4 Implement the comparisons (spaces, piece target at a fixed 1,200-token budget, λ, instruction, rewrite,
  header), each in its own run database, with dev-only kept-set precision for the piece arms.
  Verify:
  - a fixture comparison run reports each arm;
  - K3's rule keeps the default on a 2-point gain.
- [x] 9.5 Add the M12 sets to `decisions`:
  - `docs` (with `t_gate` and `t_confident` by B5's rules);
  - `standalone` (`t_standalone`);
  - `english` (≥ 95 %);
  - D9's re-ask of the who-speaks and emotion items that hold gated candidates, compared with their recorded
    answers.
  Verify: report tests on fixture answers for each set.
- [x] 9.6 Add the Not-found judges (`judge_notfound_says`, `judge_notfound_cites`) as `eval_judge` entries, their B4
  validation set format, and the end-to-end run (40 unanswerable + 10 partly, 1:1, `agent`), reading "NOT COUNTED"
  until validated.
  Verify: fixture tests for the validation report and the NOT COUNTED rule.
- [x] 9.7 Implement `horizon eval latency --part deep` (D24), with the store bypassed.
  Verify: `HORIZON_TEST=1 horizon eval latency --part deep --limit 3 --yes` completes on the virtual clock and
  reports every step, the slowest check, the 429s and the fallbacks.
- [x] 9.8 Smoke runs a deep 1:1 turn and a deep group turn on canned answers.
  Verify: the smoke report shows the passages kept, the citations and the System 1 passage rows, at $0.

## 10. The labels (design D22; D31.2)

- [x] 10.1 Write the retrieval questions and span labels blind: 205 over the corpus and the seed, in D22's mix.
  Verify:
  - the builder's counts match D22;
  - every span resolves;
  - `overlap` reports 0.
- [x] 10.2 Write the `docs` set (≈ 120, ≥ 60 yes, every mode, English 100 / Malay 10 / Chinese 6 / mixed 4), the
  `standalone` set (100, 50 follow-ups) and the `english` set (40, 10 per language), labelled blind.
  Verify: the builders' counts and splits; `overlap` reports 0.
- [x] 10.3 Write the Not-found judges' 30 planted items. The 30 real items come from the first end-to-end run, in
  phase 11.
  Verify: the planted set loads and each item names its planted failure.
- [x] 10.4 The delegated review pass (D31.2): a recorded sample per set in `evals/reviews/m12-review.md`, and any set
  with two or more disagreements relabelled whole.
  Verify: the review file lists each set's sample, disagreements and outcome.

## 11. The paid runs (design D28; each asked for with its estimate, off-peak)

- [x] 11.1 Check 5: `deep_check` on 20 pieces, the set check on 5 pairs, and the two nouls on 20 messages (≈ $0.002).
  Verify: m12.md records whether the levels' probabilities and the weighted score come back as K7 expects.
- [x] 11.2 Check 4 (local, free). Propose the two PDFs' URLs and licence notes to the user, download after the OK
  (D31.3), and run `pack@2` on them and on the corpus.
  Verify: m12.md records:
  - headings carried forward;
  - tables keeping their lines and header rows;
  - a mid-sentence page break giving `pp. N–M`;
  - Chinese cut at `。`.
- [x] 11.3 `decisions` for `docs`, `standalone` and `english` (≈ $0.013). Write `t_gate`, `t_confident` and
  `t_standalone` into the bank (version bumps, `bank-lock`, seed rebuilt).
  Verify: m12.md has each threshold against B5's rule, with the test split's figures and Wilson intervals.
- [x] 11.4 D9's re-ask (≈ $0.01).
  Verify: m12.md records each affected entry's dev accuracy with and without titles, and any version bump with its
  re-chosen floor.
- [x] 11.5 Corpus embeddings for the comparison arms (≈ $0.01), then `retrieval` on dev (≈ $0.04, with 45
  rewrites) and the piece arms' kept-set precision (≈ $0.02). Choose the space, piece target, λ, instruction,
  `t_keep` and `t_found` by D23 and K7.
  Verify: m12.md has every comparison and the thresholds, with each choice and its rule.
- [x] 11.6 `retrieval` on test, once (≈ $0.02).
  Verify: m12.md has the test figures against K7 and B5's targets (≤ 3 wrong abstains in 100; ≥ 32 of 40 abstained),
  and the naming questions reported apart.
- [x] 11.7 Check 3: 10 real rewrites (≈ $0.004).
  Verify: each passes K4's output checks and stands on its own, read by hand in m12.md.
- [x] 11.8 End to end: 50 not-found and partly replies, the judges' 30 real items labelled from them, B4 validation,
  then scoring (≈ $0.03).
  Verify: m12.md has the validation and both judges' rates against ≥ 90 %.
- [ ] 11.9 Check 2: deep-turn timing (≈ $0.09).
  Verify: m12.md has each step's p50 and p90, both 1:1 arms against NFR-01, group, debate and watch against NFR-02,
  the slowest-of-8, the 429s and the fallbacks. Any deadline or trim change goes to the user as a choice (D13, D24).
- [ ] 11.10 Spend against D28: copy every run's per-item results to `docs/ai/checks/m12/`, and check them line by
  line against `data/evals/spend.jsonl`.
  Verify: m12.md's spend table matches the log.

## 12. Docs (design D29)

- [ ] 12.1 Amend everything doc 10 §6 lists:
  - doc 01: A4, A6, A7, A13, §8, §9;
  - doc 02: B1, B2, B4, B5, B7, B8, §8;
  - doc 03: C1, §7;
  - doc 05: X1, §7;
  - doc 08: §7;
  - doc 09: M9, §7;
  - `docs/backend/05-ai-seams.md` §6.

  Then add doc 10's built notes per K, and doc 13's W12 and W6 rows.
  Verify: the docs link check reports 0 broken links in `docs/ai`.
- [ ] 12.2 Finish `docs/ai/checks/m12.md`: step 0, every run, "What M12 found" and "What M13 inherits" (D27's four
  items included).
  Verify: every number in it traces to a run folder or a committed file.

## 13. The final gates

- [ ] 13.1 Run every gate:
  - the backend `pytest` in the gate worktree, `ruff`, `mypy`;
  - the frontend `lint`, `typecheck`, `npm test`, `test:http`;
  - `seed:check`, `fixtures:check`, `export-schema:check`;
  - `HORIZON_TEST=1 … smoke`;
  - `npm run e2e`;
  - `openspec validate rag --strict`.
  Verify: all green, recorded in m12.md's final gates table.
- [ ] 13.2 Tell the user M12 is ready to archive and squash into dev. Push nothing unless asked.
  Verify: the user's answer is recorded.

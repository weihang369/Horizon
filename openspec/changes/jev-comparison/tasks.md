# Tasks

> **Constraints for every task:**
> - **Tests are offline.** No network in automated tests: the socket guard stays on, and only the in-process fake
>   provider and obviously fake `sk-or-test-…` keys are used.
> - **The key stays private.** The real key is never printed, logged or put in fixtures.
> - **One variable.** Only the decision model id changes between the two sides. No prompt, bank question, state
>   builder, DeepSeek setting or judge changes (design D14). If a finding suggests one, it goes to the user as a
>   choice question.
> - **Contract.** None changes (design D19). If any contract method, wire field, event or UI entry point turns out to
>   be needed, **stop and ask the user**.
> - **The pinned records.** `evals/canary.json`, `evals/baselines/judges.json` and
>   `evals/baselines/jev-1.13-requests.json` are never rewritten by a candidate run (D4, D5). The canary is never
>   `--accept`ed during the comparison.
> - **Paid runs** need no per-run permission, but:
>   - cap = max(1.5 × estimate, $0.01);
>   - every call goes through the store (the canary and the two probes bypass it by design);
>   - `.keep` is written when the run starts;
>   - check that no old batch process is alive before arming a run;
>   - never `--allow-peak`;
>   - a run with any DeepSeek request stays off-peak (not 09:00–12:00 or 14:00–18:00 KL); Jev-only runs may run at
>     any hour once phase 3 is in (D6).
> - **Ask the user first** before any download, spawning subagents, and any product, config, threshold or deadline
>   change.
> - **Private items.** Nothing under `private/` is ever committed (`git status` before every commit). Never commit
>   `6 RAG.pdf`.
> - **Commits and pushes.** Commit at each phase's green checkpoint, without Claude attribution. Push nothing.
> - **Gate eval commands run with `HORIZON_TEST=1`.**

## 0. Baseline and the candidate's facts

- [x] 0.1 Confirm the base:
  - check `git log origin/dev -1` and the branch (`feat/jev-comparison` from dev 33a68ec);
  - take M15's final gates as the baseline (backend 2280 passed; `test_search_on_a_loaded_database_is_fast` is
    this machine's known keyword-p99 failure);
  - run `ruff` and `mypy` clean on the branch tip.

  Record the result in `docs/ai/checks/jev-comparison.md` §0.
- [x] 0.2 Verify the candidate (design D2, $0):
  - from OpenRouter's model page or list and docs.typesafe.ai: the newest Jev id and its dated snapshot, the price,
    the context and question limits, any API or answer-shape change, and whether `typesafe/jev-1.13` is still served
    and until when;
  - record each fact with its source and date in §0;
  - if anything newer than 1.14 exists, tell the user before phase 1.
- [x] 0.3 Make the conditional deltas match the verified facts: if the id or price differ from `typesafe/jev-1.14` at
  $0.042 per million, update `specs/decider/spec.md`, `specs/demo-data/spec.md` and design D2/D15. Verify with
  `openspec validate jev-comparison --strict`.

## 1. The decision-model override and the guards (D3, D4)

- [x] 1.1 Add `--decision-model ID` to `horizon eval` (`cli.py`, `Options.decision_model`):
  - the runner sets the isolated runtime's `gateway.decision_model` and `gateway.decisions.model` after `start()`;
  - an alias is refused before the plan;
  - the report shows the model asked and the model returned.

  Verify with tests: in test mode with the fake, every Jev request of a run names the override; `seed/settings.json`
  is untouched; `~typesafe/jev-latest` exits non-zero and sends nothing.
- [x] 1.2 Make the in-process fake (`gateway/fake.py`) answer the override model. Verify that the existing fake
  tests still pass and a new test asks a second model id.
- [x] 1.3 Price the candidate per D3: when its verified price differs, read a `decisionPrices` entry keyed by model
  for the estimate and the cap; otherwise nothing is added. Verify with a unit test of the estimate at two prices.
- [x] 1.4 Key the measured marks by model (D4): `<model>|<qid>` for a non-pinned model, bare keys for the pinned one.
  Verify with tests:
  - after a pinned run, a candidate run asks every item;
  - the pinned run's marks are byte-for-byte unchanged;
  - a second candidate run sends nothing.
- [x] 1.5 Guard the judges' record (D4): a candidate run prints B4 marked "candidate, information only" and never
  calls `update_record`. Verify with a test that `judges.json` is unchanged after a full candidate `--set judges` run
  on the fake.
- [x] 1.6 Update `evals/README.md` with the option and the guards. Commit phase 1 at green.

## 2. Canary baselines per model and the store's salt (D5)

- [x] 2.1 Load the baseline by model (`canary.py`):
  - `evals/canary.json` when its `model` equals the run's model, else `evals/canary/<id with "/" → "__">.json`;
  - a candidate's first complete canary run writes its baseline and reports drift against the pinned baseline as a
    finding;
  - `--accept` on a model other than `evals/canary.json`'s is refused for that file.

  Verify with tests: first run writes the candidate file; `evals/canary.json` is unchanged; a second run with one
  changed choice reports drift and leaves both files unchanged.
- [x] 2.2 Salt each Jev store key with its own model's baseline fingerprint (runner, `store_for`, gateway lookup). A
  non-canary suite on a model with no baseline refuses and names the canary step. Verify with tests: the refusal sends
  nothing; a stored candidate answer is found again after its baseline exists.
- [x] 2.3 Prove that the 1.13 keys are unchanged. Add a test that recomputes the key of every manifest body recorded
  as stored and asserts that each one still hits the store. It runs against the committed store fixtures in test
  mode, and as a one-off script over `data/cache` and `private/evals/cache`, with its result (3,684 of 3,684) recorded
  in §0.
- [x] 2.4 Update `evals/README.md` (the canary per model, never accept during a comparison) and the store
  description. Commit phase 2 at green.

## 3. The peak check per plan, and `.keep` from the start (D6, D15)

- [x] 3.1 Add `Plan.calls_chat` (default `True`). Set it to `False` for `canary`, `decisions`, `deep-check`,
  `safety` when every part is in `JEV_PARTS`, and the comparison's probes. `Runner.run` checks `overlaps_peak` only
  when `calls_chat`. Verify with tests on a frozen clock at 10:30 KL:
  - `decisions` proceeds;
  - `latency` and `safety --part honesty` refuse;
  - each Jev-only plan run in test mode leaves only `decision` ledger rows.
- [x] 3.2 Write `.keep` when a paid run's folder is created (not only at finish). Verify with a test that a paid run
  that raises mid-way leaves a `.keep` folder that `prune_runs` never deletes.
- [x] 3.3 Update the runner docstring and `evals/README.md` (peak applies to DeepSeek plans; `.keep` at start).
  Commit phase 3 at green.

## 4. `compare-models`: the runs, the probes and the report (D7–D11)

- [x] 4.1 Name the manifest by model (`jev-<version>-requests.json` from the pinned id, D11). Verify with a test:
  1.13 still gives `jev-1.13-requests.json`, and the committed file is byte-for-byte unchanged by
  `horizon eval manifest`.
- [x] 4.2 Add `horizon eval compare-models --base --new --manifest [--step …] [--report-only RUN…]` (new
  `horizon/evals/compare.py`):
  - each step is a normal `Runner` run;
  - the run ids go to `data/evals/compare-<base>-vs-<new>.json`, and a step resumes from it;
  - every set step passes `--against-manifest`.

  Verify with an integration test on the fake: the full sequence runs; a body missing from a trimmed manifest is
  named and sent on neither side; the ledgers hold only `decision` rows.
- [x] 4.3 Pair the rows and score them drop-in and re-tuned (D8): pair on (set, id, order, part); drop-in at the
  live values; re-tuned through each set's existing chooser (the D8 table), with the chosen values written before
  test is scored. Verify with unit tests:
  - the paired McNemar example from the spec (b 2, c 6);
  - a noul set's threshold is chosen from dev rows only (test rows altered → the same threshold);
  - a set with no rule repeats drop-in and says so.
- [x] 4.4 Add the behaviour figures (D9): calibration bins and ECE per noul set; flip, first-option per order and
  both-orders rates; invalid, 429 and 529 rates excluding store hits; cost per request by set; and the cost per 1:1
  reply computed from the M15 latency run's per-turn Jev tokens. Verify with unit tests on hand-made rows, including
  the spec's first-option scenario.
- [x] 4.5 Add the paired timing probe (D10):
  - bodies from the manifest's stored bodies in the buckets <1k, 1k–2.5k, 2.5k–4k (30 each) plus 5 near 10k and 5
    near 25k;
  - alternate which model goes first, store bypassed, discard 5 warm-up requests per model per window;
  - `--step timing-a|timing-b`;
  - p50, p90 and p99 with `percentile_ci`;
  - the projected deadline-miss rate per live purpose.

  Verify with tests on the fake's fixed latencies: warm-up excluded and counted; two windows reported apart.
- [x] 4.6 Add the repeat probe (D11): the canary's 20 items × 3 per model, store bypassed; report changed choices and
  the largest p and score moves beside group A's 1.13 figure. Verify with a unit test on fixed answers.
- [x] 4.7 Write the report (`report.md`, per-item `*.jsonl` with safety hashes only, `figures.json`) from saved rows
  only. `--report-only` sends nothing. Verify with a test: re-cutting two saved fake runs writes the same report with
  zero requests and $0.
- [x] 4.8 Document "Comparing a new Jev" in `evals/README.md` (D17), with each step's command as run. Verify that
  `--help` matches the doc. Commit phase 4 at green.

## 5. Offline gates

- [x] 5.1 Run the gates:
  - backend `pytest` in the gate worktree, `ruff`, `mypy`;
  - frontend typecheck, lint, test and http (unchanged expected);
  - `seed:check`, `fixtures:check`, `export-schema:check`;
  - smoke (`HORIZON_TEST=1 horizon eval smoke --limit 5 --yes`);
  - `openspec validate jev-comparison --strict`.

  Record the table in jev-comparison.md. Any failure is fixed or explained (the known search-timing test). Commit.

## 6. The paid runs (D15; all Jev)

- [x] 6.1 The parse check (D2): one known body (canary item 1) on the candidate through the Decider path, < $0.001.
  The answer validates unchanged. Record it in §0. If the shape differs, stop and put it to the user.
- [x] 6.2 Step `canary`:
  - first 1.13's canary (expect 20/20; a 1.13 drift stops the comparison and goes to the user);
  - then the candidate's first canary, which writes `evals/canary/<candidate>.json` and reports its drift against
    1.13.

  Record both.
- [x] 6.3 Step `probe`: both models' exact misses and cost per set. Recompute D15's estimates at the verified price
  and record them.
- [x] 6.4 Step `sets` on 1.13: its ≈ 1,281 misses (expect ≈ $0.05). Record the run id, spend and any refused body.
- [x] 6.5 Step `sets` on the candidate: decisions with the judges, deep-check, and safety's Jev parts (expect
  ≈ $0.20). Record the run ids and spend; resume with `--start` if the run stops.
- [x] 6.6 Step `repeat` (≈ $0.003). Record.
- [x] 6.7 *(Window A only: after keeping 1.13, the user dropped window B, 2026-10-20.)* Steps `timing-a` and `timing-b`, ≥ 3 h apart, one may be daytime (≈ $0.05). Record the windows and the
  local clocks.
- [x] 6.8 Re-run `compare-models --step probe` to confirm everything now hits (a re-run is free). Add the spend
  table against D15 to jev-comparison.md.

## 7. The report and the findings

- [x] 7.1 Step `report`; copy the per-item rows and `figures.json` to `docs/ai/checks/jev-comparison/`. Verify that
  `git status` shows no private text (safety rows as hashes).
- [x] 7.2 Write `docs/ai/checks/jev-comparison.md`:
  - §0 the facts;
  - the per-set table (drop-in, re-tuned, McNemar, by mode where available);
  - calibration, order and first-option figures; errors; cost per request and per 1:1 reply;
  - timing (both windows, projected deadline misses); repeat;
  - the judges' information table;
  - the known gaps (the retrieval suite's passage thresholds);
  - "What the comparison found", with each finding's rows.
- [x] 7.3 Append the findings to `private/launch/findings-log.md` (not committed). Keep the figures' data for a
  LinkedIn post. Commit the docs at green.

## 8. The gate: the user decides

- [x] 8.1 Put the choice to the user with the figures (D16): **switch with the re-tuned values** (one choice per moved
  knob), **switch with the drop-in values**, or **keep 1.13**. Record the decision and its date in jev-comparison.md
  and the milestone memory. Then do phase 9 or phase 10, not both.

## 9. If the user switches

> Not run: the user kept jev-1.13 (8.1, 2026-10-20).

- [ ] 9.1 Swap the canary files (D5): 1.13's to `evals/canary/typesafe__jev-1.13.json`, the candidate's to
  `evals/canary.json`. Verify with a test that both models' stored answers are still found (spec "A switch keeps the
  candidate's answers").
- [ ] 9.2 Change the pinned id and price in `seed/pricing.json`, `seed/settings.json` and
  `frontend/src/mock/pricing.config.ts`. Apply the thresholds the user picked in 8.1, each as its own bank version or
  setting with the decision noted. Verify with `seed:check` and the pricing tests.
- [ ] 9.3 Regenerate the seed sessions and ledger (`seed/sessions/ses_seedDinner/*`, `seed/usage/ledger.json`).
  Classify every other `jev-1.13` hit (`grep -r`) as "changes" or "history" per D16 and change the first group. List
  both groups in jev-comparison.md. Verify with `fixtures:check`, the frontend contract test and the full backend
  suite.
- [ ] 9.4 Update `docs/ai/01`, `docs/ai/02`, `docs/backend/05-ai-seams.md`, `docs/requirements/07-nfr-risk-cost.md`
  and `gateway/decisions.py`'s docstring with a "since <date>, see jev-comparison.md" note. Verify that the docs link
  check reports 0 broken links.
- [ ] 9.5 Rebuild the manifest for the new pinned id (`jev-<new>-requests.json`); `jev-1.13-requests.json` stays.
  Verify that the stored counts equal the candidate's answered bodies.
- [ ] 9.6 The latency run (D12): `horizon eval latency --part blended`, off-peak (it calls DeepSeek), ≈ $0.12–0.17.
  Put every 1.13-measured deadline to the user with its new measurement and the milestone's rule, and apply the
  chosen values. Record them.
- [ ] 9.7 The last step: re-run the canary on the new pinned model, with no accept unless the user has seen a drift.
  Keep the `decider` and `demo-data` deltas. Commit at green.

## 10. If the user keeps 1.13

- [x] 10.1 Delete `specs/decider/spec.md` and `specs/demo-data/spec.md` from this change. Record "kept 1.13" and why in
  jev-comparison.md. Leave the candidate's canary baseline and stored answers in place for the next comparison.
  Verify with `openspec validate jev-comparison --strict`. Commit.

## 11. Close

- [x] 11.1 Final gates: phase 5's list again on the tip, plus `npm run e2e` in the main tree if phase 9 ran. Record the
  table.
- [x] 11.2 Add the comparison's spend row to `docs/ai/13-wrap-up.md` W6 and update the milestone memory. Offer the user
  a draft of the LinkedIn post and its infographic (dropped: the user chose not to show the comparison on
  LinkedIn, 2026-10-20).
- [ ] 11.3 Ask the user about the archive and the squash into local dev (as for M7–M15). Nothing is pushed.

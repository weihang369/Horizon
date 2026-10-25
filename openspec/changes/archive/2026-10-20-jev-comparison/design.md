# Design

## Context

The motivation is in proposal.md, "Why". This section covers only what the code and the measured records already give
the comparison, and the traps they hold.

- **The manifest exists** (M15 D19, `evals/baselines/jev-1.13-requests.json`):
  - 4,965 Jev request bodies in 22 sets, hashed without the model; 3,684 have a stored 1.13 answer.
  - The 1,281 unstored bodies are:

    | Set | Unstored bodies | Why |
    |---|---|---|
    | canary | 20 | never stored |
    | judges | 30 | |
    | emotion | 260 | reversed-option asks, keyed apart since M15 D13 |
    | who_speaks | 330 | reversed-option asks |
    | reactions | 90 | reversed-option asks |
    | debate_member | 90 | reversed-option asks |
    | docs | 121 | bodies changed after their milestones |
    | earlier | 120 | bodies changed after their milestones |
    | importance | 100 | bodies changed after their milestones |
    | recall | 120 | bodies changed after their milestones |

  - `--against-manifest` already makes the gateway refuse any Jev body the manifest doesn't list
    (`gateway/pipeline.py` `decide`).
- **The eval runtime takes its decision model from `seed/settings.json` `models.decision`** (`runtime.py` builds the
  `Gateway` with it). Every Jev call goes through `Gateway.decide`, which uses `model or self.decision_model`. So
  setting the isolated runtime's `gateway.decision_model` after `start()` moves every Jev request of an eval run.
  No live code passes another model, except the Settings model probe.
- **Store keys include the model and the accepted canary's fingerprint** (`evals/store.py` `jev_key`). The runner
  reads the fingerprint from `evals/canary.json` whatever the model.
- **Three things in today's harness would break a candidate run silently:**
  1. **The "already measured" marks are not per model.** `decisions-measured.json` is keyed by question with
     `v<version>:<items hash>`. A candidate run would skip every question already measured on 1.13 and report
     "nothing to measure".
  2. **The judges' record has no model guard.** `--set judges` calls `judges.update_record`, which would overwrite
     `evals/baselines/judges.json` with the candidate's B4 figures.
  3. **`canary --accept` rewrites `evals/canary.json`.** Every stored 1.13 answer (3,684) would go stale. And if the
     candidate's answers were salted with 1.13's fingerprint, a later re-accept at the switch would stale those too,
     so they'd be paid twice.
- **The estimate always prices Jev from the base seed's `pricing.json`** (`Runner.run` loads the price table from
  `base.seed_dir`, not the run's model). The ledger records the provider's reported cost, so only the estimate and
  the cap are affected.
- **Live Jev requests are small.** In M15's latency run ledger (`data/evals/20261019T233533-latency-4096b9`), every
  purpose is under 3.7k input tokens:
  - `turn_plan` averages 2.1k (max 3.6k);
  - `deep_check` 0.7k, `guardrail` 0.6k, `reaction` 2.4k, `debate_plan` 2.5k;
  - 1.13's mean latency is 430–550 ms per purpose.
- **Each set already has its dev-chosen rules in the code:**
  - `policies` (emotion and reaction floors);
  - `who_policies` (who-speaks, the debate member, `t_end`);
  - `m12_sets` (`docs` t_gate and t_confident, `standalone`, `english`);
  - `m13_sets` (importance, memory_guard, earlier, recall, same_fact);
  - `safety_suite.recut` (leave-one-out cross-validation, from saved answers).
- **Measured 1.13 baselines to compare against:**
  - group A (latency ≈ 420 p50 / 500 p99 ms, flat across 1–18 questions; repeatability 20 × 3 with no flip and
    p ±0.06; the oversize 429);
  - M15 8.12 (call 1 p50 438 / p90 515 ms; call 2 p50 502 / p90 746 ms);
  - per-set accuracies in m9.md–m15.md.

## Goals / Non-Goals

**Goals:**
- The same bodies, on two models, are scored by the same rules. Only the model id differs between the two sides.
- 1.13's existing paid answers are reused, and every candidate answer is paid once, including through a switch.
- Both outcomes (switch or keep) are prepared, and the choice is the user's, made at a gate with the figures.
- The next Jev version costs one command and a manifest.

**Non-Goals:**
- No rewording of any prompt, bank question or state builder for the candidate. No DeepSeek change. The judges stay
  on 1.13.
- No re-measure of the layer-3 conversations or the reply-quality suites (they would need DeepSeek; replies don't
  change with Jev, and their Jev parts are covered by the sets).
- No live fallback or deadline change before the gate.
- No comparison of the retrieval suite's passage thresholds (`t_keep`, `t_found`, cut on the retrieval suite's own
  runs, which embed and aren't in the manifest). `deep-check`'s 45 bodies compare their form and direction only.
  Listed as a known gap (Risks).

## Decisions

### D1. What exists, what is new

| Need | Exists | New in this change |
|---|---|---|
| Same bodies on both sides | the manifest, `--against-manifest` | the file name follows the model (D11) |
| Ask another model | `Gateway.decide(model=)` | `--decision-model` on eval runs (D3) |
| Safe candidate runs | — | the guards (D4), per-model canary (D5) |
| Scoring and statistics | the suites' reports, `metrics.mcnemar_exact`, `wilson`, `percentile_ci` | paired rows and drop-in / re-tuned (D8) |
| Timing and repeatability | group A's scripts, M15's latency run | the paired timing probe (D10), the repeat probe (D11) |
| Run any hour | — | the peak check per plan (D6, user choice) |

### D2. Phase 0 verifies the candidate before anything is built on it

- **The candidate's facts:**
  - read OpenRouter's model page or list and docs.typesafe.ai (changelog, limits, answer shape): the newest Jev
    id and its dated snapshot, the price, the context and question limits, any API change;
  - check whether `typesafe/jev-1.13` is still served, and for how long. If a model newer than 1.14 exists, the
    comparison targets the newest, and the user is told before phase 1.
- **The parse check:** one request with a known body (canary item 1) on the candidate, through the backend's
  `Decider` path. It confirms that the answer shape parses unchanged. It costs under $0.001.
- **If the id or price differ** from `typesafe/jev-1.14` at $0.042 per million: the `decider` and `demo-data` deltas
  and this design are updated before phase 1.
- **The facts go to `docs/ai/checks/jev-comparison.md` §0**, with their sources and the date.
- *Alternative:* trusting the 2026-10-15 note that 1.14 exists. Rejected: Jev is alpha, and the id, price and shape
  can move.

### D3. `--decision-model` sets the isolated runtime's gateway model

- **How it works:** `Options.decision_model`. After `rt.start()`, the runner sets `rt.gateway.decision_model` and
  `rt.gateway.decisions.model`. An alias (`latest`) is refused before the plan, as `DecisionsClient` already refuses
  one. The report shows the model asked beside the model returned (`Result.model`).
- **Pricing:** when the candidate's verified price differs from the pinned one, the run's price table is that
  candidate's (a `decisionPrices` map in `seed/pricing.json` keyed by model, read only by the evaluation). With the
  same price, nothing is added.
- **Test mode:** the in-process fake (`gateway/fake.py`) accepts the override model, so the offline tests run the
  whole path.
- *Alternative:* `--seed-dir` pointing at a copied seed with the candidate's id. Rejected: it copies the whole seed
  per run, the estimate still reads the base seed, and nothing marks the run as a comparison for the guards in D4.

### D4. The guards on a candidate run

A run is a *candidate run* when its decision model differs from `seed/settings.json` `models.decision`. On a
candidate run:

- **The measured marks are per model.** `decisions-measured.json` keys become `<model>|<qid>` for a non-pinned
  model. The pinned model keeps its bare keys, so today's file is unchanged and still read.
- **The judges' record is never written.** `_judge_report(record=False)` prints the B4 figures marked "candidate,
  information only".
- **`canary --accept` is refused** for the pinned baseline (D5).

*Alternative:* a separate `--compare` flag that callers must remember. Rejected: the guards must hold even when
someone runs a single suite by hand with `--decision-model`.

### D5. A canary baseline per model, and the store's salt per model (the canary trap)

- **Where the baselines live:**
  - `evals/canary.json` stays the baseline of the model named in its `model` field (today `typesafe/jev-1.13`);
  - any other model's baseline is `evals/canary/<model with "/" → "__">.json`.
- **Which fingerprint salts a key:** a Jev key is salted with the fingerprint of the baseline whose `model` is the
  request's model. For 1.13 that is today's fingerprint `0a41283d…`, so all 3,684 stored keys are unchanged. A
  test recomputes every stored manifest body's key and asserts each one still hits.
- **The candidate's first canary run:**
  - it writes the candidate's baseline (`model`, `recorded`, `fingerprint`, items);
  - it reports the drift against 1.13's 20 answers (choices changed, p moves) as the comparison's first finding.
- **Later canary runs** on the candidate follow the normal rules: drift is reported, and a baseline is accepted
  only with `--accept`.
- **Order of calls:** a non-canary suite on a model with no baseline refuses ("run `canary --decision-model <id>`
  first"). Otherwise its stored answers would be salted with nothing and become unreachable once a baseline exists.
- **On a switch (D16):**
  - 1.13's file moves to `evals/canary/typesafe__jev-1.13.json`, so its answers stay reachable for the next
    comparison;
  - the candidate's file becomes `evals/canary.json`;
  - no fingerprint changes, and no paid answer goes stale.
  - As the last step, the canary is **re-run** on the new pinned model, to check that it hasn't drifted since the
    comparison. It is accepted only if the user has seen a drift.

  This replaces the prompt's "re-accept the canary as the last step": a re-accept would re-key, and so re-pay
  (≈ $0.20), every candidate answer stored during the comparison.
- *Alternatives:*
  - a report-only canary with no baseline. Rejected: the candidate's stored answers would carry 1.13's salt, so
    the switch's re-accept would stale them.
  - salting nothing for candidates. Rejected: drift on the candidate would then never invalidate its stored
    answers.

### D6. The peak check applies only to plans with chat requests (user choice, 2026-10-20)

- **The plan says whether it calls chat:** `Plan.calls_chat: bool = True` (safe default).
- **Suites that send only Jev** set it to `False`:
  - `canary`, `decisions`, `deep-check`;
  - `safety` when its parts are all in `JEV_PARTS`;
  - the comparison's timing and repeat probes.
- **The check:** `Runner.run` checks `overlaps_peak` only when `plan.calls_chat`. The refusal message stays
  "DeepSeek's peak".
- **Why:** the peak window is DeepSeek's 2× price in `seed/pricing.json` `peak`; Jev's price doesn't change by the
  hour.
- **What it allows:** a daytime window for the timing probe (D10), which also measures Jev at a different hour from
  Malaysia.
- **Unchanged:** `--allow-peak` keeps its meaning and is still never used.

### D7. `horizon eval compare-models`: one command, normal runs underneath

- **The command:**

  ```
  horizon eval compare-models --base typesafe/jev-1.13 --new <id>
      --manifest evals/baselines/jev-1.13-requests.json
      [--step canary|probe|sets|repeat|timing-a|timing-b|report] [--report-only RUN…] [--yes]
  ```

  Each step is an ordinary `Runner` run, with its own folder, estimate, cap and ledger. The command sequences them
  and records the run ids in `data/evals/compare-<base>-vs-<new>.json`, so a step can be resumed or re-run alone.
- **The steps, in order:**
  1. **`canary`:** the base model's canary (a drift check of 1.13 itself, ≈ $0.0005), then the candidate's first
     canary (D5).
  2. **`probe`:** `--probe` on every set for both models. It prints the exact misses and cost per model and
     sends nothing.
  3. **`sets`:** for each model:
     - `decisions` over every folder with the judges, with `--against-manifest`;
     - `deep-check`;
     - `safety --part input,care,output,motion,image,song`.

     The base model's side is mostly store hits. Its 1,281 misses are paid once.
  4. **`repeat`:** the repeat probe (D11).
  5. **`timing-a`, `timing-b`:** the timing probe's two windows (D10), at least 3 hours apart.
  6. **`report`:** `compare.py` reads the saved rows and writes the report (D8, D9). $0, re-runnable.
- **Safety's answers** go to `private/evals/cache/` as today. Its per-item rows carry hashes only.
- *Alternative:* one monolithic run. Rejected: a failure late in a long Jev run would lose the folder structure that
  resuming (`--start`) and pay-once rely on.

### D8. Paired rows, drop-in and re-tuned

- **Pairing:** a row is identified by (set, item id, order: declared or reversed, part for safety). The report pairs
  the base and candidate rows on that identity. An item present on only one side is listed and left out of the
  paired statistics.
- **Drop-in:** the candidate's test rows are scored by the live rules at the live values: the bank's `thresholds`,
  the runtime's floors, safety's shipped knobs. These are exactly the values 1.13 was tuned to.
- **Re-tuned:** the candidate's dev rows are passed to the set's existing chooser. The chosen values are written to
  the report before the test rows are scored, and the test rows are scored once.

| Set(s) | Live values (1.13) | Re-tune rule (existing code) |
|---|---|---|
| emotion, reactions (and the debate slice) | floors (emotion 0.2) | `policies.choose_floor` on dev |
| who_speaks, debate_member, talk_finished | who-speaks floors, `t_end` | `who_policies` choosers on dev |
| docs | t_gate 0.45, t_confident 0.8 | `m12_sets.choose_t_gate` / `choose_t_confident` (recall ≥ 0.90, precision ≥ 0.95) |
| standalone, english | 0.35, 0.5 | `choose_t_standalone`; english at its rule |
| importance, memory_guard, earlier, recall, same_fact | levels; t_keep 0.35; t_gate 0.15; t_recall 0.50 + standout; t_same 0.50 | `m13_sets` choosers (memory D40) |
| safety:input, care, output, motion, image, song | tSteer 0.7, tCare 0.3, block 0.9 / flag 0.5, the prompt nouls' thresholds | `safety_suite.recut` (leave-one-out cross-validation) |
| judges | each judge's rule | none: information only (D13) |
| deep-check | t_keep 0.9, t_found 0.5 (from the retrieval suite) | none: form and direction only |
| canary | baseline | none: drift report |

- **Statistics per set and split:**
  - correct/n and a Wilson interval for each model;
  - the discordant counts b (only 1.13 right) and c (only the candidate right), with `mcnemar_exact(b, c)`;
  - the same by mode (one_on_one, group, watch, debate) where the item carries `kind` or a mode.
- **Reading the result:** a set "moves" only when McNemar p < 0.05; otherwise the report says "no difference shown"
  and gives the smallest difference that n could show.
- *Alternative:* comparing the candidate's figures against the milestones' recorded accuracies. Rejected: different
  runs, and some bodies changed since (`docs`, `earlier`, `importance` and `recall` have no stored answer for
  today's bodies). Pairing is the only honest comparison.

### D9. Behaviour figures, from the same rows and ledgers

- **Calibration:** per noul set with labels, ten p-bins of yes-rate against mean p, and the ECE.
- **Order:**
  - the flip rate (declared ≠ reversed);
  - the first-option rate in each order: the share of answers equal to the first listed option;
  - the share that pick the first option in both orders (position-driven).
- **Errors:** invalid answers (failed validation), and 429 and 529 counts over the requests sent (from the run logs
  and ledgers). Store hits are excluded.
- **Cost:**
  - the mean cost per request, from the ledger's provider cost, by set;
  - the cost per 1:1 reply: the M15 latency run's per-turn Jev token counts (`turn_plan`, `guardrail`,
    `face_check`, `reaction`) at each model's price. It is computed, not paid.

### D10. The paired timing probe (user choice: live sizes plus a few large)

- **The bodies:** taken from the manifest's stored bodies, bucketed by their own byte-count tokens:
  - under 1k, 1k–2.5k and 2.5k–4k: 30 bodies each (where live sends: `turn_plan` sits in 1k–4k, `deep_check` and
    `guardrail` under 1k);
  - near 10k and near 25k: 5 bodies each, as a limit check. They are only there to see the large end and the
    oversize behaviour, never to set a deadline.
  - **Found in phase 4, the maintainer's choice (2026-10-20): padded top-ups.** The manifest holds only 9 distinct bodies
    over 2.5k (emotion asks; a choice's two orders hash alike), one near 10k (an 8.2k judge body) and none near 25k.
    The manifest's bodies fill each bucket first; 2.5k–4k, ~10k and ~25k are then topped up with *padded* bodies: a
    manifest body whose longest text field repeats its own lines up to the target (3.2k, 10k, 25k). Both models get
    the identical body, so it stays paired. Padded bodies are timing-only: never scored, never stored, labelled in
    every row and counted in the report. The bodies are compiled from the datasets (the manifest's hashes), not read
    from the store, and private safety items are left out.
- **The order:** each body is sent on both models back to back, alternating which model goes first. The first 5
  requests per model per window are warm-up and are discarded.
- **The windows:** two, ≥ 3 h apart. One may be daytime (D6).
  - **The maintainer's choice (2026-10-20): report now, window B later.** The report, the write-up and the gate go ahead
    on window A (20:45 KL); window B runs when convenient and is added by a $0 re-cut (`--report-only`). It can only
    change the timing table. Window A showed the hour matters more than the model (1.13 ≈ 700 ms at 20:45 KL against
    ≈ 440 ms in M15's 07:35 KL run), so window B is best taken in a morning. After the gate (1.13 kept, no LinkedIn post) the user dropped window B:
    M15's morning run already shows the hour effect.
- **The report:** p50, p90 and p99 with `percentile_ci` per model, bucket and window. Also each live purpose's
  projected deadline-miss rate: the share of its bucket above the purpose's deadline, e.g. `turn_plan` 700,
  `guardrail` 800.
- **Cost:** ≈ $0.05 for both windows and models, mostly the large bodies.

### D11. The repeat probe, and the manifest named by model

- **The repeat probe:** the canary's 20 items are group A's A1 repeatability items (`evals/canary.json` note:
  "run 1 of A1's repeatability check is the baseline"). Each model gets 20 × 3 asks, with the store bypassed. The
  report gives the share of choices changed and the largest p and score moves, beside group A's 1.13 figure
  (0 flips, ±0.06).
- **The manifest's name:** `MANIFEST_NAME` becomes `jev-<version>-requests.json`, derived from the pinned id
  (`typesafe/jev-1.13` gives `jev-1.13`). Today's file keeps its name and bytes.

### D12. Deadlines: what the comparison can say before a switch, and what is measured after one

- **Before the gate:** the timing probe gives Jev's own latency at live sizes. The report projects each deadline's
  miss rate from it (D10). That is enough for the maintainer's choice. It is not a deadline setting.
- **After a switch:** one `horizon eval latency --part blended` (M15's must-pass run, with DeepSeek, off-peak,
  ≈ $0.12–0.17, store bypassed). It re-measures the per-stage Jev times. Every 1.13-measured deadline is then put to
  the user, with the new value chosen by the rule each milestone used:
  - `turn_plan` 700, `guardrail` 800, `guardrail_prompt` 1,500;
  - `follow_plan` 400, `debate_plan` 735;
  - `deepCheckMs` 1,500, `recall.checkMs` 1,500.

  A slower Jev is accepted and the deadlines follow the measurement. No design change works around it.
- *Alternative:* running the latency suite on both models now. Rejected by the user's rule: it pays DeepSeek for
  replies that don't change, for a decision the probe already informs.

### D13. The judges stay on 1.13

- **What stays on 1.13:** every reply-quality figure in the docs and the conversations rows. Nothing in this change
  re-judges.
- **The candidate's judge figures:** the judges table in the report shows both models' B4 figures on the 2,024
  judge bodies. The candidate's column is labelled "information only, no judge is validated by it". The record
  guard (D4) enforces it.

### D14. No rewording; the findings go to the user

- **If the candidate reads a question badly** (e.g. a set's re-tuned threshold hits the grid edge, or the
  first-option rate jumps), it is recorded in "What the comparison found" with its rows, as a finding for the audit
  or v2.
- **Any fix is a choice question for the user.** The bank versions in the manifest must stay identical; any edit
  would make the gateway refuse the bodies.

### D15. The paid runs

| # | Run | Requests | Estimate |
|---|---|---|---|
| 0 | the parse check (D2) | 1 | < $0.001 |
| 1 | both canaries | 40 | ≈ $0.001 |
| 2 | probes | 0 | $0 |
| 3 | 1.13's misses (sets) | ≈ 1,261 | ≈ $0.05 |
| 4 | the candidate: decisions with the judges | ≈ 4,559 | ≈ $0.18 |
| 5 | the candidate: deep-check and safety's Jev parts | 386 | ≈ $0.02 |
| 6 | the repeat probe | 120 | ≈ $0.003 |
| 7 | the timing probe, two windows | ≈ 440 | ≈ $0.05 |
| | **total, all Jev** | | **≈ $0.30** |
| 8 | *on a switch only:* the latency run (DeepSeek, off-peak) | ≈ 400 turns | ≈ $0.12–0.17 |

- **The estimates are recomputed** from step 2's probe at the verified price. Rows 3–5 are then priced exactly.
- **The rules for every run:**
  - the cap is max(1.5 × estimate, $0.01);
  - every call goes through the store, except the canary and the two probes, which bypass it by design;
  - check that no old batch process is alive before arming a run;
  - never `--allow-peak`.
- **`.keep` from the start:** `finish_run` writes `.keep` at the end today, so a run that dies mid-way can be
  pruned. Paid runs now write `.keep` when the run folder is created. This closes M15's open item 9.
- *Alternative:* sampling the sets to save money. Rejected: the whole comparison costs about $0.30, and paired
  statistics need every item.

### D16. The gate and both outcomes

After the report, a gate task asks the user, with:
- the per-set table;
- the behaviour figures;
- the timing;
- the cost;
- the findings.

| Option | What happens |
|---|---|
| **Switch, re-tuned values** | the candidate becomes pinned. Each re-tuned threshold that moved is applied only if the user picks it (one choice per moved knob). Then the latency run (D12), and the deadlines put to the user |
| **Switch, drop-in values** | the same, with every threshold kept at 1.13's values |
| **Keep 1.13** | the `decider` and `demo-data` deltas are deleted. Only the tooling, the report and the candidate's stored answers stay |

**On a switch, these change:**
- `seed/pricing.json` (`decision.model`, prices), `seed/settings.json` (`models.decision`),
  `frontend/src/mock/pricing.config.ts`;
- `seed/sessions/ses_seedDinner/{events,messages}.json`, `seed/usage/ledger.json`: the demo shows the current
  model. They are regenerated with `seed:check` and `fixtures:check` green;
- the tests and fixtures that assert the pinned id or read it from the seed (`test_pricing.py`,
  `test_decisions_client.py`, `test_decider*.py`, `fixtures/openrouter/decisions_ok.json`, `models_ok.json`,
  `frontend/src/contract/fixtures.test.ts`, and the others found by `grep jev-1.13`). Each one is classified in the
  task and listed in jev-comparison.md;
- `backend/horizon/gateway/decisions.py`'s docstring;
- `evals/canary.json` swaps as in D5;
- the manifest is rebuilt for the new pinned id (`jev-1.14-requests.json`);
- `docs/ai/01`, `docs/ai/02`, `docs/backend/05-ai-seams.md`, `docs/requirements/07-nfr-risk-cost.md`: the
  pinned-model statements, with a "since <date>, see jev-comparison.md" note;
- the `decider` and `demo-data` deltas apply at archive.

**Stays as history:**
- `docs/ai/checks/*.md` and group A;
- the recorded store fixtures under `backend/tests/fixtures/store/` (they are recorded 1.13 answers);
- the reducer fixtures that name the id as data;
- `evals/baselines/jev-1.13-requests.json`;
- `openspec/changes/archive/`.

### D17. The runbook for the next Jev

`evals/README.md` gains "Comparing a new Jev":
1. `horizon eval manifest` on the pinned model.
2. `compare-models --base <pinned> --new <id> --manifest <file>`, step by step.
3. The gate.
4. On a switch: the D16 list and the latency run.

The next comparison pays only the new model's requests: the pinned model's answers are stored, and its canary
baseline stays reachable (D5).

### D18. Docs and the LinkedIn figures

- **`docs/ai/checks/jev-comparison.md`:**
  - §0 the facts (D2);
  - the per-set table (drop-in, re-tuned, McNemar), the behaviour figures, timing and repeat;
  - the spend against D15;
  - "What the comparison found";
  - the decision record.
- **Per-item rows:** `docs/ai/checks/jev-comparison/*.jsonl` (safety as hashes).
- **Figures for a LinkedIn post:**
  - a paired accuracy chart, a latency chart, cost per reply;
  - saved as data in `docs/ai/checks/jev-comparison/figures.json`;
  - the findings are appended to `private/launch/findings-log.md` (never committed);
  - the user is offered a draft of the post and its infographic after the decision.
- **`docs/ai/13-wrap-up.md`:** W6 gains a row for the comparison's spend.

### D19. No contract change

No API, event or frontend behaviour changes before the gate. On a switch, only the mock pricing config and the seed
data change (the model id and its price). `export-schema:check` must stay green either way.

### D20. What a comparison run does differently (found in phase 4)

- **A body the manifest doesn't list is named, not raised.** M15's gateway raised on it, which would end a whole
  suite at its first changed item. On a run with `--against-manifest` the gateway now answers it with nothing (the
  item reads unanswered), records its hash and questions, and the run goes on. The runner writes them to the run's
  `run.json` and report; the comparison report lists the items by set and id, from the datasets at $0.
- **Provider errors are counted, not fatal**, on comparison runs only: a 429, a 5xx or a timeout (after the client's
  one retry) is recorded and its item reads unanswered, so the 429 and 529 rates (D9) come from the same runs. Live
  calls and other runs raise as before. A budget stop still ends the run.
- **`decisions` asks every item on a comparison run.** Its "already measured" marks would skip the base model's
  questions measured in M9–M15, leaving nothing to pair. Against a manifest, the marks are ignored for skipping; the
  store serves every stored answer, so the base side still costs only its misses.
- **`run.json`** in each run folder: the suite, options, decision model asked, whether it was a candidate, the
  status and spend, and the refusals and errors above. The report reads it to place each run, so
  `--report-only RUN…` needs no other record.
- **Each decisions row records its own sends and cost** (`sent`, `usd`; store hits send nothing), for D9's cost per
  request by set. Deep-check and safety are priced from their runs' ledgers.
- **The paired probes are two suites** (`compare-timing`, `compare-repeat`), store-bypassed, Jev only. They ask both
  models in one run, alternating, through `Gateway.decide(model=)`.
- **M15's manifest builder listed 491 bodies wrongly** (found by the first probe, 6.3): keyed nouls and scores under
  the bare question id instead of the live key (docs, earlier, recall, importance: 461), and the pairwise judge's
  second ask with reversed options instead of swapped replies (30). The builder now mirrors `Decisions.run`, and the
  1.13 manifest was rebuilt: the same 4,965 bodies in count, **4,404 stored** (not 3,684), so 1.13's side pays
  for 541 bodies (≈ $0.035), not 1,261. The Context table above keeps M15's figures as they were recorded.
- **Pruning:** comparison runs are paid, so they are marked `.keep` from the start (D15); the probe step's runs are
  free and pruned like any other.

## Risks / Trade-offs

- **1.13 retired mid-comparison** → phase 0 checks how long it is served. The base side is 74 % stored already. If
  1.13 disappears before its 1,281 misses are paid, those sets are reported "candidate only" against the
  milestones' recorded figures, marked unpaired.
- **The candidate's API or answer shape differs** → D2's parse check stops phase 1. A shape change is a design
  update and goes to the user, not a silent adapter.
- **The stored 1.13 answers were recorded on different days** from the candidate's: a drift since recording is
  possible → step 1 runs 1.13's canary first. A 1.13 drift is reported, and the store isn't used for 1.13's side
  until the user decides.
- **McNemar on small sets (n 20–60 per split) shows only large differences** → each row states the smallest
  difference its n could show. "No difference shown" is never reported as "equal".
- **Re-tuning on the same dev rows that the drop-in reads** → drop-in reads test at fixed values; re-tune chooses on
  dev and reads test once. Neither touches test before its values are written.
- **The timing probe isn't live turns** (no concurrency, no deadline races) → the switch path's latency run (D12)
  is the real measure. The probe only informs the choice.
- **Known gap: the retrieval suite's passage thresholds** (`t_keep`, `t_found`) aren't re-tunable from the manifest
  → recorded. If the user switches, the latency run's deep turns and `deep-check`'s direction check cover them
  roughly. A re-cut needs the retrieval suite on the new model (≈ its M12 cost), offered as a choice.
- **The peak change could let a DeepSeek run slip through** if a suite wrongly declares `calls_chat=False` → the
  default is `True`. Only the four Jev-only suites set it. A test runs each Jev-only plan in test mode and asserts
  that the ledger holds only `decision` rows.
- **A candidate with a different price makes the estimates wrong** → D3's per-model price, with phase 2's probe
  priced at the verified price.

## Migration Plan

- **The 1.13 keys don't move:** the fingerprint per model leaves every stored 1.13 key unchanged, and a test proves
  it over the manifest.
- **The measured marks don't move:** the pinned model's marks keep their bare keys.
- **Rollback of a switch:** revert the D16 file list and swap the canary files back. Both models' answers stay in
  the store, so nothing is paid again.
- **Deploy:** the squash-merge into dev is the user's decision at the end. Nothing is pushed.

## Open Questions

- The exact candidate id, its dated snapshot and its price: settled by phase 0 (D2), and the two conditional deltas
  are updated if they differ.
- Whether TypeSafe publishes a retirement date for 1.13: recorded if found. It doesn't change the plan.

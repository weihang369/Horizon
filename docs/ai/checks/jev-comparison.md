# The Jev model comparison: jev-1.13 against jev-1.14

The `jev-comparison` change (`openspec/changes/jev-comparison/`, design D1–D19). One variable changes: the Jev
decision model id. DeepSeek, every prompt, every bank question, the state builders and the judges stay as they are.
Whether to switch is the user's decision (task 8.1).

## §0 The base and the candidate's facts

### 0.1 The base (2026-10-20)

- Branch `feat/jev-comparison`, cut from local dev **33a68ec** (M15 squashed); origin/dev is still 4f696ad. The
  proposal is commit 06b84a6.
- **The baseline gates are M15's final gates** (m15.md 9.3, on the same tree). Backend: 2280 passed, 2 failed;
  one failure was fixed in M15. The other, `test_search_on_a_loaded_database_is_fast`, is this machine's known
  keyword-p99 failure, 56 ms against the test's 50 ms. Frontend: 563 passed / 63 http; e2e 66 passed, 2 skipped.
- **On the branch tip:** `ruff` clean; `mypy` clean (239 files).

### 0.2 The candidate (checked 2026-10-20)

| Fact | Value | Source |
|---|---|---|
| Newest Jev | **Jev 1.14** (`jev-1.14.0`), "the newest Jev release, available from October 14, 2026" | docs.typesafe.ai/models.md |
| OpenRouter id | `typesafe/jev-1.14` (listed beside `typesafe/jev-1.13`, `typesafe/jev-router`, `~typesafe/jev-latest`) | openrouter.ai/typesafe |
| Dated snapshot | **`typesafe/jev-1.14-20261014`**, as the provider returned it (the parse check, §0.5); the docs mention none. OpenRouter's per-model page, [openrouter.ai/typesafe/jev-1.14](https://openrouter.ai/typesafe/jev-1.14), is the OpenRouter source for 1.14; a fetch on 2026-10-20 returned 404 (likely rendered in the browser only), so the facts here come from TypeSafe's docs | both |
| Price | $0.042 per million input tokens; output free; **the same as 1.13** | docs.typesafe.ai/models.md |
| Limits | 64k per request and 32k per question by default, **the same as 1.13**. 262k each only with the opt-in `TypeSafe-Danger-Zone-Long-Context` header (unused). Rate limits per organisation; over a limit → 429 | docs.typesafe.ai/models.md |
| jev-1.13 | still listed under "Current models", **no end date** | docs.typesafe.ai/models.md |
| Aliases | TypeSafe's `jev-latest` → **1.13**; `jev-preview` → **1.14**. "If you have tuned confidence thresholds against one version, send that version's ID instead of the alias." | docs.typesafe.ai/models.md |
| Newer than 1.14 | none | docs.typesafe.ai/llms.txt (only a `jev-1.13` jaggedness page; no 1.14 page yet) |
| API | new in the docs since group A: a `box` primitive and image inputs (`images.md`). Neither is used by Horizon; the decisions endpoint and the three question types are unchanged in the index. The answer shape is confirmed by the parse check (6.1) | docs.typesafe.ai/llms.txt |

- **A finding for the user:** TypeSafe's own aliases still point their default (`jev-latest`) at 1.13 and call 1.14
  `preview`. Horizon pins exact ids (NFR-14), so this changes nothing in the plan. It is context for the decision
  at 8.1.
- **0.3: the expected id and price were right** (`typesafe/jev-1.14`, $0.042 per million), so the conditional
  `decider` and `demo-data` deltas stand as written, and D3's per-model price isn't needed (same price).

### 0.4 The 1.13 keys after the per-model salt (task 2.3, $0)

With the salt now taken from each model's own canary baseline (design D5), the manifest was rebuilt in memory from
`data/cache/` and `private/evals/cache/`. **3,684 of 3,684** bodies still find their stored jev-1.13 answer, and all
22 sets list the same body hashes as the committed `jev-1.13-requests.json`. Nothing paid is lost.
  *(Superseded by §6.3: M15's builder had listed 491 bodies wrongly; rebuilt, 4,404 are stored.)*

### 0.5 The parse check (task 6.1, 2026-10-20 19:41 KL, $0.00003)

`horizon eval canary --decision-model typesafe/jev-1.14 --limit 1` (run `20261020T114123-canary-4c1658`): canary item
1 (`emotion:chr_seedAmara`, a 7-option choice) on the candidate.
- **The answer shape is unchanged:** `type`, `choice`, `probabilities` (one per option), `confidence`, with the same
  types as 1.13's. The gateway's decisions client parsed it as it parses 1.13's.
- **The dated snapshot:** the provider returned `typesafe/jev-1.14-20261014`, which matches the 2026-10-14 release.
  1.13's runs return `typesafe/jev-1.13-…` the same way.
- The answer was within tolerance of 1.13's: `neutral` both, p 0.60 against 0.62. The run was sliced, so no
  baseline was written (a guard added before this run: a `--limit` or `--start` canary never writes one).

## The decision (task 8.1, 2026-10-20): keep jev-1.13

**The user kept `typesafe/jev-1.13`.** Why, from the figures below:
- the accuracy is tied (447 vs 443 of 565, p 0.67): there is no gain to buy;
- every threshold, floor and deadline was tuned on 1.13, and the judges are validated on it; on 1.14 six judges lose
  their B4 pass, so a switch would also need a judge-model setting or a re-validation;
- 1.14 is a little slower side by side and a little less repeatable;
- a switch costs the swap tasks, a DeepSeek latency run (≈ $0.15) and every deadline put to the user again.

What stays for the next Jev (task 10.1): the tooling (`compare-models`), this report, 1.14's canary baseline
(`evals/canary/typesafe__jev-1.14.json`) and its 4,945 stored answers. The conditional `decider` and `demo-data`
deltas were deleted from the change. **The comparison is not shown on LinkedIn** (the user's call, 2026-10-20).

## The result (for the gate, task 8.1)

**In one line:** jev-1.14 is **not measurably better or worse** than jev-1.13 on Horizon's own requests. Same price,
same answer shape, same order bias and errors; a little better calibrated; a little slower at the same hour; less
steady on a few judges. Nothing in the sets moves at p < 0.05.

The full table is `jev-comparison/report.md` (re-cut from the saved rows: `horizon eval compare-models --new
typesafe/jev-1.14 --report-only`), with `figures.json` and the per-item rows (`*.jsonl`; safety by hash only).

### Accuracy (paired, English test items)

- **Pooled over every decision set, drop-in:** 1.13 **447/565**, 1.14 **443/565**; b 26 (only 1.13 right), c 22
  (only 1.14 right); McNemar p **0.67**. No difference shown.
- **No set moves**, drop-in or re-tuned. The leans, none significant (each n could show only ≥ 0.11–0.32):

  | Set | 1.13 | 1.14 | b / c | p | Lean |
  |---|---|---|---|---|---|
  | debate member | 22/31 | 19/31 | 3 / 0 | 0.25 | 1.13 |
  | memory_guard | 47/48 | 45/48 | 2 / 0 | 0.50 | 1.13 |
  | importance (exact level) | 15/27 | 13/27 | 2 / 0 | 0.50 | 1.13 |
  | who_scene | 46/75 | 45/75 | 3 / 2 | 1.00 | — |
  | talk_finished | 31/33 | 30/33 | 3 / 2 | 1.00 | — |
  | earlier (t_gate 0.15) | 21/36 | 26/36 | 5 / 10 | 0.30 | 1.14 |
  | emotion, reactions, who_first/second/next, docs, standalone, english, recall, same_fact | equal | | | 1.00 | — |
  | deep-check (direction) | 44/45 | 44/45 | 0 / 0 | 1.00 | — |
  | safety, every knob drop-in | within 2 items | | | ≥ 0.50 | — |

- **Re-tuned** (1.14's values chosen on its dev rows): no decision set improves. One safety knob reads "moves":
  `tFlag` at 0.8, 1.14 gets 54/56 against 1.13's 45/56 at the live 0.5 (p 0.012). **That is the threshold, not the
  model:** 1.13 at 0.8 also gets 54/56 (1.14 55/56). See finding F4.
- By mode (drop-in): one_on_one 97 vs 98 of 133, group 81 vs 82 of 93, watch 110 vs 109 of 153, debate 38 vs 35
  of 55 (b 3, c 0, p 0.25). Nothing moves.

### Behaviour

| | jev-1.13 | jev-1.14 |
|---|---|---|
| Order flip (770 choices asked both ways) | 0.122 | 0.121 |
| First option in both orders (position-driven) | 0.047 | 0.045 |
| Errors (429, 5xx), unanswered rows | 0, 0 of 4,145 | 0, 0 of 4,145 (4,923 requests sent) |
| Calibration ECE, lower is better | docs 0.131, memory_guard 0.142, recall 0.133, talk_finished 0.130, output_rules 0.230, standalone 0.207, earlier 0.232, same_fact 0.053 | docs 0.116, memory_guard 0.102, recall 0.106, talk_finished 0.073, output_rules 0.178, standalone 0.190, earlier **0.274**, same_fact 0.058 |
| Price | $0.042 / M input | $0.042 / M input |
| Jev cost per 1:1 reply (M15's 3,675 input tokens per turn) | $0.000154 | $0.000154 |
| Repeat (canary 20 × 3) | 0 of 20 changed; p ±0.06 (group A's figure exactly) | **1 of 20** changed; p ±0.07; score ±0.04 |
| Canary against 1.13's answers | — | 18/20 (`emotion-2` neutral → thinking; `message-18` standalone p 0.16 → 0.05) |

### Timing (window A, 2026-10-20 20:45 KL; paired, store bypassed)

| Bucket | 1.13 p50 / p90 ms | 1.14 p50 / p90 ms |
|---|---|---|
| < 1k | 672 / 719 | 719 / 828 |
| 1k–2.5k | 703 / 781 | 766 / 938 |
| 2.5k–4k | 750 / 797 | 765 / 844 |
| ~10k (5) | 859 / 906 | 859 / 860 |
| ~25k (5, padded) | 922 / 968 | 953 / 1,062 |

- **1.14 is 15–60 ms slower at p50 and up to ~150 ms at p90**, measured side by side. Both handled 25k without a 429.
- **The hour matters more than the model:** M15's latency run (07:35 KL) had 1.13 at ≈ 440 ms p50; at 20:45 KL it
  was ≈ 700 ms. So the projected deadline misses in the report (e.g. turn_plan 700 ms: 1.13 0.58, 1.14 0.77) describe
  the evening only. Window B was dropped after the gate (the user, 2026-10-20: 1.13 kept, no LinkedIn post); M15's
  morning run already shows the hour effect.

### The judges (information only, D13)

The judges stay on 1.13. On 1.14 six judges that pass B4 on 1.13 would fail it: judge_engages, judge_keeps_side
(58 → 49 of 60, **p 0.004**), judge_relationship_fit, judge_starts_new, judge_summary_unsupported, judge_voice (and
judge_answers_last / judge_breaks_rules fail on both). See finding F3.

## What the comparison found

- **F1. No accuracy reason to switch.** Pooled 447 vs 443 of 565 (p 0.67); no set moves; the leans are small and
  split (debate member, memory_guard, importance toward 1.13; earlier toward 1.14).
- **F2. 1.14 is a little slower at the same hour** (+15–60 ms p50) and a little less repeatable (1 of 20 canary
  choices flipped across 3 asks; 1.13 none). It is a little better calibrated on six of eight noul sets.
- **F3. A switch would need the judges pinned to 1.13.** Judges ask the pinned decision model; on 1.14 six lose
  their B4 pass (judge_keeps_side significantly). Switching would need an eval-only judge model setting (a new
  setting, so a choice for the user) or a re-validation of those judges.
- **F4. tFlag 0.5 looks low for both models** (output check): at 0.8 both reach 54–55/56 against 45/56 at 0.5 on
  the 56 output items, by leave-one-out. A finding for the audit or v2, not for this change (a threshold change is
  the user's choice).
- **F5. Jev's latency depends on the hour** (≈ 440 ms morning, ≈ 700 ms evening, KL) for both models; deadlines set
  from a morning run (M15) will miss more in the evening. For the audit or the E2E test stage.
- **F6. M15's manifest had 491 bodies wrong** (§6.3), and its "docs, earlier, importance, recall bodies changed"
  note was mistaken: their 1.13 answers were stored all along. Fixed in this change.
- **F7. Known gap:** the retrieval suite's passage thresholds (`t_keep`, `t_found`) weren't compared (D8); deep-check
  agrees 44/45 on direction on both models.

## Spend (all Jev)

| Run | Spent | D15 estimate |
|---|---|---|
| Parse check | $0.00003 | < $0.001 |
| Both canaries | $0.00090 | ≈ $0.001 |
| Probes (twice) | $0 | $0 |
| 1.13's misses (sets) | $0.02912 | ≈ $0.035 (recomputed) |
| 1.14's sets | $0.16380 | ≈ $0.201 (recomputed) |
| Repeat probe | $0.00268 | ≈ $0.003 |
| Timing window A | $0.02209 | ≈ $0.03 |
| **Total** | **$0.21862** | ≈ $0.30 (window B dropped) |

## §5 The offline gates (2026-10-20, on ab7d80d, phases 0–4)

| Gate | Result |
| --- | --- |
| Backend `pytest` (gate worktree) | **2314 passed**, 0 failed, 10 deselected (41 min). M15's 2280 plus this change's 34. This machine's keyword-p99 test passed this time |
| `ruff` / `mypy` | clean / clean (243 files) |
| Frontend typecheck / lint | clean / warnings only, exit 0 (unchanged: the frontend isn't touched) |
| Frontend test / http | 563 passed, 2 skipped / 63 passed |
| `seed:check` / `fixtures:check` / `export-schema:check` / `assets:check` | 153 files match / 37 files match / schema matches (56 definitions) / 82 shipped assets covered |
| Smoke (`HORIZON_TEST=1 horizon eval smoke --limit 5 --yes`) | ok (the in-process fake) |
| `openspec validate jev-comparison --strict` | valid |
| `private/`, `6 RAG.pdf` | 0 files tracked |

What phase 4 found and settled (design D10's padded top-ups, the user's choice; D20):
- the manifest has only 9 distinct bodies over 2.5k and none near 25k, so the timing probe tops up 2.5k–4k, ~10k
  and ~25k with padded bodies (timing only; ≈ $0.03 per window for both models);
- `horizon eval manifest` rebuilt from the store is **byte-identical** to the committed `jev-1.13-requests.json`;
- on a comparison run an unlisted body is named and not sent, a provider error is counted, and `decisions` asks every
  item (the store serves the stored ones);
- a test that ran the pinned model's judge set on the fake wrote `evals/baselines/judges.json`; the file was restored
  from git and the test now writes a temporary record. Through the CLI this can't happen (`decisions` refuses test
  mode).

## §6 The paid runs (all Jev)

### 6.2 The canaries (2026-10-20 19:42 KL, $0.0009)

| Run | Model returned | Result |
|---|---|---|
| `20261020T114150-canary-3e6e90` | `typesafe/jev-1.13-20260917` | **20/20** on its own baseline: no drift since the stored answers were recorded |
| `20261020T114201-canary-05be15` | `typesafe/jev-1.14-20261014` | first run, **18/20** within tolerance of 1.13's answers; written as `evals/canary/typesafe__jev-1.14.json` (fingerprint `c27e1e1e…`) |

1.14's two differences from 1.13 (the comparison's first finding):
- `emotion-2` (`emotion:chr_seedAmara`): choice **neutral → thinking**; p(neutral) 0.62 → 0.42;
- `message-18` (`standalone`): p 0.16 → 0.05 (over the 0.10 tolerance; both read "not standalone" at 0.35).

### 6.3 The probe, and a fix to M15's manifest ($0)

The first probe found **491 bodies refused on both models**: the comparison's manifest guard working as meant, on
an error in M15's manifest builder (D20):
- **461 keyed asks** (docs 121, earlier 120, recall 120, importance 100): the suite asks them under the live key
  (`docs:chr_seedMei`, …); the builder hashed them under the bare question id;
- **30 pairwise-judge asks:** the suite's second ask swaps the two replies in the state; the builder listed a reversed
  option order instead, which hashes the same as the first ask.

The builder now mirrors `Decisions.run` exactly (with a test: a decisions run against a manifest built from the same
datasets refuses nothing), and `evals/baselines/jev-1.13-requests.json` was rebuilt ($0). Still 4,965 bodies in 22
sets; **4,404 have a stored 1.13 answer, not M15's 3,684**:
- docs, earlier, importance and recall are fully stored. M15 8.14's "bodies changed after their milestones" was the
  builder's error, not a change;
- emotion 400/520 and reactions 180/180 (the builder had compiled the reversed asks with the wrong seed, so their
  order salt missed the stored key);
- unstored: the canary 20 (never stored), docs 1, and the reversed asks of who_speaks 330, debate_member 90 and
  emotion 120.

The probe on the corrected manifest (0 refused on either model):

| Model | Step | Stored | To pay | Would pay |
|---|---|---|---|---|
| typesafe/jev-1.13 | decisions | 1,994 | 541 | $0.03487 |
| typesafe/jev-1.13 | decisions --set judges | 2,024 | 0 | $0 |
| typesafe/jev-1.13 | deep-check | 45 | 0 | $0 |
| typesafe/jev-1.13 | safety (Jev parts) | 341 | 0 | $0 |
| typesafe/jev-1.14 | decisions | 0 | 2,535 | $0.11976 |
| typesafe/jev-1.14 | decisions --set judges | 0 | 2,024 | $0.06819 |
| typesafe/jev-1.14 | deep-check | 0 | 45 | $0.00129 |
| typesafe/jev-1.14 | safety (Jev parts) | 0 | 341 | $0.01163 |

D15 recomputed at the verified price ($0.042 per million, both models): the canaries $0.0009 (spent); 1.13's
misses **$0.035**; the candidate's sets **$0.201**; the repeat probe ≈ $0.003; the timing probe ≈ $0.06 (two
windows). **Total ≈ $0.30**, as planned.

### 6.4–6.5 The sets (2026-10-20 19:50–20:41 KL, $0.193)

| Run | Model | Requests sent | Spent | Errors | Refused |
|---|---|---|---|---|---|
| `20261020T115058-decisions-87bccd` | 1.13 | 541 (the rest stored) | $0.02912 | 0 | 0 |
| `20261020T115511-decisions-531247` (judges) | 1.13 | 0 (all 2,024 stored) | $0 | 0 | 0 |
| `20261020T115515-deep-check-5010de` | 1.13 | 0 (stored) | $0 | 0 | 0 |
| `20261020T115516-safety-f53e92` | 1.13 | 0 (stored) | $0 | 0 | 0 |
| `20261020T115517-decisions-f95225` | 1.14 | 2,533 | $0.10076 | 0 | 0 |
| `20261020T122058-decisions-e14ef8` (judges) | 1.14 | 2,024 | $0.05316 | 0 | 0 |
| `20261020T123958-deep-check-798eb8` | 1.14 | 45 | $0.00108 | 0 | 0 |
| `20261020T124020-safety-5019c8` | 1.14 | 341 | $0.00880 | 0 | 0 |

No 429 or 5xx in about 5,500 requests; 1.14 answered at about 0.5–0.6 s per request, one at a time.

**A guard added after these runs:** the 1.13 judges run (all stored answers) re-wrote `evals/baselines/judges.json`
with the same figures and today's date on all 32 judges. The file was restored from git, so the dates of each
judge's real validation stay. A run against a manifest now never writes the judges' record, on either model (D13).

### 6.8 The re-probe ($0)

After the runs, every request of every set step hits the store on both models: 2,535 decisions, 2,024 judges, 45
deep-check and 341 safety each, **$0 to pay**. A re-run of the comparison, or the next one's base side, costs nothing
here.

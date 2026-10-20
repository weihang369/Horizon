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

### 0.5 The parse check (task 6.1, 2026-10-20 19:41 KL, $0.00003)

`horizon eval canary --decision-model typesafe/jev-1.14 --limit 1` (run `20261020T114123-canary-4c1658`): canary item
1 (`emotion:chr_seedAmara`, a 7-option choice) on the candidate.
- **The answer shape is unchanged:** `type`, `choice`, `probabilities` (one per option), `confidence`, with the same
  types as 1.13's. The gateway's decisions client parsed it as it parses 1.13's.
- **The dated snapshot:** the provider returned `typesafe/jev-1.14-20261014`, which matches the 2026-10-14 release.
  1.13's runs return `typesafe/jev-1.13-…` the same way.
- The answer was within tolerance of 1.13's: `neutral` both, p 0.60 against 0.62. The run was sliced, so no
  baseline was written (a guard added before this run: a `--limit` or `--start` canary never writes one).

### 0.4 The 1.13 keys after the per-model salt (task 2.3, $0)

With the salt now taken from each model's own canary baseline (design D5), the manifest was rebuilt in memory from
`data/cache/` and `private/evals/cache/`. **3,684 of 3,684** bodies still find their stored jev-1.13 answer, and all
22 sets list the same body hashes as the committed `jev-1.13-requests.json`. Nothing paid is lost.

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

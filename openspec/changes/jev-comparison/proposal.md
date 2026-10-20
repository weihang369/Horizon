# Proposal

## Why

Every Jev threshold, deadline and judge validation from M7 to M15 was measured on `typesafe/jev-1.13`, which was kept
pinned for the whole AI stage on purpose. A newer Jev (expected `typesafe/jev-1.14`) is out. Before the code audit and
the test phase, Horizon needs a measured answer to one question: is the newer Jev better for Horizon's own decisions?
That means the same requests, scored the same way, with only the decision model changed. The decision to switch is
the user's. This change measures, reports, and prepares both outcomes. Jev is a 1.0-alpha model that will keep
moving, so the comparison is also built to be re-run for the next version with one command.

## What Changes

- **A decision-model override for eval runs** (`--decision-model <id>`): an eval run's isolated runtime asks Jev on
  that model instead of the pinned one. Nothing in the seed, the app or the question bank changes.
- **The comparison is safe to run against the existing records.** A run on a model other than the pinned one:
  - never writes the judges' B4 record (`evals/baselines/judges.json`);
  - never writes the decisions suite's "already measured" marks, which are keyed by model from now on;
  - never accepts or rewrites the pinned model's canary baseline.
- **Canary baselines per model.** The pinned model keeps `evals/canary.json` (its fingerprint, and so all 3,684
  stored 1.13 answers, unchanged). A new model gets its own baseline under `evals/canary/` from its first canary run,
  and that run's drift against 1.13 is reported, not accepted. The store salts each Jev entry with the fingerprint of
  the canary baseline for that entry's model, so a later switch makes no paid answer stale.
- **`horizon eval compare-models`**:
  - runs the manifest's Jev sets on the base and the new model: the canary, every `decisions` folder with the judges,
    `deep-check`, and safety's six Jev parts;
  - the base model's side comes from the store, and only the 1,281 unstored bodies are paid;
  - writes one report from the two runs' saved rows at $0, so it can be re-cut any time: per set, accuracy drop-in at
    1.13's thresholds and re-tuned on dev then read on test, with McNemar on the same items, plus calibration,
    order bias and the first-option rate;
  - adds two small probes that bypass the store:
    - a paired timing probe (both models interleaved, two windows, warm-up discarded, buckets at live request sizes
      plus a few large items);
    - a repeat probe (the canary's 20 items × 3 per model).
- **The peak check applies only to runs that call DeepSeek.** The 2× peak window is DeepSeek's price, not Jev's. A
  plan that sends only Jev requests may run at any hour. Any run with DeepSeek still refuses to overlap peak. (User
  choice, 2026-10-20.)
- **The manifest is named by model** (`jev-<model>-requests.json`). Today's `jev-1.13-requests.json` keeps its name
  and contents.
- **The switch gate.** A gate task stops and puts the figures to the user as a choice. If they switch:
  - the decision model id and price change in the seed, settings, mock pricing, seed sessions and ledger, fixtures
    and docs;
  - the thresholds and deadlines the user picks are applied;
  - one off-peak latency run with DeepSeek re-sets the deadlines;
  - the manifest is rebuilt for the new model;
  - the `decider` and `demo-data` deltas apply.

  If they keep 1.13, those two deltas are removed before archive, and only the tooling and the report remain.
- **Out of scope:** any rewording of prompts, bank questions or state builders for the new model; any change to
  DeepSeek or the judges' model. Findings of that kind are recorded for the audit or v2 and put to the user.

## Capabilities

### New Capabilities

- `model-comparison`: comparing a candidate decision model against the pinned one on Horizon's own Jev requests. It
  covers:
  - the override and its guards;
  - per-model canary baselines;
  - the `compare-models` runs and report (drop-in and re-tuned accuracy, McNemar, calibration, order bias,
    first-option rate);
  - the paired timing and repeat probes;
  - the switch gate's outputs.

### Modified Capabilities

- `evaluation-harness`:
  - `--decision-model` and `--against-manifest` join the options;
  - the peak refusal applies only to plans that call DeepSeek;
  - the decisions suite's "already measured" marks are per model;
  - the canary's baseline is per model, and accepting one for a model other than the pinned one is refused;
  - the manifest file is named by model.
- `response-store`: a Jev entry's key is salted with the fingerprint of the canary baseline for the entry's own
  model. For the pinned 1.13 that is today's fingerprint, so every existing key is unchanged.
- `decider` (**only if the user switches**): the pinned decision model becomes the new id.
- `demo-data` (**only if the user switches**): the seed's decision model and its price become the new model's.

## Impact

- **Backend:**
  - `horizon/evals/runner.py`: the Options, the peak check per plan, the override after start, the canary
    fingerprint per model;
  - `horizon/evals/suites.py`: the Canary and Decisions guards, measured marks per model;
  - `horizon/evals/canary.py`: the baseline path per model;
  - `horizon/evals/manifest.py`: the file named by model;
  - `horizon/evals/judges.py`: the record guard;
  - `horizon/evals/cli.py`: `--decision-model`, `compare-models`;
  - new `horizon/evals/compare.py`: the orchestration, the report, the timing and repeat probes;
  - `horizon/gateway/fake.py`: the test fake accepts the override model.

  The live app path, `ai/`, the gateway's behaviour and the question bank are not touched.
- **Data:**
  - `evals/canary/<model>.json`, new;
  - `evals/baselines/` (the comparison summary);
  - `data/cache/` and `private/evals/cache/` gain the new model's answers.
- **Docs:**
  - `docs/ai/checks/jev-comparison.md` and `docs/ai/checks/jev-comparison/`;
  - `evals/README.md` (the runbook);
  - `docs/ai/13-wrap-up.md` (the spend rows);
  - on a switch only: `docs/ai/01`, `docs/ai/02`, `docs/backend/05-ai-seams.md` and
    `docs/requirements/07-nfr-risk-cost.md`.
- **Seed and frontend (on a switch only):**
  - `seed/pricing.json`, `seed/settings.json`;
  - `frontend/src/mock/pricing.config.ts`;
  - `seed/sessions/ses_seedDinner/*`, `seed/usage/ledger.json`;
  - the fixtures and tests that name the id.
- **Spend:**
  - about $0.25–0.30, all Jev, computed exactly by a `--probe` before the paid runs;
  - if the user switches, add one DeepSeek latency run, about $0.12–0.17, off-peak.

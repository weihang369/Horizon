# evals/

The evaluation harness's committed data. The code is `backend/horizon/evals/`. The design is in [docs/ai/02](../docs/ai/02-evaluation-observability.md) and [docs/ai/13](../docs/ai/13-wrap-up.md) W10, and was built in M7 (OpenSpec change `ai-foundation`).

## Layout

| Path | What it holds |
|---|---|
| `canary.json` | Jev's drift canary: 20 requests and their accepted answers. Its `fingerprint` salts every stored Jev answer. Until the first accepted drift it is a byte copy of `docs/ai/checks/group-a/results/canary.json`. |
| `datasets/<set>.jsonl` | Labelled decision items: one line `{id, question_id, split, item, label, review?}`. `datasets/_smoke/` items are `smoke_only` and never reported as a measurement. |
| `smoke/<mode>.json` | One scripted conversation per mode (three user lines) for `horizon eval smoke`. |
| `transcripts/` | Frozen transcripts (B3). `scripts/` holds the user lines the four long-history ones are generated from (M8, `horizon eval transcript`). |
| `drafter/seeds.jsonl` | The `drafter` suite's 20 seeds (10 dev / 10 test, M8). |
| `summary/items.jsonl` | The `summary` suite's 40 dropped-history inputs, built by `summary/build.py` (20/20, M8). |
| `long/*.json` | The `long` suite's three scripts, built by `long/build.py` (M8). |
| `datasets/judges/` | B4's 60 validation items per judge (30 real, hand-labelled; 30 planted by code); `m9_build.py` builds M9's names-the-feeling set and the pairwise judge's 30 known-winner pairs. |
| `datasets/emotion/`, `datasets/reactions/` | M9's speaker-emotion (100) and listener-reaction (90) sets, each with its `build.py`; labelled under `reviews/m9-labels.md`. |
| `corpus/` | Public-domain US federal documents as Markdown, with `SOURCES.md` (URL, retrieval date) and `LICENSE`. |
| `seed-v0/` | The seed every eval runs on by default: `seed/` at 36b51f4, the scripted demo the sets were labelled on (v1 test stage). The shipped `seed/` is now real recordings, so gold spans and stored request bodies stay put. `pricing.json`, `settings.json` and `runtime.json` must match `seed/` (a unit test checks); `--seed-dir` points a run at another seed. |
| `baselines/` | Accepted metric baselines. Smoke never compares with them. |
| `reviews/<set>.json` | Label-review samples and the disagreements found. |

Run folders, reports and the spend log live under `data/evals/` (gitignored). The newest 20 runs are kept.

## The split rule

A split is assigned once, when an item is created: `int(sha256(id)[:8], 16) % 3 == 0` gives `test`, anything else gives `dev`. The split is stored on the line. A test compares every existing item with `git show HEAD:` and fails if a split changes. Tune prompts and thresholds on `dev` only.

## Commands

Run these from `backend/`.

| Command | Cost | What it does |
|---|---|---|
| `uv run horizon eval smoke [--limit N]` | $0 with `HORIZON_TEST=1` | Checks that bank entries compile to valid wire questions and datasets load. Runs decisions over the smoke items and one conversation per mode. CI runs it. |
| `uv run horizon eval canary [--accept] [--decision-model <id>]` | < $0.001 | Sends the 20 canary items with the store bypassed. Passes when every choice matches the asked model's own baseline, p moves ≤ 0.10 and scores move ≤ 0.15. `--accept` rewrites that model's baseline after a drift you have seen. A model's first run writes its baseline (see "The store"). |
| `uv run horizon eval decisions [--limit N]` | paid | Policy accuracy with Wilson intervals, a calibration table and order bias (both option orders). Re-runs only questions whose bank version changed. |
| `uv run horizon eval overlap` | $0 | Fails when a dataset item copies a 6-word phrase from the bank's wording. |
| `uv run horizon eval review <set>` | $0 | Prints a seeded sample of max(15, ⌈n/5⌉) items and records it in `reviews/<set>.json`. Two or more disagreements fail the set. |
| `uv run horizon eval corpus-check` | $0 | Checks the corpus: every file has a `SOURCES.md` row, no file has an outside credit, and `LICENSE` states the terms. CI runs it. |
| `uv run horizon eval capture <messageId>` | $0 | Writes the captured AI calls of one message to `data/evals/cases/` (needs `HORIZON_CAPTURE_AI_CALLS=1` when the message ran). |
| `uv run horizon stats [--days N]` | $0 | Shows live latency, cost by purpose, cache hits, Jev's share, late and fallback rates. It opens the database read-only. |
| `uv run horizon eval bank-lock` | $0 | Records the bank's versions after you bump an edited question. |
| `uv run horizon eval drafter` / `summary` | paid (≈ $0.025 / $0.06) | M8's drafter and summariser suites; judged figures say "unvalidated" until the judge passes. |
| `uv run horizon eval long --profile agent [--set <script>]` | paid (≈ $0.12) | Rare: recall, voice drift, the real cache-hit %, summary calls. |
| `uv run horizon eval transcript [--set <script>]` | paid (≈ $0.06) | Generates the long-history frozen transcripts with `naive`. |
| `uv run horizon eval decisions --set judges` | paid (≈ $0.03) | B4's judge validation. |
| `uv run horizon eval decisions --set emotion` / `--set reactions` | paid | M9: the emotion and reaction policies, scored by the live code rule; the floor is chosen on dev, the test split is read once. |
| `uv run horizon eval moodline [--limit N]` | paid, once | M9: the mood line on vs off over up to 100 non-neutral transcript turns; E8's verdict is advice and changes nothing. |
| `uv run horizon eval latency --profile agent [--limit N]` | paid | M9: `agent` 1:1 time to the face and the first word (p50, p90), Stop at the first word, the store bypassed. |
| `uv run horizon eval transcript --short` | paid (≈ $0.02) | M15: generates the 7 short frozen transcripts (1:1 and group) with `naive`, from `transcripts/scripts/short_*.json`. |
| `uv run horizon eval conversations --profile agent\|naive [--set <id>] [--limit N] [--start S] [--part units]` | paid (≈ $0.30–0.40, both profiles) | M15 layer 3: both profiles reply from the same rebuilt frozen histories, judged turn by turn; the pairwise agent-vs-naive figure with a bootstrap interval and a sign test; plus the free runs. Judges whose version is not validated read NOT COUNTED. `--limit` is per mode and also shortens the live free runs, so slice with `--part units` (the compared units only, no free runs; each finished unit replays free from the store). |
| `uv run horizon eval faithfulness --profile agent` | paid (≈ $0.01) | M15: is each factual sentence of a deep reply supported by its passages, on the 10 two-passage questions. |
| `uv run horizon eval debate --profile naive` / `memory --profile naive [--part rewrite\|layer3]` | paid (≈ $0.06–0.10) | M15: the `naive` arms beside the stored `agent` columns. |
| `uv run horizon eval latency --profile agent --part blended --arm rate=R` | paid (≈ $0.17) | M15: the must-pass latency run (doc 02 B8): quick, deep, group, debate and watch, warm-up turns left out, the stage breakdown, and the blend at the deep rate R fixed before the run. |
| `uv run horizon eval <suite> --probe` | $0 | M15: runs the suite on stored answers only, with a dummy key and a transport that refuses every request. A miss sends nothing and is priced from the gateway's estimate, so the report says what a real run would pay. Suites that write committed files are refused. |
| `uv run horizon eval all` | $0 | M15: the probe over every suite under `agent` and `naive`, a table per suite: hits, would-pay, the estimate. It never sends. |
| `uv run horizon eval manifest` | $0 | M15: writes `evals/baselines/jev-<version>-requests.json` (named after the pinned model, e.g. `jev-1.13-requests.json`), the hash of every Jev request body the evaluation asks, and whether its answer on that model is stored. |
| `uv run horizon eval <suite> --against-manifest <file>` | paid | The Jev model comparison: the gateway sends no Jev body the manifest doesn't list (the item reads unanswered and its hash is named in the run's `run.json` and report), so only the model changes. On such a run a provider error (429, 5xx, timeout) is counted and the run goes on, and `decisions` asks every item whatever its "already measured" marks say (the store serves the stored ones). |
| `uv run horizon eval compare-models --new <id> [--step S] [--report-only [RUN…]] [--yes]` | paid, ≈ $0.30 all Jev | jev-comparison: the candidate Jev against the pinned one, step by step. See "Comparing a new Jev" below. |
| `uv run horizon eval <suite> --decision-model <id>` | paid | jev-comparison: every Jev request of the run asks `<id>` instead of the seed's pinned model, in the run's isolated copy only (an alias is refused). A *candidate* run (any model but the pinned one) never writes the pinned model's records: the judges' B4 record (its figures are printed "information only"), the decisions suite's "already measured" marks (a candidate keeps its own, keyed `<model>\|<question>`), and the canary baseline. The estimate uses the candidate's price from `pricing.json` `decisionPrices` when one is listed, else the pinned price. |

Every paid run follows the same steps:

1. It prints the plan and estimate, plus today's eval spend.
2. If its plan sends any DeepSeek (chat) request, it refuses to overlap DeepSeek's peak hours unless you pass
   `--allow-peak`. A plan of Jev requests only runs at any hour, because the peak price is DeepSeek's alone: the
   canary, `decisions`, `deep-check`, and `safety` when every part is a Jev part (`input`, `care`, `output`, `motion`,
   `image`, `song`). A suite that doesn't say is treated as calling DeepSeek (jev-comparison D6).
3. It asks `y/N`. `--yes` skips the prompt.
4. It runs in an isolated copy under `data/evals/<run-id>/<profile>/`. Your own database is never opened. A paid
   run's folder gets `.keep` as soon as it is created, so a run that stops mid-way is never pruned with the newest-20
   rule.
5. It stops itself at `--max-usd`, which defaults to 1.5 × the estimate. A budget stop ends the run `incomplete`, never with a wrong answer.

## The store

Paid answers are saved in `data/cache/<sha256>.json` and reused ("pay once"). The key is the hash of the canonical request: model, provider, parameters and body, plus the canary fingerprint for Jev entries.

- A hit sends nothing and writes no ledger row. Reports count hits.
- Only `horizon eval` runs read chat and Jev answers from the store.
- The live app stores only seed embeddings: seed knowledge and seed memories.
- These never read or write the store: the canary, latency and repeatability runs, `capture`, `import`, and private items.
- Accepting a new canary baseline changes the fingerprint, so every stored Jev answer of that model becomes stale at once.
- jev-comparison: each Jev model has its own canary baseline, and its stored answers are salted with that baseline's
  fingerprint. The pinned model's is `canary.json` (the one whose `model` it names), so every key stored before the
  comparison is unchanged. Any other model's is `canary/<id with "/" → "__">.json`, written by its first full canary
  run (`canary --decision-model <id>`), which reports its drift against the pinned answers as a finding. Every other
  suite on that model refuses until it exists. **Never `--accept` during a comparison**: accepting re-keys the model's
  stored answers, so they'd be paid again. A switch swaps the two files instead (design D5).
- A factory reset deletes `data/cache/`.

## Comparing a new Jev

The runbook for the next Jev version (OpenSpec change `jev-comparison`, design D7–D11, D17). Only the decision model
changes: DeepSeek, every prompt, every bank question, the state builders and the judges stay as they are. Every step
is Jev only, so it runs at any hour. Whether to switch is the user's decision, made after the report. Run these from
`backend/`, with the candidate's pinned id (never an alias) in place of `<id>`.

1. **The manifest of the pinned model.** `uv run horizon eval manifest` writes
   `evals/baselines/jev-<version>-requests.json` ($0). Commit it before the comparison starts: its bodies are what both
   models get.
2. **Check the candidate first** ($0): its id, price, limits and answer shape from OpenRouter and docs.typesafe.ai.
   If its price differs from the pinned one, add it to `seed/pricing.json` under `data.decisionPrices["<id>"]`
   (`inputPerM`) so the estimates and caps use it.
3. **The steps**, one at a time (`--yes` skips each run's prompt; each run's cap is max(1.5 × estimate, $0.01)):

   | Step | Command | What it does |
   |---|---|---|
   | canary | `uv run horizon eval compare-models --new <id> --step canary` | the pinned model's canary (a drift stops the comparison and goes to the user), then the candidate's first canary, which writes `evals/canary/<id with "/" → "__">.json` and reports its drift against the pinned answers |
   | probe | `… --step probe` | both models' exact misses and cost per set, from the store; sends nothing |
   | sets | `… --step sets` | on each model, against the manifest: `decisions`, `decisions --set judges`, `deep-check`, `safety --part input,care,output,motion,image,song`. The pinned side is mostly stored answers |
   | repeat | `… --step repeat` | the canary's 20 items × 3 on each model, store bypassed |
   | timing-a, timing-b | `… --step timing-a`, then `… --step timing-b` ≥ 3 h later | the paired timing probe: 30 bodies each under 1k, 1k–2.5k and 2.5k–4k, 5 near 10k and 5 near 25k (topped up with padded bodies where the manifest runs short), 5 warm-up requests per model excluded |
   | report | `… --step report` | from the saved rows only ($0): `data/evals/compare-<base>-vs-<new>/report.md`, `figures.json` and `rows/*.jsonl` (safety items by hash only) |

   Without `--step`, every step not yet done runs in order, stopping where one can't run yet (the second timing
   window). A step whose runs finished is skipped; an unfinished run re-runs, and the store serves every answer it
   already paid for. The run ids are kept in `data/evals/compare-<base>-vs-<new>.json`.
   `… --report-only` re-writes the report from those runs; `… --report-only RUN…` from the runs named.
4. **The gate.** The report gives each set drop-in (every rule at its live value) and re-tuned (the candidate's value
   chosen on dev by the set's own rule, read on test once), with McNemar on the same items; the order, calibration,
   error and cost figures; the timing with each live purpose's projected deadline misses; and the repeat. The user
   chooses: switch with the re-tuned values (one choice per moved knob), switch with the drop-in values, or keep the
   pinned model. **Never `canary --accept` during a comparison.**
5. **On a switch** (design D16): swap the canary files (the old pinned one to `evals/canary/<old id>.json`, the
   candidate's to `evals/canary.json`), change the id and price in `seed/pricing.json`, `seed/settings.json` and
   `frontend/src/mock/pricing.config.ts`, regenerate the seed sessions and ledger, rebuild the manifest for the new
   pinned id, then the must-pass latency run off-peak (it calls DeepSeek) and every deadline put to the user. No paid
   answer goes stale: each model's answers stay salted with its own baseline's fingerprint.

The next comparison pays only the new model's requests: the pinned model's answers are stored, and its canary
baseline stays reachable.

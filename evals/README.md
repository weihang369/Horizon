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
| `uv run horizon eval manifest` | $0 | M15: writes `evals/baselines/jev-1.13-requests.json`, the hash of every Jev request body the evaluation asks, and whether its jev-1.13 answer is stored. |
| `uv run horizon eval <suite> --against-manifest <file>` | paid | The Jev model comparison: the gateway refuses any Jev request whose body the manifest doesn't list, so only the model changes. |
| `uv run horizon eval <suite> --decision-model <id>` | paid | jev-comparison: every Jev request of the run asks `<id>` instead of the seed's pinned model, in the run's isolated copy only (an alias is refused). A *candidate* run (any model but the pinned one) never writes the pinned model's records: the judges' B4 record (its figures are printed "information only"), the decisions suite's "already measured" marks (a candidate keeps its own, keyed `<model>\|<question>`), and the canary baseline. The estimate uses the candidate's price from `pricing.json` `decisionPrices` when one is listed, else the pinned price. |

Every paid run follows the same steps:

1. It prints the plan and estimate, plus today's eval spend.
2. It refuses to overlap DeepSeek's peak hours unless you pass `--allow-peak`.
3. It asks `y/N`. `--yes` skips the prompt.
4. It runs in an isolated copy under `data/evals/<run-id>/<profile>/`. Your own database is never opened.
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

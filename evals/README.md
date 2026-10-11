# evals/

The evaluation harness's committed data. The code is `backend/horizon/evals/`. The design is in [docs/ai/02](../docs/ai/02-evaluation-observability.md) and [docs/ai/13](../docs/ai/13-wrap-up.md) W10, and was built in M7 (OpenSpec change `ai-foundation`).

## Layout

| Path | What it holds |
|---|---|
| `canary.json` | Jev's drift canary: 20 requests and their accepted answers. Its `fingerprint` salts every stored Jev answer. Until the first accepted drift it is a byte copy of `docs/ai/checks/group-a/results/canary.json`. |
| `datasets/<set>.jsonl` | Labelled decision items: one line `{id, question_id, split, item, label, review?}`. `datasets/_smoke/` items are `smoke_only` and never reported as a measurement. |
| `smoke/<mode>.json` | One scripted conversation per mode (three user lines) for `horizon eval smoke`. |
| `transcripts/` | Multi-turn conversations for later suites (M9+). |
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
| `uv run horizon eval canary [--accept]` | < $0.001 | Sends the 20 canary items with the store bypassed. Passes when every choice matches, p moves ≤ 0.10 and scores move ≤ 0.15. `--accept` rewrites the baseline after a drift you have seen. |
| `uv run horizon eval decisions [--limit N]` | paid | Policy accuracy with Wilson intervals, a calibration table and order bias (both option orders). Re-runs only questions whose bank version changed. |
| `uv run horizon eval overlap` | $0 | Fails when a dataset item copies a 6-word phrase from the bank's wording. |
| `uv run horizon eval review <set>` | $0 | Prints a seeded sample of max(15, ⌈n/5⌉) items and records it in `reviews/<set>.json`. Two or more disagreements fail the set. |
| `uv run horizon eval corpus-check` | $0 | Checks the corpus: every file has a `SOURCES.md` row, no file has an outside credit, and `LICENSE` states the terms. CI runs it. |
| `uv run horizon eval capture <messageId>` | $0 | Writes the captured AI calls of one message to `data/evals/cases/` (needs `HORIZON_CAPTURE_AI_CALLS=1` when the message ran). |
| `uv run horizon stats [--days N]` | $0 | Shows live latency, cost by purpose, cache hits, Jev's share, late and fallback rates. It opens the database read-only. |
| `uv run horizon eval bank-lock` | $0 | Records the bank's versions after you bump an edited question. |

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
- Accepting a new canary baseline changes the fingerprint, so every stored Jev answer becomes stale at once.
- A factory reset deletes `data/cache/`.

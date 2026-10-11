## Purpose

The evaluation harness measures Horizon's AI with `horizon eval`: it runs suites in isolated copies of the demo data, asks before spending, cannot overspend, and records results against committed baselines and datasets that follow the evaluation's data rules.

## ADDED Requirements

### Requirement: Suites and options
`horizon eval <suite>` SHALL accept the suites `canary`, `decisions` and `smoke`, and the options `--profile`, `--limit N`, `--max-usd`, `--yes` and `--allow-peak`. An unknown suite SHALL exit non-zero and list the known ones.

#### Scenario: Unknown suite
- **WHEN** `horizon eval conversations` is run
- **THEN** it exits non-zero, and the message lists `canary`, `decisions` and `smoke`

### Requirement: Estimate and ask before spending
A paid run SHALL print what will run, the number of calls, the expected time, the cost estimate and today's evaluation spend, then wait for confirmation, unless `--yes` is given. A run that would overlap peak hours SHALL refuse unless `--allow-peak` is given. A paid suite SHALL refuse to run in test mode.

#### Scenario: Declined
- **WHEN** a paid canary run is started and the user answers `n`
- **THEN** no request is sent, and no run folder is kept

### Requirement: Isolated copies per profile
Each run SHALL use a fresh copy of the seed data per profile under `data/evals/<run-id>/<profile>/`, and never the user's own data. In it:
- the profile SHALL be exactly the one requested;
- `HORIZON_AI_*`, `HORIZON_TEST` and `HORIZON_DATA_DIR` from the environment and `.env` SHALL be ignored;
- the key SHALL be read from the user's key store and never written to disk;
- the daily cap SHALL equal the run's limit, and energy SHALL be raised so no character falls asleep.

#### Scenario: User data untouched
- **WHEN** a smoke run completes
- **THEN** the user's database has no new session, message or ledger row

#### Scenario: Resolved ports reported
- **WHEN** a run with `--profile agent` completes
- **THEN** its report lists each port's resolved implementation

### Requirement: A run cannot overspend
A run SHALL stop itself when its own spend reaches `--max-usd` (default: the estimate × 1.5). A budget refusal SHALL abort the run and mark it incomplete, never count as a wrong answer.

#### Scenario: Cap reached
- **WHEN** a run's spend reaches its limit mid-run
- **THEN** the run stops, and its report says `incomplete` with the spend so far

### Requirement: Reports, spend log and baselines
Each run SHALL write `report.md` and `results.jsonl` to its folder and append its spend to `data/evals/spend.jsonl`. The newest 20 run folders SHALL be kept. An accepted run's summary SHALL be saved in `evals/baselines/<suite>.json`.

#### Scenario: Pruning
- **WHEN** a 21st run completes
- **THEN** the oldest run folder is deleted, and `spend.jsonl` still lists every run

### Requirement: The drift canary
The canary SHALL send the 20 committed canary items to Jev, never served from the store. It SHALL pass when:
- every choice equals the accepted baseline;
- every probability moves by at most 0.10;
- every raw score moves by at most 0.15.

It SHALL record the exact model ID returned. The baseline's fingerprint SHALL be verified against its answers when loaded. A new baseline SHALL be accepted only on explicit request.

#### Scenario: Drift detected
- **WHEN** one canary choice differs from the baseline
- **THEN** the run reports drift, names the item, and the baseline is unchanged

#### Scenario: Edited baseline
- **WHEN** the baseline's answers were edited by hand without updating its fingerprint
- **THEN** the harness refuses to load it

### Requirement: Decision suite
The `decisions` suite SHALL build every item's request from the question bank exactly as live, with the live deadline off. It SHALL report policy accuracy (Jev above the floor, the fallback below), a calibration table and, for choices, order bias measured in both option orders, each with its sample size and a Wilson interval. It SHALL re-run only questions whose version changed since the baseline.

#### Scenario: Unchanged version
- **WHEN** `decisions` runs twice with no bank change
- **THEN** the second run sends no request

### Requirement: Smoke runs in test mode
`horizon eval smoke` SHALL run in test mode at no cost, on the fake provider and the virtual clock. It SHALL check that:
- every request built from the bank passes the wire schema;
- every dataset loads;
- one scripted conversation per mode completes;
- the report renders.

It SHALL never compare with the baselines.

#### Scenario: CI smoke
- **WHEN** `HORIZON_TEST=1 horizon eval smoke --limit 5 --yes` runs with no key and no network
- **THEN** it exits zero, and no socket is opened

### Requirement: Usage statistics from the user's own data
`horizon stats [--days N]` SHALL read the user's database without changing it, and print:
- the time to the face and to the first word, at p50 and p90 per mode;
- the cost per turn by purpose;
- the cache-hit percentage, Jev's share of spend and Jev's latency;
- the late rate per decision purpose;
- the per-question fallback and timeout rates.

It SHALL leave out seed rows, prefetched turns and replays, and make no network call.

#### Scenario: Empty database
- **WHEN** `horizon stats` runs on a fresh install
- **THEN** it prints that there is no live data yet, and exits zero

### Requirement: Dataset splits are fixed at creation
Every layer-1 and layer-2 item SHALL carry a `dev` or `test` split, assigned once when the item is created (about one third `test`). An existing item's split SHALL never change.

#### Scenario: Split changed
- **WHEN** a dataset line's split is edited from `test` to `dev`
- **THEN** the dataset check fails and names the item

### Requirement: No overlap between the bank and the datasets
A check SHALL fail when any six-word run of a bank entry's option descriptions or examples appears in an evaluation item, after case and punctuation are normalised.

#### Scenario: Copied example
- **WHEN** a dataset item contains a bank example sentence verbatim
- **THEN** the overlap check fails and names both

### Requirement: The corpus is public domain
Every corpus document SHALL be listed in `evals/corpus/SOURCES.md` with its URL and retrieval date. It SHALL contain no copyright mark, permission notice, or contractor or partner credit. `evals/corpus/LICENSE` SHALL state that the files are US federal government works, public domain in the US, and not covered by the repository's licence.

#### Scenario: Copyright mark
- **WHEN** a corpus file contains "© 2019"
- **THEN** the corpus check fails and names the file

### Requirement: Label review sampling
`horizon eval review <set>` SHALL draw a seeded random sample of max(15, one in five) items, and record the sample and seed in `evals/reviews/<set>.json`. A set with two or more recorded disagreements SHALL be reported as needing relabelling.

#### Scenario: Two disagreements
- **WHEN** a review file records two disagreements
- **THEN** the dataset check reports that set as needing relabelling

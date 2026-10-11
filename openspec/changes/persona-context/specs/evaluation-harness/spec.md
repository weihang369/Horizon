# Spec Delta

## MODIFIED Requirements

### Requirement: Suites and options
`horizon eval <suite>` SHALL accept the suites `canary`, `decisions`, `smoke`, `drafter`, `summary`, `long` and `transcript`, and the options `--profile`, `--limit N`, `--start N`, `--set NAME`, `--max-usd`, `--yes` and `--allow-peak`. An unknown suite SHALL exit non-zero and list the known ones.

#### Scenario: Unknown suite
- **WHEN** `horizon eval conversations` is run
- **THEN** it exits non-zero, and the message lists `canary`, `decisions`, `smoke`, `drafter`, `summary`, `long` and `transcript`

### Requirement: Decision suite
The `decisions` suite SHALL build every item's request from the question bank exactly as live, with the live deadline off. It SHALL report policy accuracy (Jev above the floor, the fallback below), a calibration table and, for choices, order bias measured in both option orders, each with its sample size and a Wilson interval. A noul item SHALL be asked once and scored as `yes` when its p reaches the entry's threshold. It SHALL re-run only questions whose version changed since the baseline. `--set NAME` SHALL limit it to one dataset folder.

#### Scenario: Unchanged version
- **WHEN** `decisions` runs twice with no bank change
- **THEN** the second run sends no request

#### Scenario: Noul item
- **WHEN** a noul item labelled `yes` is answered with p 0.72 and the entry's threshold is 0.5
- **THEN** it is scored correct, from one request

### Requirement: Smoke runs in test mode
`horizon eval smoke` SHALL run in test mode at no cost, on the fake provider and the virtual clock. It SHALL check that:
- every request built from the bank passes the wire schema;
- every dataset, suite input file and transcript loads;
- one scripted conversation per mode completes, with the reply checks computed;
- one drafter seed, one summary item and the first lines of each long script run through their suites;
- the report renders.

It SHALL never compare with the baselines.

#### Scenario: CI smoke
- **WHEN** `HORIZON_TEST=1 horizon eval smoke --limit 5 --yes` runs with no key and no network
- **THEN** it exits zero, and no socket is opened

## ADDED Requirements

### Requirement: Judges are validated before they count
Each judge question SHALL have 60 validation items: 30 real outputs labelled by hand, and 30 failures planted by code. A judge SHALL pass when it is at least 85 % right on the real items, beats the always-the-commonest-answer baseline, and catches at least 90 % of the planted failures. The result SHALL be recorded per question and version. Any figure from a judge whose current version has not passed SHALL be reported as "unvalidated", never as a measurement.

#### Scenario: Unvalidated judge
- **WHEN** the summary suite runs before `judge_summary_fact`'s current version has passed validation
- **THEN** the report shows the fact-kept rate marked "unvalidated", and does not mark the target met

#### Scenario: Reworded judge
- **WHEN** a judge that passed is reworded and its version goes up
- **THEN** its figures are "unvalidated" again until it passes again

### Requirement: Drafter suite
The `drafter` suite SHALL draft 20 committed seeds (three intents, both worlds; 10 dev, 10 test) with each seed's world, and report:
- schema validity and adult age;
- 2–3 example lines;
- no `*` actions in the greeting or example lines;
- names outside the stock list and the world;
- the two draft judges.

#### Scenario: Stock name
- **WHEN** a draft's name is "Elara Voss"
- **THEN** that draft fails the name check, and the report counts it

### Requirement: Summary suite
The `summary` suite SHALL summarise 40 committed dropped-history inputs (English, Malay, Chinese and mixed; 20 dev, 20 test), each with 3 planted facts and 1 promise. It SHALL report:
- the 600-token cap and empty outputs;
- each planted fact kept, the promise kept, and its maker named (target ≥ 90 % each);
- the language and unsupported-claim checks (at most 1 failure in 20, every failure printed for reading).

#### Scenario: Failures are printed
- **WHEN** one test summary states something its lines don't support
- **THEN** the report prints that summary, its lines and the judge's p

### Requirement: Long suite
The `long` suite (`agent` only, rare, not part of `all`) SHALL run three scripted conversations (1:1 English, 1:1 Malay, group) to two drops plus 20 turns, with facts planted in turns 3–10 and 5 probes in the last 20. It SHALL report recall with its interval, the voice-drift signal, the provider cache-hit % on turns that are neither a session's first nor a drop, summary calls and cost per 100 turns, the reply checks and the repetition rates.

#### Scenario: Cache-hit % ignores store hits
- **WHEN** a long run is repeated and every reply is served from the response store
- **THEN** the report shows no cache-hit % for the repeat, rather than a figure from the earlier run

### Requirement: Reply-rule checks
Code checks SHALL run on every evaluated reply at no cost and report:
- the action rate;
- stray tags or name prefixes;
- replies over the mode's bubble target;
- more than one emoji;
- the question-ending rate;
- the card's step-2 rate;
- on free-running conversations only, the repeated-opener rate and the catchphrase rate.

#### Scenario: Repeated opener
- **WHEN** a speaker's reply starts with the same three words as one of their previous three replies
- **THEN** it counts toward the repeated-opener rate

### Requirement: Long-history frozen transcripts
`horizon eval transcript <script>` SHALL generate a frozen transcript by driving `naive` with scripted user lines, recording each turn's replies and the summary in force, and write it under `evals/transcripts/`. Four committed transcripts (1:1 × 2, group × 2) SHALL start from a history past one drop. The loader SHALL reject a transcript marked long whose history never dropped.

#### Scenario: Loader check
- **WHEN** a transcript marked long has no turn with a summary
- **THEN** loading it fails and names the transcript

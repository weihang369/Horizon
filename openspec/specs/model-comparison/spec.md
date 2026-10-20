# model-comparison Specification

## Purpose
Compares a candidate decision model against the pinned one on Horizon's own Jev requests, with only the model
changed, so a switch is decided on measured accuracy, timing, cost and stability, and can be repeated for every new
Jev version.

## Requirements

### Requirement: An eval run can ask another decision model
`horizon eval <suite> --decision-model <id>` SHALL send every Jev request of that run to `<id>` instead of the pinned
decision model, in the run's isolated copy only. The id SHALL be refused when it is an alias (it contains `latest`).
The seed, the app's settings and the question bank SHALL be unchanged by the run. The run's report SHALL name the
model asked and the model id the provider returned.

#### Scenario: Override in an isolated run
- **WHEN** `horizon eval decisions --set english --decision-model typesafe/jev-1.14` runs
- **THEN** every Jev request of the run names `typesafe/jev-1.14`, `seed/settings.json` still names the pinned model, and the report shows both the requested and the returned model id

#### Scenario: Alias refused
- **WHEN** a run is started with `--decision-model ~typesafe/jev-latest`
- **THEN** it exits non-zero before any request, and nothing is spent

### Requirement: A run on another model leaves the pinned records alone
A run whose decision model is not the pinned one SHALL NOT write the judges' validation record, SHALL NOT write the
pinned model's "already measured" marks, and SHALL NOT accept or rewrite the pinned model's canary baseline.

#### Scenario: Judges on the candidate
- **WHEN** `decisions --set judges --decision-model typesafe/jev-1.14` completes with every judge item asked
- **THEN** the report shows each judge's B4 figures for the candidate, and `evals/baselines/judges.json` is byte-for-byte unchanged

#### Scenario: Accept refused on the pinned baseline
- **WHEN** `canary --accept --decision-model typesafe/jev-1.14` is run
- **THEN** `evals/canary.json` is unchanged

### Requirement: A candidate gets its own canary baseline first
A candidate model SHALL have its own canary baseline, written from its first complete canary run, before any other of
its requests is stored. That first run SHALL report its drift against the pinned model's baseline as a finding, not a
failure. Any other suite on a candidate with no baseline SHALL refuse before sending anything.

#### Scenario: First canary on the candidate
- **WHEN** the canary runs on `typesafe/jev-1.14` for the first time and 6 items differ from 1.13's baseline
- **THEN** the report lists the 6 items' drift against 1.13, the candidate's baseline is written with its own fingerprint, and 1.13's baseline is unchanged

#### Scenario: Suite before the canary
- **WHEN** `decisions --decision-model typesafe/jev-1.14` is run before any canary run on that model
- **THEN** it refuses, names the canary as the first step, and sends nothing

#### Scenario: Later drift on the candidate
- **WHEN** the candidate's canary runs again and one choice differs from the candidate's own baseline
- **THEN** it reports drift against the candidate's baseline, which stays unchanged unless accepted explicitly

### Requirement: The comparison runs the manifest's Jev sets on both models
`horizon eval compare-models --base <id> --new <id> --manifest <file>` SHALL run, on each model, every Jev set the
manifest lists: the canary, every decisions folder with the judges, deep-check, and the safety suite's Jev parts. Every
Jev body SHALL be checked against the manifest. It SHALL send no DeepSeek request.

#### Scenario: A changed body
- **WHEN** a set's item now compiles to a body the manifest does not list
- **THEN** that item is not sent on either model, and the report names it under "not in the manifest"

#### Scenario: No chat calls
- **WHEN** a full comparison run completes
- **THEN** its ledgers hold only `decision` rows

### Requirement: Each model's answers are paid once
The base model's side SHALL be served from the store wherever an answer is stored, and only its missing bodies SHALL be
paid. The candidate's answers SHALL be stored under the candidate's own key, so re-running the comparison or a later
switch pays nothing for them again. Before the paid runs, a probe SHALL report the exact number of requests and the cost
each model would pay.

#### Scenario: Re-run is free
- **WHEN** `compare-models` runs a second time with the same manifest and models
- **THEN** every Jev answer on both sides is served from the store, and the run spends $0

### Requirement: Accuracy is reported drop-in and re-tuned on the same items
For each set, the report SHALL give both models' accuracy on the same items in two ways:
- drop-in: the candidate scored at the pinned thresholds and floors;
- re-tuned: the candidate's thresholds re-chosen on the dev split by the set's own rule, then read on test once.

Each comparison SHALL show the item counts, Wilson intervals and an exact McNemar p.

#### Scenario: Paired result
- **WHEN** a set has 40 test items, 1.13 is right on 30, the candidate on 34, and they disagree on 8 items (6 for the candidate, 2 for 1.13)
- **THEN** the row shows 30/40 and 34/40 with their intervals, b = 2, c = 6, and the exact McNemar p for (2, 6)

#### Scenario: Threshold chosen on dev only
- **WHEN** the re-tuned figure of a noul set is computed
- **THEN** its threshold is chosen from the dev rows alone, written to the report before the test rows are scored, and the test figure is computed once

#### Scenario: Set with no rule to tune
- **WHEN** a set has no threshold or floor to choose
- **THEN** its re-tuned column repeats the drop-in figure and says so

### Requirement: Behaviour beyond accuracy is reported
For each model, the report SHALL give:
- the calibration table per noul set with labels;
- for choices asked in both option orders: the order-flip rate and how often the first listed option is chosen, in
  each order;
- the invalid-answer, 429 and 529 rates;
- the measured cost per request and per 1:1 reply.

#### Scenario: First-option rate
- **WHEN** a choice item is answered with its first option in declared order and again with its first option in reversed order
- **THEN** it counts as a flip and as a first-option pick in both orders

### Requirement: Paired timing probe
The timing probe SHALL alternate the two models on the same bodies, never served from the store. It SHALL use buckets
at live request sizes (under 1k, 1k–2.5k, 2.5k–4k tokens) and five bodies each near 10k and 25k as a limit check. It
SHALL discard each window's first 5 requests per model, run in two separate time windows, and report p50, p90 and p99
with intervals per model, bucket and window.

#### Scenario: Paired windows
- **WHEN** the timing probe completes its two windows
- **THEN** each bucket shows both models' p50, p90 and p99 per window, with the warm-up requests excluded and their count stated

### Requirement: Repeat probe
The repeat probe SHALL ask the canary's 20 items three times on each model, never served from the store, and report how
often a choice changes and the largest probability and score movements.

#### Scenario: Stable model
- **WHEN** no choice changes across the three asks and the largest probability move is 0.04
- **THEN** the report shows 0 of 20 choices changed and a maximum move of 0.04 for that model

### Requirement: The report is re-cut from saved rows
The comparison report SHALL be computed only from the two models' saved run rows, and re-computing it SHALL send nothing
and spend nothing. Per-item rows SHALL be written with private safety items as hashes only.

#### Scenario: Re-cut
- **WHEN** `compare-models --report-only` is run on two saved comparison runs
- **THEN** the same report is written, no request is sent, and nothing is spent

### Requirement: The candidate's judge figures are information only
Reply-quality figures SHALL keep using the pinned model's judges during a comparison. The candidate's judge accuracy
SHALL appear in the report as information, never as a validation record or a changed figure elsewhere.

#### Scenario: Judges column
- **WHEN** the comparison report is written
- **THEN** its judges table shows both models' B4 figures and states that the candidate's figures don't validate any judge

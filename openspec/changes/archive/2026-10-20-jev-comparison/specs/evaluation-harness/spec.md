# Spec Delta

## MODIFIED Requirements

### Requirement: Suites and options
`horizon eval <suite>` SHALL accept every suite the harness defines: `canary`, `decisions`, `smoke`, `drafter`, `summary`, `long`, `transcript`, `moodline`, `latency`, `watch-history`, `freerun`, `debate-history`, `debate-plant`, `debate-quality`, `debate`, `retrieval`, `notfound`, `deep-check`, `memory`, `safety`, `embed-probe`, and from M15 `conversations`, `faithfulness` and `all`. It SHALL accept the options `--profile`, `--limit N`, `--start N`, `--set NAME`, `--max-usd`, `--yes`, `--allow-peak`, from M15 `--probe` and `--against-manifest FILE`, and from the Jev comparison `--decision-model ID`. An unknown suite SHALL exit non-zero and list the known ones. `--profile` SHALL keep its default of `naive`, whatever the app's default profile is.

#### Scenario: Unknown suite
- **WHEN** `horizon eval everything` is run
- **THEN** it exits non-zero, and the message lists the known suites, `conversations` and `all` among them

#### Scenario: The eval default stays naive
- **WHEN** `horizon eval decisions` is run without `--profile` on an app whose default is `agent`
- **THEN** the run's report says profile `naive`

#### Scenario: Decision model option
- **WHEN** `horizon eval canary --decision-model typesafe/jev-1.14` is run
- **THEN** the option is accepted, and the run's report names the model asked

### Requirement: Estimate and ask before spending
A paid run SHALL print what will run, the number of calls, the expected time, the cost estimate and today's evaluation spend, then wait for confirmation, unless `--yes` is given. A run whose plan includes any chat (DeepSeek) request and would overlap peak hours SHALL refuse unless `--allow-peak` is given; a plan of Jev requests only SHALL run at any hour, because the peak price is the chat model's alone. A suite that cannot tell SHALL be treated as calling chat. A paid suite SHALL refuse to run in test mode.

#### Scenario: Declined
- **WHEN** a paid canary run is started and the user answers `n`
- **THEN** no request is sent, and no run folder is kept

#### Scenario: Jev-only run at peak
- **WHEN** `decisions --set english` is started at 10:30 KL, a peak hour
- **THEN** it is not refused for peak, and proceeds to the estimate and the confirmation

#### Scenario: Chat run at peak
- **WHEN** `latency` is started at 15:00 KL without `--allow-peak`
- **THEN** it refuses for peak, and nothing is sent

### Requirement: The drift canary
The canary SHALL send the 20 committed canary items to Jev, never served from the store. It SHALL pass when:
- every choice equals the accepted baseline;
- every probability moves by at most 0.10;
- every raw score moves by at most 0.15.

It SHALL record the exact model ID returned. Each decision model SHALL have its own accepted baseline: the pinned model's is `evals/canary.json`, and any other model's lives under `evals/canary/`. A run SHALL compare against the baseline of the model it asked. The baseline's fingerprint SHALL be verified against its answers when loaded. A new baseline SHALL be accepted only on explicit request, except a candidate model's first baseline (see `model-comparison`).

#### Scenario: Drift detected
- **WHEN** one canary choice differs from the baseline
- **THEN** the run reports drift, names the item, and the baseline is unchanged

#### Scenario: Edited baseline
- **WHEN** the baseline's answers were edited by hand without updating its fingerprint
- **THEN** the harness refuses to load it

#### Scenario: Per-model baseline
- **WHEN** the canary runs on the pinned model while a candidate model's baseline also exists
- **THEN** it compares against `evals/canary.json` only, and the candidate's baseline is untouched

### Requirement: Decision suite
The `decisions` suite SHALL build every item's request from the question bank exactly as live, with the live deadline off. It SHALL report policy accuracy (Jev above the floor, the fallback below), a calibration table and, for choices, order bias measured in both option orders, each with its sample size and a Wilson interval. A noul item SHALL be asked once and scored as `yes` when its p reaches the entry's threshold. It SHALL re-run only questions whose version or items changed since they were last measured on the same decision model; the "already measured" marks SHALL be kept per decision model. `--set NAME` SHALL limit it to one dataset folder. For the emotion and reaction questions, policy accuracy SHALL apply the live code rules (the `neutral` + `none` merge, keep, fade, and for reactions "differs from the current face"), floors SHALL be chosen on the dev split from one seeded option order per item, and the report SHALL show the trivial baseline ("always keep the current face"; "always `none`") with the difference and its interval.

#### Scenario: Unchanged version
- **WHEN** `decisions` runs twice with no bank change
- **THEN** the second run sends no request

#### Scenario: Another model is measured afresh
- **WHEN** `decisions` has measured every question on the pinned model, and is then run with `--decision-model typesafe/jev-1.14`
- **THEN** every item is asked on `typesafe/jev-1.14`, and the pinned model's marks are unchanged

#### Scenario: Noul item
- **WHEN** a noul item labelled `yes` is answered with p 0.72 and the entry's threshold is 0.5
- **THEN** it is scored correct, from one request

#### Scenario: Emotion item with a kept face
- **WHEN** an emotion item allows keeping `thinking`, its previous face is `thinking`, and Jev answers `angry` below the floor
- **THEN** the policy answer is `thinking`, and the item is scored correct

#### Scenario: Floor chosen on dev
- **WHEN** the emotion floor is tuned
- **THEN** it is chosen from {0.5, 0.6, 0.7, 0.8, 0.9} on dev items in their seeded order, and the test split's figure is reported once with that floor

### Requirement: The Jev request manifest
`horizon eval manifest` SHALL write `evals/baselines/jev-<version>-requests.json` for the pinned decision model (for `typesafe/jev-1.13`, `jev-1.13-requests.json`) at no cost, sending nothing. For each Jev set (every decisions folder with the judges, the canary, deep-check, and safety's Jev parts), it SHALL record the SHA-256 of every request body (state and questions, without the model) as the suite compiles it, and how many have a stored answer on that model. It SHALL also record the bank versions and the canary fingerprint. Private items SHALL appear only as hashes. A later model comparison (`--against-manifest`) SHALL refuse any Jev body the manifest doesn't list.

#### Scenario: A body that changed
- **WHEN** a comparison run builds a request whose body hash is not in the manifest
- **THEN** it refuses to send that item and names it

#### Scenario: Named by model
- **WHEN** `horizon eval manifest` runs with `typesafe/jev-1.14` pinned
- **THEN** it writes `evals/baselines/jev-1.14-requests.json`, and `jev-1.13-requests.json` is unchanged

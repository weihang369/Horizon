## MODIFIED Requirements

### Requirement: Suites and options
`horizon eval <suite>` SHALL accept the suites `canary`, `decisions`, `smoke`, `drafter`, `summary`, `long`, `transcript`, `moodline` and `latency`, and the options `--profile`, `--limit N`, `--start N`, `--set NAME`, `--max-usd`, `--yes` and `--allow-peak`. An unknown suite SHALL exit non-zero and list the known ones.

#### Scenario: Unknown suite
- **WHEN** `horizon eval conversations` is run
- **THEN** it exits non-zero, and the message lists `canary`, `decisions`, `smoke`, `drafter`, `summary`, `long`, `transcript`, `moodline` and `latency`

### Requirement: Decision suite
The `decisions` suite SHALL build every item's request from the question bank exactly as live, with the live deadline off. It SHALL report policy accuracy (Jev above the floor, the fallback below), a calibration table and, for choices, order bias measured in both option orders, each with its sample size and a Wilson interval. A noul item SHALL be asked once and scored as `yes` when its p reaches the entry's threshold. It SHALL re-run only questions whose version changed since the baseline. `--set NAME` SHALL limit it to one dataset folder. For the emotion and reaction questions, policy accuracy SHALL apply the live code rules (the `neutral` + `none` merge, keep, fade, and for reactions "differs from the current face"), floors SHALL be chosen on the dev split from one seeded option order per item, and the report SHALL show the trivial baseline ("always keep the current face"; "always `none`") with the difference and its interval.

#### Scenario: Unchanged version
- **WHEN** `decisions` runs twice with no bank change
- **THEN** the second run sends no request

#### Scenario: Noul item
- **WHEN** a noul item labelled `yes` is answered with p 0.72 and the entry's threshold is 0.5
- **THEN** it is scored correct, from one request

#### Scenario: Emotion item with a kept face
- **WHEN** an emotion item allows keeping `thinking`, its previous face is `thinking`, and Jev answers `angry` below the floor
- **THEN** the policy answer is `thinking`, and the item is scored correct

#### Scenario: Floor chosen on dev
- **WHEN** the emotion floor is tuned
- **THEN** it is chosen from {0.5, 0.6, 0.7, 0.8, 0.9} on dev items in their seeded order, and the test split's figure is reported once with that floor

### Requirement: Judges are validated before they count
Each judge question SHALL have 60 validation items: 30 real outputs labelled by hand, and 30 failures planted by code. A judge SHALL pass when it is at least 85 % right on the real items, beats the always-the-commonest-answer baseline over all 60 items, and catches at least 90 % of the planted failures. The "names the feeling" judge SHALL also make at most 1 false alarm on the real items labelled clean. The pairwise judge SHALL instead have 30 pairs with a known winner, asked in both orders, and pass at 90 % or more. The result SHALL be recorded per question and version. Any figure from a judge whose current version has not passed SHALL be reported as "unvalidated", never as a measurement.

#### Scenario: Unvalidated judge
- **WHEN** the summary suite runs before `judge_summary_fact`'s current version has passed validation
- **THEN** the report shows the fact-kept rate marked "unvalidated", and does not mark the target met

#### Scenario: Reworded judge
- **WHEN** a judge that passed is reworded and its version goes up
- **THEN** its figures are "unvalidated" again until it passes again

#### Scenario: Too many false alarms
- **WHEN** "names the feeling" is 90 % right on real items but flags 2 clean replies
- **THEN** it fails validation

### Requirement: Smoke runs in test mode
`horizon eval smoke` SHALL run in test mode at no cost, on the fake provider and the virtual clock. It SHALL check that:
- every request built from the bank passes the wire schema;
- every dataset, suite input file and transcript loads;
- one scripted conversation per mode completes, with the reply checks computed;
- one drafter seed, one summary item and the first lines of each long script run through their suites;
- one planned `agent` 1:1 turn completes with its emotion row, face-check row and mood line, from fixture answers;
- the first item of the mood-line on/off run and one latency turn run through their suites;
- the report renders.

It SHALL never compare with the baselines.

#### Scenario: CI smoke
- **WHEN** `HORIZON_TEST=1 horizon eval smoke --limit 5 --yes` runs with no key and no network
- **THEN** it exits zero, and no socket is opened

## ADDED Requirements

### Requirement: The mood-line on/off run
`horizon eval moodline` SHALL take up to N non-neutral planned turns (100 by default) from the committed frozen transcripts and reply to each as a single call with and without the mood line, from the same stored history. Both arms SHALL get "names the feeling", "face and words agree" and the pairwise judge in both orders. It SHALL compare the arms with a paired bootstrap over 10-turn blocks, and print E8's verdict: keep, reword once, or propose dropping.

#### Scenario: Same history in both arms
- **WHEN** one item is run in both arms
- **THEN** the two reply requests differ only in the mood line

#### Scenario: Replay from the store
- **WHEN** the run is repeated with no bank, prompt or transcript change
- **THEN** every reply and judge answer comes from the store, and nothing is spent

#### Scenario: Verdict is advice
- **WHEN** the verdict is "propose dropping"
- **THEN** the report says so and changes no prompt or setting

### Requirement: The latency suite
`horizon eval latency` SHALL run real `agent` 1:1 quick turns through the live app path in an isolated copy, with the store bypassed. It SHALL stop each turn at its first word, and report the time to the face and to the first word (p50 and p90 with order-statistic intervals) against NFR-01. It SHALL also report Jev's `turn_plan` latency distribution and how often its deadline fired.

#### Scenario: Never from the store
- **WHEN** the latency suite runs twice
- **THEN** both runs send every request to the provider, and neither reads or writes the store

#### Scenario: Stopped at the first word
- **WHEN** a latency turn's first token arrives
- **THEN** the suite sends Stop, and the message ends `interrupted`

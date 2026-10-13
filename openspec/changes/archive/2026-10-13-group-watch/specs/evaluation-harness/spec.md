# Spec Delta

## MODIFIED Requirements

### Requirement: Smoke runs in test mode
`horizon eval smoke` SHALL run in test mode at no cost, on the fake provider and the virtual clock. It SHALL check that:
- every request built from the bank passes the wire schema;
- every dataset, suite input file and transcript loads;
- one scripted conversation per mode completes, with the reply checks computed;
- one drafter seed, one summary item and the first lines of each long script run through their suites;
- one planned `agent` 1:1 turn completes with its emotion row, from fixture answers (the mood line is off by default, D40; the moodline item forces it on for its ON arm);
- one planned `agent` group send with a follow plan, one planned `agent` watch turn and one episode recap complete, from fixture answers and canned responses;
- the first item of the mood-line on/off run, one latency turn, one follow-plan timing request and one free-run turn run through their suites;
- the report renders.

It SHALL never compare with the baselines.

#### Scenario: CI smoke
- **WHEN** `HORIZON_TEST=1 horizon eval smoke --limit 5 --yes` runs with no key and no network
- **THEN** it exits zero, and no socket is opened

## ADDED Requirements

### Requirement: The who-speaks policies
For the `who_first`, `who_second` and `who_scene` items, the decision suite SHALL score the live code rule after the floor (the pick, else the least recently spoken of Jev's top 2, or for `who_second` else `none`). The second slot SHALL be scored by balanced accuracy. Each part SHALL report its baseline (least recently spoken; round-robin for watch), the difference, and an exact one-sided paired test; a part passes at ≥ 80 %, a difference ≥ 0.15 and p < 0.05.

#### Scenario: Always none can't pass
- **WHEN** a policy answers `none` on every second-slot item
- **THEN** its balanced accuracy is 50 %

#### Scenario: Paired test
- **WHEN** the first-slot test split is scored
- **THEN** the report shows Jev's accuracy, the least-recently-spoken baseline's accuracy on the same items, their difference and the exact McNemar p

### Requirement: Floors for who speaks and the second slot
Who-speaks floors SHALL be chosen on the dev split from {0.2, 0.3, …, 0.9}, each item in its seeded live order. `floor.second` SHALL be the floor with the best balanced accuracy among those whose needless second replies are at most 15 % of the `none` items.

#### Scenario: Needless replies bound the floor
- **WHEN** floor 0.3 has the best balanced accuracy but gives needless second replies on 20 % of `none` items
- **THEN** it is not chosen for `floor.second`

### Requirement: The talk-finished threshold
The "is the talk finished?" items (about 120, at least 60 labelled yes) SHALL set `t_end` to the lowest threshold from {0.5, 0.55, …, 0.95} with precision ≥ 90 % on dev, and report recall; a recall under 50 % SHALL be flagged for rewording.

#### Scenario: Lowest precise threshold
- **WHEN** thresholds 0.7 and above reach 90 % precision on dev and 0.65 doesn't
- **THEN** `t_end` is 0.7, and the test split's precision and recall at 0.7 are reported once

### Requirement: Episode recaps in the summary suite
The `summary` suite SHALL also write 10 episode recaps from the committed watch histories, and check each with the summary judges (faithful, nothing invented, right language) and a 120-word limit in code. More than 1 failure SHALL fail the target, and every failure SHALL be printed for reading.

#### Scenario: Recap over the limit
- **WHEN** a recap item's output has 135 words
- **THEN** it counts as a failure and is printed with its lines

### Requirement: Committed watch histories
`horizon eval watch-history` SHALL generate a watch scene with `naive` through the store once, for review and commit, and refuse to overwrite a committed history without a flag.

#### Scenario: Refuses to overwrite
- **WHEN** `watch-history` runs for a history that is already committed
- **THEN** it stops without a paid call and names the flag that would overwrite it

### Requirement: Free runs for group and watch
`horizon eval freerun` SHALL run `agent` watch scenes and group sessions with scripted user lines, and report the second-reply rate (with follow-plan timeouts apart from `none`), the busiest speaker's share, the guard's firing rate and the steer's firing rate, printing every steered line. It SHALL have no target.

#### Scenario: Timeouts apart
- **WHEN** a group free run has 12 sends, 3 follow plans picking `none` and 2 late
- **THEN** the report shows 3 `none` and 2 timeouts separately

### Requirement: Follow-plan and watch timing
The latency suite SHALL have a follow part (hand-built follow states, Jev only: a miss is state assembly + Jev latency past the measured stream-end-to-`turn.end` time + 400 ms; pass at ≤ 10 % missed) and a watch part (scenes at Fast pace: `turn.end` to the next first token against NFR-02's 3 s p50). Both SHALL bypass the store and report Jev's slow spells apart from the percentiles.

#### Scenario: Slow spell reported apart
- **WHEN** 4 consecutive follow-plan requests take over 2 seconds
- **THEN** the report lists them as one slow spell, and gives the miss rate with and without it

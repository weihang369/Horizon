# evaluation-harness Specification

## Purpose

The evaluation harness measures Horizon's AI with `horizon eval`: it runs suites in isolated copies of the demo data, asks before spending, cannot overspend, and records results against committed baselines and datasets that follow the evaluation's data rules.

## Requirements

### Requirement: Suites and options
`horizon eval <suite>` SHALL accept the suites `canary`, `decisions`, `smoke`, `drafter`, `summary`, `long`, `transcript`, `moodline` and `latency`, and the options `--profile`, `--limit N`, `--start N`, `--set NAME`, `--max-usd`, `--yes` and `--allow-peak`. An unknown suite SHALL exit non-zero and list the known ones.

#### Scenario: Unknown suite
- **WHEN** `horizon eval conversations` is run
- **THEN** it exits non-zero, and the message lists `canary`, `decisions`, `smoke`, `drafter`, `summary`, `long`, `transcript`, `moodline` and `latency`

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

### Requirement: Committed debate histories
`horizon eval debate-history` SHALL generate debates once with `naive` through the live runtime and the store: 12 two-sided (8 Standard 2 v 2, 2 Standard 3 v 2, 2 Quick 2 v 2) and 1 Standard panel of 4. Each argument SHALL be saved with its phase, iteration, side and speaker, for review and commit. A committed history SHALL NOT be regenerated without `--force`, and a refused run SHALL make no call.

#### Scenario: Refused regeneration
- **WHEN** `debate-history` is run for a committed history without `--force`
- **THEN** it stops before any prompt is built or call is made

### Requirement: Planted weak sides
`horizon eval debate-plant` SHALL write, once, for each two-sided history, a planted version whose weak side's rebuttal and closing arguments repeat its own opening and ignore the other side. The weak side SHALL be the Proposition in even-numbered debates and the Opposition in odd ones. Plants SHALL be reviewed and committed like the histories.

#### Scenario: Which side is weak
- **WHEN** plants are written for debates 0 and 1
- **THEN** debate 0's Proposition and debate 1's Opposition are rewritten, and every other argument is unchanged

### Requirement: The debate member policy
The decisions suite SHALL score the member slice (about 90 items, at least 45 with a single acceptable member, at least 30 test) by the live rule: Jev's pick at or above the floor, else fixed order. It SHALL report accuracy inside the acceptable set (target 80 %), the single-answer test items against fixed order (≥ 15 points, exact one-sided McNemar test, p < 0.05), and the random-pick baseline. `floor.member` SHALL be chosen on dev over D36's grid.

#### Scenario: A pass needs both measures
- **WHEN** the test split scores 0.85 inside the set, but only 8 points above fixed order on the single-answer items
- **THEN** the report fails the member check

### Requirement: The debate suite
`horizon eval debate` SHALL score the `agent` verdict on the 12 debates, each balanced and planted, and each again with the side blocks swapped, split 4 dev / 8 test by debate. `verdict.margin` SHALL be tuned on dev only. On test it SHALL report: the strong side winning the planted items (target ≥ 7 of 8), its higher Rebuttal score (≥ 7 of 8), winner flips under the swap (at most 1 of 16), and the too-close rate.

#### Scenario: Swap flips are counted apart from ties
- **WHEN** one swapped item goes from Proposition to Opposition and another from Proposition to too close
- **THEN** the report counts 1 winner flip, and lists the change to too close apart

#### Scenario: The margin is tuned on dev only
- **WHEN** the suite chooses `verdict.margin`
- **THEN** no test item's answer is read before the choice is written

### Requirement: Prose and host checks are read in full
The debate suite SHALL check 10 `agent` verdict proses (each summary point said by that side; the rationale matches the scores; no side called factually right) and 10 host bridges (neutral; only what was argued) with first-pass nouls. It SHALL print every item for reading by hand, with a target of at most 1 failure each.

#### Scenario: Every item is printed
- **WHEN** the prose checks run
- **THEN** the report holds all 10 verdicts with each noul's `p`, whether or not they passed

### Requirement: The debate emotion slice
The emotion set SHALL gain a 40-item debate slice (30 rebuttal or closing lines for `emotion_line`, 10 openings for `emotion_debate_opening`) from the debate histories, labelled blind, with its own hash split. The floors for debate faces SHALL be chosen on its dev split over D36's grid and reported apart from the other emotion items.

#### Scenario: The slice is scored alone
- **WHEN** the emotion set is scored after this change
- **THEN** the report shows the debate slice's floor, dev and test accuracy apart, and M9's and M10's items are served from the store

### Requirement: The debate-quality judge
"Keeps its side" and "engages" SHALL each be validated on 30 real and 30 planted items before they count. They SHALL then run on every argument of the `naive` histories and of the `agent` debate free runs, reported side by side as a signal. The targets (keeps its side ≥ 95 %, engages ≥ 80 %) SHALL be judged on the layer-3 conversations at M15.

#### Scenario: An unvalidated judge doesn't count
- **WHEN** the debate-quality judge has not passed its validation
- **THEN** the suite reports its rates as not counted

### Requirement: Debate timing
The latency suite's debate part SHALL time, outside the store: the 30 debate-plan requests; 10 host bridges, from the round's last `turn.end` to the line (on time when within the pause + 1.5 s, target ≥ 8 of 10); and 5 Arbiter verdicts, from the last closing's `turn.end` to the verdict. The bridges and verdicts SHALL then be saved as suite items. Jev's slow spells SHALL be reported apart, and the 90 s watchdog kept.

#### Scenario: Bridges are kept
- **WHEN** the debate timing run ends
- **THEN** its 10 bridges and 5 verdicts are in the store, and the debate suite's prose and host checks read them without a new call

### Requirement: Debate free runs
`freerun --profile agent --mode debate` SHALL run a Standard 2 v 2 with Auto host and Arbiter, and a panel of 4 with Auto host. It SHALL report the member choice (Jev, unsure, late), host lines on time, any pause, the verdict, and the debate-quality rates.

#### Scenario: A member choice report
- **WHEN** a debate free run ends
- **THEN** the report counts its member choices by source

### Requirement: The who-speaks re-test
After `who_scene` and `who_next` move to version 3, the decisions suite SHALL ask the existing `who_scene` items again as dev, score 40 fresh `who_scene` cuts labelled blind from new watch runs as a held-out test, and score a new 40-item `who_next` set with its own split. The bars SHALL be the who-speaks bars: ≥ 80 % inside the set, and ≥ 15 points above the baseline on an exact paired test.

#### Scenario: Fresh cuts are held out
- **WHEN** the `who_scene` floor is chosen
- **THEN** it is chosen on the 100 existing items, and the 40 fresh cuts are scored once with it

### Requirement: The steer is measured
The watch free runs SHALL judge every steered line with the validated "does this line start something new?" noul, print each steered line, and report the share that starts something new against M10's 0 of 7.

#### Scenario: Steered lines are listed
- **WHEN** three watch free runs end
- **THEN** the report lists every steered line with its judge `p`, and the share that starts something new

### Requirement: Recaps are judged with their premise
The summary suite's recap check SHALL give `judge_summary_unsupported` the recap's premise as well as its lines and previous notes.

#### Scenario: A detail from the premise
- **WHEN** a recap mentions the flower festival that only the premise names
- **THEN** the unsupported-claim judge is given that premise

### Requirement: The watch faces under both merge rules
The decisions suite SHALL score the watch emotion slice, grown past 13 test items, under both rules for `emotion_line` (the `neutral` + `none` merge, and no merge), on dev and test with the same floor grid, and report them side by side for the user's choice.

#### Scenario: Both policies reported
- **WHEN** the watch emotion slice is scored
- **THEN** the report shows each rule's floor, dev and test accuracy, and the items where they differ

### Requirement: Smoke runs a debate
`smoke` SHALL run one Quick 2 v 2 `agent` debate with Auto host and Arbiter in test mode, from fixture answers and canned host and verdict responses, plus one debate-plan timing request and one rubric request, with no network call.

#### Scenario: Smoke in CI
- **WHEN** `HORIZON_TEST=1 horizon eval smoke --limit 5 --yes` runs
- **THEN** a debate reaches its verdict with host lines and scores, and no socket is opened

# Spec Delta

## ADDED Requirements

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

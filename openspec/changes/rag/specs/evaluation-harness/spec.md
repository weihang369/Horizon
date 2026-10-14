# Spec Delta

## ADDED Requirements

### Requirement: The retrieval suite
`horizon eval retrieval` SHALL load the corpus and the seed documents as their characters' sources in the run's own database and run the `agent` deep path on 205 labelled questions (100 answerable with 10 needing two passages, 40 unanswerable, 30 follow-ups, 15 non-English, 20 naming a document). It SHALL report Recall@20, Recall@8, MRR, nDCG@8, kept-set precision and recall, and the outcomes, with seed and corpus apart.

#### Scenario: Offline run
- **WHEN** `HORIZON_TEST=1 horizon eval retrieval --limit 5 --yes` runs
- **THEN** it completes with fixture answers and no network call, and its report lists every metric

### Requirement: Labels live on the text, not on pieces
A retrieval question's labels SHALL be quoted spans of its source text, graded 2 (answers) or 1 (partly). A piece SHALL count as covering a span when it holds at least 80 % of the span's characters, so every chunking is scored against the same labels.

#### Scenario: Span split by a smaller piece size
- **WHEN** the suite runs with 200-token pieces and a labelled span falls 90 % inside one piece
- **THEN** that piece counts as covering the span

### Requirement: The passage thresholds are cross-validated
`t_keep` and `t_found` SHALL be chosen from 0.5–0.9 by leave-one-out over the whole suite, and the out-of-fold outcomes SHALL be counted against the targets: at most 3 wrong abstains in 100 answerable questions, and at least 32 of 40 unanswerable abstained. `t_set` SHALL be re-tuned only when the suite holds 20 or more set checks; otherwise each set check SHALL be reported.

#### Scenario: Too few set checks
- **WHEN** the suite's run makes 9 set checks
- **THEN** `t_set` stays at its bank value, and the report lists the 9 set checks with their answers

### Requirement: The retrieval comparisons
The suite SHALL compare, each chosen on dev and confirmed once on test:
- the embedding spaces (the 1,024 default against 2,048 and bge-m3, by K3's rule);
- piece targets of 200, 300 and 400 tokens at a fixed 1,200-token budget;
- MMR λ of 0.5, 0.7 and 1.0;
- the old and new query instruction;
- rewrite against none;
- header against none.

Only kept-set precision SHALL make Jev calls.

#### Scenario: A challenger space must win clearly
- **WHEN** a challenger space gains 2 points of Recall@8 on dev
- **THEN** the default space stays, and the report says the gain is below the 3-point rule

### Requirement: The retrieval decision sets
The `decisions` suite SHALL score "needs documents?" on about 120 items (at least 60 yes) across every mode, choosing `t_gate` as the highest threshold with recall ≥ 90 % and `t_confident` as the lowest with precision ≥ 95 %. It SHALL score "standalone?" on 100 messages (50 follow-ups), choosing the highest `t_standalone` that sends ≥ 90 % of follow-ups to the rewrite, and "English?" on 40 messages in 4 languages against ≥ 95 %.

#### Scenario: Gate thresholds from dev
- **WHEN** the `docs` set is scored
- **THEN** the report names `t_gate` and `t_confident` chosen on dev, the test split's recall and precision with Wilson intervals, and the deep rate on items that need no documents

### Requirement: The not-found reply judge
Two judge questions SHALL check a reply given the not-found or partly line: whether it fails to say the documents don't cover the question (or which part), and whether it presents something beyond the documents as if from them or cites with [n]. Each SHALL be validated on 30 real and 30 planted items before it counts, then scored on 40 unanswerable and 10 partly questions end to end, against ≥ 90 % each.

#### Scenario: Not validated yet
- **WHEN** the judges' validation hasn't passed and the end-to-end run is reported
- **THEN** their figures read "NOT COUNTED"

### Requirement: Deep-turn timing
`horizon eval latency --part deep` SHALL time 100 deep 1:1 turns with a rewrite and 100 without (forced by fixture), plus 25 deep turns each in group, debate and watch, on a database holding every seed and corpus document indexed. It SHALL report each step's time, the slowest `deep_check` per turn, the 429 count and the fallback rate, bypassing the response store, against NFR-01 for each 1:1 arm and NFR-02 for the others.

#### Scenario: Offline timing
- **WHEN** `HORIZON_TEST=1 horizon eval latency --part deep --limit 3 --yes` runs
- **THEN** it completes on the virtual clock with no network call, and reports every step

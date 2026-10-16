# M13 label review (the delegated pass, U1)

The user delegated the labels and their review to the team (memory design D44 U1, 2026-10-15). This is the
labeller's recorded second pass over everything phase 9 built, done before any paid run on these sets and before any
Jev answer, rewrite or reply for them was seen. Each sample is B2's size, max(15, ⌈n/5⌉), drawn with `review_sample`
(the function behind `horizon eval review`) and the seed shown. Each sampled label was re-read against its source:
the labelled facts and their rules in `evals/datasets/earlier/facts.py` (whose docstring defines what `memory`,
`extend`, `lossy`, `reword`, `probe` and `level` mean, written before the sets were built), the frozen transcripts
for the in-session probes, and the builders. Every label follows from how its item is made, so the pass reads two
things: whether the rule gives the right label on that item, and whether the builder made the item it meant to.

The held-out test split, scored once with the thresholds chosen on dev, remains the safeguard. **No run has used it:**
the only runs on these sets so far are test-mode runs on the in-process fake. Plainly: this is not an independent
reviewer.

| Set | Items | Sample | Seed | Disagreements | Action |
|---|---|---|---|---|---|
| `importance` | 100 | 20 | 1310 | 0 | none |
| `memory_guard` | 122 | 25 | 1311 | 0 | none |
| `earlier` | 120 | 24 | 1312 | 0 | none |
| `recall` | 120 | 24 | 1313 | 0 | none |
| `judges/judge_memory_missed` (planted) | 30 | 15 | 1314 | 0 | none |
| `judges/judge_memory_unsupported` (planted) | 30 | 15 | 1315 | 0 | none |
| `judges/judge_memory_lost` (planted) | 30 | 15 | 1316 | 0 | none |
| `judges/judge_over_mention` (planted) | 30 | 15 | 1317 | 1 (`-planted-016`), and broken grammar in the replies | the builder fixed; every "yes" item re-read |
| `memory/rewrite` | 36 | 15 | 1318 | 1 (`mrw-024`'s language tag) | the tag fixed |
| `memory/probes` | 100 | 20 | 1319 | 0 | none |
| `memory/layer3` | 20 | 15 | 1320 | 3 (`ml3-018`–`020` repeated `001`–`003`) | the builder fixed; all 20 re-read |

The sampled ids are in `m13-review.json`. B4's 30 real items per new judge are labelled from the first paid
`horizon eval memory` run's `judge_states.jsonl` (the suite saves every judge state, so nothing is paid twice), under
the same rules; their review is added here then.

## Notes on the pass

- **`importance`.** Level 1 is what nobody needs later: sign-offs ("Okay, bye for now!", "Right then"), filler and a
  passing opinion ("Pink is such a happy colour"). Level 2 is a small, stable preference or a passing event (window
  seats, a courtroom drama last night). Levels 4–5 are plans with dates and anything about health or safety: the
  shellfish allergy that ends in hospital is 5, as are the dad's bypass and the penicillin allergy. The two non-English
  items sampled (`imp-058` mixed, `imp-074` Chinese) carry the levels their English versions would; they are reported
  apart, not scored (English first).
- **`memory_guard`.** "Yes" means every still-true part of the old line is in the new one. Each extension keeps the old
  line whole and adds one detail; the added detail is never judged here (that is `judge_memory_unsupported`'s job).
  Each lossy rewrite drops or blurs at least one detail the source didn't change. `mgd-094` ("Kai avoids prawns" for
  "can't eat shellfish; it sends him to hospital") loses both the scope and the severity, so it is "no". Each
  rewording sampled keeps every part in another order.
- **`earlier`.** "Yes" items need a fact that is no longer in the recent lines (the item says "not shown"). The same
  probe with the fact still in the window (`erl-091`, `erl-095`–`erl-110`) is "no": nothing has to come from earlier
  (D26). New topics asked cold are "no".
- **`recall`.** The negatives sampled include pronoun traps, and they are right as "no". "Would losing one day a week
  hurt her takings much?" is about the mum's kopitiam, not Kai's company's four-day week (`rcl-034`). "What could I take
  her to brighten up the ward?" is about the mum in hospital, not the cat that chews bouquets (`rcl-118`).
- **`judge_memory_missed`, `judge_memory_unsupported`, `judge_memory_lost`.** A line that holds the expected fact,
  even with a detail added, covers it ("no" missed). A line whose added detail nobody said is unsupported. An extension
  loses nothing, and a blurred rewrite does.
- **`judge_over_mention`.** Two problems, both in the builder, not in the label rule:
  - `-planted-016` paired Kai's grandma's white peonies with "What's your favourite flower and why?". Flowers give
    the reply a reason to mention them, so "out of place" was wrong. The builder took the new topic from the same
    character's list, whose subjects overlap that character's facts (flowers for Hana, food for Takeshi, drawing for
    Rin). `facts.unrelated` now picks a topic sharing no subject (`facts.SUBJECTS`) with the fact. It tries the
    character's own topics first, then the others' that don't greet another character by name. Running and hydration
    count as one subject.
  - The planted replies were ungrammatical ("how you runs on Tuesdays", "your landlord kept his whole deposit"). A
    judge could catch the oddness rather than the over-mention, so `you()` now conjugates and changes "his" to "your".
  - Every one of the 15 "yes" items was re-read after the rebuild. Each reply drags a fact into a message with no
    reason to raise it, and reads as a person would say it.
- **`memory/rewrite`.** Each stretch makes the changes its `expected` list says: a fact changed in Kai's words, a fact
  repeated (a confirm), and a new fact. The rest of each planted list is untouched. Each secret is something no
  character should keep (a PIN, a card number, an IC number, a phone number, a password, a home address), and each
  small-talk stretch says nothing worth a memory. `mrw-024` (debate) adds f12, which Kai says in Chinese, but was tagged
  `ms`. It is `zh` now. Its label was right, and the suite only uses the tag to report languages apart. Four
  stretches are not in English (`zh` × 2, `ms`, `mixed`), above D40's two.
- **`memory/probes`.** Every in-session probe asks for its fact without stating it, and the fact's turn is long out of
  the window when the probe is asked (the transcript's last summary covers it). The overflow probes mostly lean on
  the fact rather than ask for it ("My doctor wants to give me antibiotics…" needs the penicillin allergy). The hardest
  is `mpr-097` ("Any way to make this year less of a scramble?" for the receipts in a shoebox and the late taxes). It
  stays: a character who remembers would raise it, and a miss there is worth reading, not removing.
- **`memory/layer3`.** The builder wrapped around the 34 English facts, so `ml3-018`–`020` repeated `ml3-001`–`003`
  whole: 17 distinct pairs counted as 20 would narrow the intervals with no new evidence. `layer3_pairs` now makes 20
  distinct pairs of one character's facts, spread over all six characters. It takes neighbours first, then shifted
  neighbours. Each pair's two unrelated turns share no subject with its facts (`facts.unrelated`). All 20 were re-read
  after the rebuild.
- **Found while reviewing, not a label:** the overflow probes' lists are built by the suite (`memory_suite.overflow_list`:
  the other facts' extended lines, then small talk), not stored in `probes.jsonl`. A test checks for every overflow
  probe that the needed memory ranks below the 1,000-token list with the seed's knobs, so each probe tests overflow.

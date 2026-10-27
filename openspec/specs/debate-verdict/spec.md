# debate-verdict Specification

## Purpose
The debate verdict: rubric scores from Jev with the winner decided in code, prose from DeepSeek told the result,
work started early and reused, a pick that never waits, and fallbacks that end the debate honestly instead of hanging
or faking.

## Requirements

### Requirement: Jev scores each side on each criterion
Under `agent`, a two-sided debate with verdict Arbiter or You decide SHALL make one `rubric` request with one 5-level score question per side per criterion. The criteria SHALL be the config's rubric: known ids use their own entry, others a generic entry that names the criterion by position. Each bar's value SHALL be the score's unit × 10, to one decimal, with `scoresBy: "side"`.

#### Scenario: The default rubric
- **WHEN** an `agent` debate with the default 4 criteria reaches its verdict
- **THEN** one `rubric` request holds 8 score questions, and the verdict has 8 `scores` entries between 0 and 10

#### Scenario: An unknown criterion
- **WHEN** the config's rubric has a criterion with id `wit` and label "Wit"
- **THEN** it is asked with the generic entry, the label appears only in a quoted state field, and its bars are drawn like the others

### Requirement: Code decides the winner
The stronger case SHALL be the side with the higher mean score over the criteria, or `null` ("TOO CLOSE TO CALL") when the difference, rounded to 6 decimals, is below `verdict.margin` (0.25 shipped), so a lead of exactly the margin wins. Jev's confidence SHALL NOT be used. The bars and the banner SHALL therefore always agree.

#### Scenario: A lead of exactly the margin
- **WHEN** the bars are Proposition 2.7, 3.4, 8.6, 1.2 and Opposition 2.7, 3.4, 8.6, 2.2 with the margin at 0.25
- **THEN** `strongerCase` is `opp` (the float difference 0.24999999999999956 counts as 0.25)

#### Scenario: A near tie
- **WHEN** the means are 6.4 and 6.1 with the margin at 0.5
- **THEN** `strongerCase` is `null` and the banner reads TOO CLOSE TO CALL

### Requirement: The rubric state keeps the sides in order and within budget
The state SHALL hold the two sides as an ordered list of blocks, each with its arguments in speaking order and its missed turns, with moderator notes apart, at most 24,000 tokens. Over budget, earlier iterations' arguments and Ask answers SHALL be cut to 60 words, then every argument to 120 words; still over, the verdict SHALL be summary only.

#### Scenario: The worst case fits
- **WHEN** a 5-debater debate with 4 extensions per phase, every argument at the long cap and 10 Asks reaches its verdict
- **THEN** the rubric request is under the size check, or the verdict is summary only, and nothing is sent over the limit

#### Scenario: A swapped order is a different request
- **WHEN** the evaluation asks the same debate with the Opposition block first
- **THEN** the request differs from the live one, and it is not served from the store

### Requirement: The verdict prose
A verdict SHALL get its summary, key disagreement and rationale from one DeepSeek JSON call with the `verdict` settings and purpose `verdict`, given the transcript as quoted content, the missed turns, and the result already decided, the scores one line per criterion naming the side that leads it, or "level" (U-65). It SHALL judge argument quality only, say nothing that wasn't argued, write in the debate's language, named explicitly, and, under You decide, word the rationale as the arbiter's view.

#### Scenario: You decide
- **WHEN** the arbiter's scores favour the Opposition and the user picks the Proposition
- **THEN** the banner names the Proposition, and the rationale says "The arbiter's scores favoured the Opposition …"

### Requirement: The prose is validated
The prose SHALL hold every expected subject: 3–5 points per side (2 for a side with one or two arguments), 2–4 per panellist; a key disagreement of at most 30 words; a rationale of at most 60. Longer lists SHALL be cut to the maximum. Invalid JSON SHALL be repaired locally, then retried once, then treated as failed.

#### Scenario: Too many points
- **WHEN** the prose gives the Proposition 7 points
- **THEN** the verdict keeps the first 5

### Requirement: Verdict fallbacks never hang or fake
A failed prose SHALL keep the scores and winner, with each side's first sentences quoted from the real arguments and a note. Failed scores under Arbiter SHALL give a summary only (`decidedBy: "none"`, banner SUMMARY), and under You decide the user's pick with no scores; both with a note. A cap refusal SHALL pause, and resuming in the verdict phase with no verdict SHALL run the verdict work again.

#### Scenario: Scores fail under Arbiter
- **WHEN** the `rubric` request fails twice
- **THEN** the verdict has `decidedBy: "none"`, the banner reads SUMMARY, and the log says "The arbiter couldn't score this debate; here is the summary."

#### Scenario: The cap-refusal hang is gone
- **WHEN** the verdict's prose is refused by the daily cap, the user raises the cap and resumes
- **THEN** the verdict work runs again, and the debate ends with a verdict

### Requirement: The verdict work starts at the last closing
The verdict work SHALL start at the last argument's `turn.end` of the last phase, also under You decide, unless Extend is set. Extend and Skip SHALL discard it. End with verdict SHALL wait for a streaming argument's end and reuse work whose transcript matches, so the same verdict is never paid twice.

#### Scenario: End right after the last closing
- **WHEN** the last closing ends and the user presses End and "Go to verdict now" during the pause
- **THEN** one `rubric` request and one `verdict` request are made in all

### Requirement: The pick never waits for the verdict
`debate.pickStrongerCase` SHALL record the side and be accepted at once. The verdict SHALL be delivered when its work finishes, with `decidedBy: "user"` and the picked `strongerCase`. If no work exists, the pick SHALL start it. Pause and End SHALL stay responsive while it runs.

#### Scenario: A click before the work is done
- **WHEN** the user picks the Proposition while the rubric request is still held
- **THEN** the command is answered at once, and the verdict arrives when the work finishes, with `strongerCase: "prop"`

### Requirement: Naive's single-call verdict
Under `naive`, one DeepSeek JSON call SHALL write the scores (0–10 per side per criterion), the stronger case, the summary, the key disagreement and the rationale. Its stronger case SHALL be used as written. It SHALL use the same settings, purpose, validation and fallbacks as the prose.

#### Scenario: The yardstick's verdict
- **WHEN** a `naive` debate reaches an Arbiter verdict
- **THEN** exactly one `verdict` request is made and no `rubric` request

### Requirement: Scripted keeps the mock's verdict
`scripted` SHALL keep the mock's random verdict and its simulated `verdict` call (none for a pick), and the mock SHALL record that charge under category `chat`.

#### Scenario: Same cost category in both clients
- **WHEN** a scripted Arbiter verdict is delivered by the backend and by the MockClient
- **THEN** both record the charge under category `chat`

### Requirement: The early-end estimate
"Go to verdict now (≈ $x)" SHALL show an estimate computed from the price table and the current price period, for the dearer of the real verdicts, never a fixed amount.

#### Scenario: Peak prices the prose higher
- **WHEN** the price period is peak
- **THEN** the label's DeepSeek part uses the peak multiplier and its Jev part doesn't, so it reads ≈ $0.0026 instead of ≈ $0.0014

### Requirement: The verdict carries the margin
A verdict whose bars Jev scored SHALL carry `margin`, the lead (0–10 scale) a side's mean needs over the other's to
win (`verdict.margin`). The verdict screen SHALL show each side's mean over the criteria and that lead under the bars
(U-61), so a narrow win reads as one.

#### Scenario: A narrow win
- **WHEN** Opposition's mean is 8.83 and Proposition's 8.45 with margin 0.25
- **THEN** the screen shows "Proposition 8.45 · Opposition 8.83 · a win needs a 0.25 lead"

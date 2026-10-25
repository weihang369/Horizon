# M11 labelling rule: `who_next`, the debate member slice, the debate emotion slice and the judge sets

Written and committed **before any item is labelled** (debate design D17, D18, D21, D29; doc 02 B2; the M8 D38, M9 D27
and M10 discipline). Labels are written blind: no Jev answer to an item is seen before its label is final. A label
changes after a run only when this rule was misapplied, and the change is listed in `docs/ai/checks/m11.md` with its
reason. `evals/reviews/m10-labels.md`'s "Every set" section applies to every set here unchanged (one item, one
decision; judge the scene, not the labeller; no copying from the bank; language; hash splits that never move).

The user delegated the labels and the B2 review to the team (D29.2, 2026-10-14). The team labels as a reviewer would:
from the item alone, before any answer.

## `who_next` (group Next speaker; M10 carry-over, D17)

- 40 items from the two frozen group transcripts (`evals/transcripts/long_group_*.json`), 20 per world, all English.
- **The cut:** right after a character's line that asks no character directly (the Next speaker is pressed with nobody
  named). The candidates are the two other characters (the last speaker never speaks twice in a row, G6).
- **The acceptable set is one character:** with two candidates, accepting both measures nothing. An item is written
  only where one candidate is clearly the next voice, by m10-labels.md's reasons, strongest first: the line names them
  or speaks about them (credits, teases, quotes or contradicts them); it touches their field; their temperament fits it
  far better.
- **Never because of who spoke least.** The state carries no `last_spoke` (v3), and the label never uses it.
- The items are built by the live cast-plan state (`kind: "next"`, `last_spoke=False`) with `quoted_latest` =
  "Name: line", as the group mode builds it.

## The debate member slice (`evals/datasets/debate_member/`; D21)

- Natural slots from the 13 committed debate histories where two or three members of a side are eligible (rebuttal,
  closing and panel slots), cut with the live debate-plan state, plus written variants to reach the counts.
- **The acceptable set is one or two members.** Two only when both are equally placed. A slot where any member would
  do equally is not written as an item.
- **Reasons, strongest first:**
  1. the last opposing argument is in their field (the motion's medicine to the physician, its economics to the
     economist, its law to the litigator; the shop, the code, the trains);
  2. it attacks or answers something they argued themselves (their own latest argument, in the state);
  3. for a closing: the member whose earlier arguments carried the side's case, so they can sum it up;
  4. for a panel: the panellist most directly contradicted by the last argument.
- **`single`** marks a slot whose fixed-order answer (the first eligible member) is acceptable alone; the single-answer
  lift is measured over the other items (D21).
- **Never the fixed order as such:** the first eligible member is acceptable only by the reasons above.

## The debate emotion slice (`evals/datasets/emotion/emotion_debate.jsonl`; D29.1)

- 40 items: 30 `emotion_line` (a rebuttal or closing about the argument just made) and 10 `emotion_debate_opening`.
- M9's rule (`m9-labels.md`: one or two faces, milder wins, `keep_ok` when nothing would move the speaker) applies,
  read for a debater: an argument against them may make them `angry` only when it is personal or misrepresents them;
  a sharp point usually makes them `thinking`; a point that collapses on its own may make them `happy` (confident).
- An opening face is labelled from the motion and the side alone: usually `neutral` or `thinking`; `happy` when the
  side is plainly one they relish arguing, by their profile.

## The debate-quality judge sets (D21)

- `judge_keeps_side` ("does the argument break its side?", yes = failure) and `judge_engages` ("does it answer nothing
  that was said?", yes = failure): 30 real items each, from the committed histories, and 30 planted.
- **Real items** are labelled from the argument and its context alone. A concession of a small point that the speaker
  then says doesn't change the answer is not breaking the side (P5's rule). An argument that answers the other side's
  latest point, even badly, engages.
- **Planted items** are the real arguments rewritten by D21's plant prompt to fail on purpose: one that switches side
  or concedes the motion; one that ignores everything said and starts a new topic. Each planted argument is read
  before it is used; a rewrite that doesn't plainly fail is dropped.

## `judge_starts_new` (D18)

- 30 real items: M10's free-run watch lines, including its 7 steered lines, labelled blind; 30 planted (lines rewritten
  to only react, wrap up or hand off).
- **"Does the line start nothing new?" (yes = failure):** yes when it only reacts, agrees, recaps, says goodbye, hands
  the decision to someone, or waits; no when it brings in an event, a discovery, a new plan or a new question that
  moves the scene.

# M10 labelling rule: `who_speaks`, `talk_finished` and the watch emotion slice

Written and committed **before any item is labelled** (group-watch D23, D27; doc 07 G11; doc 02 B2; the M8 D38 and
M9 D27 discipline). Labels are written blind: no Jev answer to an item is seen before its label is final. A label
changes after a run only when this rule was misapplied, and the change is listed in `docs/ai/checks/m10.md` with its
reason.

## Every set

- **One item, one decision.** An item holds the state exactly as the live code builds it (the cast plan's state for
  `who_first`, `who_scene`, `talk_finished` and the watch faces; the follow plan's state for `who_second`), the option
  values, the seed, the label and its source.
- **Judge the scene, not the labeller.** The question is what a good host of this group (or director of this scene)
  would do with these characters, given their roles and the recent lines.
- **No copying from the bank.** Hand-written lines never reuse the bank's examples or six-word runs of its wording
  (`horizon eval overlap` enforces it).
- **Language.** A non-English line is labelled for what it says, exactly as an English one, and states its language in
  `lang`. Only English is scored for accuracy; other languages only need to run (the user's rule, 2026-10-12).
- **Splits** come from the hash rule at creation and never move (`split_for`). Each who-speaks part has at least 20
  test items.

## `who_speaks`: who answers, and who speaks up

### The acceptable set

- **One or two characters.** Two only when a reasonable host could pick either. Never all three: a set that accepts
  anyone measures nothing, so a line that any of them could answer equally is not written as an item.
- **Reasons that make someone acceptable**, strongest first:
  1. the line names them or asks about them, without an @mention (a mention never reaches Jev);
  2. the line is in their field (medicine, labour markets, the law; flowers and the shop, games and code, trains and
     punctuality) or touches their stated life (Takeshi's daughters, Rin's showcase, Hana's shop);
  3. the line answers or picks up what they just said;
  4. their temperament fits the line far better than the others' (Victor for a devil's-advocate claim, Mei for a
     confident number, Rin for a morning complaint).
- **Never because of who spoke least.** Fairness is the baseline's job and the guard's; the label is about fit.

### `who_first` (group first slot; no `none`)

- 60 items: English 50, Malay 5, Chinese 3, mixed 2.
- The candidates are the three awake characters; `last_spoke` records the character lines since each last spoke in
  the item's context (for the least-recently-spoken baseline).

### `who_second` (group second slot, after a first reply; with `none`)

- 90 items, about 65 % `none`: English 78, others 12.
- **`none` items** (`none_ok`): the first reply already did the job, and a second voice would only repeat it or crowd
  the user: a thank-you or a goodbye, a plain fact asked and answered, logistics, a question to the first replier
  alone, small talk that got its answer, a personal disclosure the first reply met with care.
- **Someone items** (acceptable set, never `none`): the user asked more than one person ("you two", "everyone",
  "what do you all think"); the first reply made a claim another character would contest from their field; the first
  reply spoke about another character or put a question to them; the first reply got something wrong in another's
  field; the line was a debate a second view clearly serves.
- The first replier is never a candidate.

### `who_scene` (watch next speaker; no `none`)

- 60 items from the two committed watch histories, each cut at a turn with at least 3 awake characters: English 52,
  others 8. The last speaker is never a candidate.
- Acceptable: whoever the last line addressed or provoked, or whose stake in the premise the scene has just touched.
- `round_robin_next` is the next character in cast order after the last speaker (the round-robin baseline).

## `talk_finished` ("is the talk finished?", a noul)

- About 120 items, at least 60 `yes`: English 100, others 20.
- **`yes`:** the thread has stopped moving: goodbye or good-night loops, polite agreement bouncing back and forth
  ("absolutely" / "couldn't agree more"), the same point made again in new words, everyone conceding with nothing
  left open.
- **`no`:** something is still open or moving, even slowly: a question waiting, a disagreement not settled, new
  information just landed, a plan half made, or the scene right after a director's note (the note is the new
  direction).
- **Judge the last few lines, not the whole scene.** A lively scene can still end in a loop; a quiet one can still
  be moving.

## The watch emotion slice (in `evals/datasets/emotion/`)

- 40 items: 32 `emotion_line` (a scene turn), 8 `emotion_opening` (the first turn, the premise and no lines).
- M9's rule applies unchanged (`m9-labels.md`: one or two faces, milder wins, `keep_ok` when nothing would move
  the character), with the watch state built live: the premise, the scene's lines and the character's face now.
- An opening face is labelled from the premise alone: usually neutral or thinking, and something else only when the
  premise plainly sets a mood for that character (a storm trapping them: thinking or surprised; a celebration:
  happy).

## Review

- B2's sample (max(15, ⌈n/5⌉) per set) is checked against this rule. The user delegated the review (D27), so the
  labeller does a recorded second pass in `evals/reviews/m10-*.md`, before any paid run, and says so plainly. The
  held-out test split, scored once with the floor chosen on dev, is the safeguard.

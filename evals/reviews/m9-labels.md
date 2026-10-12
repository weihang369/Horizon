# M9 labelling rule: the `emotion` and `reactions` sets

Written and committed **before any item is labelled** (turn-plan-emotion D27; docs/ai/06 E8; doc 02 B2; M8 D38's
discipline). Labels are written blind: no Jev answer to an item is seen before its label is final. A label changes
after a run only when this rule was misapplied, and the change is listed in `docs/ai/checks/m9.md` with its reason.

## Both sets

- **One item, one decision.** An item holds the state exactly as the live code builds it (the plan state for
  `emotion`, the reaction state for `reactions`), the option values, the seed, the previous face, the acceptable
  faces, `keep_ok` (emotion only) and its source.
- **The faces are E1's seven:** neutral, happy, sad, angry, surprised, thinking, embarrassed. `none` is not a face.
- **One or two acceptable faces.** Two only when a reasonable reader could defend either (for example sad or thinking
  after a hard question about a loss). Never three: a set that accepts almost anything measures nothing.
- **Judge the character, not the reader.** The question is how *this* character feels, given their card line and the
  recent lines, not how the labeller would feel.
- **Milder wins.** Between a strong face and a milder one that both fit, prefer the milder (thinking over angry for a
  firm disagreement; neutral over happy for plain politeness). This matches E1's `not_for` lines.
- **No copying from the bank.** Hand-written lines never reuse the bank's examples or six-word runs of its wording
  (`horizon eval overlap` enforces it).
- **Language.** A non-English line is labelled for the feeling it carries, exactly as an English one. Its item states
  the language in `lang`. Non-English items show direction only (the user's rule: English must work well, other
  languages only need the right language and face; their quality is v2).
- **Splits** come from the hash rule at creation and never move (`split_for`).

## `emotion` (100 items)

- **Previous face.** Each item has one. Roughly: a third neutral, the rest spread over the other six, so the merge and
  the fade are both exercised.
- **`keep_ok`** is true when nothing in the latest line would visibly move the character: small talk, a plain fact, a
  line that continues the current mood. Then keeping the previous face (after E3's fade: a kept surprised or
  embarrassed face becomes neutral) is correct.
  - From a **neutral** previous face, "keep" and "neutral" are the same answer (D12's merge).
  - **The cap:** between 20 and 30 items have `keep_ok` true. Counted by the builder; the build fails outside it.
- **The acceptable set** lists the face(s) the line should produce. When `keep_ok` is true, the set may still list a
  face (a line that fits both keeping and a gentle change).
- **Turn kinds:** 1:1 replies 55, group replies 30, greetings 15. A greeting is labelled from the relationship and the
  time since the last chat, as `emotion_greeting` asks: usually happy or neutral, and something else only with a
  reason in the context (they parted on a quarrel; the last chat was about a loss).
- **Languages:** English 80, Malay 10, Chinese 5, mixed 5.

## `reactions` (90 items)

- **One listener per item**, with their face now. The line is someone else's.
- **The acceptable set** is the listener's visible reaction, or `none` when the line wouldn't visibly move them.
  - A line **aimed at the listener** (their name, a question to them, praise or a jab at them) is rarely `none`.
  - Small talk, logistics and lines between two other people are usually `none`.
  - **Same face as now** counts as `none`: a reaction that doesn't change the face doesn't show.
  - **The cap:** at most 27 items list `none`. Counted by the builder.
- **Debate:** `side` is in the state. A strong point from the other side reads as thinking or angry, rarely happy; a
  teammate's good point reads as happy or neutral.
- **Modes:** group 40, debate 25, watch 25. **Languages:** English 75, others 15.

## Review

- B2's sample (max(15, ⌈n/5⌉) per set) goes to the user in `evals/reviews/m9-emotion.md` and
  `evals/reviews/m9-reactions.md`. Two or more disagreements in a set: that set is relabelled under this rule.
- If the user delegates the review again (as in M8), the labeller does a recorded second pass and says so plainly; the
  held-out test split, scored once with the floor chosen on dev, is the safeguard.

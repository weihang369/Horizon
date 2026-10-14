# M11 label review (the delegated second pass, D29.2)

The user delegated the labels and the B2 review to the team (debate design D29.2, 2026-10-14). This is the labeller's
recorded second pass over the sets task 10.3 built from the committed debate histories, done before any paid run on
them and before any Jev answer to these items was seen. Each sample is B2's size, max(15, ⌈n/5⌉), drawn by
`horizon eval review` with the seed shown, and each sampled label was re-read against `m11-labels.md` (committed before
the labels). The held-out test split, scored once with the floor chosen on dev, remains the safeguard. Plainly: this is
not an independent reviewer.

| Set | Items | Sample | Seed | Disagreements | Action |
|---|---|---|---|---|---|
| `debate_member` (pass 1) | 90 | 18 | 1110 | 1, and one rule misapplied across the set | 21 natural items replaced by written variants |
| `debate_member` (pass 2, the rebuilt set) | 90 | 18 | 1114 | 0 | none |
| `emotion/emotion_debate` | 40 | 15 | 1111 | 2 | the whole set re-read; three labels widened |
| `judges/judge_keeps_side` | 60 | 15 | 1112 | 0 | none |
| `judges/judge_engages` | 60 | 15 | 1113 | 0 | none |
| `who_speaks/who_scene_fresh` (10.11) | 40 | 15 | 1115 | 0 | none |
| `emotion/emotion_watch_2` (10.11) | 40 | 15 | 1116 | 1 | that item widened |

The sampled ids are in `m11-review.json`.

## Notes on the pass

- **`debate_member`, pass 1.** The sample held two two-member items (`dmm-012`, d03#13, Victor or Sofia) whose slot
  has only those two candidates. `m11-labels.md` says a slot where any member would do equally is not written:
  accepting both of two candidates measures nothing. The rule had been misapplied to every such slot, so all 20
  two-of-two labels were removed (d01#8, #13; d02#8; d03#8, #12, #13; d04#7, #8, #13; d05#8, #13; d06#8, #13; d07#8,
  #13; d08#8, #12, #13; d09#9, #15), with d13#14, whose re-reading found Mei's closing contradicts neither panellist
  plainly. 21 written variants took their places, each aimed plainly at one member's field, in those slots (the other
  member where a variant already existed) and in slots without a natural item (d11#7, #8; d12#7, #8; d13#9, #13). The
  two remaining two-member items (d10#14, d13#8) each have a third candidate who is not acceptable. The rebuilt set:
  90 items, 88 single-answer, English 80 / Malay 5 / Chinese 3 / mixed 2, 36 test; the fixed-order answer is acceptable
  in 46 of 90.
- **`debate_member`, pass 2.** Every sampled item points to its member by field or by name: a law question to Victor,
  a labour-market price to Mei, a school timetable to Daniel, a signal box to Takeshi, a small shop's attention to
  Hana. The Malay, Chinese and mixed items were checked for what they ask, not for their language.
- **`emotion_debate`.** Two disagreements. `emd1-013` (Hana, after her dad's train metaphors and dad joke) was `happy`
  only, and `emd1-027` (Hana, after Aiko's lantern parade and the Larsen twins' asthma) `happy` only; a reasonable
  reader could see either thinking about the point to answer, so both became `happy, thinking`. Two disagreements
  reach the rule's relabel trigger, so all 40 were re-read: one more label widened, d08#7 (Bram, after Aiko's "steady
  for farms can mean famine for children", which he can fairly hear as an accusation) to `thinking, angry`. The rest
  stand.
- **`judge_keeps_side`.** The planted items each argue plainly for their own side, so asked as the other side they break
  it. The real items keep their side through every concession (Amara would fund Sofia's pilot and still asks for the
  motion; Mei calls randomised quarters "not the motion" from the opposition); the two real `yes` items are Bram's
  (Proposition) d10#6 ("the wrong tool aimed at the wrong ditch") and d10#18 ("Against the motion.").
- **`judge_engages`.** The real rebuttals and closings each answer the other side's latest point, so the real items are
  all `no` and the planted items carry the `yes` labels; that limit is recorded with the judge's validation.
  The first planted items were each speaker's own opening in their rebuttal or closing slot (52 read, 22 dropped
  because the opening already answered the other side's opening). They failed B4 (planted 23 of 30), and the user
  chose to rebuild them (D31.2): 91 DeepSeek rewrites over four instructions, every one read against the arguments
  the judge sees with it, 59 dropped (a contrast with a point made, a concession, a name, the other side argued, a
  repeated text) and 32 kept; the set takes the first 30 in turn. All 30 planted `judge_keeps_side` candidates were
  kept.
- **`who_scene_fresh` (10.11).** Cut from the three 10.10 watch scenes after reading them, before any v3 answer.
  Each sampled cut points to one of its two candidates by name ("Amara, draft it"), by an answer owed ("Dad, shop
  rules can't be made up"), or by field (a nurse-roster point to the emergency physician). Cuts where both candidates
  fit equally were never written.
- **`emotion_watch_2` (10.11).** One disagreement: `emw21-010` (Amara hearing her line will go in the minutes, with
  seven minutes on the clock) was `happy` only; she may as fairly be thinking about the draft, so `happy, thinking`.
  Under the relabel trigger, so the rest stand. The six openings ask the opener and one more of the cast each, from
  the premise alone (three scenes, D20's six).

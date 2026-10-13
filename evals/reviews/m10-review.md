# M10 label review (the delegated second pass, D27)

The user delegated the label review (group-watch D27). This is the labeller's recorded second pass, done before any
paid run and before any Jev answer to these items was seen. Each sample is B2's size, max(15, ⌈n/5⌉), drawn by
`review_sample` with the seed shown, and each sampled label was re-read against `m10-labels.md` (committed before the
labels). The held-out test split, scored once with the floor chosen on dev, remains the safeguard. Plainly: this is
not an independent reviewer.

| Set | Items | Sample | Seed | Disagreements | Action |
|---|---|---|---|---|---|
| `who_speaks/who_first` | 60 | 15 | 1010 | 0 | none |
| `who_speaks/who_second` | 90 | 18 | 1011 | 0 | none |
| `talk_finished` | 120 | 24 | 1012 | 0 | none |
| `emotion/emotion_watch` | 40 | 15 | 1013 | 1 | that item relabelled |
| `who_speaks/who_scene` (pass 1, task 10.2) | 60 | 15 | 1014 | 2 | the whole set relabelled |
| `who_speaks/who_scene` (pass 2) | 60 | 15 | 1015 | 1 | that cut replaced |
| `who_speaks/who_scene` (G11's growth, items 61–100) | 40 | 15 | 1016 | 0 | none |

The sampled ids are in `m10-review.json`.

## Notes on the pass

- **`who_first`:** every sampled line has a clear owner by field or by name (a headache → Amara; a jobs number →
  Mei; a shop window → Hana; punctuality → Takeshi). The two two-character sets (clinics or rebates; a heatwave as a
  health or an economic emergency) are lines either specialist could fairly take first. The Malay and Chinese items
  were checked for what they ask, not for their language.
- **`who_second`:** the 15 `none` items are goodbyes, thanks, a plain fact answered or small talk that got its answer;
  none needs a second voice. The three someone items each have the rule's reason: a health claim answered only on
  money (→ Amara), a question put to Victor that Mei answered half of (→ Victor), and an economics claim answered only
  on its human cost (→ Mei).
- **`talk_finished`:** the `yes` items are goodbye loops, agreement loops and the same point repeated; the `no` items
  each leave something open (a plan, a question, a disagreement, fresh news). One closer call, kept as labelled:
  "For a student game? Dad, it's insane." (`tlk-076`) is `no`, because the news has just landed and the scene is
  still reacting to it.
- **`emotion_watch`:** one disagreement. `emw-002`, Takeshi hearing "A thousand!" about Rin's player count, was
  labelled `happy` only. A reasonable reader could see him proud (`happy`) or puzzled by what the number means
  (`thinking`); the rule allows two faces exactly then, so the set became `happy, thinking`. One disagreement is
  under the rule's relabel trigger (two or more), so the rest of the set stands.
- **`who_scene`** (task 10.2, labelled after reading both watch histories, before any Jev answer; all English by the
  user's choice). Each cut has two candidates, the characters who didn't just speak, so every set holds exactly one
  name. Pass 1 found two labels that don't hold: Meridian #22 ("someone going quiet when they were chatty" only
  implies Victor) and #72 (Mei asked Victor to read the clause and Amara has the clinic's stake; either could fairly
  answer). Two disagreements trigger B2's relabel, so all 60 cuts were re-read with the reading the rule implies made
  explicit: a direct address or question outranks a mention; a cut where both candidates are addressed directly, or
  both are only mentioned, isn't an item; otherwise the one named, or plainly in their field, is the label. Nine cuts were dropped (Meridian #3, #7, #22, #45, #69, #72, #77; Sunny Hollow #16,
  #36) and nine clear ones added. Pass 2 found one more of the same kind, Meridian #39 (Victor mentions Amara and Mei
  and addresses neither); it was replaced by Sunny Hollow #11 (Rin: "the clipboard always wins, hana"). For
  transparency: the dropped cuts mostly agreed with the round-robin baseline (7 of 9 at pass 1) and the added ones
  mostly didn't, so the baseline's test-split score moved from 16/20 to 11/20 between the passes. The cuts were chosen
  by the rule above without looking at the baseline; the shift says that ambiguous cuts in round-robin histories
  tend to name the next character in order.
- **`who_scene`'s growth** (task 10.3; G11: the first 60's test interval, 0.43–0.82, straddled 0.80; the user chose
  to grow). 40 cuts from two new 50-turn naive histories (`meridian_inquiry`, `sunnyhollow_market`), labelled blind
  under the same reading before any Jev answer to them, numbered 61–100 after the first 60 so no id or split moved.
  46 cuts qualified; the six weakest mention-only ones (Sunny Hollow Market 11, 14, 25, 28, 36, 37) were left out to
  keep B2's 40. The sample of 15 found no disagreement.

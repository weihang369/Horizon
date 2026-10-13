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

# M12 label review (the delegated second pass, D31.2)

The user delegated the labels and the B2 review to the team (rag design D31.2, 2026-10-14). This is the labeller's
recorded second pass over the sets phase 10 built, done before any paid run on them and before any Jev answer, search
result or reply for these items was seen. Each sample is B2's size, max(15, ⌈n/5⌉), drawn with `review_sample` (the
function behind `horizon eval review`) with the seed shown. Each sampled label was re-read against its source text and
`m12-labels.md`, which was committed before the labels (688005a). The held-out test split, scored once with the
thresholds chosen on dev, remains the safeguard. Plainly: this is not an independent reviewer.

| Set | Items | Sample | Seed | Disagreements | Action |
|---|---|---|---|---|---|
| `retrieval` (pass 1) | 205 | 41 | 1210 | 2 (`ret-a077`, `ret-n016`) | the whole set re-read; 6 items relabelled |
| `retrieval` (pass 2, the relabelled set) | 205 | 41 | 1216 | 1 (`ret-u028`) | that item replaced |
| `docs` | 121 | 25 | 1211 | 0 | none |
| `standalone` | 100 | 20 | 1212 | 0 | none |
| `english` | 40 | 15 | 1213 | 0 | none |
| `judges/judge_notfound_says` (planted) | 30 | 15 | 1214 | 0 | none |
| `judges/judge_notfound_cites` (planted) | 30 | 15 | 1215 | 0 | none |

The sampled ids are in `m12-review.json`. The Not-found judges' 30 real items per judge are labelled from the first
end-to-end run (task 11.8) under the same rule, and their review is added here then.

## Notes on the pass

- **`retrieval`, pass 1.** Both disagreements were the same mistake: a rule whose conditions must all hold had one
  condition graded 1. `ret-a077` (when is evidence relevant?) needs Rule 401's (a) *and* (b). `ret-n016` (when can a
  treatise come in under 803(18)?) needs (A) *and* (B). Neither condition answers alone, and both carry the answer, so
  both are grade 2, as `ret-a087`'s two-part hearsay definition already was. Two disagreements reach the rule's
  relabel trigger, so all 205 were re-read against their sources. Four more labels changed:
  - **`ret-f029`:** Rule 410(a)'s lead-in ("not admissible against the defendant…") is what makes (a)(4) an answer.
    It went from 1 to 2.
  - **`ret-n004`:** the page-5 sushi-rice tip is both sentences of the page, so "three cups of rice and a splash more
    vinegar" went from 1 to 2.
  - **`ret-n007`:** "what does page 9 say about the pilot wards" is answered by the pilot's description as much as by
    its results, so the description went from 1 to 2.
  - **`ret-a050` and `ret-x006`:** their escalation span had dropped the sentence's opening, "Escalate any headache
    that is sudden and severe ("thunderclap")". A thunderclap headache is the first symptom asked about, so the span
    is now the whole sentence.
- **`retrieval`, pass 2.** One disagreement. `ret-u028` ("Do federal employees get their birthday off?") was
  unanswerable, but the holidays fact sheet lists every designated holiday, so the list answers it by absence. It is
  replaced by a question no source answers ("How many hours of sick leave does a federal employee earn each pay
  period?"; the handbook mentions sick leave only as a leave category, never an accrual rate). The other unanswerable
  items sampled hold no such reading: no source gives a teenager's calorie target, a fracture's triage grade, the
  pilots' length or a spousal privilege. Every answerable item's span was read in place: it answers in the user's
  terms, it isn't over-long, and where a second place says the same thing (Mei's fact sheets and handbook) every
  place is labelled.
- **`docs`.** The sampled items are `yes` when the message turns on what the titles could hold: the fatigue review's
  shifts and burnout, the triage guide's headaches, the pilots, the moot notes, and Grandma's recipes. They are `no`
  for small talk, feelings, and facts outside the titles, including in the character's own field (Mei on the minimum
  wage, a coffee stain for Amara).
  - Read in full, the debate item `dcs-111` (d13#13) stays `yes`: Amara's closing turns on "the round-the-clock
    staffing that Mei's range shows is the real expense", which is the pilots' shift-based figure.
  - **Found while building, not a label:** late in the panel debate and the three-a-side debate (d13#7, d13#12, d09#8,
    d09#9), X9's 2,000-token cap drops every member's gate, so live never asks "needs documents?" there. Those cuts
    are not items, and the finding goes to `docs/ai/checks/m12.md`.
- **`standalone`.** Every follow-up leans on its earlier lines ("Which caveat?", "With what?", "What's the other?").
  Every standalone message names its subject, even where the earlier lines share it.
- **`english`.** English with a borrowed word or a place name (calamansi, Shinkansen, ramen) is `yes`. Malay and
  Chinese are `no`, and so are mixed sentences that switch language mid-sentence ("is that normal ke?", "Grandma 的
  rainy-day soup").
- **The planted Not-found items.** Each sampled reply carries exactly the failure it names, and its passages are real
  quotes from that character's sources (the builder checks each one).
  - **`says`:** a Malaysian legal cap taken from the IOM recommendation; a baking time added beside a correct [1];
    "every employer gives it" for Columbus Day.
  - **`cites`:** the five-sites and ninety-five-percent number changes; an [n] with nothing kept; "teleworkers abroad
    lose every federal holiday" pinned on the Inauguration Day passage.
  - Some `says` items also carry a citation fault, and some `cites` items an incomplete answer. Each file's label
    only concerns its own judge, so this changes no label.

# M15 labelling rule: the third `reactions` set (`rea3`)

Written by the team on 2026-10-19 for images-music 8.13 (design D16: "a reworded question re-versions `reaction` and
needs a fresh blind set"). The rule is `evals/reviews/m9-labels.md`'s `reactions` section and its 2026-10-12 amendment,
unchanged:

- One listener per item, with their face now; the line is someone else's.
- The acceptable set is the listener's visible reaction (one or two of E1's seven faces), or `none` when the line
  wouldn't visibly move them. The listener's face now is never in the acceptable set.
- Lines that clearly concern or move the listener get a reaction: their name with news, praise, a jab, a confession or
  a correction aimed at them, or news that plainly changes their day.
- Truly mild lines are `none`: logistics, weather, small talk, a thank-you to the chair, a calm argument or a plain
  fact that isn't about the listener.
- Debate: a calm argument from the other side is `none`; only a pointed line (the listener named, mocked, corrected or
  conceded to) gets a reaction.
- At most 27 items accept `none`. Modes: group 40, debate 25, watch 25. Languages: English 75, others 15.

**Blind:** every line is written for this set, and every label is final before any Jev answer to a `rea3` item exists.
They are committed with this note before the run. The test split is read once, at the floor chosen on dev with D36's
grid, and is never relabelled after a run. A label changes only if this rule was misapplied, and such a change is
listed in `docs/ai/checks/m15.md` with its reason.

**Review:** the user delegated M15's decisions to the team (2026-10-19). As in M9 and M12, the held-out test split is
the safeguard.

# M12 labelling rule: the retrieval questions, the gate sets and the Not-found judges

Written and committed **before any item is labelled** (rag design D22, D31.2; doc 02 B2; doc 10 K14; the M8–M11
discipline). Labels are written blind: no Jev answer, no search result and no reply for an item is seen before its
label is final. A label changes after a run only when this rule was misapplied, and the change is listed in
`docs/ai/checks/m12.md` with its reason. `evals/reviews/m10-labels.md`'s "Every set" section applies to every set here
unchanged: one item, one decision; judge the item, not the labeller; no copying from the bank; language; hash splits
that never move.

The user delegated the labels and the B2 review to the team (D31.2, 2026-10-14). The team labels as a reviewer would:
from the item and its source text alone, before any answer. The held-out test split is the safeguard.

## The retrieval questions (`evals/datasets/retrieval/`; D22)

The sources are what the run database loads for each seed character:
- **Amara:** the four NIOSH nurse-training modules, plus the seed's *Meridian Shift Fatigue Review 2025* and *ED triage
  guidelines*;
- **Hana:** the four USDA ARS nutrition articles, plus *Grandma's recipe notebook*;
- **Mei:** the four OPM work-schedule documents, plus *Four-day week pilot summaries* (the failed appendix holds no
  pieces);
- **Victor:** Federal Rules of Evidence Articles IV, VII and VIII, plus *Moot court notes*.

A question is asked of one character about that character's own sources, as a user would ask in 1:1.

### The mix (D22)

| Kind | Count | Rule |
|---|---|---|
| answerable | 100 | the sources answer it. 10 need two passages (two grade-2 spans in different places, neither answering alone). 10 are answered only in part (`partly`): the message asks two things and the sources hold one; the held part's span is grade 2. About a quarter are about the seed documents. |
| unanswerable | 40 | on the same topics as the character's sources, and nothing in them answers it, checked by reading the whole of each source. The question must be one a user would plausibly ask that character. No spans. |
| follow-up | 30 | two earlier lines (`Name: text`) and a message that can't be understood alone (a pronoun, an ellipsis, a missing subject). Labelled for the question the three lines ask together. |
| non-English | 15 | Malay 8, Chinese 7, all answerable, labelled on the English source text. |
| naming | 20 | the message names a document the way a person would (by its subject or its heading, never by file name). 12 also name a section (a module, a rule, an appendix, a heading, or a seed page or section). `named` records the names used. |

Characters share the questions about evenly. Mei's handbook is long, so her questions spread across its sections.

### The labels

- **A label is an exact quote** from the source text: the corpus document as stored (UTF-8, nothing else), or the
  seed's authored piece. It must sit in exactly one place (the builder refuses a missing or doubled quote).
- **Grade 2 (answers):** the quoted text alone answers the question, or the part it is needed for.
- **Grade 1 (partly):** the quoted text helps (a needed condition, a definition, half of a range) but does not answer
  alone.
- **Quote the smallest span that carries the answer,** usually one or two sentences. Never a whole section: a span is
  covered when a piece holds 80 % of its characters, and an over-long span punishes small pieces unfairly.
- **Every place that answers is labelled.** When two places answer the same question equally (the fact sheet and the
  handbook say the same rule), both are grade 2. A question is not written if it has more than three such places.
- **Unanswerable is checked by reading,** not by searching: a near miss (the same topic, a different number, a
  different group of employees) is still unanswerable, which is the point of the set.
- **No question copies its span.** A question asks in the user's words, not the source's; a naming question may use the
  document's title words.

## "Needs documents?" (`evals/datasets/docs/`; D22, B2, B5)

- **About 120 items, at least 60 `yes`;** English 100, Malay 10, Chinese 6, mixed 4. Every mode: 1:1, group, watch and
  debate.
- **The state is the live one:** the 1:1 plan state, the cast plan state (group and watch) or the debate plan state,
  built by the live builders, with the candidate's real seed document titles in `quoted_documents`. The question is
  asked under its live key `docs:{characterId}` with the candidate's name.
- **`yes`:** the line being answered asks about, or turns on, facts, figures, rules or details that the candidate's
  documents could plausibly hold, judged from their titles and the character's field. **`no`:** small talk, feelings,
  plans, opinions, jokes, or facts plainly outside the documents' subject.
- **The hard cases are written on purpose:** a factual question outside the titles' subject (`no`), an opinion that
  turns on a figure the documents hold (`yes`), a feeling about a shift that names nothing to look up (`no`).
- **Items come from** the committed transcripts, watch scenes and debate histories (cut at a line the candidate would
  answer), plus written variants to reach the counts.

## "Standalone?" (`evals/datasets/standalone/`)

- **100 messages, each with two earlier lines;** 50 follow-ups (`no`: they lean on the earlier lines) and 50 that stand
  alone (`yes`), even when the earlier lines are on the same topic.
- **A message stands alone** when a stranger reading only it would know what is asked: its subject is named, any `it`
  or `that` refers inside the message itself. A greeting with a full question after it stands alone.
- The 1:1 plan state, as the live code builds it.

## "English?" (`evals/datasets/english/`)

- **40 messages, 10 each in English, Malay, Chinese and mixed.** `yes` only for English. A borrowed word or a name
  ("roti canai", "Shinkansen") doesn't change an English sentence. Mixed means the sentences themselves switch language
  (`no`).
- The 1:1 plan state, as the live code builds it.

## The Not-found judges' planted items (`evals/datasets/judges/judge_notfound_*.jsonl`; K14, B4)

- **30 planted items per judge,** each a message from the retrieval suite's unanswerable or partly questions, the
  passages a deep turn could plausibly keep for it (real quotes from the character's sources, numbered as the reply
  sees them, or the none-kept line), and a hand-written reply carrying one planted failure. Label `yes` (every judge's
  "yes" is the failure). Each item names its failure in `failure`.
- **`judge_notfound_says` failures:** answers fully as if covered; answers the held half and never mentions the other;
  hedges ("it depends") without saying the documents don't cover it; covers it from general knowledge with no word
  about the documents.
- **`judge_notfound_cites` failures:** a fact the passages don't hold credited to "the documents" or "the guide"; an
  `[n]` with no matching passage; an `[n]` on a sentence its passage doesn't support; a number changed from the
  passage's.
- A planted reply is otherwise a good in-character reply: the same length and voice as a real one, so the failure is
  the only thing to catch.
- **The 30 real items** come from the first end-to-end run (task 11.8), read and labelled under this rule before the
  judges' answers on them are seen.

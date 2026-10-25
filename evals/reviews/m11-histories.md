# M11 debate histories: the review (task 10.1)

`horizon eval debate-history` (`naive`, 2026-10-14 18:00 KL, run `20261014T100033-debate-history-de436c`, $0.05571
against an estimate of $0.12760) wrote the 13 debates of `evals/debates/scripts/`: 154 arguments, every debate complete
(d01–d08 12/12, d09–d10 15/15, d11–d12 8/8, d13 12/12). Every argument was read before anything was built from them.
The run folder is kept (`.keep`): `naive/as-run/` holds the files as the run wrote them, and `naive/repair.json` every
line this review changed, with its text before and after and the response it was rebuilt from.

## What the review found

1. **The runtime lost text from 45 of the 154 arguments (29 %).** Each argument's full response is in the run's
   response store, and every difference between it (through the naive tag parser) and the stored message is text
   missing from the message, never text added: a first word (d02#4 "Thank" of "Thank you, Kai"), a last phrase (d01#15
   "…Anyone who gives" for "…Anyone who gives you one number is selling something."), or a piece mid-reply (d04#5,
   d09#4, d11#3, d13#5). The token events of those messages miss the same text, so a viewer never saw it either.
   **Cause:** the coalescer's trailing timer (session runtime, M3) takes its buffered text and then waits for the
   session's write lock to emit it; when the next delta, or the stream's end, settled the timer while it waited, the
   cancel dropped that text. A debate turn shares the lock with reactions, the debate plan and host lines, so the race
   was common there. **Fixed** in `sessions/turn.py` (a timer already writing is waited for, never cancelled), with
   `tests/sessions/test_turns.py::test_a_token_the_timer_is_writing_is_never_lost`, which loses both pieces on the old
   code. The fix changes no wire format or contract.
2. **`naive` writes its notes in 14 arguments.** The model opens `<e:thinking>`, plans the turn ("Keep it short,
   train metaphors, and land a dad joke."), closes `</e:thinking>`, then argues (11 times), or plans across repeated
   opening tags or a first paragraph (d02#12, d08#3, d13#10). The parser takes the first tag as the face and strips
   only `<e:…>`, so the notes and the closing tag were shown. Another 10 arguments end with a stray closing tag
   (`…Probably.</e:happy>`). `agent` never writes these tags (its prompt forbids them), so only `naive` is affected; one
   M8 group transcript (`long_group_meridian.json`) has the same closing tag. A `naive` parser or prompt change is a
   product choice and goes to the user with the phase's other findings.
3. **Four arguments end mid-sentence as the model wrote them:** d04#8, d05#5 and d13#8 hit the 320-token debate cap
   (`length`; their notes spent the budget), and d03#8 stopped there (`stop`). They stay as written.
4. **Three of the 13 `naive` verdicts fell back to the quoted summary** (the first sentence of each argument): d03 (the
   rationale 74 words, over 60), d07 (the rationale 61 words, the key disagreement 34, over 30) and d13 (the panel
   summary keyed `chr_seedSofia` for `chr_evalSofia`). Seven of the 13 needed the paid retry. The history verdict is
   kept as the run delivered it and nothing measures it; the `agent` verdict's prose passes the same limits, which the
   `debate` suite (10.8) measures.
5. **Content.** Every speaker argues the side they were given and answers the other side's latest point, except one
   real slip kept as written: d10#18, Bram (Proposition) closes "Against the motion." Two arguments open with a bare
   face word ("Surprised." d10#9, "Sad." d10#17), and d03#8's Victor opens "Surprised —"; kept as written. Voices hold
   (Takeshi's trains and fish, Hana's flowers and "Probably", Rin's lowercase "fight me", Victor's three points and
   Latin), with persona noise kept: Bram calls Rin "he" (d08#12) and Hana takes the blame (d08#14), Mei and Victor cite the seed world's
   working-time passages as analogies ([1]–[5]), Rin invents a feasibility study (d07#3).

## The repair (applied to the committed files)

Each changed line was rebuilt from its own stored response through `TagParser` (the speaker's names, as `naive`
runs it); the changes were then read one by one.

- **Restored (45):** d01#12, #14, #15; d02#4, #14, #15; d03#2, #3, #8; d04#3, #5, #10, #12; d05#2, #4, #5, #12;
  d06#3, #8, #9; d07#2, #4, #7, #8, #9, #15; d08#5, #8, #10; d09#4, #5, #6, #9, #16, #17; d10#15; d11#3, #8;
  d12#2, #7, #10; d13#4, #5, #7, #10.
- **Notes cut (14):** the text before the last `</e:…>` (d04#8, #9, #12, #14; d05#5, #8, #9, #13, #14; d13#7, #8),
  or before the argument's first words where no closing tag marks it (d02#12 "Kai, one last thing", d08#3 "the mandate
  doesn't fix the problem it names", d13#10 "Victor's frame isn't the only map").
- **Closing tag removed (10):** d04#7, d05#10, #15, d08#4, #9, #10, #12, #14, d09#6, d10#18.
- **Kept whole after reading:** d08#8 and d08#13 (Rin's lowercase replies over two or three paragraphs are speech in her
  voice, addressed to the room, not notes).

Later speakers saw the damaged text of earlier arguments as the debate ran; the arguments still answer each other, and
no item's label depends on the difference. The faces (`emotion`) are the run's, unchanged.

## The planted weak sides (task 10.2)

`horizon eval debate-plant` (run `20261014T102813-debate-plant-ae0f85`, $0.00796 against $0.01504) rewrote the weak
side's rebuttals and closings of the 12 two-sided debates (prop weak on even-numbered debates, opp on odd; D21): 46
arguments, written to `evals/debates/planted/`. Each was read against its original and the speaker's opening.

- **40 do what the plant asks:** the speaker's opening points again, the other side unanswered (names kept from the
  speaker's own opening, such as Hana's "here's the part I really love, Aiko", are the opening's, not an answer).
- **Two came back unchanged** (DeepSeek returned the original): d05#15 (Hana answers Aiko's kitchen) and d09#11 (Sofia
  answers Daniel's 31 % and Mei's trial).
- **Four still answer a point:** d03#10 (Sofia answers Daniel's burnout cost), d08#12 (Bram keeps Aiko's fallback),
  d11#10 (Victor: "the other side has argued for redesign") and d12#9 (Bram prices the quieter shells and the drone
  show). d05#10 and d10#16 only echo the other side's images (the platform, the padlock).
- They are kept as written (D21: the plants are written once, by DeepSeek). Each planted debate keeps at least two
  of its weak side's arguments plainly weakened; the `debate` suite's margin rule (D21) is what tells whether a plant
  made its side the weaker one, and a planted debate that doesn't is reported there.

# Tasks

> **Constraints for every task:**
> - **Tests are offline.** No network in automated tests: the socket guard stays on, and only the in-process fake
>   provider and obviously fake `sk-or-test-…` keys are used.
> - **The key stays private.** The real key is never printed, logged or put in fixtures.
> - **Contract.** M15 changes none (design D18). If any contract method, wire field, enum value, event or UI entry
>   point turns out to be needed, **stop and ask the user** before changing it.
> - **Background work and waits.** New background work starts only through `rt.spawn`, `actor.background` or a named
>   after-turn task; new waits use the runtime clock.
> - **Nothing tuned is re-versioned** except by the user's choice: no bank entry, threshold or deadline changes.
>   The honesty line (D5) and `naive`'s tag line (D14, `naive-9`…`naive-12`) are the only prompt edits, and both
>   are choices.
> - **Not in M15:**
>   - no image or song is generated (the v3 image check and W3's identity edit are the endgame's, by eye);
>   - the Jev model id stays `jev-1.13`;
>   - no style reference images.
> - **Private items.** Nothing under `private/` is ever committed. `git status` shows nothing from `private/` before
>   every commit. Never commit `6 RAG.pdf`.
> - **No user text in the shared response store** (W10). Latency runs and the canary bypass it.
> - **Commits and pushes.** Commit at each phase's green checkpoint, without Claude attribution. Push nothing unless
>   the user asks.
> - **Ask the user first** before:
>   - any paid run (phase 8, each with its own estimate, off-peak: not 09:00–12:00 or 14:00–18:00 KL; the overrun
>     cap is max(1.5 × estimate, $0.01));
>   - any download;
>   - spawning subagents;
>   - any prompt, wording, threshold, deadline or setting change a finding suggests (as choices).
> - **Gate eval commands run with `HORIZON_TEST=1`.**
> - **Before any paid batch,** check that no earlier batch script or process is still alive.
>
> **Every phase ends with these gates green:**
> - `uv run pytest`, `uv run ruff check`, `uv run mypy horizon`;
> - `npm run typecheck`, `npm run lint`, `npm test`, `npm run test:http`;
> - `npm run seed:check`, `npm run fixtures:check`, `npm run export-schema:check`;
> - `HORIZON_TEST=1 uv run horizon eval smoke --limit 5 --yes`.
>
> **Checkpoint:** commit the phase.

## 0. The base and the storms (design D2)

- [x] 0.1 Confirm M14's gates on a570f5f in the gate worktree:
  - backend pytest (2179 plus the face-check fix, 10 deselected), ruff, mypy (236 files);
  - frontend 563 / http 63;
  - e2e 65 + 2 skipped;
  - `openspec validate images-music --strict`;
  - the docs link check (517, 0 broken).

  Record them in a new `docs/ai/checks/m15.md` §0. Any difference is reported before phase 1.
- [x] 0.2 Add one storm test per new cancel path to the cancel-storm suite, each marked `xfail(strict=True)` with the
  phase that makes it pass:
  - a hinted `emotion_regenerate` cancelled, or its character deleted, between compile and the provider call;
  - a song task cancelled after its prompt is built;
  - the key cleared with Jev call 1 parked, with the output check parked, and during a pause run;
  - a `conversations` and a `latency` run stopped between turns and inside a turn.

  Verify: pytest collects them and they xfail.

## 1. Images and songs (design D6, D7, D8)

- [x] 1.1 Add compiler v3's lines to `ai/image_prompt.py`, word for word from I1, plus `IMAGE_PROMPT_VERSION = "v3"`
  and the docstring. Verify unit tests:
  - original and clothed in `base` and `sheet`;
  - the sheet's Avoid line;
  - the apparent-age line in `emotion_edit` and `tweak`;
  - no originality line in `tweak`;
  - the positive-wording test;
  - the name-never-appears test over every template for the six seed characters.
- [x] 1.2 Add `emotion_edit(..., identity=False)` with W3's line, and pass `identity=True` from `image_job` only for
  a hinted `emotion_regenerate`. Verify:
  - an API test sends a hint, and the provider prompt has the line and none of the hint's words;
  - an empty or whitespace hint gives no line;
  - no `guardrail` request is sent;
  - `emotion_set` and blinks are unchanged;
  - 0.2's `emotion_regenerate` storm passes.
- [x] 1.3 Regenerate the four golden fixtures with `HORIZON_UPDATE_GOLDEN=1`, adding `identity_edit` and `version`.
  Read the diff line by line against I1 and W3, and update `docs/ai/image-model-test/TESTING.md`'s appendix and the
  `ai-ports` golden scenario. Verify: `test_image_prompt.py` passes, and the diff touches only v3's lines.
- [x] 1.4 Change `song_prompt(brief)` to I2's text, and update every caller (`NaiveSong`, `brief_refused`,
  `commit_song`). Verify `tests/jobs/test_song.py`:
  - the example brief gives I2's example;
  - the title and the name never appear;
  - the check reads the same text the provider gets;
  - the stored title and provenance are right;
  - 0.2's song storm passes.

## 2. ASSETS.md (design D9)

- [x] 2.1 Add the "Generated music" section after the table's end marker: Google's terms as group A A4 read them
  (owner, restrictions, attribution, the read date and URL), SynthID, user songs under those terms, and the seed
  themes procedural until the endgame. Amend doc 12 check 3's note. Verify: `npm run assets:check` passes with the
  same rows.

## 3. The store: both orders, the probe, `all`, the manifest (design D13, D19)

- [x] 3.1 Add the order salt to the Jev key, only when a question's options differ from the bank's declared order.
  Verify unit tests:
  - a declared-order request keeps a stored group A entry's exact key;
  - the reversed order gets a new key and is sent;
  - `decisions`' order-bias rows now count real flips on the fake.
- [x] 3.2 Add `--probe` to the runner: a miss reserves and sends nothing and answers empty (D13, as amended in apply),
  priced by the gateway's estimate; a chained suite with any miss is priced at its whole estimate; a deny transport
  keeps the run off the network. Verify:
  - tests with a seeded store (a hit served, a Jev miss, chat and embedding misses);
  - the ledger, the spend log, the store, the measured marks and the judge baselines are unchanged after a probe.
- [x] 3.3 Add `horizon eval all` as the probe over every suite, printing hits, would-pay and estimates. Verify:
  `HORIZON_TEST=1 horizon eval all` runs on the fake with no request sent and lists every suite.
- [x] 3.4 Add `horizon eval manifest`, which writes `evals/baselines/jev-1.13-requests.json` from the store: per Jev
  set, the request-body hashes, the bank versions and the canary fingerprint; private items by hash only. Add the
  comparison check that refuses an unlisted body. Verify unit tests on a seeded store, including a changed body
  named and refused.

## 4. The honesty rewording (design D5)

- [x] 4.1 **Bring D5's candidate wordings (A, B, C, or the user's edit) to the user**, with the acceptance rule
  (sincere ≥ 27/30; in-story at least today's 15/30, aiming at ≥ 27/30) and the choice of one or two measured
  candidates (≈ $0.05 / $0.10). Record the answer in `m15.md`.
- [x] 4.2 Put the chosen wording in `S2_LINES` and the TS twin. Move the labels `agent-1`…`agent-8` to
  `agent-9`…`agent-16` in `persona.py`, `turn.py` and `personaPrompt.ts`. Regenerate the shared persona fixtures
  from one run. Verify:
  - the twin test is byte-equal;
  - the `persona-prompt` and `ai-ports` label scenarios pass with the new labels;
  - `naive`'s bytes are unchanged.
- [x] 4.3 If phase 8's measure rejects every candidate, revert 4.2 (the line and the labels), and drop the
  `persona-prompt` honesty scenario and the label deltas from this change before archive. Verify: the fixtures equal
  a570f5f's.

## 5. Transcripts, judge sets and the emotion items (design D10, D12, D16)

- [x] 5.1 Cut the 9 frozen transcripts from the committed histories:
  - 4 debate windows of 8–12 arguments, from debates outside the debate suite's test split;
  - 5 watch windows, 2 from `meridian_long`.

  Each records its source history and window, and stores the summary in force and the start-of-session memory list
  per turn. Verify: the loader test (20 expected once 5.2's are generated; 13 now) and line-for-line equality with
  the source.
- [x] 5.2 Write the 7 short `naive` scripts (1:1 × 4, group × 3) in `evals/transcripts/scripts/`:
  - the ≥ 10 non-English or mixed lines and the 10 planted wrong claims, each labelled;
  - two 1:1 and one group script asking about the seed documents, including one question they don't cover;
  - no safety items.

  Add `transcript --short`. Verify: the scripts load, the labels count ≥ 10 each, and `transcript --short --probe`
  runs on the fake.
- [x] 5.3 Build `judge_pairwise` v3's 30 known-winner pairs (D12's four planted defects against real replies from
  the committed transcripts), and bump its version. Verify: the builder test (one defect per pair, both orders
  generated) and `bank-lock`.
- [x] 5.4 Add the stays-in-character judges:
  - `judge_voice`'s rebuilt real set;
  - new `judge_persona_fact` and `judge_answers_last`, each with 30 real (from the committed transcripts' replies)
    and 30 planted items;
  - `judge_sentence_supported`, with real items from M12's saved deep turns and planted unsupported sentences.

  Label the real items blind under `evals/reviews/m15-labels.md`, and **ask the user to spot-check them**. Verify:
  the sets load, `overlap` passes, and `bank-lock` passes.
- [x] 5.5 Write the 40 new emotion items, labelled blind before any run and split by the hash rule. Verify: the set
  holds 140 items, and the split test passes.

## 6. Conversations, the `naive` arms and the latency run, offline (design D11, D14, D15, D16)

- [x] 6.1 Build `horizon eval conversations`:
  - the per-turn rebuild (moodline's builder, generalised to every mode);
  - both profiles in separate isolated copies;
  - the per-mode comparison (the speaker named);
  - the judges of the "Layer 3 judgements" requirement;
  - the 100-reply sample;
  - the saved states.

  Verify:
  - smoke `conversations --limit 1` per mode on the fake at $0;
  - a test that both profiles' requests share the stored history;
  - 0.2's conversations storm passes (a stopped run is `incomplete`).
- [x] 6.2 Add layer 3's statistics: mean p(agent better) over both orders, the paired bootstrap over conversations
  (2,000 seeded resamples), win/tie/loss with the exact sign test, order disagreement, length bias, English-first
  reading on test. Verify: unit tests with hand-worked answers.
- [x] 6.3 Add the free runs to the suite: one per mode per profile, G11's 3 + 3 and V11's 2 for `agent`. Report
  fallback and timeout rates from uncached calls, cost per turn, repetition, talk finished, debate phases and
  keeps-side/engages. Verify: `--limit 1` on the fake.
- [x] 6.4 **Bring D14's `naive-6` tag line to the user.** If chosen: change `naive/prompt.py` (`naive-9`…`naive-12`) with its
  test and fixtures. If declined: drop the `ai-ports` "naive tag line" requirement from this change. Either way, add
  the free note-in-tag rate to the debate and conversations reports. Verify: the prompt test and the rate's unit
  test.
- [x] 6.5 Enable `debate --profile naive` and `memory --profile naive` per D14, beside the `agent` columns. Verify:
  `--limit 1` for each on the fake.
- [x] 6.6 Add `latency --part blended`:
  - the five parts and the warm-up discard;
  - the recorded window and provider;
  - the per-stage breakdown and the blend at a rate fixed before the run;
  - the folded-in late rates (`turn_plan`, `guardrail` 800, `follow_plan`, `debate_plan`, recall) and the cache hit.

  Verify: `--limit` per part on the fake, the warm-up scenario, and 0.2's latency storm passes.
- [x] 6.7 Add the sentence-faithfulness part on the 10 two-passage retrieval items. Verify: `--limit 1` on the fake.

## 7. The default and the key read once (design D3, D4)

- [x] 7.1 Change `ProfileSpec.choose`'s default to `agent` with a key, and remove the `memory_writer` test-mode
  special case. Fix the module docstring (no `/health` claim) and add the start-up log line. Verify:
  - the new four-case default test;
  - the profile unit tests updated;
  - `test_memory_writer_m13.py` unchanged and passing;
  - backend and e2e (pinned `scripted`) unchanged.
- [x] 7.2 Make `TurnRunner` read the key once per turn, for every port of the reply. Verify:
  - D4's tests (key cleared with the plan parked, and with the output check parked: an `error` reply with no
    scripted text and no scripted guardrail row; key set mid-turn: this turn scripted, the next `agent`);
  - 0.2's key storms pass.
- [x] 7.3 Update README's configuration, `docs/backend/05-ai-seams.md`, `evals/README.md` (the new commands and
  `--probe`), doc 01 A12, doc 02 B12 and W4's last row. Verify: the docs link check.

## 8. The paid runs (design D17)

Each run: the user's explicit OK with its estimate, off-peak, capped, store where W10 allows, folder `.keep`,
per-item results under `docs/ai/checks/m15/`, no live older batch.

- [x] 8.1 The canary (< $0.001, store-bypassed). Verify: it passes, or a drift goes to the user before anything
  else.
- [x] 8.2 `horizon eval all` (the probe, $0). Record D13's table as found in `m15.md`. **Bring any re-run to the
  user as a choice**, one suite at a time.
- [x] 8.3 The M14 song part on the new prompt (≈ $0.001). Verify: refused ≥ 9/10, falsely refused ≤ 1/20, recorded.
- [x] 8.4 The 7 short transcripts (≈ $0.02). The team reads each before commit, and the user spot-checks. Verify:
  the loader finds 20, and every label holds.
- [x] 8.5 B4 for `judge_pairwise` v3, `judge_voice`, `judge_persona_fact`, `judge_answers_last` and
  `judge_sentence_supported` (≈ $0.015). A failing judge may be reworded once, by the user's choice. Verify: results
  in `evals/baselines/judges.json`.
- [x] 8.6 The honesty re-measure, one or two wordings by 4.1's choice (≈ $0.05 / $0.10), in the fixed order. Apply
  D5's rule. **Bring the result to the user** (keep the wording, try the advisory-line tweak, or revert by 4.3).
- [x] 8.7 M13's layer 3 re-run on the new system message (≈ $0.04), re-judged. Verify: the figures beside M13's in
  `m15.md`.
- [x] 8.8 The emotion set's 40 items (≈ $0.002). Read the test split once at floor 0.2, and record it beside m9's.
- [x] 8.9 `conversations`, both profiles, with the free runs (≈ $0.30–0.40, priced from 8.2's probe and the measured
  per-turn costs). Verify: the report, every saved state, and the run folder `.keep`.
- [x] 8.10 The citation judge's re-validation on the run's real failures, and sentence faithfulness on the 10
  two-passage items (≈ $0.01). **If faithfulness fails its target**, bring multi-document thinking to the user as a
  choice.
- [x] 8.11 The `naive` arms of `debate` and `memory` (≈ $0.06–0.10). Verify: both columns in `m15.md`.
- [x] 8.12 **Bring D15's window choice to the user** (A one off-peak window ≈ $0.17, recommended; B two off-peak
  windows; C one off-peak and one peak). Then run the must-pass latency run. Verify: NFR-01 blended, NFR-02, NFR-29
  and the per-stage table in `m15.md`.
- [x] 8.13 **Bring the findings to the user as choices:**
  - any deadline from 8.12's distributions;
  - any NFR miss's fix (D15);
  - the optional D16 items (the reaction rewording, the mood-line re-test, the drafter catchphrase fix).

  Apply only what is chosen, re-measuring only the part it touches.
- [x] 8.14 Run `horizon eval manifest` and commit `evals/baselines/jev-1.13-requests.json`. Record the spend table
  against D17 and `spend.jsonl` in `m15.md`.

## 9. Docs and the final gates (design D19, D20)

- [ ] 9.1 Amend everything D20 lists not already done: doc 12's §5, I7, §4 and "Built in M15" notes; doc 13's W3,
  W4, W6, W10 and W12 rows; doc 02 B3, B4 and B8; doc 11 S2's note. Verify: the docs link check, with 0 broken.
- [ ] 9.2 Finish `docs/ai/checks/m15.md`: the runs, the findings, the user's choices, and **"What the AI stage
  leaves"** (D19: the manifest and how the Jev 1.14 comparison uses it; the endgame list; the LinkedIn figures and
  good-emotion cases). Verify: it is linked from doc 13.
- [ ] 9.3 Final gates on the gate worktree:
  - backend pytest, ruff, mypy;
  - frontend typecheck, lint, test, http;
  - `seed:check`, `fixtures:check`, `export-schema:check`, `assets:check`;
  - smoke, e2e;
  - `openspec validate images-music --strict`;
  - the docs link check;
  - `git status` clean of `private/`.

  Record them in `m15.md`.
- [ ] 9.4 Ask the user how M15 finishes (archive + squash into dev, as before). Do nothing further without the
  answer.

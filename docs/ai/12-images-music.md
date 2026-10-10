# 12: Images and music leftovers

> **Status: agreed with the user, 2026-10-10** (AI stage, task 12 of 13).
> - It settles what doc 11 left here (§7): the "original character" rule and the adult-appearance clause in the image
>   templates, and what happens to a refused image or song prompt. It also closes the parts of **OQ-AI-09/10/11**
>   that D-61, D-87 and D-88 left open: the style lock, the song prompt, and the Lyria licence.
> - Decisions are numbered **I1–I9**, each with the alternatives we rejected.
> - **The user's three choices** (all three were the recommendation): the text the user writes into an image prompt
>   gets a **Jev text check** before any image is paid for; the song prompt **drops the character's name** and an
>   edited brief gets **the same kind of check**; the style lock stays **the preset's prompt fragment only** (style
>   reference images go to the v2 backlog).
> - It builds on docs [01](01-agent-architecture.md) to [11](11-safety.md).
> - **No contract change.** These already exist: the `content_refused` code; a task's
>   `error { code, message, retryable }`; `ThemeSong.licenseNote`; `StylePreset.referenceImageUrls` (left empty).
> - **No new UI entry point.** The existing Retry button on a failed image task is hidden when the task can't be
>   retried (I5).
> - **D-88 stands:** finished images still get no automated gate. The checks here read **text, before money is
>   spent**; they never look at an image.

## 1. The question

The image prompt compiler is real in both profiles, Seedream 5.0 Flash makes portraits (D-61) and Lyria 3 Clip makes
themes (D-87). Three things were still open:

1. what keeps a portrait **original and adult** when the user writes part of the prompt;
2. what keeps a theme song from **copying a named artist or song**;
3. whether the art style is locked by **reference images** or by text alone.

## 2. What Horizon already has

From the code:

- **The compiler** ([image_prompt.py](../../backend/horizon/ai/image_prompt.py)) builds four prompts: `base`
  (text-to-image), `emotion_edit` and `tweak` (edits of the locked base), and `sheet`.
  - **The character's name never reaches the image model.** The subject block is "a 29-year-old emergency doctor"
    plus the appearance; the seed appearance summaries name no one.
  - `base` and `sheet` carry the adult clause ("Adult character with adult proportions and a mature face.") and
    "childlike or teenage features" in their Avoid line.
  - An age under 18 returns a `REFUSED` warning; the worker fails the task with `content_refused`, not retryable,
    with no call ([worker.py:285](../../backend/horizon/services/jobs/worker.py#L285)).
- **Three kinds of user-written text reach an image prompt:**

  | Text | Where it enters | Job |
  |---|---|---|
  | the "Doesn't look like them" note (≤ 300 characters) | `base(note=…)`, after the subject | `portrait_candidates` |
  | the tweak text (≤ 300 characters) | `tweak(text)`, as "Apply ONLY this small change" | `portrait_tweak` |
  | appearance fields the user edits (role, summary, attributes, extra details) | the subject block | `portrait_candidates`, the sheet |

- **Seedream refusals** (a 403 moderation response) already become `content_refused`
  ([gateway/errors.py](../../backend/horizon/gateway/errors.py)), retryable by default.
- **The song prompt** ([naive/creation.py](../../backend/horizon/ai/naive/creation.py), `song_prompt`) starts
  `Instrumental theme music for "Sarah's Theme".` and lists the brief's genres, moods, instruments, tempo and vibe.
  The brief comes from the drafter, or from the user's edit in the job input. A Lyria refusal, error, timeout or rate
  limit falls back to the free procedural theme with a note (`SONG_FALLBACK`, design D7); the note shows under the
  player (`licenseNote`).
- **The style preset** (`seed/style-presets.json`) has one entry, `style_horizon_anime`: a prompt fragment and an
  empty `referenceImageUrls`.
- **The Retry button** on a failed image task (PortraitStep, EmotionsStep) shows whatever `retryable` says, and
  `JobScheduler.retry` re-queues any failed task with attempts left.

**Gaps:**
1. `emotion_edit` and `tweak` **don't carry the adult clause**, though NFR-27 says every image prompt must. "Make her
   look younger" goes to Seedream with nothing against it.
2. **No template says "original character"** (doc 11 S9 left it here; R-06).
3. **User text is unchecked.** The name stays out, but a likeness can be described ("looks exactly like Keanu
   Reeves").
4. **The Lyria prompt carries the character's name**, and an edited brief can say "in the style of Coldplay".
5. **Lyria's licence terms** (NFR-24, OQ-AI-11) haven't been read from a primary source.

## 3. Decisions

### I1. Template lines: original, adult, SFW

**Decision:** the compiler (prompt version **v3**; TESTING.md and the golden fixtures in
`backend/tests/fixtures/image_prompt/` follow) gains:

- **`base` and `sheet`:** after the style and adult lines,

  ```text
  An original character: not a likeness of any real person, celebrity or existing fictional character; no logos or brand marks.
  ```

- **The Avoid line** (`base`, `sheet`) adds "nudity, underwear or swimwear, blood or open wounds, weapons" (hands are
  out of frame and there are no props anyway).
- **`emotion_edit` and `tweak`:** after the Keep line, "The character stays an adult with adult proportions and a
  mature face." `tweak` also gets the original-character line, since its change is user text.

**Worked example (`tweak`, v3):**

```text
Edit this image. Keep the exact same character: identical face shape, … and art style. The character stays an adult
with adult proportions and a mature face. An original character: not a likeness of any real person, celebrity or
existing fictional character; no logos or brand marks. Apply ONLY this small change: Add a thin silver nose ring.
Keep the pose, background and art style.
Do not add hands, props, text, tears streaming, or any new objects. Do not change the crop.
```

**Why:** NFR-27 says every image prompt carries the adult clause; S9 asked for the originality rule; Seedream bills
per image, so ≈ 40 more words cost nothing.

**Rejected:**
- **The adult clause in `base` only:** an edit can still drift a face younger ("make her look younger").
- **Naming the forbidden things in the positive prompt** ("not nude"): image models often draw what a prompt
  names; the Avoid line is where the D-61 run put every exclusion.

### I2. Names stay out of both prompts

**Decision:**
- **Images:** unchanged; the subject stays name-free (a compiler test asserts the name never appears).
- **Songs:** the prompt no longer names the theme. It opens "Instrumental theme music for a character." and gains
  "An original piece: do not imitate any named artist, band or existing song." before "No vocals, no lyrics." The
  stored title ("Sarah's Theme") and the procedural theme are unchanged.

**Worked example (song, after):**

```text
Instrumental theme music for a character. Genres: lo-fi, jazz. Mood: warm. Instruments: piano, brushes.
Tempo: about 84 BPM. Feel: rainy-day café. An original piece: do not imitate any named artist, band or existing song.
No vocals, no lyrics. A 30-second piece that loops cleanly.
```

**Why:** the name tells Lyria nothing musical, and a character named after a singer ("Taylor's Theme") would put a
real name into the prompt.

**Rejected:** keeping the title for "flavour": there is no musical gain, and only a risk.

### I3. The image text check (user's choice)

**Decision:** before an image job's first paid call, **one Jev noul reads only the user-written text**. If it says
no, the job's tasks fail with `content_refused` and **no image is paid for**.

- **What is read:**
  - `portrait_candidates` and the expression sheet: the compiled subject block plus the note;
  - `portrait_tweak`: the tweak text;
  - emotion edits and blinks: nothing (their prompts are fixed templates).
- **The noul** (Jev state `{ quoted_text }`; the instructions end with doc 11 S6's `quoted_*` sentence):

  > "Does this portrait description ask for any of these: the likeness of a real person or of an existing fictional
  > character (by name or by an unmistakable description); nudity, underwear, swimwear or sexual content; blood or
  > open wounds; a child or teenage look?"

- **Port:** the internal `Guardrail` port gains `check_prompt(ctx, kind: "image" | "song", text) -> GuardrailResult`
  (not the contract):
  - `agent`: the Jev noul;
  - `naive`: pass with no checks (the yardstick, as doc 11 S5's `naive` guardrail);
  - scripted: pass with no call.
- **Purpose `guardrail`** (the `decision` category, never drains energy). The ledger row carries the job ID, so its
  cost shows in the job's actual cost. **Deadline 1,500 ms**, the motion check's.
- **p ≥ `safety.tImage`** → every task in the job fails with `content_refused`, `retryable: false`, and the message
  "Portraits can't show a real person's or an existing character's likeness, nudity, gore or a young look. Change the
  wording and try again." The job's hold is released as for any failed task.
- **Jev failed or late** → the job goes on (I1's template lines, Seedream's own filter and the user's eye still
  apply), and the skip is logged.
- **One call per job:** the first task asks; the job's other tasks (the 4 candidates) wait on the same answer. Answers
  are cached in memory by SHA-256 of (noul version, kind, text), so a re-roll or a sheet with an already-checked
  subject costs nothing.

**Worked example:** the user types the tweak "make him look like Henry Cavill".
1. The `portrait_tweak` job starts; its task asks Jev about "make him look like Henry Cavill".
2. Jev answers p = 0.93 ≥ `safety.tImage`.
3. The task fails: "Portraits can't show a real person's… Change the wording and try again." No Retry button; no
   Seedream call; ≈ $0.00002 spent.
4. The user writes "give him a square jaw and short dark hair" → p = 0.04 → the tweak runs.

**Why:** R-06 (likeness and IP) is a launch risk; OQ-AI-08's floor says "no named IP or real-person likeness". The
name is already kept out, so the only path left is the user's own words. A refusal before the call saves the
$0.018–0.072 that a refused or unusable image costs. "Maximize Jev" fits: a bounded yes/no on short text.

**Rejected:**
- **Template lines and the provider only** (offered): $0, but a likeness described in plain words gets through, and
  the user pays for each attempt.
- **DeepSeek rewrites the user's text into plain visual facts** (offered): ~$0.0003 and ~2 s per job, and it can
  change what the user meant.
- **Checking the finished image:** D-88 (no image gate), and Jev takes no images.

### I4. The song brief check (user's choice)

**Decision:** when the song job carries **a brief the user edited** (`input.brief`), `check_prompt(kind: "song")`
reads it before the Lyria call. A drafter's brief is not checked: the drafter already has the originality rule (doc
11 S9), and I2's prompt line plus Lyria's own filter cover it.

- **The noul:** "Does this music brief ask to copy or imitate a named real artist, band, composer or existing song,
  film score or game soundtrack?" Genre and era words ("80s synthwave", "baroque", "Celtic folk") are fine.
- **p ≥ `safety.tSong`** → **no Lyria call**; the task succeeds with the procedural theme (as for any
  `SONG_FALLBACK`), with its own note: "The brief named an artist or an existing piece, so this is the procedural
  theme rendered in the app. Edit the brief and regenerate for a composed one."
- **Jev failed or late** → Lyria is called as today.
- Same deadline, cache and port as I3.

**Worked example:** the user edits the vibe to "sounds like Coldplay's Yellow".
- Jev: p = 0.95 → the procedural theme with the brief note, $0.00002 spent instead of $0.04.
- With "warm British indie rock, chiming guitars": p = 0.06 → Lyria composes it.

**Why:** a refused Lyria call may still be billed ([gateway/errors.py](../../backend/horizon/gateway/errors.py): "a
refusal still costs its prompt"), and the user otherwise gets a fallback with no idea why.

**Rejected:**
- **Prompt lines only** (offered): Lyria blocks named singers' voices but may not refuse "in the style of" a band;
  either way the user learns nothing.
- **Failing the song task** instead of the fallback: every other song failure leaves a free theme (design D7); a
  refusal shouldn't be worse.

### I5. Refused tasks and Retry

**Decision:**
- A task refused by I3 or by the under-18 rule is `content_refused`, `retryable: false`. **The Retry button is hidden
  when `retryable` is false** (PortraitStep, EmotionsStep), and `JobScheduler.retry` refuses such a task with
  `conflict` ("This task can't be retried as it is. Change the wording and start a new one.").
- A **provider** refusal (Seedream's 403) stays retryable: the same prompt can pass on a second try.

**Why:** today Retry would re-send a prompt that is refused by design, every time.

**Rejected:** leaving Retry visible: with the I3 cache it would cost nothing, but it is a button that can only fail.

### I6. Style lock: the prompt fragment only (user's choice)

**Decision:** v1 keeps today's lock: the preset's `promptFragment` in every base and sheet prompt, and the locked base
as the only reference for edits. `referenceImageUrls` stays empty. Style reference images go to the **v2 backlog
(§6)**.

**Why:**
- a reference portrait in a base call can **leak its face** into a new character, which breaks the originality rule
  (I1) and identity;
- the real seed portraits don't exist yet (D-52), so there is nothing to reference;
- the D-61 run already scored the style 5/5 with text alone.

**Rejected:** a paid test of one seed base as a style reference for two new characters (offered, ≈ $0.15): worth
doing only once there are real seed portraits, which is a v2 question.

### I7. Evaluation

**Decision:**
- **The `safety` suite (doc 11 S10) gains two parts:**

  | Part | Items | Measure | Target |
  |---|---|---|---|
  | **image text** (I3) | 30: 15 to refuse (named likenesses, unmistakable descriptions, nudity, gore, a young look), 15 hard-safe ("a faded scar across the left cheek", "grey beard, looks about 60", "goth makeup", "short and slight", "looks tired, dark circles") | refused; falsely refused | ≥ 13/15; ≤ 1/15 |
  | **song brief** (I4) | 10: 5 naming artists, bands or pieces, 5 genre or era words | refused; falsely refused | ≥ 4/5; ≤ 1/5 |

  Thresholds `safety.tImage` and `safety.tSong` are cross-validated like the other safety thresholds (0.1–0.9 grid,
  Wilson intervals). The "to refuse" items stay in `private/evals/safety/`; the harmless ones are committed.
- **The image-model checks still open from D-61** (Hana v2, Amara's skin tone not lightened, Rin's adult read,
  Victor's fine detail; ≈ $0.40) run with the **v3** template at the paid-check point, scored by eye on the contact
  sheet (D-88). They now also confirm that the adult line in edits doesn't move the face (identity S6 ≥ the D-61
  run's 5).

**Why:** the hard-safe half keeps I3 from refusing ordinary character design, as in doc 11.

**Rejected:** an automated image eval with a vision model: D-88.

### I8. Lyria licence and provenance

**Decision (launch checklist, free):**
- Before any Lyria song is committed as a seed asset, **read Google's primary terms** for Lyria through the API
  (output ownership, commercial use, attribution) and record them in `ASSETS.md`. Secondary sources disagree on
  commercial use, and none quote the API terms.
- `ASSETS.md` names the **SynthID** watermark Google puts in every Lyria track (inaudible; NFR-24 asks for
  watermarks to be named).
- If the terms forbid the use, the seed themes stay procedural (D-83) and the README says so; user-generated songs
  are the user's own business under those terms, linked from Settings → About.

**Why:** OQ-AI-11 and NFR-24 ask for exactly this, and it costs nothing.

### I9. Speed and cost

| Step | When | Added wait | Cost |
|---|---|---|---|
| I1 template lines | every image prompt | none | $0 (Seedream bills per image) |
| I2 song prompt | every Lyria call | none | $0 (Lyria bills per clip) |
| I3 image text check | each `portrait_candidates`, `portrait_tweak` and sheet job, once; repeats cached | ≈ 0.1–1.5 s before the first paint, on a ~17 s job | ≈ 400 tokens ≈ $0.00002 |
| I4 song brief check | song jobs with an edited brief | ≈ 0.1–1.5 s before a ~16 s call | ≈ $0.00002 |
| I7 suite parts | eval runs | | 40 Jev requests ≈ $0.001 |

- A character's whole creation adds ≈ $0.00004 at most (one base job, one sheet or emotion job, one song).
- The safety suite stays ≈ $0.07; **`all` is unchanged at ≈ $1.08 / $1.65 / $0.78**.
- If doc 01's check 4 finds Jev bills the state per question, nothing here changes: each check asks one question.

## 4. Checks before this is locked

| # | Check | Pass mark | If it fails |
|---|---|---|---|
| 1 | The D-61 image checks with the v3 template (I7), by eye | identity across edits as in the D-61 run; Amara's skin tone kept; Rin reads adult | reword the v3 lines; the user decides |
| 2 | The two new suite parts (I7), inside doc 11's check 1 | I7's counts | reword the nouls before moving thresholds |
| 3 | Lyria's primary terms read (I8) | recorded in `ASSETS.md` | seed themes stay procedural |

## 5. Changes this design needs (each approved at its OpenSpec change)

| Change | Where | From |
|---|---|---|
| Compiler v3: the original-character line, the Avoid additions, the adult line in `emotion_edit` and `tweak`, the original line in `tweak`; TESTING.md, the golden fixtures and a name-never-appears test | backend + docs + tests | I1, I2 |
| `song_prompt` without the title, with the original-piece line; `tests/jobs/test_song.py` | backend + tests | I2 |
| `Guardrail.check_prompt(ctx, kind, text)`: `agent` Jev nouls (image, song) with `safety.tImage` and `safety.tSong`, 1,500 ms, in-memory cache by SHA-256; `naive` and scripted pass; one answer per job shared by its tasks (`worker.image_job`); refusal → `content_refused`, `retryable: false`, I3's message | backend + config | I3 |
| `call_song`: the check on `input.brief` only; refused → `SongFallback` with the brief note (a new note next to `theme.FALLBACK_NOTE`) | backend | I4 |
| Retry hidden when `retryable` is false (PortraitStep, EmotionsStep); `JobScheduler.retry` refuses a non-retryable task with `conflict` | frontend + backend | I5 |
| The `safety` suite's image-text and song-brief parts | eval | I7 |
| `ASSETS.md`: SynthID and the Lyria terms | docs | I8 |
| **Docs amended with this doc:** doc 02 B5 (two threshold rows); doc 11 S9 (images: see doc 12), S10 (two parts), S11 (a pointer to I9), §7; docs/v2 §6 (style references) | docs | consistency |

## 6. Left for later tasks

- **Task 13:** the two new Jev questions in the Jev map; OQ-AI-09/10/11 marked resolved (09 by D-61, 10 by D-61 + I6,
  11 by D-87 + I2–I4 + I8). The checks run in creation jobs, not sessions, so Insight's System 1 section doesn't show
  them.
- **v2 backlog (§6):** style reference images for a cast-wide look.
- **Launch checklist:** I8's terms.

## Sources

- D-45, D-52, D-61, D-83, D-87, D-88; NFR-24, NFR-27; R-05, R-06; OQ-AI-08 to 11.
- `docs/ai/image-model-test/` (the D-61 run, TESTING.md).
- Google's Lyria 3 coverage (SynthID in every track; the API blocks named singers' voices and copyrighted lyrics):
  [ppc.land](https://ppc.land/googles-lyria-3-5-puts-full-length-ai-songs-in-gemini-and-the-api/),
  [deeplearning.ai](https://charonhub.deeplearning.ai/google-debuted-lyria-3-an-app-that-turns-text-or-images-into-30-second-songs/).
  Secondary sources only; I8 asks for the primary terms.

# 04: The persona prompt and the profile drafter

> **Status: agreed with the user, 2026-10-09** (AI stage, task 4 of 13).
> - It resolves OQ-AI-16 (the prompt template behind `systemPromptPreview`) and writes the prompt wording that doc 03
>   left open (C4 length targets, C5 one message per line, repetition).
> - Decisions are numbered **P1–P12**, each with the alternatives we rejected. (P, not D, so they are not confused with
>   the requirements' D-numbers.)
> - It builds on [01-agent-architecture](01-agent-architecture.md) (A1–A14),
>   [02-evaluation-observability](02-evaluation-observability.md) (B1–B12) and
>   [03-llm-parameters](03-llm-parameters.md) (C1–C9). It amends one line of doc 01 (A5, the emotion tag; see P7).
> - **No contract change.**

## 1. The question

Two places turn a character's profile into words:
- **The persona prompt:** the system message DeepSeek receives on every reply. It sets how the character sounds, how
  long they talk, whether they repeat themselves, and what "View as prompt" shows (CHR-05 AC1).
- **The profile drafter:** the one DeepSeek call that writes a whole character from a one-line seed in the creation
  wizard.

**The user's decisions (2026-10-09):**
- **Drop the emotion-tag instruction.** Jev chooses the face (doc 01 A5); asking DeepSeek for a tag it then throws
  away is wasted work and a source of format errors (P7).
- **No actions or stage directions** (`*smiles*`) in any mode, watch included. The face already shows the emotion
  (P6). The user leaned to "never" and left the final call to us; we chose never.
- **Reply in the user's language**, mixed languages included, English when unclear (P6).
- **The approved greeting is used word for word in the first chat; later chats get a generated one** (P9).
- **Forbid four AI habits:** the assistant voice, being too agreeable, flattery, and ending every message with a
  question (P6).
- **Very short user messages:** match the short energy, and now and then lead (P6).
- **Emoji follow the character:** at most one per message, none for formal characters (P6).
- The rest of the recommendations (the card layout, the real prompt preview, the size limit, the drafter changes, the
  repetition metric) were accepted as presented.

## 2. What Horizon already has

From the code:

- **The naive compiler** ([naive/prompt.py](../../backend/horizon/ai/naive/prompt.py), `PROMPT_VERSION = "naive-2"`;
  doc 03 makes it `naive-3`) builds one system message:
  - one `Label: value` line per profile field, then the You card, one line for the mode, the content-rating line, and
    the emotion-tag rule ending "reply in character, briefly, in plain text";
  - then a second system message with the rolling summary, then the history window
    ([window.py](../../backend/horizon/ai/naive/window.py): the speaker's own lines as `assistant`, everyone else's as
    `user` prefixed with "Name: ");
  - then the dynamic tail: the retrieval block (D-93) and a per-turn cue (greeting, debate, answer, scene, variant).
- **Gaps found in it:**
  - **`relationshipToUser` never reaches the prompt.** The contract field exists ("your girlfriend"), and the mock
    template in the wizard shows it, but the compiler skips it.
  - Catchphrases and example lines are listed with no instruction, so the model tends to repeat them verbatim.
  - The appearance is not in the prompt, so a character asked "what do you look like?" invents an answer that can
    contradict its portrait.
  - There is no length target (doc 03 C4 adds one) and no rule against repetition. DeepSeek's repetition penalties
    are not supported (doc 03 F3b), so the prompt is the only control.
- **"View as prompt" shows a mock.** The wizard's `composePrompt`
  ([ProfileStep.tsx](../../frontend/src/features/wizard/steps/ProfileStep.tsx)) is labelled "mock template" and differs
  from what the backend sends. The naive drafter never fills `systemPromptPreview`; the scripted drafter fills a
  one-line fake ([scripted/drafts.py](../../backend/horizon/ai/scripted/drafts.py)).
- **The drafter** ([naive/creation.py](../../backend/horizon/ai/naive/creation.py)) is one JSON-mode call from
  `Seed: … Intent: …`:
  - its schema has no `exampleLines` and no `relationshipToUser`, so user-made characters sound flatter than the seed
    characters (which have example lines);
  - it is not told the world, the names already used in it, or the You card;
  - its system prompt has no guidance on names, so drafts drift to stock AI names ("Elara Voss", "Kael").
- **The 1:1 greeting** ([one_on_one.py](../../backend/horizon/sessions/modes/one_on_one.py)) passes the stored
  greeting as `LineHint.text`. The scripted engine says it; the naive engine ignores it and pays for a generated
  greeting on every new chat.
- **Worlds have no description** in the contract, only a name and the You card, so the world part of the prompt is
  thin. Adding a description would be a contract change, which is not proposed here.
- `ParticipantView` already carries each participant's `role`, so a group cast can be described without new data.

## 3. The design in one picture

```text
system message 1 (fixed for the session, cached)
  # Who you are          <- the card (P3), at most ~1,500 tokens (P4)
  # Your world and the user
  # This session         <- mode block: cast, motion or premise, length line (P5)
  # How to reply         <- the rules (P6), last before the history
system message 2         <- rolling summary (changes only when re-summarised)
history window           <- own lines = assistant; others = "Name: text"
dynamic tail (per turn)  <- retrieval block · mood line (doc 01 A5) · deep length line (C4) · repeat hint (P8, off) · cue
```

## 4. Decisions

### P1. A new compiler for the `agent` profile; `naive` stays the yardstick

**Decision:**
- The prompt in this doc is a new, pure compiler for the **`agent`** profile (doc 01 A12), with
  `prompt_version = "agent-1"`. It takes the profile, the appearance summary, the world name and You card, the
  session's mode data (cast names and roles, motion, side, premise), the content rating and the length line, and
  returns the system message. No I/O, so it is cheap to test and to run anywhere.
- The **`naive`** profile keeps its own compiler with only doc 03's changes (`naive-3`). Doc 02 B3 compares `agent`
  against `naive`; if both used the new prompt, the evaluation could not show what the new prompt is worth.
- The **scripted** profile has no prompt, but the preview (P10) still uses the `agent` compiler, because that is what
  the app sends once a key is added.

**Rejected:**
- Rewriting the naive compiler in place: the yardstick would move, and the eval would measure only the planner.
- One compiler with flags per profile: two products in one function, and every change risks the baseline.

### P2. Layout: four fixed blocks, rules last; everything per turn after the history

**Decision:** system message 1 holds four blocks, in this order:
1. **Who you are:** the card (P3).
2. **Your world and the user:** the world name; the You card; the character's `relationshipToUser`.
3. **This session:** the mode block (P5), including the mode's length line (C4).
4. **How to reply:** the rules (P6).

- All four are fixed for the session, so the prefix stays cached (NFR-35). The rules come last because they are the
  most recent instructions before the history, where they hold best.
- Per-turn content stays in the **dynamic tail**, in this order: the retrieval block (D-93), the mood line (doc 01 A5,
  worded in task 6), the deep length line (C4), the repeat hint (P8, off by default), then the turn cue.
- Format: short `#` headings and plain lines, written to the character in the second person ("You are …"). It is
  about 600–900 tokens for a seed character (check 1 measures it).

**Rejected:**
- XML-style tags: no gain shown for DeepSeek, and harder to read in the preview the user sees.
- Shared rules first, for cache hits across characters: the saving is about $0.00004 per new session, not worth
  putting the rules furthest from the history.

### P3. The card

**Decision:** the card uses every profile field that shapes how the character talks, and only those.

```text
# Who you are
You are Dr. Amara Okafor, 38 (she/her), an emergency physician & public-health researcher.
Your line: "Let's figure out what's actually going on."
Personality: Calm under pressure, warm, direct and evidence-first. Honest about uncertainty.
Traits: calm, warm, direct, evidence-first, honest.
Backstory: Fifteen years in emergency medicine. Started a burnout study after losing two colleagues to it.
Goals: Help people understand their symptoms well enough to get the right care.
Expertise: emergency medicine, public health, burnout research.
Boundaries: no definitive diagnoses; direct red-flag symptoms to emergency care.
Looks: <appearanceSummary>

# How you talk
Short paragraphs. Asks 1–2 clarifying questions before advising. Plain language.
Tone: reassuring. Formality: neutral.
Quirks: asks clarifying questions first; always flags red-flag symptoms.
Catchphrase (use rarely, not in every message): "Let's figure out what's actually going on."
How you sound (style only; don't copy these word for word):
- "Where is it, exactly? And what's changed lately?"
- "That's same-day care, not a chat with me."

# Your world and the user
World: Meridian.
The user is <You card name>. About them: <You card line>. To you, they are: <relationshipToUser>.
```

- **Added:** `relationshipToUser` (the bug in §2), and a "Looks" line from `appearanceSummary`, so self-descriptions
  match the portrait.
- **Reworded:** catchphrases are "use rarely, not in every message"; example lines are "style only; don't copy these
  word for word". These are the two fields models overuse most.
- **Left out:** the greeting (only used to open a chat, P9); the palette, the song brief and the raw appearance
  attributes (only used for images and music).
- Empty fields are skipped, as today. With no You card the user is "the user"; with no relationship that clause is
  dropped.

**Rejected:** the raw appearance attributes (about 150 tokens of hex colours and enums the model doesn't need).

### P4. A size limit for the card

**Decision:** the card is at most **1,500 tokens** (counted with the existing `count_tokens`). `backstory` has no
length limit in the contract, so a pasted 5,000-word backstory is possible.
- Over the limit, the **backstory is cut first**, at a sentence end, with "…". If it is still over, `goals` is cut
  the same way. The other fields are short lists in practice.
- The preview (P10) shows the cut, so the user sees what the model gets.

**Why:** every token of the card is paid uncached on the first turn of each session and re-read on every turn; a
very long backstory also drowns the speaking style.

**Rejected:**
- No limit: cost and quality both suffer silently.
- A contract `maxLength` on `backstory`: a contract change, and it would reject existing data.

### P5. The session block, per mode

**Decision:**

| Mode | The block says | Length line (C4) |
|---|---|---|
| 1:1 | "This is a private one-to-one chat with {user}." | "Write 1–3 short messages, each on its own line, about 70 words in all." |
| Group | "This is a group chat with {user} and: Hana (barista), Rin (…)." Names with roles. | "Write 1–2 short messages, each on its own line, about 50 words in all." |
| Watch | "{user} is watching this scene, not taking part. Premise: … With you: …" | "Write 1–2 short lines, each on its own line, about 50 words in all." |
| Debate | The motion, your side, your opponents (task 8 words the rest). | "Write one paragraph, no line breaks, about {80 / 140 / 220} words." |

- The deep 1:1 target (2–4 messages, about 120 words) is per turn, so it goes in the dynamic tail (C4), not here.
- Debate arguments and host lines stay one bubble (C5); their prompts beyond this slot are task 8's.
- `{user}` is the You card's display name, or "the user".

### P6. The reply rules

**Decision:** the "How to reply" block for 1:1 (the other modes swap the lines marked †):

```text
# How to reply
- Talk like a real person texting, never like an assistant: no "happy to help", no headings, lists or menus of options.
- † Write 1–3 short messages, each on its own line, about 70 words in all.
- Plain words only: no actions or stage directions such as *smiles*, no tags, and no name in front of your line.
- † Speak only as yourself. Never write lines for {user}.
- Reply in the language {user} is writing in; mixing languages is fine. If you can't tell, use English.
- Have your own views. Disagree or push back when {first} would. Don't flatter {user} or praise their messages.
- Don't end every message with a question.
- † If {user} writes something very short, answer short too. Now and then, bring something up yourself, from your own
  life, work or interests.
- Don't reuse openers, phrases or your catchphrase from your recent messages.
- <emoji line>
- <content-rating line>
```

- **Group:** "Speak only as yourself. Never write lines for {others} or {user}." This pairs with the C6 stop
  sequences, which catch the slips.
- **Watch:** "Speak only as yourself; never write lines for {others}." The short-message rule is dropped (the user
  isn't talking). The language rule becomes "Use the language of the premise; if you can't tell, English."
- **Debate:** the short-message and question rules are dropped (task 8 owns the debate style).
- **Emoji line:** formality `formal` → "Don't use emoji." Otherwise → "Use emoji only if it fits how you talk, and at
  most one per message."
- **Content-rating line:** today's two variants stay as a slot. Task 11 writes the safety wording (including what a
  character says when sincerely asked whether it is an AI), and for advisory characters the "inform, don't replace a
  professional" line.
- **The four forbidden habits** come from the user: assistant voice, too agreeable, flattery, a question at the end of
  every message.

**Rejected:**
- Actions allowed in watch only: they repeat the live face, add output tokens, and give the four modes two rules.
- Always replying in English: excludes users who write in Malay or Chinese for no saving.
- A fixed language per character: needs a new profile field, a contract change.

### P7. No emotion tag in the `agent` prompt

**Decision:**
- The `agent` prompt has **no emotion-tag instruction**. Jev chooses the face before the first word (doc 01 A5).
- **Jev failed, late or unsure → the previous face stays.** Before, a Jev failure fell back to DeepSeek's tag; now
  failure and "unsure" have the same rule.
- In MANUAL mode nothing changes: the face is the user's.
- The tag parser stays on the `agent` path for one job: removing a stray tag or a "Name:" at the start of a reply
  (C6's name-prefix buffer). It never changes the face there.
- The `naive` profile keeps its tag (it has no Jev), so the yardstick is unchanged.

**Why:** with Jev deciding, the tag is a choice DeepSeek makes that we discard. It costs an instruction competing with
the persona for attention, about 5 output tokens per reply, and a parse step that can fail. The effect on quality is
small, but it is pure cost with no use.

**Amends doc 01:** A5 ("the existing `<e:label>` instruction stays in the cached prefix … the tag is used only when Jev
failed") and the fallback table's emotion row ("Jev failed or late → DeepSeek's inline tag"). Both now read "keep the
previous face" for the `agent` profile. Task 6 still words the mood line and runs the emotion evaluation.

**Rejected:** keeping the tag as the Jev-failure fallback (doc 01 as written): it pays on every turn for a case Jev
should almost never hit, and a stale face for one turn is harmless.

### P8. Repetition: a rule, a metric, and a hint held in reserve

**Decision:**
- **The rule** in P6 ("don't reuse openers, phrases or your catchphrase") plus the card wording in P3.
- **The metric,** added to doc 02's layer-3 run, computed in code at $0:
  - **repeated-opener rate:** the share of replies whose first three words match one of the same speaker's previous
    three replies in that session;
  - **catchphrase rate:** the share of replies containing the catchphrase.
  - Targets: repeated openers under 10 %, catchphrase in under 20 % of replies.
- **The hint, off by default:** one dynamic-tail line, "Your last replies began: '…', '…', '…'. Start differently.",
  built from the speaker's own last three replies (about 20 tokens). A config switch turns it on if the metric misses
  its target. It goes after the history, so the cached prefix is untouched.

**Rejected:**
- Repetition penalties: not supported by DeepSeek (doc 03 F3b).
- Rewriting a repeated reply after the fact: it has already streamed to the screen.
- The hint on from day one: it can over-steer (the model avoids good, natural openers), and it is not needed until
  the metric says so.

### P9. Greeting: the approved line first, generated after

**Decision:**
- A new 1:1 session uses the **stored greeting word for word** when the character has **no other non-seed 1:1
  session** (`sessions.is_seed = false`, the character a participant). Seed recordings don't count; a deleted session
  doesn't count.
  - No model call: $0, no energy, no ledger row, and it appears after the usual greeting delay.
  - It is passed as `LineHint(kind="greeting", text=…, verbatim=True)`; `verbatim` is a new internal field. The
    `naive` and `agent` engines say a verbatim line as it is, the way the scripted engine already does, with a trace
    that records no model call.
  - The face is `happy`, as the scripted greeting already uses (demo parity), with no Jev call.
- **Later sessions** generate the greeting as today, with the greeting cue gaining "Don't reuse your usual greeting:
  '<stored greeting>'." Task 9 can add "last time we talked about …".
- The scripted profile is unchanged (it always says the stored greeting).

**Why:** the user approved this exact line in the wizard, it costs nothing, and the first chat opens about 1–2 s
faster. A generated greeting afterwards avoids the same line every time.

**Rejected:**
- Always the stored greeting: the same opening line in every chat.
- Always generated (today): one paid call and a slower start per new chat, for a line the user already approved.

### P10. "View as prompt" shows the real prompt

**Decision:**
- The `agent` compiler gets a **TypeScript twin** (`frontend/src/domain/personaPrompt.ts`). Both are checked against
  **shared fixtures** (`backend/tests/fixtures/persona_prompt/`), the same pattern as the tag parser
  (`tagParser.fixtures.test.ts`), so they produce byte-identical text.
- The wizard's Profile step replaces the mock `composePrompt` with the twin: the **1:1 variant**, with this world's
  name and You card. It updates live as the user edits, including the P4 cut, and the "mock template" label goes.
  The token count stays the ≈ estimate it is today.
- The backend does not fill `systemPromptPreview`; the scripted drafter's one-line fake is removed. The field stays
  optional in the contract and unused (no contract change).

**Rejected:**
- The backend filling `systemPromptPreview` on read: the wizard saves explicitly, so the preview would be stale while
  the user edits, the mock client would still need its own copy, and it also depends on the world's You card, which
  can change after the character is saved.
- Keeping the mock: CHR-05 promises the user sees the prompt; a mock that differs from what is sent breaks that.

### P11. The drafter writes the whole voice and knows the world

**Decision:**
- **The draft schema adds** `exampleLines` (2–3 short lines; the contract allows 0–3) and `relationshipToUser` (for
  the `companion` intent; empty, and then omitted, for the others).
- **The user message adds** the world's name, the names already used by characters in that world, and the You card
  (so a companion's relationship fits who the user is in this world).
- **The system prompt adds:**
  - names that fit the role and the culture of the setting; never a name already in the world; avoid stock AI names
    (a short list: Elara, Kael, Seraphina, Lyra, Aria, Voss, Thorne);
  - a concrete backstory with specific details and one flaw;
  - a speaking style made of habits you could hear (sentence length, words they use), not adjectives;
  - a greeting of at most 2 short lines and example lines that show the voice and differ from the greeting;
  - **plain speech only in the greeting and example lines** (no `*actions*`), since the greeting is shown word for
    word (P9) and the example lines teach the style (P3).
- **Unchanged from doc 03:** one JSON-mode call, validation, one retry on a parse or validation failure, temperature
  1.0, 2,400 `max_tokens`. A draft gets about 100 tokens longer (≈ $0.0001).
- `regenerate_field` gets the same name and plain-speech rules for the greeting.
- The job passes the world's name, the cast's names and the You card to `NaiveDrafter.draft` (an internal change in
  `services/jobs/worker.py`; the port signature gains one optional `world` argument).

**Rejected:**
- Validating names in code (stock list or duplicates) and retrying: a retry costs a whole draft, and the user edits
  the name in the wizard anyway. The eval measures how often it happens (P12).
- Two or three drafts to choose from: 2–3× the cost; the wizard already has per-field regenerate.

### P12. Evaluation additions

**Decision:** added to doc 02's harness, all within its budget:
- **Drafter suite** (layer 1, ≈ $0.02 a run, B7 asks before spending): 20 seeds across the three intents and two
  worlds.
  - Code checks: contract-valid, adult, 2–3 example lines, no `*` actions in the greeting or example lines, name not
    in the stock list or the world.
  - Jev atomic checks (B4): fits the seed; voice is distinct from the other drafts; the relationship fits the You card.
- **Reply-rule checks** on doc 02's layer-3 conversations (no extra DeepSeek calls):
  - code: action rate (`*…*`), stray tag or name prefix, bubbles over the mode's target, emoji over one, question-ending
    rate, repeated-opener and catchphrase rates (P8);
  - Jev atomic checks: in character; replies in the user's language; no assistant voice; pushes back when it should
    (a planted "user says something wrong" line); no flattery.
- **Targets:** actions and stray tags under 2 %; question-ending under 50 %; the P8 targets. A miss is a prompt fix,
  re-run on the dev split (B2) before the test split.

## 5. Checks before this is locked

1. **Prompt size, offline, $0.** Compile the six seed characters in all four modes; record the token count of each
   system message. Expect about 600–900; anything over 1,500 for the card is a P4 bug.
2. **First layer-3 run** (doc 02 B7, needs the user's OK when it runs): the P12 targets. No separate paid check is
   added for this task.

## 6. Changes this design needs (each approved at its OpenSpec change)

| Change | Where | Kind |
|---|---|---|
| The `agent` persona compiler (P1–P6), `prompt_version = "agent-1"`; the card limit (P4) | new `ai/agent/persona.py` (next to the agent engine) | backend |
| No tag instruction on the `agent` path; Jev failure keeps the previous face; parser only strips stray tags and name prefixes (P7) | the agent reply engine, the turn plan's emotion fallback | backend |
| The repeat hint behind a config switch, off (P8) | `frontend/scripts/seed-build/runtime.config.ts` → `seed/runtime.json`; `domain/runtime_config.py` | config |
| `LineHint.verbatim`; first-chat rule; engines say a verbatim line with no call; greeting cue gains the "don't reuse" line (P9) | `ai/contexts.py`, `sessions/modes/one_on_one.py`, `ai/naive/turn.py`, `ai/naive/prompt.py` (`turn_cue`), the agent engine | backend |
| `appearanceSummary` reaches the compiler (P3) | `ai/contexts.py` (`CharacterView`), where the context is built | backend |
| TS twin + shared fixtures; Profile step uses it; remove the mock and the scripted fake preview (P10) | `frontend/src/domain/personaPrompt.ts`, `ProfileStep.tsx`, `backend/tests/fixtures/persona_prompt/`, `ai/scripted/drafts.py`, `frontend/src/mock/banks/drafts.ts` | frontend + backend |
| Drafter schema, prompt and world context (P11) | `ai/naive/creation.py`, `ai/ports.py` (`ProfileDrafter.draft` gains `world`), `services/jobs/worker.py`; scripted drafter and mock bank fill `exampleLines` for parity | backend + frontend |
| Eval: drafter suite, reply-rule checks, repetition metrics (P8, P12) | the `horizon eval` harness (doc 02 §7) | backend |
| Doc 01 A5 and its fallback table's emotion row (P7); OQ-AI-16 resolved; CHR-05 AC1 drops "it's a mock in the UI phase" | `docs/ai/01-agent-architecture.md`, `docs/requirements/02, 08` | docs |

**No contract change.** `relationshipToUser`, `exampleLines` and `systemPromptPreview` already exist; `verbatim` and
the drafter's `world` argument are internal.

## 7. Left for later tasks

- The mood line's wording and the emotion evaluation (task 6).
- Group and watch turn-taking, including when a character should stay quiet or address another character (task 7).
- Debate argument, host and verdict prompts (task 8).
- "Last time we talked about …" greetings and memory in the prompt (task 9).
- The content-rating, advisory and "are you an AI?" wording (task 11).

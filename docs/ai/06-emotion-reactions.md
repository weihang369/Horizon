# 06: Emotion and reactions

> **Status: agreed with the user, 2026-10-09** (AI stage, task 6 of 13).
> - It resolves OQ-AI-07 (the AUTO emotion source; doc 01 A5 already chose Jev first) and the two items doc 01 left
>   to this task: **the mood line's wording** and **the emotion evaluation**. It also designs the listener reactions
>   (MULTI-04) that doc 01 A7 made one Jev call.
> - Decisions are numbered **E1–E9**, each with the alternatives we rejected.
> - It builds on [01-agent-architecture](01-agent-architecture.md) (A1–A14),
>   [02-evaluation-observability](02-evaluation-observability.md) (B1–B12),
>   [03-llm-parameters](03-llm-parameters.md) (C1–C9),
>   [04-persona-prompt-drafter](04-persona-prompt-drafter.md) (P1–P12) and
>   [05-context-engineering](05-context-engineering.md) (X1–X10).
> - **No contract change.** One behaviour fix in both session reducers (E6), with shared fixtures.

## 1. The question

The face is the most visible AI decision in Horizon (SC-2, "the AI is visibly the star"). Doc 01 decided that Jev
picks the speaker's face before the reply is written (A5) and that a failure or an unsure answer keeps the previous
face (A4). Task 6 decides **how Jev is asked**, **how DeepSeek is told the mood so the words agree with the face**,
**what a kept face means over several turns**, **how listeners react** in group, debate and watch, and **how all of
it is measured**.

**The user's decisions (2026-10-09), all four as recommended:**
- **The mood line is a mild phrase plus one rule**, and neutral sends no line (E4).
- **Short faces fade:** a kept surprised or embarrassed face goes back to neutral; happy, sad, angry and thinking
  stay (E3).
- **At most 2 listener reactions per message**, the most confident ones whose face actually changes (E5).
- **The face-and-words check runs in evaluation only** for now; it goes live with the System 1 Insight section
  (E7).

## 2. What Horizon already has

From the code:

- **The contract already carries everything:** `turn.start.emotion`, the `emotion` event (`characterId`, `emotion`,
  `source`), the `reaction` event (with `p` and `source`), `Message.reactions`, and `TurnTrace.emotion`
  (`chosen`, `source`, `candidates[{label, p}]`). `EmotionSource` is `user | llm | classifier | default`.
- **`naive`:** DeepSeek starts each reply with `<e:LABEL>`; [tag_parser.py](../../backend/horizon/ai/naive/tag_parser.py)
  turns it into an `Emotion` event, so the face appears with the first word, not before it. `naive` stays this way:
  it is the yardstick (doc 04 P7).
- **Listener reactions are random in every profile.** `naive` has no reactions implementation, so it resolves to
  `ScriptedReactions` ([scripted/ports.py](../../backend/horizon/ai/scripted/ports.py)): each listener reacts with
  probability `reactionChance` (0.7) and a random face, 300–800 ms after `turn.end`. The mock
  ([turnScript.ts](../../frontend/src/mock/script/turnScript.ts)) does the same.
- **`ReactionPredictor.predict` is synchronous** and records no spend; doc 01 already makes it async (its changes
  table).
- **Two findings:**
  1. **The reducers ignore `turn.start.emotion`.** Both the Python reducer
     ([reducer.py](../../backend/horizon/services/runtime/reducer.py)) and the TypeScript one read the face only
     from `emotion`, `reaction` and `turn.end`. So the face is sent as an `emotion` event straight after
     `turn.start` (E2), which needs no reducer or contract change.
  2. **A late reaction can change a speaker's face mid-reply (a D-46 break).** The runtime plays reactions as a
     background task ([turn.py](../../backend/horizon/sessions/turn.py) `_reactions`) that is not cancelled when the
     next turn starts, and both reducers apply a reaction's face even to the character who is streaming. The mock's
     "Reactions late or missing" scenario (2.5–4 s late) can trigger it today. E5 and E6 fix it.

## 3. The design in one picture

```
before the first word                         after turn.end (never delays the next speaker)
─────────────────────                         ──────────────────────────────────────────────
Jev call 1 (turn_plan)                        Jev reaction call (one request, one question per listener)
  "which face fits how {name} feels?"           → code keeps ≤ 2 confident changes
  → code: pick, or keep (fade short faces)      → each plays 300–800 ms after turn.end
gateway preflight OK                            → anything still pending is dropped at the next turn.start
  → turn.start, then `emotion` (the face)
DeepSeek streams, told the mood by one          eval only (for now): Jev reads the words alone and
  line in the dynamic tail                      guesses the face → "face and words agree"
```

## 4. Decisions

### E1. The speaker's emotion question (inside Jev call 1)

**Decision:**
- **One choice question per candidate**, in the `turn_plan` request (doc 01 A4), using the state doc 05 X9 already
  defines (`cast[].about`, `cast[].face`, `latest`, `recent`; watch's 12 lines; debate's motion and side):
  - 1:1 and group: *"Which face fits how {name} feels on reading the latest message?"*
  - watch and debate (no user line): *"Which face fits how {name} feels about the last line?"*
- **Options: the 7 emotions plus `none`** ("no clear change: keep the current face", doc 01 A3 rule 5). They are
  shuffled with the turn's stored seed, `none` included (A3 rule 4).
- **Every option has a `what`, a `not_for` and examples** with the same field names (A3 rule 3). The question bank
  (doc 02 B9) starts from these; the examples are short chat lines and may not appear in any evaluation item
  (doc 02 B2, no leakage):

  | Option | `what` | `not_for` |
  |---|---|---|
  | neutral | calm, at rest; a plain exchange with nothing to feel strongly about | a line that clearly pleases, hurts or startles them |
  | happy | pleased, amused, warm, relieved, proud | polite agreement with nothing to be glad about |
  | sad | hurt, disappointed, sorry, missing someone, low | mild disagreement; being tired |
  | angry | annoyed, offended, frustrated, defensive | firm disagreement said calmly |
  | surprised | caught off guard by news, a twist or an unexpected question | something they already knew or expected |
  | thinking | weighing a hard question, unsure, working something out | an ordinary question with an easy answer |
  | embarrassed | flustered, shy, caught out, praised more than they can take | being wrong in a calm, matter-of-fact way |
  | none | nothing in the line changes how they feel | a line that clearly calls for one of the faces above |

- **The options are always all 7,** even for a Lean-mode character with no portrait for some of them. The UI
  already shows neutral plus that emotion's effects and tint (EMO-06), and the mood line (E4) still shapes the
  words.
- **The group second replier** is asked again in its short re-plan after the first reply (doc 01 A4), so its face can
  react to what was just said. Debate asks it for every eligible member; watch for every candidate (doc 01 A4).
- **MANUAL mode still asks it** (it costs almost nothing inside the same request). The answer is recorded in the
  trace for Insight (CHAT-04 AC5), but it never reaches the screen or the prompt (E4).
- **Confidence floor:** set by doc 02 B5's grid against the existing target (≥ 80 % inside the acceptable set).
  Below the floor counts as unsure (E3).

**Rejected:**
- **only the 4 portraits a Lean character has:** the options would differ per character, so one floor and one bank
  would not fit all, and the mood would be lost exactly where the UI already has a fallback;
- **an intensity score next to the choice:** a second question with no visible use (there is one portrait per
  emotion), and a degree Jev is weaker at than a pick;
- **`none` left out:** without it Jev has to pick a face on every line, so faces flicker on small talk.

### E2. How the face reaches the screen and the trace

**Decision:**
- The agent engine yields `Emotion` **as its first event, as soon as the gateway preflight succeeds** (the stream is
  open, before the first token). The runtime then appends `turn.start` and the `emotion` event together, so a
  refused reply still leaves no message (doc 01 A5).
- **The `emotion` event carries the face, not `turn.start.emotion`,** because both reducers ignore the latter (§2
  finding 1). The `emotion` event is the path every client and the replay already handle.
- **`source`:**

  | Where the face came from | `source` |
  |---|---|
  | Jev's pick above the floor | `classifier` |
  | kept or faded: Jev said `none`, was unsure, failed or was late (E3) | `default` |
  | `naive`'s inline tag | `llm` (today's value, unchanged) |
  | MANUAL | `user` (unchanged) |

- **`TurnTrace.emotion`:** `chosen` (the face shown), `source`, and `candidates` = **the top 3 emotions by Jev's
  probability**. `none` is not an emotion, so it is left out of `candidates`; when `none` won, the bars still show
  what Jev weighed. A Jev failure leaves `candidates` out. In MANUAL, `chosen` is Jev's pick (what AUTO would have
  shown).
- **The verbatim first greeting** keeps doc 04 P9's stored face and `source: default`; no Jev call runs.

**Rejected:**
- **starting to read `turn.start.emotion` in both reducers:** a behaviour change in two reducers and their fixtures
  for no gain, since the `emotion` event arrives in the same append;
- **a new `EmotionSource` value for "kept":** a contract change; Insight's System 1 section (doc 01 A12) will show
  the reason for every fallback anyway.

### E3. Kept faces, and short faces fade

**Decision:**
- **A face is "kept"** when Jev answers `none`, is below the floor, fails or is late (doc 01 A4).
- **Short faces fade:** a kept **surprised** or **embarrassed** face becomes **neutral**. A kept **happy, sad, angry,
  thinking** or **neutral** face stays. This is code (doc 01 A3 rule 7), a fixed set in config (`emotion.fade`).
- The faded or kept face is what the mood line describes (E4), so the words follow the face that is shown.
- **The same rule applies to the group re-plan.** Listener faces set by reactions stay until the next reaction or
  the character's own turn; the reaction question sees the current face and may answer `neutral` (E5).

**Why:** surprise and embarrassment are moments, not moods. Keeping them across several turns looks frozen; keeping a
sad or angry face while the topic continues looks right.

**Rejected:**
- **always keep:** a character stays shocked for turns on end;
- **always go to neutral:** every unsure turn would erase a mood that is still true, and faces would flicker
  between neutral and the real mood.

### E4. The mood line

**Decision:**
- **One line in the dynamic tail** (doc 04 P2: after the retrieval block, before the repeat hint, the voice reminder
  and the cue), so the cached prefix never changes with the mood (NFR-35, doc 05 X6). It is always in English; the
  reply still follows the user's language (doc 04).
- **Wording:**

  > `{name}'s mood right now: {phrase}. Let it show in how you word this reply; don't name the feeling.`

  | Face | `{phrase}` |
  |---|---|
  | happy | in a good mood |
  | sad | a bit low |
  | angry | a bit annoyed |
  | surprised | caught off guard |
  | thinking | thoughtful, turning something over |
  | embarrassed | a little embarrassed |
  | neutral | *(no line)* |

- **The phrases are milder than the labels on purpose.** The label sets the face; the phrase only tunes the tone.
  Told "angry", DeepSeek tends to overact (shouting, insults), which breaks the persona more than a mismatched face
  would.
- **"Don't name the feeling"** stops replies such as "I'm so happy!". It sits next to doc 04's rule against stage
  directions (`*smiles*`); the face already shows the emotion.
- **No line for neutral, and no line in MANUAL mode** (the reply stays independent of the user's chosen face, D-07,
  CHAT-04 AC3). A kept face (E3) gets the line for the face that is shown.
- **Size and cost:** about 25–35 tokens, uncached, ≈ $0.000005 per reply. Doc 05 X1's tail budget (≈ 60 for the
  mood line, the repeat hint, the voice reminder and the cue) holds it.
- **Versioning:** the line is part of the `agent-1` prompt (doc 04 P1); the phrase table lives with the compiler and
  its TS twin, so "View as prompt" shows it.

**Rejected:**
- **a bare label** ("Mood: angry"): shortest, but it invites overacting;
- **no mood line:** the face and the words would agree only by luck, which breaks A5's "the words and the face
  always agree";
- **a per-emotion paragraph or an intensity word from Jev's probability:** more tokens per turn for a difference the
  evaluation could not see.

### E5. Listener reactions (group, debate, watch)

**Decision:**
- **A `JevReactions` implementation** of `ReactionPredictor` for the `agent` profile; `predict` becomes **async**
  (doc 01). **One Jev request after `turn.end`** (`Decider` purpose **`reaction`**, which the gateway already maps to
  the `decision` category), started only when the reply completed and the session is in AUTO (today's guard).
- **Listeners:** today's rule: present, not muted, with enough energy for a reply. The speaker is never a listener.
  1:1 has none, so no call is made.
- **The state** (doc 01 A3 rule 6, small and named):
  - `line`: the speaker's name and the reply, quoted, cut to 600 (first 450 + last 150);
  - `before`: the line before it (often the user's), quoted, cut to 300;
  - `listeners[]`: `name`, `about` (≤ 60, as in doc 05 X9), current `face`; in debate also `side` ("same side as
    the speaker" / "the other side");
  - `mode`.
- **One choice question per listener:** *"How does {listener} react to this line?"* Options: the 7 emotions plus
  `none` ("no visible reaction"), with the same `what` / `not_for` pattern as E1 and shuffled with the stored seed.
- **Code decides what shows.** A reaction is kept only if:
  1. the pick is not `none`, and its confidence is above the **reaction floor** (doc 02 B5's grid, target below);
  2. **the face differs from the listener's current face;**
  3. it is one of the **2 most confident** for this message (by the chosen option's probability).
- **Timing:** each kept reaction plays at **300–800 ms after `turn.end`** (today's `reactionDelayMs`, one random delay
  each from the turn seed), or as soon as Jev answers if that is later. The call has a **1.5 s** timeout
  (`timeoutsMs.decision.reaction` = 1500 in `seed/pricing.json`); a late or failed call shows nothing (MULTI-04 AC2
  allows it).
- **Pending reactions are dropped at the next `turn.start`** in the session. The runtime cancels the session's
  `reactions` background task before it appends any `turn.start`, so a reaction is only ever about the newest line
  (§2 finding 2). E6 guards the same rule in the reducers.
- **The event:** `reaction` with `source: classifier` and `p` = the chosen option's probability. No trace change.
- **Cost:** about 400 tokens of state plus ~150 per listener question; with 4 listeners ≈ 1,000 tokens × $0.042 / M
  ≈ **$0.00004 per character message**. It counts toward the daily cap only, never energy (ENG-02 AC2).
- **Other profiles:**
  - `scripted` keeps its random reactions but becomes async and **records a simulated `reaction` call** at the
    decision price, so the cost HUD matches the `agent` profile's shape (D-81, as doc 05 X3 does for the summary);
  - `naive` keeps resolving to the scripted one: reactions are not part of the yardstick comparison.
  - The mock's `turnScript` gets the same "drop at the next turn start" rule.

**Rejected:**
- **every confident listener** (the user chose 2): a five-character group flickers after every line;
- **at most 1:** debates lose the "listeners react with their faces" moment the vision describes
  (requirements doc 01, "Debate live"), where an ally and an opponent both react;
- **reactions inside Jev call 1 of the next turn:** the line they react to is only known after `turn.end`, and the
  next turn's plan must not wait for them;
- **reactions to the user's own message:** the speakers already react through E1; listeners react to the reply.
  Unchanged from today;
- **DeepSeek writing reactions:** slower, costlier, and no probabilities.

### E6. A reaction never changes the face of the character who is speaking

**Decision:**
- **Both reducers** (Python and TypeScript) still record a `reaction` on its message, but **do not apply its face**
  when the reacting character's own turn is streaming (`state.turn.characterId` / the streaming message's author).
- Shared reducer fixtures gain the case "a reaction for the streaming speaker arrives mid-stream: recorded, face
  unchanged".

**Why:** E5's cancel covers the live runtime, but not old event logs, the mock's late-reaction scenario, or a slow
client applying events late. D-46 ("one message, one emotion") and doc 02 B8's **face-flip rate of 0** need the guard
where the face is decided: the reducer.

**Rejected:** relying on the runtime's cancel alone: replay and the mock would still flip faces.

### E7. The face-and-words check: evaluation only, for now

**Decision:**
- Doc 01 A7's post-turn check graph loses its emotion branch **in the live app** until the System 1 Insight section
  (doc 01 A12, a contract change with its own approval) exists. Today's trace has no field for the result, so a live
  check would be paid for and not shown.
- The check itself is unchanged and runs in the evaluation (doc 02 B4's "Face and words agree": Jev reads only the
  reply and picks one of the 7 emotions).
- **When the System 1 section is approved,** the check goes live as one Jev call after `turn.end` (about $0.00001 a
  turn) and Insight shows "face and words agree: yes / no". It never changes the face (D-46).

**Rejected:** a live check now, writing only to the ledger: a cost with no reader.

### E8. Evaluation additions

**Decision** (fits doc 02's layers; each new Jev question is validated as B4 describes before it is trusted):
- **Layer 1, emotion: ~100 items instead of 40** (doc 02 B2's "every other question" row), because the face shows on
  every turn of every mode. Spread: all four modes, both worlds, English, Malay, Chinese and mixed lines, and at least
  15 items where "keep the previous face" is the right answer. Each item already records one or two acceptable faces,
  the previous face, and whether keeping it is acceptable (doc 02 B2). Target unchanged: **≥ 80 % inside the
  acceptable set**, with the E3 fade applied before scoring.
- **Layer 1, reactions: a new set of 60 items** (a line, its context and one listener; group, debate and watch). The
  acceptable set may include `none`. Target **≥ 80 % inside the acceptable set**; the floor comes from doc 02 B5's
  grid. The report also gives the **share of messages that get a reaction** (no target; the seed scripts react on most
  lines, so a share under ~30 % is read by hand).
- **Layer 3, two reply checks on `agent` replies that carried a mood line:**
  - **"Doesn't name the feeling"** (a new noul: "does the reply state the character's own feeling outright, such as
    'I'm so happy'?", phrased so yes means a failure is found): **≥ 95 %** pass on the ~150 such replies;
  - **"Face and words agree"** (doc 02 B4's existing choice): the words' guess equals the shown face or `neutral` in
    **≥ 80 %**, and **clashes** (happy against sad or angry, either way) **≤ 5 %**.
- **Mood line on vs off, once** (run with the other paid checks before coding): 100 turns of the frozen transcripts
  are replied to again without the line; both arms get the two checks above and the pairwise judge in both orders.
  The line stays unless it lowers the pairwise preference (average probability under 0.45) or fails to improve
  agreement; then it is reworded, not dropped. ≈ $0.06 once.
- **NFR-29** is measured exactly as doc 02 B8 says (face time minus first-word time per source, face-flip rate 0).
  The E6 reducer case and an E5 timing case are added to the offline tests.
- **Judge validation** (doc 02 B4) for the new noul: 60 items (30 real + 30 planted), < $0.01 once.
- **Offline, $0:** the fade rule, the mood line per face (none for neutral and MANUAL), the top-2 and "differs" rules,
  the cancel at the next `turn.start`, the E6 reducer fixture, and the shuffled options with the stored seed.
- **Doc 02 B7 cost:** `decisions` ≈ $0.07 (was $0.06: 60 more emotion items and 60 reaction items, both orders);
  `conversations` unchanged at ≈ $0.38 (the new noul is under a cent); **`all` ≈ $0.59** (about RM 2.5); ≈ $0.81 at
  peak; ≈ $0.42 once `naive` replies are cached.

### E9. Speed and cost, in one place

| Item | When | Cost | Time |
|---|---|---|---|
| Speaker emotion (E1) | inside Jev call 1, every turn | ≈ $0 extra (one more question in the same request) | none extra; the face shows at preflight, before the first word |
| Mood line (E4) | every AUTO reply that isn't neutral | ≈ $0.000005 | none |
| Reactions (E5) | after each character message in group, debate, watch | ≈ $0.00004 | after `turn.end`; never delays the next speaker |
| Face-and-words check (E7) | evaluation only | — | — |

## 5. Checks before this is locked

1. **Offline, $0:** E8's offline tests on the seed characters in all four modes.
2. **With the other paid checks before coding** (the user approves the total then): E8's mood-line on/off run
   (≈ $0.06), and the layer 1 emotion and reaction sets inside the first `decisions` run.

## 6. Changes this design needs (each approved at its OpenSpec change)

| Change | Where | Kind |
|---|---|---|
| The emotion question per candidate and its bank entries; MANUAL still asks (E1) | the turn plan graph (doc 01 A4), the question bank (doc 02 B9) | backend |
| The agent engine yields `Emotion` first after preflight; sources and `TurnTrace.emotion` candidates (E2) | the agent reply engine, `sessions/turn.py` | backend |
| The fade rule and `emotion.fade` in config (E3) | the turn plan's emotion fallback; `runtime.config.ts` → `seed/runtime.json`; `domain/runtime_config.py` | backend + config |
| The mood line and its phrase table, none for neutral and MANUAL (E4) | `ai/agent/persona.py` and its TS twin (doc 04), shared fixtures | backend + frontend |
| `JevReactions`; async `ReactionPredictor.predict`; scripted reactions record a simulated `reaction` call; the 1.5 s timeout (E5) | new `ai/agent/reactions.py`, `ai/ports.py`, `ai/profile.py`, `ai/scripted/ports.py`, `sessions/turn.py` (`_reactions`); `seed/pricing.json` gains `timeoutsMs.decision.reaction` (its old `emotion: 300` entry goes unused once the emotion is inside `turn_plan`, doc 01 A4) | backend + config |
| Pending reactions cancelled before any `turn.start` (E5) | `sessions/actor.py` (a named, cancellable reactions task), `sessions/turn.py` | backend |
| The mock drops reactions at the next turn start (E5) | `frontend/src/mock/script/turnScript.ts` and the engines that schedule turns | frontend |
| A reaction never changes the streaming speaker's face (E6) | `services/runtime/reducer.py`, `frontend/src/engine/sessionReducer.ts`, the shared reducer fixtures | backend + frontend |
| Post-turn graph without the live emotion branch until A12 (E7) | the post-turn check graph (doc 01 A7) | backend |
| Eval: emotion set to ~100, the reactions set, the new noul, the mood-line run, offline tests (E8) | `evals/`, the `horizon eval` harness, `backend/tests/` | backend |
| Doc 02: B2 sizes, B4 judge row, B5 reaction target, B7 cost | `docs/ai/02-evaluation-observability.md` | docs |
| Doc 01: A4's emotion fallback row (fade), A5 (the `emotion` event, the mood line's home), A7 (live emotion check waits for A12); OQ-AI-07 resolved | `docs/ai/01-agent-architecture.md`, `docs/requirements/08` | docs |

**No contract change.** Every field already exists (§2). E6 changes reducer behaviour, not the contract: no new
event, field or entry point.

## 7. Left for later tasks

- Custom emotions (EMO-07): v2.
- Watch's pacing, the talk-finished question and energy-aware turn-taking (task 7).
- Debate's member choice and the verdict (task 8); E5's debate `side` label is the only debate input here.
- The quoted-content wording in the emotion and reaction states (task 11).
- The live face-and-words check, with the System 1 Insight section (doc 01 A12's approval).

## Sources

- TypeSafe Jev notes on choice questions, option fields, first-option lean and small states: see doc 01 A3 and its
  sources.
- Requirements: CHAT-03 (timing, crossfade), CHAT-04 (AUTO / MANUAL), MULTI-04 (listener reactions), EMO-06 (missing
  portrait), NFR-29, D-07, D-46.

# 06: Emotion and reactions

> **Status: agreed with the user, 2026-10-09** (AI stage, task 6 of 13). **Revised after an independent review**
> (it checked the code; 23 findings, all addressed).
> - It resolves OQ-AI-07 (the AUTO emotion source; doc 01 A5 already chose Jev first) and the two items doc 01 left
>   to this task: **the mood line's wording** and **the emotion evaluation**. It also designs the listener reactions
>   (MULTI-04) that doc 01 A7 made one Jev call.
> - Decisions are numbered **E1–E9**, each with the alternatives we rejected.
> - It builds on [01-agent-architecture](01-agent-architecture.md) (A1–A14),
>   [02-evaluation-observability](02-evaluation-observability.md) (B1–B12),
>   [03-llm-parameters](03-llm-parameters.md) (C1–C9),
>   [04-persona-prompt-drafter](04-persona-prompt-drafter.md) (P1–P12) and
>   [05-context-engineering](05-context-engineering.md) (X1–X10).
> - **No contract change.** One change to derived state in both session reducers (E6), with shared fixtures, and one
>   small Insight display rule (E2).

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
- **The face-and-words check** went live with the System 1 Insight section ([doc 13](13-wrap-up.md) W1, W2; E7).

## 2. What Horizon already has

From the code:

- **The contract already carries everything:** `turn.start.emotion`, the `emotion` event (`characterId`, `emotion`,
  `source`, optional `messageId`), the `reaction` event (with `p` and `source`), `Message.reactions`, and
  `TurnTrace.emotion` (`chosen`, `source`, `candidates[{label, p}]`). `EmotionSource` is
  `user | llm | classifier | default`.
- **How a face reaches the screen today** ([reducer.py](../../backend/horizon/services/runtime/reducer.py)
  `_apply_emotion`, and its TypeScript twin `sessionReducer.ts`):
  - an `emotion` event with a `messageId` sets `message.emotion` and `emotionSource`;
  - if it arrives **before the first token**, the face is held in `pendingEmotion` and **shown with the first token**
    (CHAT-03 AC4: "the emotion appears at stream start"); later, it is shown at once ("switches late");
  - `turn.start.emotion` is applied too, but **with the source hard-coded to `llm`**;
  - in MANUAL the face is recorded on the message but not shown on the portrait (CHAT-04 AC5); a MANUAL face change
    is an `emotion` event **without** `messageId`, source `user` ([commands.py](../../backend/horizon/sessions/commands.py)
    `_set_emotion`).
- **The gateway's preflight runs inside the stream.** `Gateway.chat_stream` is an async generator: the cap, key and
  credit preflight runs on the first `__anext__`, which returns only with the provider's first chunk
  ([pipeline.py](../../backend/horizon/gateway/pipeline.py)). An engine has no moment "after preflight, before the
  first chunk" to act on.
- **`naive`:** DeepSeek starts each reply with `<e:LABEL>`; [tag_parser.py](../../backend/horizon/ai/naive/tag_parser.py)
  turns it into an `Emotion` event. `naive` stays this way: it is the yardstick (doc 04 P7).
- **Listener reactions are random in every profile.** `naive` resolves `reactions` to `ScriptedReactions`
  ([scripted/ports.py](../../backend/horizon/ai/scripted/ports.py)): each listener reacts with probability
  `reactionChance` (0.7) and a random face, 300–800 ms after `turn.end`. The mock
  ([turnScript.ts](../../frontend/src/mock/script/turnScript.ts)) does the same and charges nothing for it.
- **`ReactionPredictor.predict` is synchronous, records no spend, and is called inside `finish`** before the
  background task is spawned ([turn.py](../../backend/horizon/sessions/turn.py) `_reactions`), using `ctx.session`,
  which was built when the turn (or its prefetch) started.
- **Findings:**
  1. **A late reaction can change a speaker's face mid-reply (a D-46 break).** Reactions play in a background task
     that nothing cancels except the actor's `stop()` (not `clear()`, so not Stop, leave, a cap pause or the end),
     and both reducers apply a reaction's face even to the character who is streaming. The seed dinner chat already
     contains the case: `ses_seedDinner` seq 25 is a reaction for Rin 10 ms after her own `turn.start`. The mock's
     "Reactions late or missing" scenario (2.5–4 s late) makes it common.
  2. **The next turn starts about 0.5 s after `turn.end`** in group (`turnGapMs` 400, `thinkingMs` 60; a released
     prefetch replays at once; seed dinner: `turn.end` at 03.279, next `turn.start` at 03.779), and watch "Fast" is
     500 ms. A reaction rule tied to "the next turn starts" would cut most reactions (E5).
  3. **Insight's emotion section puts the top candidate's band next to `chosen`**
     ([InsightDrawer.tsx](../../frontend/src/features/insight/InsightDrawer.tsx)), which is misleading when the face
     shown is not Jev's top pick (E2).

## 3. The design in one picture

```
before the first word                           after turn.end (never delays the next speaker)
─────────────────────                           ──────────────────────────────────────────────
Jev call 1 (turn_plan), per candidate:          Jev reaction call (one request, one question per listener,
  "which face fits how {name} feels?"             listeners read fresh from the session state)
  → code: Jev's pick, or keep (short faces fade)  → code keeps ≤ 2 confident changes (+ fades)
DeepSeek's first chunk arrives                    → each plays 300–800 ms after turn.end
  → turn.start + `emotion` (one append)           → the next speaker's reaction is dropped when its turn
  → the face shows with the first word              starts; all are dropped at a user message, Stop, pause, end
DeepSeek streams, told the mood by one
  line in the dynamic tail                      eval only (for now): Jev reads the words alone and
                                                  guesses the face → "face and words agree"
```

## 4. Decisions

### E1. The speaker's emotion question (inside Jev call 1)

**Decision:**
- **One choice question per candidate**, in the `turn_plan` request (doc 01 A4), using the state doc 05 X9 defines
  (`cast[].about`, `cast[].face`, `latest`, `recent`; watch's 12 lines; debate's motion and side). The wording
  depends on what the character is answering:

  | Turn | Question |
  |---|---|
  | 1:1 and group, answering the user | *"Which face fits how {name} feels on reading the latest message?"* |
  | watch, debate (no user line) | *"Which face fits how {name} feels about the last line?"* |
  | debate opening, after the host's line | *"Which face fits how {name} feels about arguing for their side of the motion?"* |
  | watch's first turn | *"Which face fits how {name} feels at the start of this scene?"* (the premise is in the state) |
  | a generated greeting (doc 04 P9, a later first chat) | *"Which face fits how {name} feels on meeting {user_name} again?"* |

  The verbatim first greeting asks nothing (doc 04 P9).
- **Options: the 7 emotions plus `none`** ("no clear change: keep the current face", doc 01 A3 rule 5). They are
  shuffled per question (A3 rule 4) with a seed **derived per question** from the stored per-turn seed: `f"{session seed}:{turn index}:{question}"`,
  so a turn can be replayed exactly. The System 1 section stores the per-turn part as `system1.seed` ([doc 13](13-wrap-up.md) W1).
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

- **`neutral` and `none` mean the same thing when the current face is neutral.** In that case code adds their
  probabilities together (as `neutral`) before the floor is applied, so a split between them does not count as
  "unsure".
- **One measure throughout:** Jev's **confidence** for the floor (doc 01 A4, doc 02 B5), and the **chosen option's
  probability** only for display (`p`, Insight's bars).
- **The options are always all 7,** even for a Lean-mode character with no portrait for some of them. The UI shows
  neutral plus that emotion's effects and tint (EMO-06), and the mood line (E4) still shapes the words.
- **Which paths ask again after the first reply:** the group **auto** policy's second replier (and Step in's) is
  chosen by doc 07 G2's follow plan, which also asks its gates and emotion, so its face can react to the first reply.
  A **prefetched** reply keeps the answers it was planned with, before the line it follows existed: debate openings
  from their own Jev call 1, and every Everyone reply from the run's single call 1 (doc 07 G4). Watch never prefetches: its next plan starts at `turn.end` (doc 07 G8).
- **MANUAL mode still asks it** (it costs almost nothing inside the same request): see E2 for where the answer goes.
- **Confidence floor:** set by doc 02 B5's grid against E8's target. Below the floor counts as unsure (E3).

**Rejected:**
- **only the portraits a Lean character has:** the options would differ per character, so one floor and one bank
  would not fit all, and the mood would be lost exactly where the UI already has a fallback;
- **an intensity score next to the choice:** a second question with no visible use (one portrait per emotion);
- **`none` left out:** without it Jev has to pick a face on every line, so faces flicker on small talk.

### E2. How the face reaches the screen and the trace

**Decision:**
- **The agent engine yields `Emotion` on DeepSeek's first chunk, before the first `Token`.** The preflight has
  passed by then (§2), so a refused reply still leaves no message (doc 01 A5). The runtime appends `turn.start` and
  the `emotion` event **in one `actor.emit`**, so nothing (such as a pending reaction) can land between them.
- **The face shows with the first word** (CHAT-03 AC4's `pendingEmotion`), never after it: the face-to-first-word gap
  on this path is 0 (NFR-29). The user still sees the face before reading anything, because the face crossfade starts
  with the first word and the words take longer to read. Doc 01 A5's "before the first word" is corrected to this.
- **The agent path never sets `turn.start.emotion`**, because both reducers would store it as `llm` (§2).
- **`source`:**

  | Where the face came from | `source` |
  |---|---|
  | Jev's pick above the floor | `classifier` |
  | kept or faded: Jev said `none`, was unsure, failed or was late (E3) | `default` |
  | the verbatim first greeting (doc 04 P9) | `default` (unchanged) |
  | `naive`'s inline tag | `llm` (unchanged) |
  | a MANUAL face change from the portrait menu (no `messageId`) | `user` (unchanged) |

- **In MANUAL mode** (CHAT-04 AC5, D-07):
  - the turn's `emotion` event carries **what AUTO would have chosen**, with `classifier` or `default` as above. The
    reducers record it on the message and in the trace and never put it on the portrait. The message's log icon
    (CHAT-03 AC3) therefore shows the AI's pick, the same as `naive` today;
  - **the base face for "kept" is the character's last AI-chosen face** (the `emotion` of their latest message in
    this session, else neutral), **not** the face the user set. The fade (E3) acts on that, never on the user's
    choice;
  - no mood line (E4) and no reactions (today's guard, MULTI-04 AC3).
- **`TurnTrace.emotion`:** `chosen` (the face sent), `source`, and `candidates` = **the top 3 emotions by Jev's
  probability**, with `neutral` merged as E1 says. `none` is not an emotion, so it is left out of `candidates`. A Jev
  failure leaves `candidates` out.
- **An Insight display rule (UI only):** when `chosen` is not the top candidate, the section drops the band next to
  `chosen` and shows the chip **"kept"** instead of the source, so a kept face is not shown with another emotion's
  confidence. The greeting stays labelled by its source.

**Rejected:**
- **yielding the face "after preflight, before the first chunk":** the gateway has no such point (§2); adding one
  changes the gateway for a moment the reducers would not show anyway (the face is held until the first token);
- **setting `turn.start.emotion` and changing both reducers to read a source from it:** a reducer and fixture change
  for nothing the `emotion` event in the same append doesn't already give;
- **a new `EmotionSource` value for "kept":** a contract change; the System 1 section ([doc 13](13-wrap-up.md) W1) shows the reason
  for every fallback.

### E3. Kept faces, and short faces fade

> **Amended by doc 11 S4:** while the care cue is on, code forces the speaker's face into neutral, sad or thinking on
> every path (E1's Jev answer, the Jev-failed kept face, this section's kept face); any other face becomes neutral.

**Decision:**
- **A face is "kept"** when Jev answers `none`, is below the floor, fails or is late (doc 01 A4). The base is the
  current face in AUTO, and the last AI-chosen face in MANUAL (E2).
- **Short faces fade:** a kept **surprised** or **embarrassed** face becomes **neutral**. A kept **happy, sad, angry,
  thinking** or **neutral** face stays. This is code (doc 01 A3 rule 7), a fixed set in config (`emotion.fade`).
- The face sent (kept or faded) is what the mood line describes (E4), so the words follow the face shown.
- **Listener faces fade too:** a listener whose face is surprised or embarrassed and who gets no reaction on the next
  reaction pass (E5) gets a `neutral` reaction with `source: default`, **outside the cap of 2**. So a character who
  rarely speaks (muted, exhausted, or not chosen by the auto policy) is never left frozen on a short face. A muted or
  exhausted character gets this fade only, never a Jev reaction.

**Why:** surprise and embarrassment are moments, not moods. Keeping them across several turns looks frozen; keeping a
sad or angry face while the topic continues looks right.

**Rejected:**
- **always keep:** a character stays shocked for turns on end;
- **always go to neutral:** every unsure turn would erase a mood that is still true, and faces would flicker
  between neutral and the real mood;
- **a timer that resets short faces after N seconds:** an extra event stream outside any turn, and different
  behaviour in replay at other speeds.

### E4. The mood line

**Decision:**
- **One line in the dynamic tail** (doc 04 P2: after the retrieval block, before the repeat hint, the voice reminder
  and the cue), so the cached prefix never changes with the mood (NFR-35, doc 05 X6). It is always in English; the
  reply still follows the user's language (doc 04). Like the rest of the prompt (doc 04 P2), it speaks to the
  character in the second person.
- **Wording:**

  > `Your mood right now: {phrase}. Let it show in how you word this reply; don't name the feeling.`

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
- **"Don't name the feeling"** stops replies such as "I'm so happy!": the words should show the feeling, not report
  it. It sits next to doc 04's rule against stage directions (`*smiles*`); the face already shows the emotion.
- **No line for neutral, and no line in MANUAL mode** (the reply stays independent of the face, D-07, CHAT-04 AC3).
- **Size and cost:** about 25–30 tokens, uncached, ≈ $0.000005 per reply. Doc 05 X1's tail figure (≈ 60) is a
  planning number for the usual case; a debate Ask cue or a watch director's note (which carry user text) already go
  past it, and so does a turn with the repeat hint or voice reminder on. The tail has no cap; X1's ~1,000-token slack
  under the budget absorbs it, and Insight's context bar shows any overflow (doc 05 X1).
- **Versioning:** the line is part of the `agent-1` prompt (doc 04 P1); the phrase table lives with the compiler and
  its TS twin, so "View as prompt" shows it.
- **Measured, not assumed:** E8's on/off run decides whether the line stays.

**Rejected:**
- **a bare label** ("Mood: angry"): shortest, but it invites overacting;
- **no mood line from the start:** the face and the words would agree only by luck; E8 measures whether the line
  earns its tokens instead;
- **a per-emotion paragraph or an intensity word from Jev's probability:** more tokens per turn for a difference the
  evaluation could not see.

### E5. Listener reactions (group, debate, watch)

> **Amended by doc 11 S4:** no listener reactions on a turn where the care cue is on.

**Decision:**
- **A `JevReactions` implementation** of `ReactionPredictor` for the `agent` profile. `predict` becomes **async and is
  called inside the background task**, never in `finish`, so the Jev call cannot delay the next speaker. One Jev
  request after `turn.end` (`Decider` purpose **`reaction`**, already mapped to the `decision` category), only when
  the reply completed and the session is in AUTO (today's guard).
- **Listeners are read fresh from the actor's state** when the task runs (not from the turn's `ctx.session`, which
  may predate a mute or an energy change): present, not muted, with enough energy for a reply, not the speaker. 1:1
  has none, so no call is made.
- **The state** (doc 01 A3 rule 6, small and named):
  - `line`: the speaker's name and the reply, quoted, cut to 600 (first 450 + last 150). *All quoted fields take
    the bank-wide `quoted_` names from M7 (doc 11 S6, [doc 13](13-wrap-up.md) W4), here `quoted_line` and `quoted_before`;*
  - `before`: the line before it (often the user's), quoted, cut to 300;
  - `listeners[]`: `name`, `about` (≤ 60, as in doc 05 X9), current `face`; in debate also `side` ("same side as
    the speaker" / "the other side");
  - `mode`.
- **One choice question per listener:** *"How does {listener} react to this line?"* Options: the 7 emotions plus
  `none` ("no visible reaction"), with E1's `what` / `not_for` pattern, the E1 `neutral` + `none` merge when the
  listener's face is neutral, and a derived seed (`…:react:{listener}`).
- **Code decides what shows.** A reaction is kept only if:
  1. the pick is not `none`, and Jev's **confidence** is above the **reaction floor** (doc 02 B5's grid, E8 target);
  2. **the face differs from the listener's current face**, read again just before the event is appended;
  3. it is one of the **2 most confident** for this message.

  Plus E3's fades, outside the cap.
- **Timing:** each kept reaction plays at **300–800 ms after `turn.end`** (today's `reactionDelayMs`, one delay each
  from the derived seed), or as soon as Jev answers if that is later. The call has a **1.5 s** timeout
  (`timeoutsMs.decision.reaction` = 1500 in `seed/pricing.json`); a late or failed call shows nothing (MULTI-04 AC2
  allows it).
- **When pending reactions are dropped** (the session's reactions task is named, so it is cancelled without touching
  other background tasks, such as the face check, [doc 13](13-wrap-up.md) W2):

  | Event | What is dropped |
  |---|---|
  | the next turn's `turn.start` (in the same `actor.emit` as its `emotion`, E2), including a released prefetch | **only the reaction for that turn's speaker**; the others still play (a group's next turn starts ≈ 0.5 s after `turn.end`, §2 finding 2) |
  | a new user message, Stop, leave, a cap pause, the session's end, MANUAL switched on | **all** pending reactions |

  Just before each append, the task re-checks that the session is still AUTO and the listener is still present and
  unmuted.
- **A failure never touches the session.** Any `ProviderError`, including a budget refusal of the reaction call, is
  caught inside the task and logged; it never triggers the cap pause (that is the reply's job).
- **The event:** `reaction` with `source: classifier` and `p` = the chosen option's probability (fades: `default`,
  no `p`).
- **Cost:** about 400 tokens of state plus ~300 per listener question (each carries the 8-option table); with 4
  listeners ≈ 1,600 tokens × $0.042 / M ≈ **$0.00007 per character message**, more if doc 01's check 4 finds the
  state billed per question. It goes to the ledger and counts toward the daily cap only, never energy (ENG-02 AC2).
  Like the rolling summary (doc 05 X3), it is not part of the message's `usage`, so the session's cost HUD (which sums
  `turn.end` usage) leaves it out; [doc 13](13-wrap-up.md) W7 keeps the counter to reply spend, with a tooltip pointing to Settings → Cost.
- **Other profiles:**
  - `scripted` keeps its random reactions, becomes async, and **records a simulated `reaction` call** at the decision
    price (D-81, as doc 05 X3 does for the summary), so the ledger and the daily cap see the same calls as `agent`;
  - the **mock charges the same simulated call** (`h.charge`, as its group routing does) and applies the same drop
    rules, so the portable spend and cap tests stay in step (R-15);
  - `naive` keeps resolving to the scripted one: reactions are not part of the yardstick comparison.

**Rejected:**
- **every confident listener** (the user chose 2): a five-character group flickers after every line;
- **at most 1:** debates lose the "listeners react with their faces" moment the vision describes (requirements doc
  01, "Debate live"), where an ally and an opponent both react;
- **dropping every reaction at the next `turn.start`** (this doc's first draft): the next turn starts ≈ 0.5 s after
  `turn.end`, so most reactions would never show;
- **reactions inside Jev call 1 of the next turn:** the line they react to is only known after `turn.end`, and the
  next turn's plan must not wait for them;
- **reactions to the user's own message:** the speakers already react through E1; listeners react to the reply.
  Unchanged from today;
- **DeepSeek writing reactions:** slower, costlier, and no probabilities.

### E6. A reaction never changes the face of the character who is speaking

**Decision:**
- **Both reducers** (Python and TypeScript) still record a `reaction` on its message, but **do not apply its face**
  when the reacting character is the author of the message in `streamingId` (from its `turn.start` to its
  `turn.end`). `state.turn` is not used for this, because it outlives `turn.end`.
- The recorded reaction stays on `message.reactions` as what was predicted; the portrait shows the speaker's own face.
- **Fixtures:** the shared reducer fixtures gain "a reaction for the streaming speaker, before and after its first
  token: recorded, face unchanged", and the seed case `ses_seedDinner` seq 25 (Rin) is added. The seed equivalence
  check is re-run.
- **This changes derived state, not the contract:** `participants[].currentEmotion` and `displayEmotion` can differ
  between seq 24 and the first token. No event, field or entry point changes. A stored session re-reduced after this
  change (crash recovery, fork, D-79) can show a different face only in that window; its final state is the same.

**Why:** E5's runtime rules cover the live app, but not old event logs, the mock's late-reaction scenario, or a
client applying events late. D-46 ("one message, one emotion") and doc 02 B8's **face-flip rate of 0** need the
guard where the face is decided: the reducer.

**Rejected:** relying on the runtime alone: replay and the mock would still flip faces.

### E7. The face-and-words check: evaluation only, for now (superseded: live, [doc 13](13-wrap-up.md) W2)

**Decision:**
- Doc 01 A7's post-turn check graph has **no live emotion branch** until the System 1 Insight section exists (doc 01
  A12, a contract change). **The user approved that section in principle on 2026-10-09; [doc 13](13-wrap-up.md) W1 designs it,** once
  tasks 7–11 have added their Jev questions. Today's trace has no field for the result, so a live check would be paid
  for and not shown.
- The check itself runs in the evaluation (doc 02 B4's "Face and words agree": Jev reads only the reply and picks
  one of the 7 emotions).
- **When the System 1 section is built,** the check goes live as one Jev call after `turn.end` (≈ $0.00002 per checked reply,
  [doc 13](13-wrap-up.md) W2) and Insight shows "face and words agree: yes / no". It never changes the face (D-46).

**Rejected:** a live check now, writing only to the ledger: a cost with no reader.

### E8. Evaluation additions

**Decision** (fits doc 02's layers and statistics; each new Jev question is validated as B4 describes before it is
trusted):
- **How targets are read here:** on the **test split** (doc 02 B2's 2/3 dev, 1/3 test), the target applies to the
  point estimate, the Wilson interval is always reported, and a set whose interval straddles the target **grows by 40
  items** (doc 02 B2's rule). Sets this size catch a gross failure and show the direction; they do not prove a
  percentage.
- **Floors are tuned the way they run live:** on **one seeded shuffle per item**, as the live call asks. The second
  order (doc 02 B6) is used only to measure the first-option lean, not to tune the floor.
- **Layer 1, emotion: ~100 items instead of 40** (doc 02 B2's "every other question" row), because the face shows
  on every turn of every mode. Spread: all four modes and the E1 turn kinds, both worlds, English, Malay, Chinese
  and mixed lines. Each item records one or two acceptable faces, the previous face, and whether keeping it is
  acceptable (doc 02 B2).
  - **No more than 30 % of items** may list "keep" (or `neutral` from a neutral face) as acceptable, and at least 20
    must, so the keep path is both tested and unable to carry the score.
  - **Targets:** ≥ 80 % inside the acceptable set (E3's fade and E1's merge applied first), **and at least 15 points
    above the trivial baseline "always keep the current face"** on the same test items.
- **Layer 1, reactions: a new set of 90 items** (30 test; a line, its context and one listener; group, debate and
  watch). The same 30 % cap on items where `none` is acceptable. **Targets:** ≥ 80 % inside the acceptable set, and
  at least 15 points above the baseline "always `none`". The report also gives the **share of messages that would get
  a reaction**; the latency suite (doc 02 B8) reports the **share actually shown** after E5's drops and timeout. A
  shown share under ~30 % is read by hand.
- **Layer 3, two reply checks.** First, the frozen-transcript run counts the `agent` replies that carried a mood line
  (non-neutral faces, AUTO); the targets below are confirmed on that count before they are used.
  - **"Names the feeling"** (a new noul: "does the reply state the character's own feeling outright, such as 'I'm
    so happy'?"; a pass is "no"): point estimate **≥ 95 %**, every failure read. Its judge validation (doc 02 B4) adds
    a requirement: **at most 1 false alarm on the 30 clean real replies**, since a judge that flags 5 % of clean
    replies would make the target meaningless.
  - **"Face and words agree"** (doc 02 B4's existing choice), measured **only on turns whose face is not neutral**:
    the **exact match** (the words' guess equals the face shown), and **clashes** (happy against sad or angry, either
    way) **≤ 5 %**. Exact match has no fixed target; it is the quantity the on/off run compares.
- **Mood line on vs off, once** (in M9, [doc 13](13-wrap-up.md) W6, so the line is settled before the other suites are tuned): **up to 100 non-neutral turns** of
  the frozen transcripts are replied to again without the line. Both arms get the two checks above and the pairwise
  judge in both orders. Compared **per conversation with a paired bootstrap** (doc 02 B1). Decided in advance:
  - **keep the line** if exact match rises (its 95 % interval above 0) and the pairwise preference is not worse (its
    interval reaches 0.5 or above);
  - **reword once and re-run** if exact match rises but the replies are judged worse;
  - **propose dropping it** (to the user, before any change) if exact match does not rise, or still judged worse
    after the rewording.
  - ≈ $0.06 once.
- **NFR-29** is measured as doc 02 B8 says (amended): face time minus first-word time per source, where on the
  `agent` path the sources are `classifier` (Jev's pick) and `default` (kept or faded); the verbatim greeting is left
  out; the face-flip rate must be 0.
- **Judge validation** (doc 02 B4) for the new noul: 60 items (30 real + 30 planted), < $0.01 once.
- **Offline, $0:** the fade rule (speaker and listener), the `neutral` + `none` merge, the mood line per face (none
  for neutral and MANUAL), the MANUAL base face, the top-2 and "differs" rules, every drop point in E5's table, the
  one-append `turn.start` + `emotion`, the E6 reducer fixtures, and the derived seeds.
- **Doc 02 B7 cost:** `decisions` ≈ $0.07 (was $0.06: 60 more emotion items and 90 reaction items, both orders);
  `conversations` unchanged at ≈ $0.38 (the new noul is under a cent); **`all` ≈ $0.59** (about RM 2.5); ≈ $0.81 at
  peak; ≈ $0.42 once `naive` replies are cached (doc 07 G11 later makes these $0.65 / $0.92 / $0.46, and doc 08 V11 $0.80 / $1.18 / $0.55, and doc 09 M12 $0.98 / $1.48 / $0.68, and doc 10 K14 $1.01 / $1.53 / $0.71, and doc 11 S10 $1.08 / $1.65 / $0.78).

### E9. Speed and cost, in one place

| Item | When | Cost | Time |
|---|---|---|---|
| Speaker emotion (E1) | inside Jev call 1, every AUTO or MANUAL turn | ~300 tokens per candidate: ≈ $0.00001 (1:1) to ≈ $0.00007 (5 candidates), more if Jev bills the state per question (doc 01 check 4). Doc 05 X9's $0.00003–0.00008 covers the state only | none extra: same request; the face shows with the first word |
| Mood line (E4) | every AUTO reply that isn't neutral | ≈ $0.000005 | none |
| Reactions (E5) | after each character message in group, debate, watch | ≈ $0.00007 with 4 listeners | after `turn.end`; never delays the next speaker |
| Face-and-words check (E7) | live from milestone M9: after `turn.end`, non-neutral AUTO faces ([doc 13](13-wrap-up.md) W2) | ≈ $0.00002 per checked reply | none: after `turn.end` |

## 5. Checks before this is locked

1. **Offline, $0:** E8's offline tests on the seed characters in all four modes, and the seed equivalence re-run
   (E6).
2. **In M9** ([doc 13](13-wrap-up.md) W6): the layer 1 emotion and reaction sets in its `decisions` slice, and E8's mood-line
   on/off run (≈ $0.06).

## 6. Changes this design needs (each approved at its OpenSpec change)

| Change | Where | Kind |
|---|---|---|
| The emotion question per candidate and per turn kind, its bank entries, the `neutral` + `none` merge, derived seeds; MANUAL still asks (E1) | the turn plan graph (doc 01 A4), the question bank (doc 02 B9) | backend |
| The agent engine yields `Emotion` on the first chunk; `turn.start` + `emotion` in one emit; never `turn.start.emotion`; sources; the MANUAL base face; `TurnTrace.emotion` candidates (E2) | the agent reply engine, `sessions/turn.py` (`_start`) | backend |
| Insight: no band and a "kept" chip when `chosen` is not the top candidate (E2) | `frontend/src/features/insight/InsightDrawer.tsx` | frontend |
| The fade rule and `emotion.fade` in config; listener fades (E3) | the turn plan's emotion fallback, the reactions task; `runtime.config.ts` → `seed/runtime.json`; `domain/runtime_config.py` | backend + config |
| The mood line and its phrase table, none for neutral and MANUAL (E4) | `ai/agent/persona.py` and its TS twin (doc 04), shared fixtures | backend + frontend |
| `JevReactions`; async `ReactionPredictor.predict` called inside the task; listeners read from `actor.state`; re-checks before each append; errors caught; scripted reactions record a simulated `reaction` call; the 1.5 s timeout (E5) | new `ai/agent/reactions.py`, `ai/ports.py`, `ai/profile.py`, `ai/scripted/ports.py`, `sessions/turn.py` (`_reactions`); `seed/pricing.json` gains `timeoutsMs.decision.reaction` (its old `emotion: 300` entry goes unused once the emotion is inside `turn_plan`, doc 01 A4) | backend + config |
| A named, cancellable reactions task; per-speaker drop at `turn.start`; full drop at a user message and in `clear()` (Stop, leave, cap pause, end) and on MANUAL (E5) | `sessions/actor.py` (`background`, `clear`), `sessions/turn.py`, `sessions/commands.py` (`_emotion_mode`) | backend |
| The mock charges the simulated `reaction` call and applies the same drop rules (E5) | `frontend/src/mock/script/turnScript.ts`, the mock engines | frontend |
| A reaction never changes the streaming speaker's face; fixtures incl. `ses_seedDinner` seq 25 (E6) | `services/runtime/reducer.py`, `frontend/src/engine/sessionReducer.ts`, the shared reducer fixtures | backend + frontend |
| ~~Post-turn graph without the live emotion branch until the System 1 section (E7)~~ Superseded: no post-turn graph; the face check is one Jev call in its own task ([doc 13](13-wrap-up.md) W2) | the after-turn work | backend |
| Eval: emotion set ~100 and reactions set 90 with the keep / `none` cap and baselines, the new noul with its false-alarm rule, the exact-match measure, the on/off run with its decision rule, single-order floor tuning, offline tests (E8) | `evals/`, the `horizon eval` harness, `backend/tests/` | backend |
| Doc 02: B2 sizes, B4 judge rows, B5 reaction target and single-order tuning, B7 cost, B8 sources | `docs/ai/02-evaluation-observability.md` | docs |
| Doc 01: A4's emotion fallback row (fade), A5 (first chunk, `emotion` event, face with the first word), A7 (live emotion check waits for the System 1 section); OQ-AI-07 resolved | `docs/ai/01-agent-architecture.md`, `docs/requirements/08` | docs |

**No contract change.** Every field already exists (§2). E6 changes derived reducer state, not the wire format; the
Insight rule is display only.

## 7. Left for later tasks

- Custom emotions (EMO-07): the full product (requirements EMO-07), not v1.
- ~~Watch's pacing, the talk-finished question and energy-aware turn-taking (task 7).~~ Resolved by doc 07 G6–G9.
- ~~Debate's member choice and the verdict (task 8)~~ resolved by doc 08 V2 and V7–V9; E5's debate `side` label is the only debate input here.
- ~~The quoted-content wording in the emotion and reaction states (task 11).~~ Resolved by doc 11 S6 (`quoted_*`
  fields).
- ~~The System 1 Insight section, with the live face-and-words check and the derived seeds (task 13).~~ Resolved by
  [doc 13](13-wrap-up.md) W1 (the section and `system1.seed`) and W2 (the live check).
- ~~Whether post-turn spend (reactions, the summary) shows in the session's cost HUD (task 13's pricing review).~~
  Resolved by [doc 13](13-wrap-up.md) W7: the counter stays reply spend; its tooltip points to Settings → Cost.

## Sources

- TypeSafe Jev notes on choice questions, option fields, first-option lean and small states: see doc 01 A3 and its
  sources.
- Requirements: CHAT-03 (timing, crossfade), CHAT-04 (AUTO / MANUAL), MULTI-04 (listener reactions), EMO-06 (missing
  portrait), ENG-02, NFR-29, D-07, D-46, D-79, D-81, R-15.

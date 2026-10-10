# 07: Group and watch turn-taking, and energy

> **Status: agreed with the user, 2026-10-10** (AI stage, task 7 of 13). **Revised after an independent review**
> (it checked the code; 14 findings, all addressed; one of them changed a user decision, see §1).
> - It resolves OQ-AI-06 (group and watch turn-taking) and OQ-AI-17 (energy-aware orchestration), except a debate side
>   whose members are all exhausted, which is task 8's. It also settles the items earlier docs left here: **when a
>   character answers another character** (doc 04 §7), **watch's "Summarise" recap** (doc 05 X3) and **what "the talk
>   is finished" does** (doc 01 §8).
> - Decisions are numbered **G1–G13**, each with the alternatives we rejected.
> - It builds on [01-agent-architecture](01-agent-architecture.md) (A1–A14),
>   [02-evaluation-observability](02-evaluation-observability.md) (B1–B12),
>   [03-llm-parameters](03-llm-parameters.md) (C1–C9),
>   [04-persona-prompt-drafter](04-persona-prompt-drafter.md) (P1–P12),
>   [05-context-engineering](05-context-engineering.md) (X1–X10) and
>   [06-emotion-reactions](06-emotion-reactions.md) (E1–E9).
> - **No contract change and no requirement change.** Every new trace value fits fields that exist
>   (`routing.question`, `routing.reason`, `forcedBy: "round_order"`). The one place a contract change looked
>   necessary (ending a watch scene early) was replaced by steering (G7).

## 1. The question

In group chat and watch, several characters share one conversation. Doc 01 already decided that Jev call 1 asks
**who speaks** (group auto, watch) and **is the talk finished?** (watch), that @mentions answer first, and what
happens when Jev fails or is unsure (A4). Task 7 decides **how many characters answer and when the second is
chosen**, **how watch stays fair and keeps moving**, **what energy changes about who is picked**, and **how it is
all measured**.

**The user's decisions (2026-10-10):**
- **The second replier in group Auto is chosen after the first reply**, by Jev, within 400 ms of the first reply's
  end; when Jev is late, nobody adds a second reply (G2). **If Jev proves slow, Jev stays:** testing it is one of the
  project's purposes, so the deadline follows the measured latency and the result is reported (G2).
- **When a watch scene runs dry, the next speaker is steered somewhere new.** No early end, so no contract change; the
  turn cap still ends the episode (G7).
- **Watch speakers are Jev's pick, plus a rule that nobody is left out:** never the same speaker twice in a row, and
  anyone silent for 2 full rounds gets the next turn (G6).
- **Energy matters only at zero** (G9). The user first chose "tired characters skip optional extra turns"; the
  review then found that ENG-04 AC4 (a Must) says "Tired (< 20%) is cosmetic only … They still talk", and the user
  chose to follow the requirement. Tired characters are picked like anyone else.

## 2. What Horizon already has

From the code:

- **Group** ([group.py](../../backend/horizon/sessions/modes/group.py)): `send` posts the user's message, then one
  job asks the `Router` and runs the speakers in order with a **400 ms gap** (`turnGapMs`) after each turn
  ([common.py](../../backend/horizon/sessions/modes/common.py) `speak_then`). Archived, muted and (unless mentioned)
  exhausted characters are skipped and listed in `skipped` with reasons `archived`, `muted`, `exhausted`. A turn
  emits `turn.next`, waits `thinkingMs` (60 ms), emits `turn.thinking`, then builds the context and streams
  ([turn.py](../../backend/horizon/sessions/turn.py)). In the seed dinner chat `turn.next` lands about 440 ms after
  the previous `turn.end`, so NFR-02's 500 ms already has only about 60 ms to spare.
- **The `naive` router already uses Jev** ([naive/router.py](../../backend/horizon/ai/naive/router.py)): one `choice`
  over the eligible cast plus `none`, then the top pick plus every option above p 0.25, at most 2 in all (mentions
  count toward the 2), **all decided before anyone speaks**. Its state passes `lastSpoke` as a raw sequence number.
  Its fallback is the least recently spoken character. When the question would have one option or fewer, it returns
  the mentions only.
- **The `scripted` router** (the demo and the mock's twin) gives random scores plus a name bonus and always takes the
  top 2 in Auto.
- **Everyone answer** runs the whole unmuted cast in cast order, writing "{name} is asleep, skipping." for sleepers,
  with up to 2 replies generated ahead (`prefetchMax`).
- **Next speaker** without a chosen character picks **at random** from the awake, unmuted cast minus the last speaker.
- **Watch** ([watch.py](../../backend/horizon/sessions/modes/watch.py)) is **round-robin** from the opening speaker
  (`WatchDirector.order`), skipping asleep characters; when everyone is asleep it pauses with a top-up prompt. The
  real gap between watch turns is **the 400 ms turn gap plus `paceMs`** (Slow 3 s, Normal 1.5 s, Fast 0.5 s), because
  `speak_then` sleeps first and only then sets the pace timer. **Step in** answers with **2 random** awake
  characters. **Summarise** returns a canned sentence in every profile (`naive` resolves to `scripted`), and on a
  provider error it emits nothing.
- **Energy** ([energy.py](../../backend/horizon/domain/energy.py)): `exhausted` below one estimated reply (4 points
  off-peak, 8 at peak), `tired` below 20 % of max. Only a character's own reply drains it (ENG-02). Tired is cosmetic
  (ENG-04 AC4).
- **Sending:** the composer is blocked while a reply is thinking or streaming
  ([Composer.tsx](../../frontend/src/features/session/Composer.tsx)), so in the UI a user can send in the gap
  between two replies (including the 60 ms between `turn.next` and `turn.thinking`) or after the last one. The
  server does not block a send while a reply streams; it only refuses while another session is live.
- **The contract** fixes `skipped[].reason` to `exhausted | muted | archived` and `forcedBy` to
  `user_ask | mention | nudge | round_order`; `routing.question` and `routing.reason` are free strings, and Insight
  shows `reason` as a line of text ([InsightDrawer.tsx](../../frontend/src/features/insight/InsightDrawer.tsx)).
  Session-level `error` events are stored by the reducers but no screen renders them.

**Findings:**
1. **Auto can answer with silence.** With no @mention, if Jev picks `none` and nobody else is above 0.25, nobody
   replies to the user's message. A user who writes to the group and hears nothing will think it broke.
2. **The second replier is chosen blind.** It is decided before the first reply exists, so it can't answer the first
   character and often repeats the same point.
3. **A message sent in the gap is answered late.** If the user sends during the gap between two replies, the queued
   second character still answers the *previous* message, after the new one is already on screen.
4. **"Is the talk finished?" has no outcome yet** (doc 01 §8): ending a scene early needs a new paused reason, which
   is a contract change.
5. **Doc 05 X9 put energy ("ok" / "tired") into Jev's state.** Jev would then mix the budget into a story decision
   with no rule for how much. Energy is a budget mechanic; code applies it, not Jev.

## 3. The design in one picture

```
group, user sends "…"                                   watch, every turn
──────────────────────                                  ─────────────────
@mentions answer first                                  turn gap 400 ms + pace (0.5 / 1.5 / 3 s)
no mention → Jev call 1: who answers first?               the next plan runs inside this wait (G8)
  (no "nobody" option: someone always answers, G1)      a Speak next nudge, else: anyone silent 2 rounds? (G6)
first reply streams … turn.end                          else Jev call 1: who speaks next? (last speaker excluded)
  ├─ follow plan (Jev, deadline turn.end + 400 ms):       · is the talk finished? → yes: steer sentence (G7)
  │    who, if anyone, speaks up now?                   reply streams with the cue
  │    yes → second reply, cue: "Hana just answered…"   Summarise → one DeepSeek recap (G10)
  │    no / late / unsure → done (G2)
  └─ a new user message cancels replies not yet announced (G5)
```

## 4. Decisions

### G1. Group Auto's first slot: someone always answers

**Decision:**
- **With no @mention, the first-slot question has no `none` option.** Someone in the cast always answers the user's
  message. `none` stays only where a reply is truly optional: the second slot (G2).
- **When only one character is eligible, they answer without a Jev call** (the question would have one option).
- **With an @mention, the mentioned characters answer first and the first-slot question is not asked.** With one
  mention, the follow plan (G2) may add a second voice. With two or more mentions, they all answer and nothing is
  added (mentions count toward Auto's 2, as today, but every mentioned character always answers).
- **When every mentioned character is asleep,** each gets ENG-04's asleep note with Top up, and nobody else answers:
  the user addressed someone specific, and another character answering instead would feel wrong. No follow plan
  runs.
- **The question** (one `choice`, doc 01 A3's rules):
  - instructions: "{user} just wrote to the group. Who would naturally answer first?";
  - each option: `what` = "{name} ({role}): {about}" (doc 05 X9's `about`), `not_for` = "not {name} when the message
    is plainly for someone else, by name or by topic";
  - options shuffled with the per-turn seed (A3 rule 4).
- **Fallbacks stay doc 01 A4's:** Jev failed or late → the least recently spoken; Jev unsure → the least recently
  spoken of Jev's top 2. Both are "someone answers", which is now true on every path.
- **Which profiles:** see G13. `naive` gets the same fix (no `none` with no mention, and a single eligible character
  answers), because silence is a bug, not part of the yardstick's design.

**Rejected:**
- **keeping `none` in the first slot:** it allows silence after a user's message (finding 1);
- **asking a separate "should anyone answer?" noul:** a user message in a group always deserves an answer, so the
  question would only add a way to fail;
- **someone else answering when the only mentioned character is asleep:** it ignores whom the user addressed.

### G2. The second slot is chosen after the first reply (the follow plan)

**Decision:**
- **When the first reply's `turn.end` has been appended, the turn runner starts a short Jev request (the follow
  plan)** that decides whether anyone speaks up now. It sees the first reply, so the second character can answer it
  or add something new.
- **What it asks**, in one request, like call 1 (doc 01 A4):
  - **who speaks up now** (`choice`): "{first} has just answered {user}. Would one of these characters naturally
    speak up now?" Options: the eligible cast **minus everyone who already answered this message**, plus **`none`**
    ("nobody: {first}'s answer covered it"; `not_for`: "not when someone was addressed by name or asked a
    question");
  - **per candidate:** the gates and the emotion (doc 06 E1's question, worded for this turn kind). This replaces
    doc 01 A4's "re-plan for the second replier": it is the same request, now also choosing who.
- **Amended by doc 11 S5:** the follow plan now **starts when the first reply's stream ends**, in parallel with the
  output check, instead of after `turn.end`; a block cancels it. A steered or care turn (doc 11 S3, S4) has no follow
  plan.
- **A deadline, not a timeout:** purpose `follow_plan`, deadline **`turn.end` + 400 ms**
  (`timeoutsMs.decision.follow_plan` = 400, measured from `turn.end`). The deadline **replaces** the 400 ms turn gap
  for this step instead of adding to it, so `turn.next` comes at most about 400 ms after `turn.end`, inside NFR-02's
  500 ms even with state assembly included.
- **Fallbacks favour silence, because the slot is optional:**

  | Case | Result |
  |---|---|
  | Jev picks a character above the floor `floor.second` | that character replies second |
  | Jev picks `none` | no second reply |
  | Jev unsure (below `floor.second`) | no second reply |
  | Jev failed or past the deadline | no second reply; counted as a timeout, apart from `none` (B8, G11) |

- **`floor.second`** is tuned on dev as **the floor with the best balanced accuracy (G11) among those whose needless
  second replies stay at or under 15 % of the `none` items**: a needless reply costs energy and adds noise, a
  missing one is mild.
- **When it doesn't run:** two or more mentions; every mentioned character asleep (G1); policy `everyone` or
  `mentioned`; a cancelled send (G5); nobody left to ask.
- **The second reply's trace:** `routing.question` = the follow-plan question, `routing.candidates` from the follow
  plan, `routing.selected`.
- **If check 3 shows Jev is slow from Malaysia, Jev stays** (the user, 2026-10-10: testing Jev is one of the
  project's purposes, so "if Jev is slow, we accept the fate"). The deadline is then set from the measured Jev
  latency (its p90), so the second slot still works, and this optional turn gets a recorded NFR-02 exception for
  `turn.next`. The measured latency is reported as a finding about Jev, not designed around.

**Rejected:**
- **choosing the second replier up front (today's way):** never late, but blind to the first reply (finding 2); it
  is not a fallback for a slow Jev either (the user's rule above);
- **a 400 ms timeout started after the gap or after the context is built:** it adds to the ~440 ms `turn.next` already
  takes and breaks NFR-02;
- **"unsure → least recently spoken" for this slot:** that fallback exists so that someone answers; here the safe
  default is silence;
- **one Jev request per candidate ("would X speak up?"):** more round trips and no comparison between candidates.

### G3. The turn cue: one sentence about whom the character is answering

Doc 04 left "when a character should address another character" to this task.

**Decision:**
- **The turn cue** (the last line of the dynamic tail, doc 04 P2) **gains one optional sentence** per turn kind,
  always in English, about 15–25 tokens:

  | Turn | Sentence |
  |---|---|
  | group second reply (G2), Step in's second reply | "{first} has just answered. Don't repeat them; add your own angle, or answer {first} directly." |
  | Next speaker (G4), no user message | "Nobody asked you directly; say something that moves the talk on. You may answer anyone." |
  | watch, the talk is finished (G7) | "This thread has run its course. Take the scene somewhere new that still fits the premise." |
  | any other turn | none |

- **Where it sits:** inside the cue, after the director's note when there is one, so the mood line (doc 06 E4) and
  the cached prefix are untouched (NFR-35).
- **It shows in the context X-ray** as part of the cue, so Insight already shows why a character answered someone.
- **"Them", not "him" or "her":** the sentence never guesses a character's pronouns.

**Rejected:**
- **no sentence:** the second replier's most common failure is restating the first reply in other words;
- **a rule in the cached mode block ("answer other characters when it makes sense"):** it applies to every turn,
  including first replies where there is nobody to answer, and it can't name who just spoke.

### G4. Next speaker, Everyone answer, and Step in

**Decision:**
- **Next speaker** (without a chosen character) asks Jev call 1 **who speaks next**, with **no `none`** and **without
  the last speaker** (today's exclusion). One eligible character answers without a Jev call. Fallbacks as G1. With a
  chosen character it stays forced (`nudge`). Its cue carries G3's "Nobody asked you" sentence.
- **Everyone answer** still goes through the whole unmuted cast, and sleepers still get "{name} is asleep,
  skipping." (ENG-04 AC3). The awake characters speak **in the order of Jev's probabilities** (most likely to answer
  first) instead of cast order.
  - **One call 1 at the start of the run** asks who speaks (for the order) and every awake character's gates and
    emotion. Every reply of the run, prefetched or not, uses that call's answers (doc 06 E1 is amended to say so).
  - If Jev fails, cast order, and each reply's gates and emotion take doc 01 A4's fallbacks.
  - Prefetch (up to 2 ahead) is unchanged; it starts once the order is known.
- **Step in** (watch) follows the group Auto rule, as MULTI-11 already says: G1 for the first reply (someone always
  answers), G2 for an optional second. It replaces today's 2 random characters.

**Rejected:**
- **random Next speaker (today):** it ignores who was addressed or has something to say;
- **one call 1 per Everyone speaker:** more requests for answers the run's single call already gives.

### G5. A new user message cancels the previous message's replies that haven't been announced

**Decision:**
- **"Not announced" means no `turn.next` yet.** When a user message arrives, every reply for the previous message
  that has not emitted `turn.next` is cancelled: a follow plan in flight and the second reply it would start, the
  rest of an Everyone run, Step in's second reply.
- **A reply that has emitted `turn.next` runs to the end**, even if it hasn't streamed yet. That window is the 60 ms
  of `thinkingMs` plus network delay; cutting a turn there would leave the client's `thinkingId` set with no event
  to clear it (an unstarted turn closes silently), which would need a contract or reducer change. The rare late
  answer is accepted.
- **A streaming reply is never cut by a send.** The UI can't send then anyway, and a send from another client is
  queued behind it. Only **Stop** cuts a reply (keeping its partial text, as today).
- **Cancelled prefetched replies are discarded with their spend and their energy drain standing** (D-77, as Stop
  does today). A finished prefetch is not shown either: it answers the old message, which is finding 3 again.
- Pending listener reactions are dropped too (doc 06 E5 already does this at a user message).
- Then routing runs on the new message as usual.
- **Shared runtime, so every profile** (G13), and the mock's group engine, with a parity fixture.

**Rejected:**
- **keeping the queue (today):** the second character answers an older message after the user moved on (finding 3);
- **cutting a turn that was already announced:** needs new client-side cleanup for a window of about 60 ms;
- **cutting the streaming reply as well:** it throws away a reply the user is reading; Stop already does that.

### G6. Who speaks next in watch

**Decision**, in this order for each watch turn:
1. **A Speak next nudge wins** (as today; `forcedBy: "nudge"`).
2. **Nobody is left out (code):** a character who hasn't spoken in the last **2 full rounds** gets the turn.
   - A round is the number of awake, unmuted characters; "spoken" means **any message by that character since the
     scene started**, counted **from the message log** (never from memory, because the actor is rebuilt after an idle
     release). Step turns and Step in replies count as messages.
   - A character who just woke up or was unmuted can qualify at once; bringing them back in is the point.
   - If several qualify, the one silent longest. A director's note doesn't change the rule.
   - Its trace: `forcedBy: "round_order"` (Insight's "Round order" tape) and `routing.reason` "{name} hadn't spoken
     for {n} turns." The who-speaks question is not asked; the call still asks that character's gates and emotion.
3. **Otherwise Jev call 1 asks who speaks next** (doc 01 A4), with **no `none`** and **without the last speaker**:
   - instructions: "In this scene, who would naturally speak next?";
   - options as G1, with the premise and the last 12 lines in the state (doc 05 X9's `watch` field);
   - **one option left (two awake characters, or one):** that character speaks without a who-speaks question. With
     only one awake character, they continue alone, as today.
- **Opening speaker "Auto":** the first turn asks the same question with the premise and no lines yet. A chosen
  opening speaker is forced, as today.
- **Fallbacks as G1** (least recently spoken; unsure → least recent of Jev's top 2), the last speaker still excluded.
- **Which profiles:** `agent` only (G13). `scripted` and `naive` keep round-robin (`WatchDirector.order`).

**Rejected:**
- **Jev alone:** a quiet character can vanish from a 20-turn scene;
- **round-robin with Jev only for gates and emotion:** scenes feel mechanical, and nobody reacts to being addressed;
- **a hard rotation inside each round:** too rigid; the guard only steps in when Jev's picks have left someone out.

### G7. When a watch scene runs dry: steer, don't end

**Decision:**
- **The "is the talk finished?" noul stays in watch's call 1** (doc 01 A4). Wording: "Has the current thread of this
  scene run its course, with the characters repeating themselves, going in circles or saying goodbye?" (a high value
  means yes, A3 rule 2).
- **Yes (p ≥ `t_end`) adds G3's steer sentence to this turn's cue.** The scene moves on instead of looping on
  goodbyes or polite agreement, the most common watch failure.
- **Limits:**
  - at most **one steer every 3 turns**, so the scene doesn't hop between topics;
  - **not while a director's note is active** (its 2 turns): the user's note is already the new direction.
- **The scene still stops only at the turn limit or the daily cap, and pauses when everyone is asleep** (MULTI-10
  AC2–AC3), so there is no new outcome and **no contract change**. Doc 01 §8's contract row is withdrawn.
- **Fallback:** Jev failed or late → no steer (doc 01 A4: "talk finished: no").
- **`t_end` keeps doc 02 B5's rule** (the lowest threshold with precision ≥ 90 %): a false "yes" means an abrupt
  change of topic, which viewers notice.
- **In Insight:** the steer sentence shows in the context X-ray's cue (G3). The noul's probability joins the System 1
  section ([doc 13](13-wrap-up.md) W1).

**Rejected:**
- **ending the episode early:** needs a new paused reason (a contract change) and cuts scenes the user set a length
  for;
- **dropping the question:** saves a few tokens per turn, but nothing would catch a looping scene before the turn cap.

### G8. Watch plans the next turn during the wait between turns

**Decision:**
- **At each watch `turn.end`, the next turn's Jev call 1 starts at once**, while the turn gap and the pace timer run
  (about 0.9 s at Fast, 1.9 s at Normal, 3.4 s at Slow). When the timer fires, the plan is usually ready, so Jev's
  time is hidden inside the pace the user chose.
- **No plan starts when this turn reached the turn limit,** or when the session is ending.
- **The plan is stored with what it was made from:** the actor's epoch, the seq of the last message, the active
  director's note, the nudge, and each cast member's awake, muted and current-face state. At turn time the runtime
  rebuilds that fingerprint; **if anything differs, the plan is thrown away and made again** (about $0.00005). This
  covers a director's note, Step in, a Speak next nudge, mute or unmute, a MANUAL face change, a top-up, a character
  waking up by regeneration, Extend and Play after a pause, without listing triggers one by one.
- **Lifecycle:** the plan task is held with the actor's timers, so **`clear()` cancels it** (Stop, leave, a cap pause,
  Summarise, the end). An idle release drops it with the rest of the mode state; the next turn plans afresh.
- **Only the plan runs ahead, never the reply:** a reply prefetched during the pace would be paid for and then wasted
  whenever the user reacts with a director's note, which is exactly when they are paying attention.
- **Which profiles:** wherever a `TurnPlanner` runs, so `agent` (G13).

**Rejected:**
- **planning after the pace (today's order):** the gap becomes turn gap + pace + Jev + first token;
- **a list of invalidating events:** easy to miss one (the review found four missing); the fingerprint can't miss a
  change to its own inputs;
- **prefetching the whole next reply:** paid output lost on every director's note or step-in.

### G9. Energy and who gets picked (OQ-AI-17)

**Decision:**
- **Energy matters only at zero.** Exhausted characters are skipped everywhere, as today (ENG-04), listed in
  `skipped` as `exhausted`; an @mentioned exhausted character gets the asleep note with Top up (unchanged).
- **Tired is cosmetic, as ENG-04 AC4 says:** a tired character (under 20 % of max) is picked exactly like anyone
  else, in every slot and every mode.
- **Energy leaves Jev's state.** Doc 05 X9's `energy` field is removed: Jev judges the conversation, code applies the
  budget (finding 5). Exhausted characters were never candidates; tired ones are now treated the same as everyone.
- **Orchestration never drains energy** (ENG-02): the follow plan, watch's plan-ahead and the episode recap go to the
  daily cap only.
- A debate side whose members are all exhausted stays task 8's question (resolved by doc 08 V5: the debate pauses).

**Rejected:**
- **tired characters skip optional extra turns** (the first answer): it breaks ENG-04 AC4, and it saved only about 4
  points per skipped reply;
- **watch favouring energy:** a scene's cast would shrink to whoever has the most energy left, which the user didn't
  choose.

### G10. Watch's "Summarise": a real recap

**Decision:**
- **`Summariser.episode` becomes one DeepSeek call** in `naive` and `agent` (`scripted` keeps its canned text and its
  simulated call).
- **Input:** the premise, the cast's names and roles, the rolling summary when there is one (doc 05 X3), and the
  history window (≤ 9,000, doc 05 X2), quoted as content.
- **Instruction:** "Write a short recap of this scene for someone who watched it: one paragraph, at most 120 words,
  past tense, third person, in the language the characters used. End with one sentence on where things stand. Only
  say what happened in the lines; invent nothing."
- **Settings:** a new `runtime.llm.calls` row `episode` (thinking off, temperature **0.7** like the rolling summary,
  doc 03 C1: it must be faithful), `max_tokens` 400, an overall limit of **30 s** (`timeoutsMs.episode`); ledger
  purpose **`episode_summary`** (category `summary`), charged to the daily cap, never to energy.
- **Shown** as today: a `note` message of kind `summary`.
- **Failure** (provider error, timeout, refusal, empty output): **no fake recap.** A plain system note goes in the log:
  "The recap couldn't be written this time. Try Summarise again." No screen renders session-level `error` events, so
  a note is the only way the user learns of it, and it needs no contract or UI change. A cap refusal pauses the
  session, as today.
- **Cost:** at most ≈ 10,000 tokens in (mostly uncached, a different prefix) + ≈ 250 out ≈ **$0.0017 off-peak**,
  $0.0034 at peak; a usual 20-turn scene is about a third of that. Only when the user presses the button.

**Rejected:**
- **bullet points:** a scene reads better as a short story recap, and bullets drop the "who did what to whom";
- **reusing the rolling summary as the recap:** it is written for the model (facts, promises), not for a viewer;
- **the canned text when the call fails:** it would look like a real recap of a scene it never read;
- **the `error` event:** stored but never shown, so the button would seem to do nothing.

### G11. Evaluation additions

**Decision** (doc 02 B2, B3 and B5 are amended):
- **The who-speaks set grows from ~100 to ~210 items** in three parts, each split dev / test as B2 says, each test
  split at least 20 items, and each grown by B2's 40 items when its interval straddles the target:

  | Part | Items (test) | Acceptable answers | Target (B5), on the policy after the floor |
  |---|---|---|---|
  | group first slot (no `none`) | 60 (20) | the set of natural first answerers | ≥ 80 % inside the set, **and ≥ 15 points above "least recently spoken"** |
  | group second slot (the follow plan) | 90 (30), **about 65 % with `none` right**, matching the expected live rate | the set, or `none` | **balanced accuracy** (the mean of the accuracy on "someone" items and on `none` items) ≥ 80 %, **and ≥ 15 points above "least recently spoken"**; "always `none`" scores 50 % on this measure, so it can't pass; needless and missing replies reported apart |
  | watch next speaker | 60 (20), every item with **at least 3 awake characters** | the set (last speaker never in it) | ≥ 80 % inside the set, **and ≥ 15 points above round-robin** |

  - **The margin over a baseline is judged with an exact paired test** on the test split (Jev and the baseline answer
    the same items), not by comparing intervals, which is too blunt at these sizes (B1).
- **"Talk finished"** keeps its ~120-item noul set and `t_end` rule (B5); its items now include goodbye loops and
  polite-agreement loops, the failures G7 targets.
- **Group and watch signals** (no target, a signal for review; `agent` only, because they depend on who actually
  spoke, which frozen transcripts fix in advance):
  - **More free runs:** 3 watch runs of 30 turns and 3 group runs of 12 user messages, on top of B3's one per mode;
  - the **second-reply rate** in group Auto (expected 20–40 %; outside 10–60 % I look at it with the user), with
    follow-plan timeouts counted apart from `none`;
  - the **busiest speaker's share** of character lines per session;
  - how often the **nobody-left-out rule** fires in watch (above 20 % of turns means Jev's picks are unfair and the
    question is reworded);
  - how often the **steer** fires, and whether the next line actually moves on (the judge's noul "does this line
    start something new?").
- **Episode recap:** 10 recaps, 8 from the frozen watch transcripts (at two points each) and **2 from one long
  committed watch history** (about 100 turns, past one drop, so the rolling summary and a ~10,000-token input are
  tested). Checked by doc 05 X10's summary judge nouls (faithful, nothing invented, right language) plus "≤ 120
  words" in code. Target: at most 1 failure, each read. Added to the `summary` suite. The long history is generated
  once by `naive`, reviewed and committed (≈ $0.02, once).
- **Cost:** decisions ≈ +220 Jev requests (≈ 1,920 in all, ≈ $0.08); summary suite +10 recaps ≈ +$0.02 (≈ $0.08);
  conversations +6 agent free runs ≈ +$0.03 (≈ $0.41). **`all` ≈ $0.65** (≈ $0.92 at peak, ≈ $0.46 with the
  `naive` replies cached; the recaps are cached by request hash like every DeepSeek reply). Doc 08 V11 later makes
  these $0.80 / $1.18 / $0.55, and doc 09 M12 $0.98 / $1.48 / $0.68, and doc 10 K14 $1.01 / $1.53 / $0.71, and doc 11 S10 $1.08 / $1.65 / $0.78.

**Rejected:**
- **one accuracy number for both group slots:** the second slot's right answer is often `none`, so a mixed number
  hides "never adds anyone";
- **plain accuracy for the second slot:** with about 65 % `none` items, "always `none`" would score 65 %;
- **a target on the second-reply rate:** the rate follows the conversations; the labelled items already say when a
  second voice is right;
- **reading the busiest-speaker and guard signals from frozen transcripts:** their speakers are fixed by `naive`'s
  round-robin, so the guard could never fire.

### G12. Speed and cost, in one place

| Step | When | Latency | Cost |
|---|---|---|---|
| Group first slot | inside call 1 (doc 01 A4) | none extra | none extra |
| Follow plan (G2) | from the stream's end (doc 11 S5), deadline `turn.end` + 400 ms, replacing the turn gap | none extra when Jev is in time | ≤ 2,000 tokens × $0.042/M ≈ **$0.00008** per send that has a first reply |
| Turn cue sentence (G3) | in the cue | none | ≈ 25 uncached tokens ≈ $0.000004 |
| Everyone order (G4) | the run's one call 1 | none extra | none extra |
| Watch plan-ahead (G8) | during the turn gap and the pace | hidden by the wait | the plan it replaces; a redo after a change ≈ $0.00005 |
| Steer (G7) | inside call 1 | none | the noul is already asked |
| Episode recap (G10) | on Summarise | ≈ 2–4 s (one non-streamed call) | ≤ ≈ $0.0017 off-peak |

A group send with two replies costs about **$0.0001 more in Jev** than today's single route call; that rounds to
nothing next to the replies themselves.

### G13. Which profile does what

`scripted` runs the demo and must keep its event stream identical to the frontend mock's; `naive` is the yardstick
and keeps its design except for bugs; `agent` gets the design.

| Decision | `scripted` (demo, mock twin) | `naive` (yardstick) | `agent` |
|---|---|---|---|
| G1 first slot without `none`, one eligible answers | unchanged (random scores, top 2) | **yes** (bug fix) | yes |
| G1 every mentioned character asleep → no one else | yes (shared runtime) | yes | yes |
| G2 follow plan | no (top 2 up front) | no (its up-front pick is what `agent` is compared with) | yes |
| G3 turn-cue sentence | no | no | yes (the `agent` compiler and its TS twin) |
| G4 Next speaker and Step in via Jev, Everyone order | no (random, as the mock) | no | yes |
| G5 cancel replies not yet announced | **yes**, with the same change in the mock's group engine | yes | yes |
| G6 watch speaker and guard | no (round-robin) | no (round-robin) | yes |
| G7 steer | no | no | yes |
| G8 plan-ahead | no planner | no planner | yes |
| G9 energy at zero only, no energy in Jev's state | unchanged | unchanged (its router's state never had energy) | yes |
| G10 real recap | no (canned + simulated call) | **yes** | yes |

**Rejected:** changing the `scripted` picks to look like `agent`: every change would need the same change in the
mock and new parity fixtures, for a demo that already shows routing in Insight.

## 5. Checks before this is locked

Collected for the paid-check step after all 13 tasks (the user's rule), not run now:

| # | Check | Pass | If it fails |
|---|---|---|---|
| Doc 01 check 3 (extended) | Add **50 follow-plan requests** from hand-built states ([doc 13](13-wrap-up.md) W6 A2), Jev only (≈ $0.004), to the latency run; record the share that misses `turn.end` + 400 ms, with the state assembly included | ≤ 10 % miss the deadline | G2's rule: keep Jev, set the deadline from the measured p90, record the NFR-02 exception and the finding |
| Doc 01 check 3 (extended) | Watch at Fast pace (about 0.9 s between turns): time from `turn.end` to the next first word with the plan-ahead | the next first word within NFR-02's 3 s p50 | Fast keeps the plan-ahead, and the doc records the real gap |

## 6. Changes this design needs (each approved at its OpenSpec change)

None changes the HTTP contract or a requirement.

| Change | Kind | Why | Decision |
|---|---|---|---|
| The first-slot question without `none` when nobody is mentioned, and one eligible character answering without Jev, in `naive` and `agent`; all-asleep mentions add nobody | backend | finding 1 | G1 |
| The **follow plan**: `Decider` purpose `follow_plan`, `timeoutsMs.decision.follow_plan` = 400 as a deadline from `turn.end`, started by the turn runner and replacing `turnGapMs` for that step, ledger purpose; replaces doc 01 A4's second-replier re-plan; `floor.second` in the question bank | backend + config | finding 2 | G2 |
| The turn cue's optional sentence (second reply, Next speaker, steer), in the `agent` compiler and its TS twin with shared fixtures ("View as prompt") | backend + frontend | doc 04 §7 | G3 |
| Next speaker and Step in call the planner; Everyone's single call 1 gives the order and every speaker's gates and emotion; asleep notes kept | backend | today's random picks | G4 |
| A user message cancels the previous send's replies that have no `turn.next` yet, in the runtime and the mock's group engine, with a parity fixture | backend + mock | finding 3 | G5 |
| Watch: nudge, then the nobody-left-out guard counted from the message log (`forcedBy: "round_order"`), then the planner without the last speaker; "Auto" opening via the planner (`agent` only) | backend | G6 | G6 |
| Watch steer: the `t_end` noul adds the cue sentence, once per 3 turns, not during a director's note | backend | finding 4 | G7 |
| Watch plan-ahead during the wait, stored with its input fingerprint and cancelled by `clear()`; none at the turn limit | backend | speed | G8 |
| Energy removed from Jev call 1's state (doc 05 X9) | backend | finding 5 | G9 |
| `Summariser.episode` as one DeepSeek call (`naive`, `agent`), `runtime.llm.calls.episode`, `timeoutsMs.episode` 30 s, ledger purpose `episode_summary`, a system note on failure | backend + config | doc 05 X3 | G10 |
| Eval: who-speaks set to ~210 items in three parts with balanced accuracy and paired baseline tests; 6 more `agent` free runs; one long committed watch history; 10 episode recaps in `summary` | evals | measure it | G11 |
| **Docs to amend:** doc 01 A3 rule 5 (where `none` exists), A4 (second-replier re-plan → G2's follow plan; Everyone's order) and §8 (the watch contract row withdrawn); doc 02 B2, B3, B5, B7, B8; doc 03 C1 (the `episode` row); doc 04 §7 (resolved); doc 05 X9 (no `energy`), X3 (the recap designed here) and its cost note; doc 06 E1 (the follow plan; Everyone's single call) and its cost note | docs | consistency | all |

## 7. Left for later tasks

- ~~A debate side whose members are all exhausted (task 8, OQ-AI-17).~~ Resolved by doc 08 V5.
- ~~The debate member choice and its turn cue (task 8, doc 01 A14).~~ Resolved by doc 08 V2 and V4.
- ~~How the "talk finished" probability and the follow plan's candidates show in Insight's System 1 section (task
  13).~~ Resolved by [doc 13](13-wrap-up.md) W1: `turn_plan` and `follow_plan` rows; a follow plan that picked nobody goes on the
  previous reply's trace.
- Whether a group may run longer exchanges between characters without the user (beyond 2 replies per message): not
  in v1; MULTI-03 caps Auto at 2, and Next speaker already lets the user ask for more.

## Sources

- Horizon requirements: MULTI-02, MULTI-03, MULTI-09 to MULTI-11, MULTI-17, ENG-02, ENG-04, NFR-02
  ([02-functional-requirements](../requirements/02-functional-requirements.md),
  [07-nfr-risk-cost](../requirements/07-nfr-risk-cost.md)); OQ-AI-06 and OQ-AI-17
  ([08-open-questions-handoff](../requirements/08-open-questions-handoff.md)).
- Code: [group.py](../../backend/horizon/sessions/modes/group.py), [watch.py](../../backend/horizon/sessions/modes/watch.py),
  [common.py](../../backend/horizon/sessions/modes/common.py), [actor.py](../../backend/horizon/sessions/actor.py),
  [turn.py](../../backend/horizon/sessions/turn.py), [prefetch.py](../../backend/horizon/sessions/prefetch.py),
  [naive/router.py](../../backend/horizon/ai/naive/router.py), [scripted/ports.py](../../backend/horizon/ai/scripted/ports.py),
  [energy.py](../../backend/horizon/domain/energy.py), [schema.json](../../backend/horizon/contract/schema.json),
  [sessionReducer.ts](../../frontend/src/engine/sessionReducer.ts), [runtime.json](../../seed/runtime.json),
  [pricing.json](../../seed/pricing.json).
- Course notes: 7.1 Agents §7.1.6 (blackboard and swarm patterns need hard termination bounds; watch keeps its caps).
- [TypeSafe: confidence-gated routing](https://docs.typesafe.ai/patterns/confidence-routing.md) (floors per question,
  set by the cost of acting on a wrong answer).

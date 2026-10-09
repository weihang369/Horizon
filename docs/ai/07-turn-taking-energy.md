# 07: Group and watch turn-taking, and energy

> **Status: agreed with the user, 2026-10-10** (AI stage, task 7 of 13).
> - It resolves OQ-AI-06 (group and watch turn-taking) and OQ-AI-17 (energy-aware orchestration), except a debate side
>   whose members are all exhausted, which is task 8's. It also settles the items earlier docs left here: **when a
>   character answers another character** (doc 04 §9), **watch's "Summarise" recap** (doc 05 X3) and **what "the talk
>   is finished" does** (doc 01 §8).
> - Decisions are numbered **G1–G12**, each with the alternatives we rejected.
> - It builds on [01-agent-architecture](01-agent-architecture.md) (A1–A14),
>   [02-evaluation-observability](02-evaluation-observability.md) (B1–B12),
>   [03-llm-parameters](03-llm-parameters.md) (C1–C9),
>   [04-persona-prompt-drafter](04-persona-prompt-drafter.md) (P1–P12),
>   [05-context-engineering](05-context-engineering.md) (X1–X10) and
>   [06-emotion-reactions](06-emotion-reactions.md) (E1–E9).
> - **No contract change.** Every new trace value fits fields that exist (`routing.question`, `routing.reason`,
>   `forcedBy: "round_order"`). The one place a contract change looked necessary (ending a watch scene early) was
>   replaced by steering (G7).

## 1. The question

In group chat and watch, several characters share one conversation. Doc 01 already decided that Jev call 1 asks
**who speaks** (group auto, watch) and **is the talk finished?** (watch), that @mentions answer first, and what
happens when Jev fails or is unsure (A4). Task 7 decides **how many characters answer and when the second is
chosen**, **how watch stays fair and keeps moving**, **what energy changes about who is picked**, and **how it is
all measured**.

**The user's decisions (2026-10-10), all four as recommended:**
- **The second replier in group Auto is chosen after the first reply**, by Jev, with 400 ms to answer; when Jev is
  late, nobody adds a second reply (G2).
- **When a watch scene runs dry, the next speaker is steered somewhere new.** No early end, so no contract change; the
  turn cap still ends the episode (G7).
- **Watch speakers are Jev's pick, plus a rule that nobody is left out:** never the same speaker twice in a row, and
  anyone silent for 2 full rounds gets the next turn (G6).
- **Tired characters (under 20 % of their max) don't take optional extra turns:** they are never added as group's
  second reply, and everything else is unchanged (G9).

## 2. What Horizon already has

From the code:

- **Group** ([group.py](../../backend/horizon/sessions/modes/group.py)): `send` posts the user's message, then one
  job asks the `Router` and runs the speakers in order with a **400 ms gap** (`turnGapMs`) after each turn
  ([common.py](../../backend/horizon/sessions/modes/common.py) `speak_then`). Archived, muted and (unless mentioned)
  exhausted characters are skipped and listed in `skipped` with reasons `archived`, `muted`, `exhausted`.
- **The `naive` router already uses Jev** ([naive/router.py](../../backend/horizon/ai/naive/router.py)): one `choice`
  over the eligible cast plus `none`, then the top pick plus every option above p 0.25, at most 2 in all, **all
  decided before anyone speaks**. Its state passes `lastSpoke` as a raw sequence number. Its fallback is the least
  recently spoken character.
- **The `scripted` router** (the demo and the mock's twin) gives random scores plus a name bonus and always takes the
  top 2 in Auto.
- **Everyone answer** runs the unmuted cast in cast order, with up to 2 replies generated ahead (`prefetchMax`).
- **Next speaker** without a chosen character picks **at random** from the awake, unmuted cast minus the last speaker.
- **Watch** ([watch.py](../../backend/horizon/sessions/modes/watch.py)) is **round-robin** from the opening speaker
  (`WatchDirector.order`), one turn every `paceMs` (Slow 3 s, Normal 1.5 s, Fast 0.5 s), skipping asleep characters;
  when everyone is asleep it pauses with a top-up prompt. **Step in** answers with **2 random** awake characters.
  **Summarise** returns a canned sentence in every profile (`naive` delegates to `scripted`, doc 05 X3).
- **Energy** ([energy.py](../../backend/horizon/domain/energy.py)): `exhausted` below one estimated reply (4 points
  off-peak, 8 at peak), `tired` below 20 % of max. Only a character's own reply drains it (ENG-02).
- **The composer is blocked while a reply is streaming or thinking**, so a user can only send between turns: in
  group, during the ~0.5 s gap between two replies, or after the last one.
- **The contract** fixes `skipped[].reason` to `exhausted | muted | archived` and `forcedBy` to
  `user_ask | mention | nudge | round_order`; `routing.question` and `routing.reason` are free strings, and Insight
  shows `reason` as a line of text ([InsightDrawer.tsx](../../frontend/src/features/insight/InsightDrawer.tsx)).

**Findings:**
1. **Auto can answer with silence.** With no @mention, if Jev picks `none` and nobody else is above 0.25, nobody
   replies to the user's message. Group Auto promises "the AI chooses up to 2", but a user who writes to the group
   and hears nothing will think it broke.
2. **The second replier is chosen blind.** It is decided before the first reply exists, so it can't answer the first
   character and often repeats the same point.
3. **A message sent in the gap is answered late.** If the user sends during the ~0.5 s between two replies, the
   queued second character still answers the *previous* message, after the new one is already on screen.
4. **"Is the talk finished?" has no outcome yet** (doc 01 §8): ending a scene early needs a new paused reason, which
   is a contract change.
5. **Doc 05 X9 put energy ("ok" / "tired") into Jev's state.** Jev would then mix the budget into a story decision
   with no rule for how much. Energy is a budget mechanic; code should apply it, not Jev.

## 3. The design in one picture

```
group, user sends "…"                                   watch, every turn
──────────────────────                                  ─────────────────
@mentions answer first                                  pace wait (0.5 / 1.5 / 3 s) ─┐ the next plan runs
no mention → Jev call 1: who answers first?             during it (G8)                ┘ inside this wait
  (no "nobody" option: someone always answers, G1)      Jev call 1: who speaks next? (last speaker excluded)
first reply streams … turn.end                            · nobody spoke for 2 rounds? → code picks them (G6)
  ├─ follow plan (Jev, ≤ 400 ms, alongside the gap):      · is the talk finished? → yes: steer note (G7)
  │    who, if anyone, speaks up now? (tired left out)  reply streams with the cue
  │    yes → second reply, cue: "Hana just answered…"   Summarise → one DeepSeek recap (G10)
  │    no / late / unsure → done (G2)
  └─ a new user message cancels the queued second (G5)
```

## 4. Decisions

### G1. Group Auto's first slot: someone always answers

**Decision:**
- **With no @mention, the first-slot question has no `none` option.** Someone in the cast always answers the user's
  message. `none` stays only where a reply is truly optional: the second slot (G2).
- **With an @mention, the mentioned characters answer first and the first-slot question is not asked.** With one
  mention, the follow plan (G2) may add a second voice. With two or more mentions, they all answer and nothing is
  added (mentions count toward Auto's 2, as today, but every mentioned character always answers).
- **The question** (one `choice`, doc 01 A3's rules):
  - instructions: "{user} just wrote to the group. Who would naturally answer first?";
  - each option: `what` = "{name} ({role}): {about}" (doc 05 X9's `about`), `not_for` = "not {name} when the message
    is plainly for someone else, by name or by topic";
  - options shuffled with the per-turn seed (A3 rule 4).
- **Fallbacks stay doc 01 A4's:** Jev failed or late → the least recently spoken; Jev unsure → the least recently
  spoken of Jev's top 2. Both are "someone answers", which is now true on every path.
- **`naive` gets the same one-line fix** (no `none` when nobody is mentioned). Silence is a bug, not part of the
  yardstick's design, so fixing it in both keeps the comparison about the design. `naive` otherwise keeps its
  up-front second pick (finding 2), which is exactly what the comparison should test against.

**Rejected:**
- **keeping `none` in the first slot:** it allows silence after a user's message (finding 1);
- **asking a separate "should anyone answer?" noul:** a user message in a group always deserves an answer, so the
  question would only add a way to fail.

### G2. The second slot is chosen after the first reply (the follow plan)

**Decision:**
- **At the first reply's `turn.end`, a short Jev request (the follow plan) decides whether anyone speaks up now.**
  It sees the first reply, so the second character can answer it or add something new.
- **What it asks**, in one request, like call 1 (doc 01 A4):
  - **who speaks up now** (`choice`): "{first} has just answered {user}. Would one of these characters naturally
    speak up now?" Options: the eligible cast **minus everyone who already answered this message, minus tired
    characters (G9)**, plus **`none`** ("nobody: {first}'s answer covered it"; `not_for`: "not when someone was
    addressed by name or asked a question");
  - **per candidate:** the gates and the emotion (doc 06 E1's question, worded for this turn kind). This replaces
    doc 01 A4's "re-plan for the second replier": it is the same request, now also choosing who.
- **Purpose `follow_plan`, timeout 400 ms** (`timeoutsMs.decision.follow_plan`). It runs **alongside the existing
  400 ms turn gap**, so when Jev answers in time it adds no delay, and `turn.next` still arrives within NFR-02's
  500 ms of the previous `turn.end`.
- **Fallbacks favour silence, because the slot is optional:**

  | Case | Result |
  |---|---|
  | Jev picks a character above the floor `floor.second` | that character replies second |
  | Jev picks `none` | no second reply |
  | Jev unsure (below `floor.second`) | no second reply |
  | Jev failed or later than 400 ms | no second reply; the trace of the first reply is unchanged, and the timeout is counted (B8) |

- **`floor.second`** is its own floor, tuned in B5's way: a needless second reply costs energy and adds noise, a
  missing one is mild; the eval reports both mistakes (G11).
- **When it doesn't run:** two or more mentions; policy `everyone` or `mentioned`; a cancelled send (G5); nobody
  left after the filters.
- **The second reply's trace:** `routing.question` = the follow-plan question, `routing.candidates` from the follow
  plan, `routing.selected`; if a tired character was left out, `routing.reason` says so (G9).
- **If check 3 shows the 400 ms is too tight** (more than 20 % of follow plans time out from Malaysia), I bring it
  back to the user with the two ways out: raise the timeout and accept a slower `turn.next` for this optional turn
  (an NFR-02 exception), or go back to choosing the second replier up front.

**Rejected:**
- **choosing the second replier up front (today's way):** never late, but blind to the first reply (finding 2);
- **a longer timeout:** breaks NFR-02's 500 ms for `turn.next`;
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
  | group second reply (G2), step-in second reply | "{first} has just answered. Don't repeat them; add your own angle, or answer {first} directly." |
  | Next speaker (G4), no user message | "Nobody asked you directly; say something that moves the talk on. You may answer anyone." |
  | watch, the talk is finished (G7) | "This thread has run its course. Take the scene somewhere new that still fits the premise." |
  | any other turn | none |

- **Where it sits:** inside the cue, after the director's note when there is one, so the mood line (doc 06 E4) and
  the cached prefix are untouched (NFR-35).
- **It shows in the context X-ray** as part of the cue, so Insight already shows why a character answered someone.
- **"Them" not "him/her":** the sentence never guesses a character's pronouns.

**Rejected:**
- **no sentence:** the second replier's most common failure is restating the first reply in other words;
- **a rule in the cached mode block ("answer other characters when it makes sense"):** it applies to every turn,
  including first replies where there is nobody to answer, and it can't name who just spoke.

### G4. Next speaker, Everyone answer, and Step in

**Decision:**
- **Next speaker** (without a chosen character) asks Jev call 1 **who speaks next**, with **no `none`** and **without
  the last speaker** (today's exclusion). Fallbacks as G1. With a chosen character it stays forced (`nudge`).
  Its cue carries G3's "Nobody asked you" sentence.
- **Everyone answer** still runs every awake, unmuted character, but **in the order of Jev's probabilities** from the
  who-speaks question (most likely to answer first) instead of cast order. The question is asked in the same call 1
  as the gates and emotions, so the order is free. If Jev fails, cast order. Prefetch (up to 2 ahead) is unchanged.
- **Step in** (watch) follows the group Auto rule, as MULTI-11 already says: G1 for the first reply (someone always
  answers), G2 for an optional second. It replaces today's 2 random characters.

**Rejected:**
- **random Next speaker (today):** it ignores who was addressed or has something to say;
- **asking Jev for an Everyone order with a separate request:** call 1 already returns the probabilities.

### G5. A new user message cancels the previous message's queued replies

**Decision:**
- **When the user sends in the gap between replies, every reply still queued for the previous message is
  cancelled:** group Auto's second reply (and its follow plan), the rest of an Everyone run, Step in's second reply.
  A reply that is already streaming is never cut here; the composer is blocked during streaming anyway, and only
  **Stop** cuts a reply (keeping its partial text, as today).
- Prefetched replies that are cancelled are discarded with their spend standing (D-77, as Stop does today).
- Pending listener reactions are dropped too (doc 06 E5 already does this at a user message).
- Then routing runs on the new message as usual.
- **Shared runtime, so every profile** (and the mock's group engine, to keep parity).

**Rejected:**
- **keeping the queue (today):** the second character answers an older message after the user moved on (finding 3);
- **cutting the streaming reply as well:** it throws away a reply the user is reading; Stop already does that when
  the user wants it.

### G6. Who speaks next in watch

**Decision:**
- **Jev call 1 asks who speaks next** (doc 01 A4), with **no `none`** and **without the last speaker**, unless they
  are the only awake character, in which case they continue.
  - instructions: "In this scene, who would naturally speak next?";
  - options as G1, plus the premise and the last 12 lines in the state (doc 05 X9's `watch` field).
- **Opening speaker "Auto":** the first turn asks the same question with the premise and no lines yet. A chosen
  opening speaker is forced, as today.
- **Nobody is left out (code, before Jev is asked):** a character who hasn't spoken in the last **2 full rounds**
  (2 × the number of awake, unmuted characters, counted in turns since the scene started or since they woke up or
  were unmuted) **gets the next turn**. If several qualify, the one silent longest. The who-speaks question is then
  not asked (the call still asks that character's gates and emotion).
  - Its trace: `forcedBy: "round_order"` (Insight's "Round order" tape) and `routing.reason` "{name} hadn't spoken
    for {n} turns."
- **Fallbacks as G1** (least recently spoken; unsure → least recent of Jev's top 2), the last speaker still excluded.
- **`scripted` and `naive` keep round-robin** (`WatchDirector.order`): `scripted` is the mock's twin, and `naive` is
  the yardstick. In `agent`, the planner's pick replaces `WatchDirector.order`.

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
- **The scene still ends only at the turn limit,** the daily cap, or when everyone is asleep (MULTI-10 AC3), so there
  is no new outcome and **no contract change**. Doc 01 §8's contract row is withdrawn.
- **Fallback:** Jev failed or late → no steer (doc 01 A4: "talk finished: no").
- **`t_end` keeps doc 02 B5's rule** (the lowest threshold with precision ≥ 90 %): a false "yes" means an abrupt
  change of topic, which viewers notice.
- **In Insight:** the steer sentence shows in the context X-ray's cue (G3). The noul's probability joins the System 1
  section when task 13 designs it.

**Rejected:**
- **ending the episode early:** needs a new paused reason (a contract change) and cuts scenes the user set a length
  for;
- **dropping the question:** saves a few tokens per turn, but nothing would catch a looping scene before the turn cap.

### G8. Watch plans the next turn during the pace wait

**Decision:**
- **At each watch `turn.end`, the next turn's Jev call 1 starts at once**, while the pace timer runs (0.5 / 1.5 / 3 s).
  When the timer fires, the plan is usually ready, so Jev's time is hidden inside the pace the user chose.
- **The plan is thrown away and made again** if anything it depends on changes first: a director's note, Step in, a
  Speak next nudge, a mute or unmute, or a character falling asleep or being topped up. A plan costs about
  $0.00005, so redoing it is cheap.
- **Pause** keeps a ready plan; Play uses it unless one of the changes above happened.
- **Only the plan runs ahead, never the reply:** a reply prefetched during the pace would be paid for and then
  wasted whenever the user reacts with a director's note, which is exactly when they are paying attention.
- Every profile with a planner runs it this way; the `scripted` planner answers at once and emits no events, so the
  mock's event stream is unchanged.

**Rejected:**
- **planning after the pace (today's order):** the gap becomes pace + Jev + first token;
- **prefetching the whole next reply:** paid output lost on every director's note or step-in.

### G9. Energy and who gets picked (OQ-AI-17)

**Decision:**
- **Exhausted characters are skipped everywhere, as today** (ENG-04), and listed in `skipped` as `exhausted`. An
  @mentioned exhausted character gets the asleep note with Top up (unchanged).
- **Tired characters (under 20 % of max) are never offered for an optional extra turn:** group Auto's second slot and
  Step in's second reply (G2). They still answer when Jev picks them first, when mentioned, under Everyone, on Next
  speaker, and in watch.
  - The trace: `skipped` can't say "tired" without a contract change, so the second reply's `routing.reason` reads
    "Left out of the second reply (tired): {names}." When no second reply happens, nothing is shown.
  - In the demo, tired Rin (180 / 1000) speaks up a little less often, which fits the "tired" label.
- **Energy leaves Jev's state.** Doc 05 X9's `energy` field is removed: Jev judges the conversation, code applies the
  budget (finding 5).
- **Watch picks by the story;** energy only matters when a character is exhausted (G6).
- **Orchestration never drains energy** (ENG-02): the follow plan, watch's plan-ahead and the episode recap go to the
  daily cap only.
- A debate side whose members are all exhausted stays task 8's question.

**Rejected:**
- **only zero matters:** a tired character keeps taking optional turns until they fall asleep mid-session;
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
  doc 03 C1: it must be faithful), `max_tokens` 400; ledger purpose **`episode_summary`** (category `summary`),
  charged to the daily cap, never to energy.
- **Shown** as today: a `note` message of kind `summary`.
- **Failure** (provider error, timeout, refusal, empty output): **no fake recap.** The existing `error` event
  (retryable) is emitted so the user can press Summarise again. A cap refusal pauses the session, as today.
- **Cost:** ≈ 10,000 tokens in (mostly uncached, a different prefix) + ≈ 250 out ≈ **$0.0017 off-peak**, $0.0034 at
  peak. Only when the user presses the button.

**Rejected:**
- **bullet points:** a scene reads better as a short story recap, and bullets drop the "who did what to whom";
- **reusing the rolling summary as the recap:** it is written for the model (facts, promises), not for a viewer;
- **the canned text when the call fails:** it would look like a real recap of a scene it never read.

### G11. Evaluation additions

**Decision** (doc 02 B2 and B5 are amended):
- **The who-speaks set grows from ~100 to ~130 items**, split dev / test as B2 says:

  | Part | Items | Acceptable answers | Target (B5) |
  |---|---|---|---|
  | group first slot (no `none`) | 40 | the set of natural first answerers | ≥ 80 % inside the set, **and ≥ 15 points above "least recently spoken"** |
  | group second slot (the follow plan) | 50, of which **40–60 % have `none` as the right answer** | the set, or `none` | ≥ 80 % right, **and ≥ 15 points above the better of "always `none`" and "least recently spoken"**; needless and missing second replies reported apart |
  | watch next speaker | 40 | the set (last speaker never in it) | ≥ 80 % inside the set, **and ≥ 15 points above round-robin** |

- **"Talk finished"** keeps its ~120-item noul set and `t_end` rule (B5); its items now include goodbye loops and
  polite-agreement loops, the failures G7 targets.
- **The layer 3 group and watch transcripts and the free runs report** (no target, a signal for review):
  - the **second-reply rate** in group Auto (expected 20–40 %; outside 10–60 % I look at it with the user);
  - the **busiest speaker's share** of character lines per session;
  - how often the **nobody-left-out rule** fires in watch (above 20 % of turns means Jev's picks are unfair and the
    question is reworded);
  - how often the **steer** fires, and whether the next line actually moves on (the judge's noul "does this line
    start something new?").
- **Episode recap:** 10 recaps from the 5 frozen watch transcripts (at two points each), checked by doc 05 X10's
  summary judge nouls (faithful, nothing invented, right language) plus "≤ 120 words" in code. Target: at most 1
  failure, each read. Added to the `summary` suite.
- **Cost:** decisions ≈ +60 Jev requests (still ≈ $0.07); summary suite +10 recaps ≈ +$0.02 → ≈ $0.08. **`all` ≈
  $0.61** (≈ $0.85 at peak, ≈ $0.42 with cached replies, since the recaps are cached by request hash like every
  DeepSeek reply).

**Rejected:**
- **one accuracy number for both group slots:** the second slot's right answer is often `none`, so a mixed number
  hides "never adds anyone";
- **a target on the second-reply rate:** the rate follows the conversations; the labelled items already say when a
  second voice is right.

### G12. Speed and cost, in one place

| Step | When | Latency | Cost |
|---|---|---|---|
| Group first slot | inside call 1 (doc 01 A4) | none extra | none extra |
| Follow plan (G2) | after the first reply, alongside the 400 ms gap | ≤ 400 ms, hidden by the gap when Jev is in time | ≤ 2,000 tokens × $0.042/M ≈ **$0.00008** per send that has a first reply |
| Turn cue sentence (G3) | in the cue | none | ≈ 25 uncached tokens ≈ $0.000004 |
| Everyone order (G4) | inside call 1 | none | none extra |
| Watch plan-ahead (G8) | during the pace wait | hidden by the pace | the plan it replaces; a redo after a change ≈ $0.00005 |
| Steer (G7) | inside call 1 | none | the noul is already asked |
| Episode recap (G10) | on Summarise | ≈ 2–4 s (one non-streamed call) | ≈ $0.0017 off-peak |

A group send with two replies costs about **$0.0001 more in Jev** than today's single route call; at the current
volume that rounds to nothing next to the replies themselves.

## 5. Checks before this is locked

Collected for the paid-check step after all 13 tasks (the user's rule), not run now:

| # | Check | Pass | If it fails |
|---|---|---|---|
| Doc 01 check 3 (extended) | Add **50 follow-plan requests** from the frozen group transcripts, Jev only (≈ $0.004), to the latency run; record the share over 400 ms | ≤ 20 % over 400 ms | G2's fallback rule: bring the two options to the user |
| Doc 01 check 3 (extended) | Watch at Fast pace (0.5 s): time from `turn.end` to the next first word with the plan-ahead | the next first word within NFR-02's 3 s p50 | Fast pace keeps the plan-ahead but the pace label notes the real gap |

## 6. Changes this design needs (each approved at its OpenSpec change)

None changes the HTTP contract.

| Change | Kind | Why | Decision |
|---|---|---|---|
| The first-slot question without `none` when nobody is mentioned, in `naive` and `agent` | backend | finding 1 | G1 |
| The **follow plan**: `Decider` purpose `follow_plan`, `timeoutsMs.decision.follow_plan` = 400, ledger purpose, run alongside `turnGapMs`; replaces doc 01 A4's second-replier re-plan; `floor.second` in the question bank | backend + config | finding 2 | G2 |
| The turn cue's optional sentence (second reply, Next speaker, steer), in the `agent` compiler and its TS twin with shared fixtures ("View as prompt") | backend + frontend | doc 04 §9 | G3 |
| Next speaker and Step in call the planner; Everyone ordered by Jev's probabilities | backend | today's random picks | G4 |
| A user message cancels the previous send's queued replies, in the runtime and the mock's group engine, with a parity fixture | backend + mock | finding 3 | G5 |
| Watch: planner pick without the last speaker, the nobody-left-out guard (`forcedBy: "round_order"`), "Auto" opening via the planner (`agent` only) | backend | G6 | G6 |
| Watch steer: the `t_end` noul adds the cue sentence, once per 3 turns, not during a director's note | backend | finding 4 | G7 |
| Watch plan-ahead during the pace wait, with invalidation | backend | speed | G8 |
| Tired characters left out of the second slot, with the `routing.reason` text; energy removed from Jev call 1's state (doc 05 X9) | backend | finding 5 | G9 |
| `Summariser.episode` as one DeepSeek call (`naive`, `agent`), `runtime.llm.calls.episode`, ledger purpose `episode_summary`, the retryable error on failure | backend + config | doc 05 X3 | G10 |
| Eval: who-speaks set to ~130 items in three parts, the second-slot baselines, the layer 3 group and watch signals, 10 episode recaps in `summary` | evals | measure it | G11 |
| **Docs to amend:** doc 01 A4 (second-replier re-plan → G2's follow plan; Everyone now asks who speaks) and §8 (the watch contract row withdrawn); doc 02 B2, B5, B7; doc 03 C1 (the `episode` row); doc 04 §9 (resolved); doc 05 X9 (no `energy`) and X3 (the recap designed here); doc 06 E1 (the re-plan is the follow plan) | docs | consistency | all |

## 7. Left for later tasks

- A debate side whose members are all exhausted (task 8, OQ-AI-17).
- The debate member choice and its turn cue (task 8, doc 01 A14).
- How the "talk finished" probability and the follow plan's candidates show in Insight's System 1 section (task 13).
- Whether a group may run longer exchanges between characters without the user (beyond 2 replies per message): not
  in v1; MULTI-03 caps Auto at 2, and Next speaker already lets the user ask for more.

## Sources

- Horizon requirements: MULTI-02, MULTI-03, MULTI-09 to MULTI-11, MULTI-17, ENG-02, ENG-04, NFR-02
  ([02-functional-requirements](../requirements/02-functional-requirements.md),
  [07-nfr-risk-cost](../requirements/07-nfr-risk-cost.md)); OQ-AI-06 and OQ-AI-17
  ([08-open-questions-handoff](../requirements/08-open-questions-handoff.md)).
- Code: [group.py](../../backend/horizon/sessions/modes/group.py), [watch.py](../../backend/horizon/sessions/modes/watch.py),
  [common.py](../../backend/horizon/sessions/modes/common.py), [actor.py](../../backend/horizon/sessions/actor.py),
  [naive/router.py](../../backend/horizon/ai/naive/router.py), [scripted/ports.py](../../backend/horizon/ai/scripted/ports.py),
  [energy.py](../../backend/horizon/domain/energy.py), [schema.json](../../backend/horizon/contract/schema.json),
  [runtime.json](../../seed/runtime.json), [pricing.json](../../seed/pricing.json).
- Course notes: 7.1 Agents §7.1.6 (blackboard and swarm patterns need hard termination bounds; watch keeps its caps).
- [TypeSafe: confidence-gated routing](https://docs.typesafe.ai/patterns/confidence-routing.md) (floors per question,
  set by the cost of acting on a wrong answer).

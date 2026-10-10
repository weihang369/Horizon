# 08: Debate

> **Status: agreed with the user, 2026-10-10** (AI stage, task 8 of 13).
> - It resolves OQ-AI-05 (debate orchestration) and the last open part of OQ-AI-17 (**a debate side whose members are
>   all exhausted**). It also settles what earlier docs left here: **the debate member choice** (doc 01 A14), **the
>   debate argument, host and verdict prompts** (doc 03 §7, doc 04 §7), **what the host and the verdict see** (doc 05
>   §7) and **the debate rubric judge** (doc 02 B4).
> - Decisions are numbered **V1–V12**, each with the alternatives we rejected. **Revised after an independent review**
>   (it checked the code; 18 findings, all addressed, none changing a user decision).
> - It builds on [01-agent-architecture](01-agent-architecture.md) (A1–A14),
>   [02-evaluation-observability](02-evaluation-observability.md) (B1–B12),
>   [03-llm-parameters](03-llm-parameters.md) (C1–C9),
>   [04-persona-prompt-drafter](04-persona-prompt-drafter.md) (P1–P12),
>   [05-context-engineering](05-context-engineering.md) (X1–X10),
>   [06-emotion-reactions](06-emotion-reactions.md) (E1–E9) and
>   [07-turn-taking-energy](07-turn-taking-energy.md) (G1–G13).
> - **No contract change and no requirement change.** The member choice uses `routing` fields that exist
>   (`question`, `candidates`, `selected`, `forcedBy: "round_order"`, `reason`), so doc 01 §8's "new trace marker"
>   is withdrawn. Host lines are `note` messages, as today. The verdict fills the `Verdict` shape that exists.

## 1. The question

A debate is the most structured mode: phases in order, two sides (or a panel), a host and a verdict. Doc 01 already
decided that **code keeps the structure and the side order, and Jev picks which member of a side speaks** (A14), and
that **the verdict is Jev rubric scores, with DeepSeek writing the prose** (A7's verdict graph). Task 8 decides **how
the member is picked and when**, **how the sides are kept from drifting into agreement**, **what happens when a side
runs out of energy**, **what the host says**, **how the verdict is scored, decided and written**, and **how all of it
is measured**.

**The user's decisions (2026-10-10):**
- **A side whose members are all asleep pauses the debate with a top-up prompt** (V5), as watch already does when
  everyone is asleep. No forfeit, no one-sided debate.
- **The Auto host's lines are written by DeepSeek and prepared ahead,** shown whole, with today's fixed sentence as
  the fallback (V6).
- **The two-sided winner is decided by code from Jev's rubric scores,** with a "too close to call" margin, so the bars
  and the winner always agree (V7).
- **Sides are kept apart by per-phase cues, a side lock and an evaluation measure,** with no live check (V4, V11).
- Standing rule (doc 07 G2): **if Jev proves slow, Jev stays**; deadlines follow the measured latency and the result is
  reported.

## 2. What Horizon already has

From the code:

- **The runtime** ([debate.py](../../backend/horizon/sessions/modes/debate.py)) is a deterministic phase machine:
  the configured phases run in order (`quick`: opening → closing; `standard`: opening → rebuttal → closing), each
  opening with a `phase` event, a `ROUND n · LABEL` note and, with `moderator: auto_host`, one host `narration` note.
  Two-sided debates interleave `prop[i]` / `opp[i]` (uneven sides allowed: 2 v 1 runs P, O, P); panels follow cast
  order. Each member speaks once per phase. Every turn is `forcedBy: "round_order"`.
- **Openings are generated ahead:** up to 2 later openings (`prefetchMax`) stream in parallel and are revealed at
  speaking pace.
- **Timing:** the debate starts 1.6 s after Start (`debateStartMs`); each turn is followed by the 400 ms turn gap
  (`speak_then`), then `turn.next` names the next speaker, then auto-advance waits `pauseMs` (1.5 s) before the next
  step. So `turn.next` lands about 400 ms after `turn.end`.
- **Steering:** Ask (a directed question, answered at the front of the queue as kind `answer`), Interject (a
  moderator message in the history), Extend round (the phase repeats as iteration 2), Skip to closing, End debate
  (with or without verdict), and "You decide" (`debate.pick`).
- **Energy:** an asleep member is skipped with "{name} is asleep, skipping." **If a whole side is asleep, the other
  side simply keeps talking:** the debate becomes one-sided without telling anyone.
- **The host** ([scripted/ports.py](../../backend/horizon/ai/scripted/ports.py) `ScriptedDebateHost`) is used by
  **every profile** (`naive` has no host of its own): three fixed sentences, and `narration()` returns a string, so it
  can't call a model.
- **The verdict** is the mock's `make_verdict` in every profile: random scores (higher for a random winner, 15 %
  "too close"), each side's first sentences as the summary bullets, and a fixed key disagreement. Only a verdict the
  user doesn't pick charges a simulated call. In "You decide" the verdict is built **when the user clicks**.
  A provider error leaves the session in the verdict phase with nothing shown.
- **The debate prompt** (`naive`, [naive/prompt.py](../../backend/horizon/ai/naive/prompt.py)): "This is a moderated
  debate on the motion … Opponents: …" (it lists everyone, teammates included, as opponents) and the cue "Give your
  {phase} statement for {side}, round {n}. Stay under a few sentences."
- **The contract:** `DebateConfig.rubric` is data (any 2–6 criteria); the mock and fixtures use Evidence · Rebuttal ·
  Clarity · Persuasion. `Verdict` has `decidedBy`, `strongerCase` (`prop` / `opp` / `null`), `scoresBy`,
  `scores[] {subjectId, criterionId, value}` (the UI draws `value / 10`), `summary[] {subjectId, points[]}`,
  `keyDisagreement` and `rationale`. A host line is a `note` with author `host` and kind `narration`.
- **Motion suggestions** are a fixed list in the frontend (`setupLogic.ts` `suggestMotions`).

**Findings:**
1. **A fully asleep side silently turns the debate one-sided,** and the verdict then judges a debate one side never
   argued.
2. **Teammates are told they are opponents** (the naive prompt lists the whole cast as "Opponents").
3. **Nothing stops the sides drifting into agreement.** All characters run on one model, and agents on one base model
   tend to converge ("debate collapse", doc 01 §6); the cue only names the phase.
4. **The host never mentions what was said,** and **the verdict reads nothing**: it is random in every profile,
   including the ones that spend real money on the arguments.
5. **"You decide" waits for the verdict only after the click,** so the reveal stalls on a model call once the verdict
   is real.

## 3. The design in one picture

```
Start ─ host welcome (DeepSeek, written during the 1.6 s start delay; fixed line if late)      V6
  │
  ├─ ROUND 1 · OPENING   openings in fixed order, 2 generated ahead (unchanged)
  │
  ├─ every turn.end ──► debate plan for the next slot (Jev, deadline turn.end + 400 ms)        V2
  │                       which member of the side (only when 2+ can speak) + their gates and emotion
  │                       late / unsure → next member in fixed order; turn.next announces them
  │                     side with nobody awake → pause, top-up prompt                          V5
  │
  ├─ last turn of a round ends ──► host bridge (DeepSeek, shown after the banner)               V6
  ├─ ROUND 2 · REBUTTAL / ROUND 3 · CLOSING   cues: answer their strongest point; no new points V4
  │
  └─ last closing ends ──► verdict work starts at once (also for "You decide")                 V9
        Jev: 4 criteria × 2 sides, one request ─► code: averages, margin → stronger case       V7
        DeepSeek: bullets, key disagreement, rationale (JSON), told the result                 V8
        host verdict lead-in fills the wait                                                    V6
```

## 4. Decisions

### V1. The structure stays a phase machine in code (OQ-AI-05)

**Decision:**
- **Code runs the debate:** the phases, the side order (two-sided interleaving, uneven sides as today), "each member
  once per phase", Extend, Skip to closing and the daily budget cap (a debate has no turn cap). This answers OQ-AI-05's "state machine vs an LLM moderator".
- **The models only fill slots inside it:** Jev picks the member (V2) and scores the verdict (V7); DeepSeek writes the
  arguments (V4), the host lines (V6) and the verdict prose (V8).
- **Openings keep the fixed order** (A14), so they are still generated ahead.
- **Not in v1** (as MULTI-05 says): cross-examination, a cast character as chair, AI-written motion suggestions
  (they would need a new contract method; the fixed list stays).

**Rejected:**
- **an LLM moderator that decides who speaks and when a phase ends:** it can loop, skip a side or end early, and
  fairness would depend on a prompt;
- **AI-written motion suggestions:** a new contract method for a "Should" item.

### V2. The debate plan: Jev picks the member right after each turn

**Decision:**
- **When a turn's `turn.end` has been appended, the runtime starts the plan for the next slot** (`Decider` purpose
  **`debate_plan`**). It holds, in one request (doc 01 A4's debate row, Speculative Fan-Out):
  - **which member speaks** (`choice`), only when **two or more** members of that side can speak (awake and not yet
    heard in this phase); with one, there is no question;
  - **per eligible member:** the gates and the emotion (doc 06 E1's question for the debate turn kind).
- **The question, per phase** (options shuffled, A3 rule 4; each option's criteria are the member's name and `about`,
  ≤ 60 characters, doc 05 X9):

  | Phase | Question |
  |---|---|
  | rebuttal | "The {other side} has just argued this (the last opposing argument, in the state). Which of these {side} speakers is best placed to answer it?" |
  | closing | "Which of these {side} speakers is best placed to sum up {side}'s case and answer what is still open?" |
  | opening | not asked: openings keep the fixed order |
  | panel, any phase after opening | "Which of these panellists has the most to say about the last argument?" |

  There is **no `none`**: the slot must be filled. The state holds the motion, the phase, the side, **the last
  opposing argument** in full (with uneven sides the argument just before may be a teammate's, so it is not used), and
  each candidate's latest argument cut to 60 words, so Jev can see who already covered a point (doc 05 X9 amended).
- **A deadline, not a timeout:** `timeoutsMs.decision.debate_plan` = **400**, measured from `turn.end`. It **replaces
  the 400 ms turn gap** for this step (as doc 07 G2 does), so `turn.next` still comes about 400 ms after `turn.end`,
  inside NFR-02's 500 ms.
- **Fallbacks** (doc 01 A4's row, unchanged):

  | Case | Member |
  |---|---|
  | Jev's pick above `floor.member` | Jev's pick |
  | Jev unsure (below `floor.member`) | the next eligible member in today's fixed order |
  | Jev failed or past the deadline | the same |

- **The member is fixed at the deadline,** because `turn.next` announces them. **The request keeps running until the
  turn starts** (the 1.5 s pause): if its answer arrives by then, the chosen member's gates and emotion are used;
  otherwise the turn uses the usual turn-start fallbacks (quick, keep the face; doc 01 A4).
- **So debate turns get their plan during the pause,** instead of at turn start. A plan is the same request as call 1
  would be; it costs nothing extra except the choice question.
- **A stored plan uses doc 07 G8's fingerprint and lifecycle unchanged:** the actor's epoch, the seq of the last
  **character or user** message (system notes, round notes and host lines don't count, so a banner doesn't spoil the
  plan), the moderator note, and each member's awake, muted and current-face state; it is held with the actor's
  timers, so `clear()` cancels it (Stop, End, a cap pause, leaving). If the fingerprint differs at turn start (an Ask,
  an Interject, a MANUAL face change, a top-up, Play after a pause), the announced member stays and the gates and
  emotion are asked again with the normal `turn_plan` timeout.
- **Phase boundaries:** no `turn.next` is sent after a phase's last turn (as today: the next phase's banner comes
  first). The plan for the next phase's first slot is made at that last `turn.end` and stored with its target
  (phase, iteration); `begin_phase` uses it only if the phase it opens is that target and the fingerprint holds,
  otherwise that first slot plans at turn start (`turn_plan` timeout; late or unsure → fixed order). Extend and Skip
  therefore discard it, like the prefetches today.
- **Trace:** `routing.question` = the question above, `routing.candidates` with Jev's probabilities,
  `routing.selected`, `forcedBy: "round_order"` (the side is still set by the order), and `routing.reason` =
  "Side by the debate order; speaker chosen by Jev" (or "… next in order: Jev was late / unsure"). These fields exist,
  so **no contract change** (doc 01 §8's "new trace marker" is withdrawn).
- **If check 3 shows Jev is slow from Malaysia, Jev stays** (the standing rule): the deadline is set from the measured
  p90, with a recorded NFR-02 exception for `turn.next`, reported as a finding about Jev.

**Rejected:**
- **planning at turn start (as other modes do):** the debate already pre-announces its next speaker, and the pause
  hides the Jev call for free;
- **choosing every member of a phase up front:** blind to the arguments the choice should answer;
- **Jev choosing openings:** it would stop the openings being generated ahead (NFR-02 at the start);
- **a `none` option:** the slot belongs to the side; skipping it is the energy rule's job, not Jev's.

### V3. Who may speak, and the energy rules inside a phase

**Decision:**
- **Each member speaks at most once per phase** (A14). A side gets as many slots per phase as it has members
  (2 v 1 runs P, O, P).
- **A slot whose side has nobody awake who hasn't yet spoken, but someone awake who has,** is skipped with
  "{name} is asleep, skipping." for the asleep member, as today: the side has been heard in this phase.
- **A slot whose side has nobody awake at all** pauses the debate (V5).
- **Energy is checked when the plan is made and again at turn start.** An awake candidate can still fall asleep in
  between: an Ask aimed at them during the pause drains them, and the asleep line is one estimated reply, which doubles
  when peak pricing starts. If the announced member is asleep at turn start, the next eligible teammate speaks (with a
  fresh `turn.next`); with none, the slot follows the two rules above.
- **Asleep members are listed in the next turn's `routing.skipped`** with reason `exhausted` (OQ-AI-17), as group
  does.

### V4. The debate prompt: keeping the sides apart

The `agent` compiler (doc 04 P1) gets the debate wording; `naive` keeps its own (V12), apart from the teammate bug.

**Decision:**
- **Session block** (cached, doc 04 P5's debate row):

  ```text
  This is a moderated debate run by {user}. The motion: "{motion}".
  You argue {FOR | AGAINST} the motion, on the {Proposition | Opposition}{ with {teammates}}.
  Arguing {against | for} it: {opponents with their roles}.
  ```

  Panel: "This is a moderated panel debate run by {user} on: "{motion}". Each panellist argues their own position.
  Also on the panel: {others with their roles}."
- **The debate reply rules** replace the short-message, question and "very short" lines of doc 04 P6:

  ```text
  - You argue {for | against} the motion for the whole debate. Never concede it or switch sides. You may grant a small
    point, then say why it doesn't change the answer.
  - Argue the way {name} would: your own voice, your own reasons and examples. Don't invent statistics, studies or
    quotes.
  - Speak to the room. Attack arguments, never people.
  - Use the motion's language; if you can't tell, English.
  ```

  Panel: the first line becomes "Hold the position {name} would actually hold. Don't drift into agreeing with the
  others just to be agreeable."
- **The per-turn cue** (dynamic tail), one line per phase, plus optional sentences:

  | Phase | Cue |
  |---|---|
  | opening | "Give your opening statement: your case in two or three reasons." |
  | rebuttal | "Give your rebuttal: name the strongest point the other side has made so far and answer it, then strengthen your own case." (panel: "the strongest point you disagree with") |
  | closing | "Give your closing statement: why your side's case is the stronger one. Answer what is still open, and add no new arguments." |
  | extended round | the phase line + "The round was extended: make a point not yet made." |

  - **Teammate sentence:** "{teammate} has already spoken for your side this round: add to it, don't repeat it."
  - **Moderator sentence** (once, for the next argument after an Interject): "Take the moderator's last note into
    account."
  - **Ask** keeps kind `answer` ("Answer the moderator's question directly: …"); the side lock still applies.
  - The length line stays in the session block (doc 04 P5): one paragraph, about 80 / 140 / 220 words.
- **Findings 2 and 3:** teammates are named as teammates (also fixed in `naive`, as a bug), and the side lock plus the
  rebuttal cue are the defence against collapse. The evaluation measures it (V11): **no live check.**

**Rejected:**
- **a live Jev check "did this argument concede the motion?" with a regenerate:** it adds a call per argument and
  sometimes a second reply's cost and wait; the user chose to measure first;
- **a different model per side:** against the cost rule, and the persona voices already differ (doc 04);
- **giving panellists a stance written by a model first:** an extra call before the debate, and the persona is
  already enough to argue from.

### V5. A side with nobody awake pauses the debate (OQ-AI-17)

**Decision:**
- **When a slot comes up and nobody on that side is awake** (panel: nobody on the panel), the debate pauses, like
  watch's everyone-asleep pause, except that **every** asleep member of the side gets a note (watch notes only the
  first participant):
  - each gets the existing asleep note, "{name} is asleep (⚡ {current})." (asleep means below one estimated reply, so
    the number can be above 0), with its `energy_exhausted` notice, so the UI offers Top up;
  - a system note: "The {Proposition | Opposition} is asleep. Top someone up to continue the debate." (panel:
    "Everyone on the panel is asleep. …");
  - `session.paused` with reason **`user`**, and the actor is held.
- **The slot is not used up.** After a top-up, ▶ (or Next turn) runs the same slot. Pressing ▶ without a top-up
  pauses again with the same notes.
- **Ending instead:** End debate, or Skip to closing, works as usual. If the verdict then runs, it is told which turns
  each side missed and why ("Opposition: 2 turns missed, everyone on that side was asleep"), and the prose says so
  (V8).
- **Shared runtime:** this is a rule, not AI, so it applies to every profile, and the **mock's debate engine gets the
  same change** with a parity fixture (as doc 07 G5 did for the group engine).
- **No contract change:** pause reason `user` and `energy_exhausted` exist and are already used this way by watch.

**Rejected:**
- **forfeit to the verdict:** a running-out-of-energy game mechanic would decide a debate about argument quality;
- **continuing one-sided (today):** finding 1; the verdict would judge a side that never argued;
- **a new pause reason `energy`:** a contract change for what `user` plus the notes already show.

### V6. The Auto host: DeepSeek lines, written ahead, shown whole

Only with `moderator: auto_host`. With "You" as moderator only the round banners show, as today.

**Decision:**
- **Four kinds of line**, each a `note` with author `host` and kind `narration` (as today), one bubble (doc 03 C5):

  | Line | Written from | Requested | Shown |
  |---|---|---|---|
  | welcome | the motion, the format, the sides and names | at Start | after ROUND 1's banner; waits until Start + 3 s at most |
  | bridge to rebuttal / closing | the round just finished (its arguments, quoted as content) | at that round's last `turn.end` | after the next banner; waits at most 1.5 s after the banner |
  | the extended round's line | the round so far, plus "the round was extended" | when Extend's `begin_phase` runs | after its banner; waits at most 1.5 s |
  | bridge after Skip to closing | everything argued so far | when Skip's `begin_phase` runs | after the CLOSING banner; waits at most 1.5 s |
  | verdict lead-in | the closings | at the last closing's `turn.end`, with the verdict work (V9) | after the VERDICT banner; waits at most 1.5 s |

  **Each request is keyed by the (phase, iteration) it introduces;** when Extend or Skip changes what comes next, a
  request made for something else is dropped.

  The request starts during the turn gap, the pause (1.5 s) and the banner, so a line is usually ready when it is
  needed. **When it isn't ready by its deadline, the fixed sentence of today is used** and the late answer is dropped.
- **Instruction:** "You are the host of this debate. Write one or two sentences, at most 40 words. Stay neutral: never
  say or hint who is winning, and never add an argument of your own. {Welcome: introduce the motion and the
  speakers. | Bridge: name each side's main line in the round just finished, then introduce the next round. | Lead-in: thank the
  speakers, then, by verdict mode: the arbiter is weighing the arguments | it's now {user}'s call | here is the
  summary.} Use the motion's language."
- **Settings:** `runtime.llm.calls.host`: thinking off, temperature **1.0** (doc 03 C1), output **text** (not
  streamed: the user's choice; the contract would allow a streamed `host` turn, but it would have to run through
  the turn runner and the reducer for a 40-word line), `max_tokens` 120. Ledger
  purpose `host` (category chat), daily cap only (ENG-02 AC2).
- **Failure** (error, refusal, empty, over 60 words): the fixed sentence. The lead-in, which has none today, gets
  three fixed lines, one per verdict mode ("Thank you all. The arbiter is weighing the arguments." / "… Now it's your
  call." / "… Here is the summary."). A cap refusal pauses the session, as today.
- After End debate the app goes straight to the verdict screen, so the lead-in may only be seen in the log; that is
  fine.
- **`DebateHost.narration()` becomes async** and receives the session context (doc 01 §8's row).
- **Profiles:** `naive` and `agent` share this host. `scripted` keeps its fixed sentences (mock parity), and so has no
  verdict lead-in.

**Rejected:**
- **fixed lines (today):** the host never mentions what was said (finding 4);
- **streamed host lines:** host turns through the turn runner and the reducer, and each round change would wait on
  a stream;
- **a host line before every argument:** about 12 more calls a debate, and the round banners already pace it.

### V7. The verdict score: Jev scores, code decides the winner

Two-sided debates with verdict by **Arbiter** or **You decide** only.

**Decision:**
- **One Jev request** (`Decider` purpose **`rubric`**, which the gateway already lists as a decision purpose) with
  **one `score` question per side per criterion**: 8 with the default 4 criteria, at most 12 (the contract allows
  2–6). Jev runs them in parallel on the same state.
- **State:** the motion, the sides with their members, the missed-turn facts (V5), and the arguments as **two side
  blocks** (all of one side's arguments in speaking order, each labelled with its phase and speaker, then the other
  side's; Ask answers inside their speaker's block, moderator notes in a third short block). Quoted as content (doc 05).
  Blocks let the evaluation swap which side comes first without breaking what answers what (V11).
- **A size budget, because nothing caps Extend or Ask:** the state is held to **24,000 tokens** (inside Jev's 32K for
  state plus the longest question). Over it, code first cuts every argument of an **earlier iteration** of a phase and
  every Ask answer to its first 60 words, keeping each phase's latest iteration whole; still over, every argument is
  cut to its first 120 words. Only if it is still over does the verdict degrade to summary-only (V8). A worst-case
  size test (5 debaters, 4 extensions per phase, long turns, 10 Asks) is part of the change.
- **The rubric** (`DebateConfig.rubric` is data; these are the default criteria and their questions). Each has **5
  levels** written as concrete descriptions:

  | Criterion | Question (for one side) | Level 1 → level 5 |
  |---|---|---|
  | Evidence | "How well does the {side} back its claims with reasons, examples or facts?" | bare assertions → every main claim backed by a specific, relevant reason or example |
  | Rebuttal | "How directly does the {side} answer the other side's strongest points?" | ignores the other side → names their strongest point and answers it |
  | Clarity | "How easy is the {side}'s case to follow?" | no clear claim → one clear claim, each reason plainly linked to it |
  | Persuasion | "How convincing would a neutral listener find the {side}'s case, judging argument quality and not whether it is true?" | not at all → hard to resist |

  A criterion the user's config names without a known question gets a generic question built from its label
  ("How strong is the {side} on {label}?") with generic levels.
- **Bars:** Jev's weighted position *w* (1–5) becomes `value` = (*w* − 1) / 4 × 10 ([doc 13](13-wrap-up.md) W11: `unit` × 10), to one decimal (the UI draws
  `value / 10`). `scoresBy: "side"`.
- **The winner, in code:** each side's mean over the criteria (equal weights); if the difference is under the margin
  **`verdict.margin`** (start **0.5** on the 0–10 scale, tuned in V11), `strongerCase` is `null` ("TOO CLOSE TO CALL",
  MULTI-08 AC2b); otherwise the higher side. The bars and the banner can never disagree.
- **Jev's confidence is not used** for the winner: the margin already covers a near tie, and a score question's
  confidence measures how peaked one answer is, not the comparison.
- **Panel debates and verdict "None"** get no scores and no winner (MULTI-05, MULTI-08 AC4): only the prose (V8).
- **Order bias:** live, the Proposition block comes first. The evaluation asks again with the blocks swapped (V11).
  If that shows a lean toward one position, the fix is asking both orders and averaging (≈ $0.0003 more a debate), not
  a different design.

**Rejected:**
- **a separate Jev "who won?" question:** the bars could then disagree with the banner;
- **DeepSeek decides the winner:** against "maximise Jev", and a writer deciding its own verdict can't be checked
  apart from its prose;
- **one Jev score per criterion comparing both sides:** a comparison question has an order (first-option lean) and
  gives no per-side bar;
- **weighting Persuasion higher:** no evidence for any weight; equal weights are explainable in one line.

### V8. The verdict prose: DeepSeek JSON, told the result

**Decision:**
- **One DeepSeek call** (`runtime.llm.calls.verdict`: thinking off, temperature **0.7**, like the summaries, because it
  must be faithful; output **JSON** (doc 03 C7: JSON mode, validated, one retry); `max_tokens` **1,200** (a 5-member
  panel in Chinese or Malay can pass 700, and only generated tokens are billed); overall limit
  **30 s**, `timeoutsMs.verdict`). Ledger purpose `verdict` (category chat), daily cap only.
- **Input:** the motion, the format, the sides and names, the transcript (quoted as content), the missed-turn facts,
  and **the result already decided**: the scores and the stronger case (two-sided), or "summary only". The prompt
  carries **one example output** and the mapping from each name to its `subjectId` (`prop`, `opp`, or the panellist's
  character id), as doc 03 F2 asks of JSON mode.
- **Instruction:** "Write the arbiter's notes as JSON with `summary` (for each {side | panellist}: 3–5 points, each
  at most 20 words, what they argued, in their own terms), `keyDisagreement` (one sentence: the point the debate
  turned on) and `rationale` (two sentences explaining {the result} from the scores). Judge the quality of the
  arguments, never which side is factually right. Say nothing that wasn't argued. Use the debate's language. If a
  side missed turns, say so plainly." Panel: 2–4 points per panellist.
- **"You decide":** the prose is written before the click (V9), so the rationale is written **as the arbiter's view**:
  "The arbiter's scores favoured the {side}: …" or "The arbiter found it too close to call: …". It never claims the
  banner's result, which is the user's. (The card shows the rationale outside the "Show Arbiter's view" toggle, which
  only hides the bars, so its wording must say whose view it is.)
- **Validation:** every expected subject present; two-sided 3–5 points per side (MULTI-08 AC1; 2 accepted for a side
  that made only one or two arguments), panel 2–4; more are cut to the maximum; `keyDisagreement` ≤ 30 words;
  `rationale` ≤ 60 words. Invalid → one retry → the fallback below.
- **The verdict** sent is `{decidedBy, strongerCase, scoresBy, scores, summary, keyDisagreement, rationale}`, as the
  contract has it.
- **Failure, without a hang or a fake** (finding 4; the session is in the verdict phase, so it must end):

  | What failed | Verdict sent | Note in the log |
  |---|---|---|
  | the prose only | Jev's scores and winner; `summary` = each side's first sentences, **quoted from the real arguments** by code (today's extraction); no key disagreement, no rationale | "The arbiter's notes couldn't be written; the summary quotes the speakers." |
  | the Jev scores (after one retry), Arbiter | **summary only** (`decidedBy: "none"`): the banner reads SUMMARY, not a made-up "too close" | "The arbiter couldn't score this debate; here is the summary." |
  | the Jev scores, You decide | the user's pick (`decidedBy: "user"`), no scores, no rationale | the same note |
  | both | summary only (You decide: the pick), with the quoted summary | both notes |
  | a cap refusal | nothing yet; the session pauses, as today | — |

  **Today's cap-refusal hang is fixed:** `go_verdict` returns on a refusal and `step` ignores the verdict phase, so
  after the user raises the cap and resumes, the screen stays on DELIBERATING for ever. **Resuming in the verdict phase
  with no verdict runs the verdict work again**, and a refusal on the pick path is caught the same way (the pick is
  kept).

**Rejected:**
- **plain text with labels parsed by code** (doc 01 §6's old line): a summary per side and three fields is exactly what
  JSON mode is for, and the drafter already uses it;
- **letting DeepSeek see no scores:** its rationale could contradict the banner;
- **today's canned key disagreement in the fallback:** it reads like a real finding about a debate it never read.

### V9. The verdict work starts at the last closing, also for "You decide"

**Decision:**
- **The verdict work (V7 then V8) starts when the last turn of the last phase ends,** unless Extend is set, in parallel
  with the turn gap, the pause, the VERDICT banner and the existing 1.8 s delay. Extend or Skip discard it (at most
  ≈ $0.002 wasted).
- **End debate → "Go to verdict now"** keeps the current argument (`clear(keep_current=True)`), so the work starts
  **after that argument's `turn.end`**, never on a half-written transcript. The work is stored with a transcript
  fingerprint (the seq of the last character message and the iteration); End right after the last closing finds a
  matching one and reuses it instead of paying twice.
- **"You decide":** the same work starts then too, so it is usually ready before the click (MULTI-08 AC3's summary
  first, then the pick). The pick sets `strongerCase` and `decidedBy: "user"`; the arbiter's scores and rationale stay
  in the card, written as the arbiter's view (V8). **If the click comes first, `debate.pick` only records the side
  and returns:** the verdict is delivered by a job when the work finishes (the button shows "…", as today). The pick
  never waits inside the actor's command inbox, so Pause and End stay responsive and the HTTP request returns at once.
- **`DebateHost.verdict` splits** into `assess(ctx, by)` (started early, cancellable, held with the actor's timers so
  `clear()` cancels it) and `deliver(picked)`. `scripted` keeps its synchronous verdict and its simulated charge.
- **Expected wait:** Jev ≈ 0.3–1 s, then the prose ≈ 300 tokens, about 5–8 s, from the last closing's `turn.end`. The
  first ~3.7 s are the gap, the pause, the banner and the delay that exist today, so the viewer waits about 2–5 s more,
  with the host's lead-in on screen (V6). This is measured (§5).

**Rejected:**
- **starting at the click (today):** finding 5;
- **streaming the prose into the card:** JSON can't stream usefully, and the card's reveal is one ceremony.

### V10. Steering, unchanged in shape

**Decision:** Ask, Interject, Extend, Skip to closing, End debate and the auto-advance toggle keep today's behaviour.
What changes: an Interject adds V4's moderator sentence to the next argument. A stored plan (V2), a host request
(V6) and the started verdict work (V9) each check what they were made from (a fingerprint or a target phase) rather
than a list of events, so any steering that changes their inputs makes them be redone or dropped.

### V11. Evaluation additions

**Decision** (doc 02 B2, B4, B5, B7 and B8 are amended):
- **Debate member set (layer 1): 90 items** (30 test), rebuttal and closing slots with 2–3 eligible members, from the
  frozen debate transcripts and the debate suite's runs; **at least half have a single acceptable member** (the last
  argument plainly falls in one member's field). Targets (B5): **≥ 80 % inside the acceptable set**; and on the
  single-answer items, **≥ 15 points above the fixed order**, judged with an exact paired test. With 2–3 members and
  broad acceptable sets, 80 % is close to a free pass, so the lift is measured only where one answer is right; the
  random-pick baseline is reported too.
- **Debate quality judge** (B4's row): two nouls per argument, checked like every judge (30 real + 30 planted, B4):
  - **keeps its side:** "Does this argument support the {side}'s position on the motion?" (planted: an argument from
    the other side, relabelled);
  - **engages** (rebuttals and closings): "Does this argument answer a specific point the other side made?" (planted:
    an opening statement put in a rebuttal slot).

  On the layer-3 debate turns (4 frozen transcripts, both profiles) and the debate free runs. Targets: `agent` keeps
  its side on **≥ 95 %** of arguments and engages on **≥ 80 %** of rebuttals and closings; both reported next to
  `naive`.
- **Verdict set (new, in a new `debate` suite):** 12 debates (the 4 frozen debate transcripts plus 8 generated once by
  `naive`, reviewed and committed), each in two versions:
  - **balanced:** as written;
  - **planted weak side:** one side's rebuttal and closing replaced by versions that repeat its opening and ignore
    the other side (written once by DeepSeek, reviewed, committed), so the stronger side is known.

  **Split by debate: 4 dev (8 items), 8 test (16 items).** `verdict.margin` is tuned on dev only, so the planted
  versions pass while the balanced ones aren't all called "too close". Measures on test, each failure read (a
  gross-failure check, B2):
  - planted: **the strong side wins in ≥ 7 of 8**, and its **Rebuttal** score is higher in ≥ 7 of 8 (Evidence is not
    targeted: the weak versions repeat the opening, which keeps its evidence);
  - **side-order swap:** every debate again with the Opposition block first (V7); a change from one winner to the other
    may happen in **at most 1 of 16**; changes to or from "too close" are reported apart (the margin makes them
    likelier and they matter less);
  - the "too close" rate on the balanced debates (no target);
  - **the `naive` verdict as baseline** (V12): the same measures, reported side by side. This is the project's test of
    "Jev scores vs an LLM judging in one call".
- **Prose checks:** 10 `agent` verdicts (Arbiter, You decide and panel); nouls: every summary point is something that
  side said (per point); the rationale states the same result as the arbiter's scores; the rationale doesn't say a
  side is factually right. Target: at most 1 failure, each read.
- **Host checks:** 10 bridges from the frozen transcripts; nouls: neutral (doesn't say who is winning); mentions only
  what was argued. At most 1 failure, each read.
- **Free runs:** 2 more `agent` debates (Standard, 2 v 2 with Auto host and Arbiter; a panel of 4), so the member
  choice, the host, the pause rule and the verdict run live.
- **Cost (off-peak, first run):** decisions +180 Jev requests of ~3,000 tokens ≈ +$0.023 (≈ $0.10); the new `debate`
  suite ≈ $0.10 (Jev ≈ $0.012, the 48 `naive` baseline verdicts ≈ $0.063, prose, host lines and checks ≈ $0.02);
  conversations +2 free runs ≈ +$0.03 (≈ $0.44). **`all` ≈ $0.80** (≈ $1.18 at peak; ≈ $0.55 with the `naive`
  replies and verdicts cached; doc 09 M12 later makes these $0.98 / $1.48 / $0.68, and doc 10 K14 $1.01 / $1.53 / $0.71, and doc 11 S10 $1.08 / $1.65 / $0.78). **Once:** generating the 8 debates and the 12 planted rewrites ≈ $0.09. If Jev bills
  the state per question (doc 01 check 4), the suite's Jev part grows to about $0.10.

**Rejected:**
- **labelling real debates with a human winner:** no human check (B4, the user's decision), and judging debates is
  slow to label; planted weak sides give known answers for free;
- **a live side-keeping check:** the user chose measure-first (V4);
- **a "too close" target:** the right rate depends on the debates.

### V12. Speed, cost and profiles, in one place

**Speed and cost** for a Standard 2 v 2 debate, medium turns, Auto host and Arbiter (off-peak; DeepSeek doubles at
peak, Jev doesn't):

| Step | When | Latency | Cost |
|---|---|---|---|
| Debate plan (V2) | from each `turn.end`, deadline + 400 ms, replacing the turn gap | none extra when Jev is in time | the choice question only, about 4 a debate: ≈ $0.0001 |
| Host lines (V6) | welcome at Start, a bridge per round change, the lead-in | hidden by the pause and the banners; at most +1.5 s per round change when late | 4 × ≈ 2,000 in + 60 out ≈ **$0.0013** |
| Verdict scores (V7) | after the last closing | ≈ 0.3–1 s | ≈ 6,000 tokens ≈ $0.0003 (≈ $0.002 if Jev bills the state per question, 8 questions) |
| Verdict prose (V8) | after the scores | ≈ 5–8 s, mostly hidden (V9) | ≈ 6,000 in + 300 out ≈ **$0.0011** |

About **$0.003 a debate** on top of the arguments, all on the daily cap, none on energy (ENG-02 AC2).

**Which profile does what** (`scripted` must keep the mock's event stream; `naive` is the yardstick; `agent` gets
the design):

| Decision | `scripted` (demo, mock twin) | `naive` (yardstick) | `agent` |
|---|---|---|---|
| V2 debate plan, Jev member choice | no (fixed order) | no (fixed order) | yes |
| V4 debate prompt | no | teammates named as teammates (bug fix); otherwise its own prompt | yes (the `agent` compiler and its TS twin) |
| V5 asleep side pauses | **yes**, with the same change in the mock's debate engine | yes | yes |
| V6 DeepSeek host | no (fixed lines) | **yes** | yes |
| V7 Jev scores, code winner | no (random, as the mock) | **no: one DeepSeek JSON call writes the scores, the winner and the prose** (the baseline V11 compares with) | yes |
| V8 prose and its fallbacks | no | yes (its single call) | yes |
| V9 early start | no | yes | yes |

**Rejected:** giving `naive` the scripted verdict: a profile that spends real money on the arguments would then show a
random winner.

## 5. Checks before this is locked

Collected for the paid-check step after all 13 tasks (the user's rule), not run now:

| # | Check | Pass | If it fails |
|---|---|---|---|
| Doc 01 check 3 (extended) | **30 debate-plan requests** from hand-built states ([doc 13](13-wrap-up.md) W6 A2) (Jev only, ≈ $0.003): the share that misses `turn.end` + 400 ms, state assembly included | ≤ 10 % miss | keep Jev, set the deadline from the measured p90, record the NFR-02 exception and the finding (V2) |
| Doc 01 check 3 (extended) | **10 host bridges and 5 verdicts** (≈ $0.01): time to the host line, and from the last closing's `turn.end` to the verdict | bridges ready within the pause + 1.5 s on ≥ 8 of 10; the verdict's real wait recorded | bridges: the deadline grows to the measured p90, so a round change waits a little longer (a bridge is never written before the round's last argument, or it would miss it); the verdict: a shorter prose target |
| Doc 01 check 4 (extended) | Whether an 8-question `rubric` request bills the state once or per question (`usage.cost`), and that a `score` answer's weighted position runs over the levels as 1–5 (V7's bar mapping) | recorded | the cost table follows; the mapping follows the real scale |

## 6. Changes this design needs (each approved at its OpenSpec change)

None changes the HTTP contract or a requirement.

| Change | Kind | Why | Decision |
|---|---|---|---|
| The **debate plan**: `Decider` purpose `debate_plan` (**added to the gateway's `PURPOSE_CATEGORY` as a decision**; `call_ctx` refuses unknown purposes), `timeoutsMs.decision.debate_plan` = 400 as a deadline from `turn.end` replacing `turnGapMs` for that step; the member question per phase over the last opposing argument, `floor.member` in the question bank; doc 07 G8's fingerprint and lifecycle; the phase-boundary plan with its target; energy re-checked at turn start; routing trace with `forcedBy: "round_order"`, `reason` and `skipped` | backend + config | A14 | V2, V3 |
| A slot whose side has nobody awake pauses the debate (notes, `energy_exhausted`, reason `user`, slot kept), in the runtime **and the mock's debate engine**, with a parity fixture; missed turns passed to the verdict | backend + mock | finding 1 | V5 |
| The debate session block, reply rules and per-phase cue in the `agent` compiler and its TS twin with shared fixtures; teammates named as teammates in `naive` | backend + frontend | findings 2, 3 | V4 |
| `DebateHost.narration()` async with the session context; a DeepSeek host (`runtime.llm.calls.host`, text, `max_tokens` 120, ledger purpose `host`), requested ahead, keyed by (phase, iteration), with deadlines and the fixed sentence as fallback; lines for Extend and Skip; a verdict lead-in worded per verdict mode with three fixed fallbacks (`naive`, `agent`) | backend + config | finding 4 | V6 |
| The verdict: `DebateHost.verdict` split into `assess` / `deliver`; Jev purpose `rubric` (one score question per side per criterion, the rubric's levels in the question bank, generic levels for unknown criteria), the state in side blocks with the 24,000-token budget and its worst-case test; `verdict.margin`; DeepSeek JSON prose (`runtime.llm.calls.verdict` at 0.7, `max_tokens` 1,200, an example output, `timeoutsMs.verdict` 30 s); "You decide" rationale as the arbiter's view; a non-blocking `debate.pick`; End starting the work after the current turn and reusing matching work; the failure table; **resume in the verdict phase re-runs the verdict** (today's hang); the `naive` single-call verdict | backend + config | findings 4, 5 | V7, V8, V9, V12 |
| "Go to verdict now (≈ $x)" (MULTI-07 AC4) is a hard-coded $0.0012 in `EndDebate.tsx`; it becomes an estimate from `pricing.json` and the current price period for the active profile | frontend | the new verdict's cost | V12 |
| Eval: 90-item debate member set with single-answer items; the debate-quality nouls; the new `debate` suite (12 debates split dev / test, planted and side-swapped versions, prose and host checks, `naive` baseline); 2 more `agent` debate free runs | evals | measure it | V11 |
| **Docs to amend:** doc 01 A7 (the verdict graph), A14, §6 (debate collapse; the verdict's JSON line), §8 (the trace-marker and host rows), §9; doc 02 B2, B4, B5, B7, B8, §8; doc 03 C1 (`host`, `verdict` rows) and §7; doc 04 P5 and §7; doc 05 X9 (the debate plan's state) and §7; doc 06 §7; doc 07 §7 and the cost pointers in docs 05–07 | docs | consistency | all |

## 7. Left for later tasks

- ~~How the member choice, the verdict's Jev probabilities and the host's fallbacks show in Insight's System 1
  section (task 13).~~ Resolved by [doc 13](13-wrap-up.md) W1: the member choice is a `debate_plan` row; the rubric scores stay
  on the verdict screen; host lines are not character messages, so they have no Insight (INS-01 AC5).
- ~~Retrieval in debate turns (task 10).~~ Resolved by doc 10 K4 and K7: the motion plus the last opposing argument,
  never rewritten; the gate decides per member; k = 2; never abstains.
- ~~What a debater says when a motion is unsafe, and checking the motion itself: task 11.~~ Resolved by doc 11 S3:
  the motion is checked once at creation (`content_refused`), and a moderator line by the next `debate_plan`.
- Not in v1: cross-examination, a cast character as chair, AI-written motion suggestions (MULTI-05).

## Sources

- Horizon requirements: MULTI-04 to MULTI-08, MULTI-16, ENG-02, ENG-04, NFR-02
  ([02-functional-requirements](../requirements/02-functional-requirements.md),
  [07-nfr-risk-cost](../requirements/07-nfr-risk-cost.md)); OQ-AI-05 and OQ-AI-17
  ([08-open-questions-handoff](../requirements/08-open-questions-handoff.md)).
- Code: [debate.py](../../backend/horizon/sessions/modes/debate.py), [common.py](../../backend/horizon/sessions/modes/common.py),
  [watch.py](../../backend/horizon/sessions/modes/watch.py) (the everyone-asleep pause),
  [scripted/ports.py](../../backend/horizon/ai/scripted/ports.py) (`ScriptedDebateHost`, `make_verdict`),
  [naive/prompt.py](../../backend/horizon/ai/naive/prompt.py), [profile.py](../../backend/horizon/ai/profile.py),
  [gateway/context.py](../../backend/horizon/gateway/context.py) (purposes `host`, `verdict`),
  [types.ts](../../frontend/src/contract/types.ts) (`DebateConfig`, `Verdict`),
  [VerdictScreen.tsx](../../frontend/src/features/ensemble/VerdictScreen.tsx),
  [setupLogic.ts](../../frontend/src/features/ensemble/setupLogic.ts), [runtime.json](../../seed/runtime.json),
  [pricing.json](../../seed/pricing.json).
- Course notes: 7.1 Agents §7.1.6 and §7.1.11 (debate patterns on one base model converge; structure and termination
  belong in code).
- [TypeSafe: composite scoring](https://docs.typesafe.ai/patterns/composite-scoring.md) (atomic scores combined with
  weights in code) and [confidence-gated routing](https://docs.typesafe.ai/patterns/confidence-routing.md).

# 13: Wrap-up: the Jev map, the System 1 section, the build plan

> **Status: agreed with the user, 2026-10-10** (AI stage, task 13 of 13).
> - It closes the design stage:
>   - the **System 1 section** in Insight: doc 01 A12, approved in principle on 2026-10-09; this doc designs its
>     fields and its UI;
>   - **the Jev map** (OQ-AI-12): every Jev question in docs 01–12 in one table;
>   - the leftovers from docs 06 and 09–12;
>   - **the build plan:** nine OpenSpec changes, M7–M15;
>   - **the paid checks**, in two groups.
> - Decisions are numbered **W1–W10**, each with the alternatives we rejected. W10 records the user's rule given at
>   the end of the task: **pay once, reuse everywhere** (checks, evaluation and the demo share every paid output).
> - **The user's four choices** (all four were the recommendation):
>   - System 1 is **one generic list** of questions;
>   - the **face-and-words check goes live**, while citations stay evaluation-only;
>   - "Doesn't look like them" adds **one fixed identity line**;
>   - the stage ships as **nine changes**.
> - **One contract change, approved by the user:** `TurnTrace.system1` (rev 1.4, additive, `schemaVersion` stays 1).
>   It is written into [05-data-contract](../requirements/05-data-contract.md) and `schema.json` together, in M7 (W1).
>   No other contract change, and no new UI entry point.
> - **Requirement-level edits:** the ones the user approved in tasks 3–12 are applied with this doc (§4). Two follow
>   from earlier agreed designs and are listed separately for the user to see:
>   - the scope table's v1.1 row also moves Jev rubric scoring, memory importance scoring and the evaluation harness
>     into v1 (docs 08, 09 and 02 put them there);
>   - ENG-02 AC2's list also names the face check (W2).
> - It builds on docs [01](01-agent-architecture.md) to [12](12-images-music.md).

## 1. The question

Docs 01–12 each added Jev questions, and each left items "for task 13". What is still open:

1. Insight shows only part of what Jev decided. `routing` and `emotion` show candidates, `guardrail` shows the checks
   and `calls` shows each call's latency and a fallback flag. The gates, the safety nouls, Jev call 2's scores, the
   follow and debate plans, and the threshold each answer was compared with show nowhere.
2. The face-and-words check (doc 06 E7) was waiting for that section.
3. "Doesn't look like them" sends a sentence nothing reads (doc 12 §6).
4. There is no single list of Jev questions: what each asks, its threshold, its fallback and its cost.
5. The stage has to be split into OpenSpec changes, and the paid checks have to be put in order.
6. Smaller leftovers:
   - whether post-turn spend shows in the cost counter (doc 06 §7);
   - Memory tab pagination and a "View source" that can point at a deleted session (doc 09 §7);
   - the requirement-doc edits approved in tasks 3–12.

## 2. Decisions

### W1. The System 1 section: one generic list of Jev questions (the user's choice)

**The contract (rev 1.4, additive):**

```ts
TurnTrace {
  …
  system1?: {
    seed?: string;                 // "{session seed}:{turn index}"; each question's shuffle seed adds ":{question id}" (doc 06 E1)
    questions: {
      purpose: string;             // the Decider purpose: turn_plan | follow_plan | debate_plan | deep_check | guardrail | face_check
      id: string; version: number; // the question-bank entry (doc 02 B9)
      label: string;               // its short wording from the bank, e.g. "needs documents?"
      about?: string;              // the character, piece or line it was asked about
      answer: string;              // the option, the level, or "yes" / "no"
      p?: number;                  // a noul: always p(yes); a choice or score: the answer's probability; absent on a fallback
      threshold?: number;          // the floor or threshold the answer was compared with
      result: "used" | "below_threshold" | "fallback" | "not_used";
    }[];                           // at most 64 rows
  };
}
```

- **What `result` means:**
  - `used`: the answer cleared its floor or threshold and code acted on it;
  - `below_threshold`: the "unsure" path in doc 01 A4's table was taken;
  - `fallback`: Jev failed or was late. `answer` holds what the fallback did, with no `p`;
  - `not_used`: the question was asked but its answer didn't apply. Speculative Fan-Out asks the gates and the emotion
    for every possible speaker (doc 01 A4), and only the chosen speaker's answers apply.
- **Timings stay in `calls`**, which already holds each call's purpose, latency, cost and fallback flag.
- **The bank gains a `label` per question** (a few words). `id` and `version` tie the row to the exact wording, so a
  result is never compared across wordings (doc 02 B9).

**Who writes it:**
- `system1` joins the sections only the runtime writes (`model`, `energy`, `routing`; doc 05-ai-seams §2.1). An engine's
  `TracePatch` that sets it is rejected.
- The runtime adds rows from:
  - the turn plan;
  - Jev call 2 (retrieval runs in the runtime, D-92);
  - the output check;
  - the face check (W2).
- **Rows are keyed by (purpose, id, about).** A later row with the same key replaces the earlier one, so no source
  overwrites another's rows. This is the lesson of doc 11's guardrail checks, which `deep_merge` used to replace.
- **A plan that starts no reply puts its rows on the previous reply's trace**, through a second `insight` event. The
  contract already lets a later `insight` replace the earlier trace (rev 1.3). This covers:
  - a follow plan that picked nobody (doc 07 G2);
  - a watch plan that steered the next line (doc 07 G7).

  A plan that does start a reply puts its rows on that reply's trace.
- **Not in the System 1 section:** Jev work that isn't part of a turn. Its spend shows in Settings → Cost (the ledger),
  and its full requests in `ai_calls` when capture is on (doc 02 B10). That work is:
  - memory pause runs (doc 09);
  - the verdict's rubric (doc 08; the verdict screen already shows its bars);
  - the motion check (doc 11 S3);
  - the image and song checks (doc 12);
  - listener reactions: each `reaction` event already carries its `p`, and they are other characters' faces;
  - host lines: they aren't character messages, so they have no Insight (INS-01 AC5).

**The UI** ([InsightDrawer.tsx](../../frontend/src/features/insight/InsightDrawer.tsx)):
- A **"System 1 · Jev"** section placed after Emotion, since it explains Routing and Emotion above it.
- Rows are grouped by purpose. Each group header shows the call's latency from `calls`, e.g. "before the reply ·
  412 ms", or "fallback" when the call failed.
- Each row reads: the label, the answer, `p` with its band (INS-01 AC4: `0.71 · HIGH`, never bare precision), the
  threshold, and what code did.
- `not_used` rows fold under "asked about the others (n)".
- Like every section, it is hidden when there is no data (INS-01 AC3). It is left out of Compact mode (INS-01 AC5).
- INS-01 AC2 gains the bullet (§4).

A deep 1:1 turn would show:

```
System 1 · Jev
 before the reply · 412 ms
   needs documents?          yes · p(yes) 0.81 · HIGH    ≥ 0.35 → deep
   needs something earlier?  no  · p(yes) 0.12 · LOW     < 0.40 → no recall
   emotion                   thinking · 0.62 · MED       → shown
   input safe?               p(steer) 0.03 · LOW         → no cue
   standalone?               no  · p(yes) 0.22 · LOW     → rewritten
 passages · 530 ms
   Ch.3 p.12                 answers · 0.88 · HIGH       → kept [1]
   Ch.5 p.40                 partly · 0.54 · MED         → kept [2]
   Ch.1 p.2                  doesn't help · 0.71         → dropped
 output check                p(breaks rules) 0.02 · LOW  → pass
 after the reply
   face and words agree?     yes · 0.66 · MED
```

**Profiles:**
- `agent` fills every row.
- `naive` fills the one Jev question it asks: the router's `route` choice.
- `scripted` and the MockClient give fixed rows from their fixtures: the scripted turn planner (doc 01 A12) and
  `turnScript.ts`. This keeps mock parity, so the public demo shows the section too.
- The seed sessions' recorded traces are left as they are. Insight hides the empty section. The real demo sessions
  (v1 endgame) will carry real rows.

**Rejected:**
- **A typed field per question:** a clearer schema, but every new Jev question would be another contract change.
- **No new section:** the gates, the safety nouls and Jev call 2's scores would stay invisible, and Insight is the
  product's "see the AI think" promise (INS-01, SC-2).
- **Timings inside `system1`:** they would duplicate `calls`.
- **Fabricated rows in the seed traces:** the recorded seed sessions would show decisions nothing made.

### W2. The face-and-words check goes live (the user's choice)

- **Purpose `face_check`.** It is a new decision purpose in `PURPOSE_CATEGORY` (category `decision`), with
  `timeoutsMs.decision.face_check` = 1,500 in `seed/pricing.json` and its mock mirror.
- **The question:** doc 02 B4's choice over the 7 emotions. Its state is **the reply text only**, cut to its last
  600 tokens, with the `quoted_*` sentence (doc 11 S6). The bank entry is shared with the evaluation, so the live check
  and the eval measure the same wording.
- **When:** after `turn.end`, in the after-turn work beside reactions. It runs on AUTO turns whose face isn't neutral,
  which is where doc 06 E8 measures it. It is skipped for MANUAL (the user chose the face), for neutral faces, and for
  a blocked reply.
- **The row:**
  - **answer:** "yes" when Jev's pick is the face shown; "clash" for happy against sad or angry, either way (doc 06
    E8); otherwise "no (words read: {pick})";
  - **p:** the probability Jev gave the face shown.

  It reaches Insight through a second `insight` event (W1).
- **It never changes the face (D-46).** A late or failed call adds no row.
- **Cancelled by `clear()`** (Stop, leave, cap pause, end), like reactions. The next `turn.start` doesn't cancel it,
  since it touches only the trace.
- **Spend:** about 400–700 tokens, so ≈ $0.00002 per checked reply. It is ledger category `decision`, counts toward the
  daily cap and never drains energy. ENG-02 AC2's list names it (§4).
- **Other profiles:**
  - `scripted` records a simulated `face_check` call (D-81) and answers "yes";
  - the mock does the same;
  - `naive` has no check.
- **`all` is unchanged:** the evaluation already runs this check (doc 06 E8).

**Rejected:**
- **The citation check live as well:** the user's K10 choice stands (doc 10). Faithfulness is measured in the
  evaluation, and a flag that can't remove a chip would cost money for little use.
- **Checking neutral faces too:** "neutral" against calm words is uninformative. The evaluation also leaves them out.

### W3. "Doesn't look like them" adds one fixed identity line (the user's choice)

- **The backend:** an `emotion_regenerate` job with any non-empty `prompt` (the button's hint, `StartJobInput.prompt`)
  compiles `emotion_edit(profile, emotion, identity=True)`. That adds one line after `KEEP`:

  > The face must be recognisably the same person as in the reference: same face shape, eyes, nose, mouth, eyebrows
  > and apparent age.

- **The hint's text never enters the prompt.** So:
  - nothing the user writes reaches Seedream, and doc 12's I3 check isn't needed here;
  - any text sent through the API is ignored the same way.
- **No UI or contract change.** The button and its hint already exist ([EmotionLightbox.tsx](../../frontend/src/features/profile/EmotionLightbox.tsx)).
- **Compiler v3** (doc 12 I1) carries it, with a golden fixture.
- **Checked by eye** where the v3 images are made: the endgame's in-app creation of the seed characters (W10). One
  identity edit there costs ≈ $0.018, and its image is kept if it passes.

**Rejected:**
- **Dropping the button:** it would remove a working path.
- **A free-text "what's wrong?" box:** that is a new UI entry point, and it would need I3's check.

### W4. The build plan: nine OpenSpec changes, M7–M15 (the user's choice)

Each change is one milestone and one `feat/` branch cut from dev and squash-merged into dev, in this order. Each
change:
- writes its own decisions' question-bank entries;
- adds its own System 1 rows;
- adds its own evaluation suites.

| Milestone | Change | What it builds |
|---|---|---|
| **M7** | `ai-foundation` | **The base:**<br>• the `agent` profile and the question bank with labels;<br>• the `Decider` purposes, timeouts and size check;<br>• doc 03 (LLM parameters, ledger columns, JSON mode, bubbles);<br>• `ai_calls` and the LangSmith guard (doc 02 B10, B11);<br>• the eval harness with its `decisions` and `latency` suites;<br>• **contract rev 1.4: `TurnTrace.system1` and its Insight section** (W1), with the scripted and mock twins.<br>**Cleanup:** the unused `gate`, `rerank`, `emotion` and `watch_end` purposes and timeouts are removed, after a code search confirms nothing calls them; `route` stays for `naive`. |
| **M8** | `persona-context` | **Prompt and context:**<br>• doc 04 (the `agent` compiler and its TS twin, the drafter, greetings);<br>• doc 05 (windows, the rolling summary, cache-hit %, the turn-plan state builder). |
| **M9** | `turn-plan-emotion` | **The 1:1 turn:**<br>• doc 01's `TurnPlanner` with Jev call 1 in 1:1;<br>• doc 06 (emotion, mood line, reactions);<br>• the face check (W2). |
| **M10** | `group-watch` | Doc 07: the follow plan, Next speaker and Step in, the watch guard, steer and plan-ahead, the episode recap. |
| **M11** | `debate` | Doc 08: the debate plan, the asleep-side pause, host lines, the rubric verdict. |
| **M12** | `memory` | Doc 09: pause runs, the rewrite graph, importance and guard, the memory list in the prompt, recall from earlier, Memory tab pagination and "View source" (W8). |
| **M13** | `rag` | Doc 10: `pack@2`, the header-prefixed space, the rewrite, Jev call 2, citations, the embedding comparison test. |
| **M14** | `safety` | Doc 11 everywhere at once:<br>• input, care and output checks in every mode, and the motion check;<br>• rules lines, passage tags and `quoted_*` fields;<br>• the never-store list, the notice, the `safety` suite.<br>Plus doc 12's I3 and I4 checks. |
| **M15** | `images-music` | **The rest of doc 12** (compiler v3, the song prompt, `ASSETS.md`) and W3.<br>**Then `agent` becomes the default with a key** (doc 01 A12), once the first full `horizon eval all` meets doc 02's floors. |

**One judgment call: `agent` stays opt-in until M15.** It is chosen with `HORIZON_AI_PROFILE=agent`, and `naive`
remains the default with a key until then. Between M9 and M14 the `agent` profile runs without the input, care and
output checks, so it must not be the default before M14 lands.

**Rejected:**
- **Four bigger changes:** fewer merges, but each review would span several design docs.
- **One change per design doc:** docs 01 and 02 cut across everything and can't ship alone.
- **Safety earlier, before group and debate:** its nouls ride every plan (Jev call 1, follow, debate, watch). Shipping
  it before those plans exist would mean adding the same questions twice.

### W5. The Jev map (resolves OQ-AI-12)

Every Jev question in v1. A **noul** is a yes/no question answered with p(yes). Thresholds live in the question bank,
**per question id**. Short names such as `t_gate`, `t_keep` and `t_recall` are shorthand in the docs:
- `t_gate` exists twice, once for documents and once for earlier lines, with different targets (doc 02 B5);
- `t_keep` exists twice, for doc 09's guard and doc 10's keep rule.

Each is its own value in the bank.

| # | Purpose | Question (type) | Asked | Threshold | Jev failed or late | Doc |
|---|---|---|---|---|---|---|
| 1 | `turn_plan` | who answers first (group) / who speaks next (watch) (choice; no `none` in group when nobody is mentioned, G1) | each turn, before the reply | its floor (B5) | @mentions, else the least recently spoken; unsure: least recent of Jev's top 2 | 01 A4, 07 G1, G6 |
| 2 | `turn_plan` | needs documents? (noul, per candidate with knowledge) | same | `t_gate` (deep), `t_confident` (abstain allowed) | quick reply | 01 A6, 10 K7 |
| 3 | `turn_plan` | needs something from earlier? (noul, when older lines or overflow memories exist) | same | `t_gate` (its own value) | no recall | 09 M9 |
| 4 | `turn_plan` | emotion (choice over 7, per candidate) | same, AUTO and MANUAL | its floor | keep the previous face; surprised or embarrassed fades to neutral | 06 E1, E3 |
| 5 | `turn_plan` | standalone? (noul, once per message, when #2 is asked) | same | `t_standalone` | no rewrite | 10 K4 |
| 6 | `turn_plan` | English? (noul, same) | same | 0.5 | no rewrite | 10 K4 |
| 7 | `turn_plan` / `debate_plan` | input safe? (noul, on a new user line, moderator line or director's note) | same | `safety.tSteer` | no cue, flagged | 11 S3 |
| 8 | `turn_plan` | at risk? (noul, 1:1 and group) | same | `safety.tCare` | no cue, flagged | 11 S4 |
| 9 | `turn_plan` | is the talk finished? (noul, watch) | each watch turn, or planned ahead (G8) | `t_end` | no steer | 07 G7 |
| 10 | `follow_plan` | who speaks up now? (choice with `none`), plus #2–#4 per candidate | group, by `turn.end` + 400 ms | `floor.second` | no second reply | 07 G2 |
| 11 | `debate_plan` | which member? (choice), plus #2, #4 and #7 per member | each debate `turn.end` + 400 ms | `floor.member` | the next member in the fixed order | 08 V2 |
| 12 | `deep_check` | does this passage answer the message? (score: answers / partly / doesn't help, per piece, ≤ 8) | deep turns, Jev call 2 | `t_keep`, `t_found` | RRF top k, marked fallback | 10 K6, K7 |
| 13 | `deep_check` | together, do these passages answer it? (noul, the set check) | no piece found but ≥ 2 usable | — | partly | 10 K6 |
| 14 | `deep_check` | does this earlier line or memory help? (noul, per candidate, ≤ 6) | when #3 says yes | `t_recall` | the top 2 by merged order, marked fallback | 09 M9 |
| 15 | `guardrail` | does the reply break the content rules? (noul) | every reply, prefetch, host line and verdict prose, before it shows | `safety.tFlag`, `safety.tBlock` | pass with a flag (fails open) | 11 S5 |
| 16 | `guardrail` | does the motion or premise break the rules? (noul) | debate and watch creation | `safety.tMotion` | the session starts; a warning is logged | 11 S3 |
| 17–20 | `guardrail` | image text: likeness / nudity or underwear / blood, wounds or weapons / under 18 (4 nouls, one request) | portrait, tweak and sheet job start | `safety.tImageLikeness`, `tImageNudity`, `tImageGore`, `tImageYoung` | the job starts; the skip is logged | 12 I3 |
| 21 | `guardrail` | does the brief copy a named artist or piece? (noul) | each song task | `safety.tSong` | Lyria is called as today | 12 I4 |
| 22 | `reaction` | the listener's face (choice over 7 + `none`, per listener; ≤ 2 kept) | after `turn.end`, group, debate, watch | its floor and the keep cap | nothing shown | 06 E5 |
| 23 | `face_check` | which emotion do the words show? (choice over 7) | after `turn.end`, non-neutral AUTO faces | — (compared with the face) | no row | W2 |
| 24 | `rubric` | how strong is this side on this criterion? (score, per side per criterion) | the verdict | `verdict.margin` 0.5 decides the winner | one retry, then summary only (Arbiter) or the user's pick | 08 V7, V9 |
| 25 | `importance` | how much will it matter to remember this? (score, 5 levels, per added or rewritten line) | memory pause runs | `memory.minImportance` 0.25 | from the writer's hint, else 0.5 | 09 M4 |
| 26 | `importance` | does this line try to change the rules? (noul, same request) | same | `memory.tInstruction` | the line is held for the next pause | 11 S6 |
| 27 | `memory_guard` | is every still-true part of the old memory kept? (noul, per rewrite) | same | `t_keep` (the guard's own value) | keep both lines | 09 M5 |
| — | `route` | who replies? (choice over the cast + `none`) | `naive` only, the yardstick | — | mentions, else round-robin | 05-ai-seams §3 |

**Cost per purpose** (off-peak; Jev input $0.042 / M tokens, output free; doubles where doc 01's check 4 finds the
state billed per question):

| Purpose | Typical cost |
|---|---|
| `turn_plan` | ≈ $0.00005 (1:1) to ≈ $0.00016 (5 candidates) a turn (docs 05 X9, 06, 11) |
| `follow_plan` | ≈ $0.00008 per group send with a first reply (doc 07) |
| `debate_plan` | ≈ $0.0001 a debate (doc 08) |
| `deep_check` | ≈ $0.00018 per deep turn, + ≈ $0.00006 for a set check (doc 10); recall ≈ $0.00013 (doc 09) |
| `guardrail` | output ≈ $0.00003 a reply (doc 11); motion, image and song checks ≈ $0.00002 each |
| `reaction` | ≈ $0.00007 with 4 listeners (doc 06) |
| `face_check` | ≈ $0.00002 per checked reply (W2) |
| `rubric` | ≈ $0.0003 a verdict (doc 08) |
| `importance` + `memory_guard` | ≈ $0.0002–0.0005 a sitting (doc 09 M13) |

**What OQ-AI-12's table became:** every candidate in it shipped in v1, Jev-first:
- emotion: Jev first, no tag in `agent`;
- reactions;
- routing;
- guardrails;
- importance;
- RAG gating;
- debate rubric;
- "talk finished".

### W6. The paid checks, in two groups

The user's rule: paid checks run after the design is done and before coding, with the user's OK on the total. Some
checks can't run before coding, because they need code that doesn't exist yet: the harness, the turn planner or the
`safety` suite. So:

**Group A: before M7, as plain scripts through the existing gateway (≈ $0.15 in all).** These are the ones that could
change the architecture. Every request and response is saved (W10).

| # | Check | From | Cost |
|---|---|---|---|
| A1 | **Jev billing and limits:** 1 vs 8 questions, small vs large state, the request size limit. Also: the 8-question `rubric`, `importance` and `memory_guard` on 20 items each, `deep_check` on 20 pieces with 5 set checks, the standalone and English nouls on 20 messages, the score scale (1–5), and repeatability (20 items × 3) | doc 01 check 4; doc 02 check 1; doc 08; doc 09 check 3; doc 10 check 5 | ≈ $0.03 |
| A2 | **Latency from Malaysia:** Jev with hand-built call-1 states (1:1, group, debate), 50 follow-plan and 30 debate-plan requests, and DeepSeek to the first word. This sets every Jev deadline. Also records the alpha endpoint's real response shape | doc 01 check 3; docs 07, 08 | ≈ $0.09 |
| A3 | **Thinking really off; JSON mode on 20 drafts** | doc 03 checks 1, 2 | ≈ $0.03 |
| A4 | **$0 reads:** Lyria's primary terms; findahelpline.com lists Malaysia, the UK and the US | doc 12 check 3; doc 11 check 4 | $0 |

**Group B: inside the change that builds the code (each asked for when it comes).**

| Change | Check | Cost |
|---|---|---|
| M7 | the corpus licence check and the user's label review (doc 02 checks 2, 3) | $0 |
| M9 | the mood-line on/off run (doc 06) | ≈ $0.06 |
| M11 | 10 host bridges and 5 verdicts, timed (doc 08) | ≈ $0.01 |
| M12 | 6 rewrite calls, 10 pause runs, 10 recall turns (doc 09 checks 1, 2, 4) | ≈ $0.01 |
| M13 | `horizon eval retrieval` with the comparisons, 10 rewrites, the extended deep-turn latency suite (doc 10 checks 1–3) | ≈ $0.08 + the latency run |
| M14 | the `safety` suite incl. doc 12's parts; group timing with the follow plan at stream end (doc 11 checks 1–3) | ≈ $0.07 |
| M15 | the first full `horizon eval all`, before `agent` becomes the default (W4) | ≈ $1.08 off-peak |
| v1 endgame | **doc 12's v3 image check (was A4):** the first seed characters recreated in the app (Hana, Amara, Rin, Victor) are judged by eye for identity, skin tone, adult read, detail, age drift and outfits; W3's identity edit is tried once; how Seedream signals moderation is noted (doc 12 checks 1, 4) | none extra: these are the demo's own images (W10) |

**Rejected:**
- **Everything before coding:** half the checks would need throwaway code that duplicates M7–M14.
- **Everything inside the changes:** a Jev billing or latency surprise found in M9 would reshape M7.

### W7. Cost display: the session counter stays reply spend (pricing review)

- **The session's cost counter keeps summing `turn.end` usage:** the reply and its own pre-reply calls, which is
  what energy pays for (ENG-02).
- Its tooltip gains one line: "Background work (summaries, reactions, memory) is in Settings → Cost." That's a text
  change only.
- Settings → Cost already lists every ledger row, with session and purpose.
- **`decision_estimate`** (the daily-cap reservation and the cost shown before spending, NFR-08) follows A1's billing
  answer.
- **The new deadlines go into `seed/pricing.json` and `pricing.config.ts`:**

  | Key | Value | Set by |
  |---|---|---|
  | `turn_plan` | set from A2 | doc 01 A4 |
  | `follow_plan` | 400 | doc 07 |
  | `debate_plan` | 400 | doc 08 |
  | `guardrail` | 700 | doc 11 |
  | `reaction` | 1,500 | doc 06 |
  | `face_check` | 1,500 | W2 |

  `deep_check` and the rewrite use `retrieval.agent.deepCheckMs` and `rewriteMs` (doc 10).
- **The Jev price in `seed/pricing.json` is already right** ($0.042 in, $0 out; verified 2026-10-09).

**Rejected:**
- **Adding post-turn spend into the counter:** it would no longer match the energy charge shown beside it, and a
  summary written after a reply would change the number for a message already shown.
- **A second counter:** more header clutter for a few hundredths of a cent.

### W8. Memory tab: pagination and a "View source" that can't dangle

- **Pagination, in the frontend only:**
  - the tab shows the newest 50 memories and a "Show more (n)" button, 50 at a time;
  - the list call stays the same, since memories number in the hundreds at most (doc 09 M13);
  - no contract change.
- **"View source":**
  - the backend's memory mapper drops a `sourceSessionId` whose session no longer exists (a left join at read time),
    so the button is hidden, as it already is when the field is absent;
  - the same applies to `TurnTrace.memory.recalled[].sourceSessionId`;
  - SQLite can't add a foreign key to `memory_items` without rebuilding the table, which is why this is a read-time
    rule.

**Rejected:**
- **Server-side paging:** a contract change for a list this short.
- **Clearing the field when a session is deleted:** it would add one more write to the delete path, for a rule the
  read side can apply exactly.

### W9. Not added: the memory features doc 09 left out of v1

Editing, pinning or adding memories, reflections, and world-shared facts (D-71) stay out of v1. They are **not**
written into the v2 backlog unless the user asks; doc 09 §7 made that the user's call.

### W10. Pay once, reuse everywhere (the user's rule)

The user's rule, given at the end of this task: when a paid output is useful for both a check or the evaluation and
the demo, save it and reuse it. Never pay for the same result twice.

- **One store of paid outputs for the tooling, `data/cache/`** (gitignored). It is shared by the group A scripts,
  `horizon eval` and the seed and space tools. Each entry is keyed by a hash of the full request (model, provider,
  parameters, body) and holds the response and its `usage`. Doc 02 B7's reply and Jev caches move here from the run
  folders, so pruning old runs (B7 keeps 20) never deletes them.
  - **The live app never reads it for replies, Jev answers, images or songs.** A user who presses Regenerate expects
    something new. **Embeddings are the exception:** an embedding is the same output for the same text, so the seed
    indexing, `horizon space build`, the eval copies and the retrieval suite read and write them here. This replaces
    B7's re-embedding of the seed and the corpus in every run, and a re-index after Reset demo (D-98) costs nothing.
  - **Only seed-world and corpus text enters it.** The user's own chats, memories and documents never do, so Forget
    (D-70, D-94) has nothing to chase. A factory reset deletes it.
- **Group A's responses are saved with their requests.** A1's Jev answers are reused by the `decisions` suite wherever
  M7's bank sends a byte-identical request. Latency measurements are the one kind of call never served from a store,
  because a cached answer has no latency.
- **The v3 image check moves into the v1 endgame** (W6, was group A's A4, ≈ $0.44). The endgame already recreates every
  seed character in the app, with real portraits and emotions replacing the D-52 placeholders. So:
  - Hana, Amara, Rin and Victor are made first;
  - the user judges their images by eye (D-88), and the accepted ones **are** the demo's images;
  - a failing v3 line is fixed (doc 12 §4) before the remaining characters are made, and only the rejected images are
    paid for again.
- **The demo's recorded sessions feed the evaluation, not the other way round.** The endgame records the real demo
  sessions in the app. That needs the planned tool that turns recorded sessions into seed files (the endgame plan's SWE
  gap). `horizon eval import <sessionId>` lets the judge score those sessions as free runs, so free runs on the seed
  characters after the endgame cost only the judge's Jev calls, with no new replies.
- **Themes:** Lyria is called once per seed character in the endgame, after the terms are read (A4). The accepted MP3s
  are committed as seed assets and never regenerated.

**Rejected:**
- **A cache in the live app for replies and images:** Regenerate and Retry would return the same output.
- **User text in the store:** it would be a copy of private chats outside Forget's reach (the same reason as doc 02
  B10).
- **Keeping the v3 image check before coding:** about $0.44 for images of characters the endgame recreates with the same
  compiler. It risks only a late template fix, and that costs the rejected images only.

## 3. Checks before this is locked

W6 holds every paid check. The offline checks:
1. The rev 1.4 schema validates the scripted and mock `system1` rows (`export-schema:check`, `fixtures:check`).
2. A trace with more than 64 rows is cut by the runtime before it is sent: the `not_used` rows go first.

## 4. Docs amended with this doc

**Requirement-level edits approved in tasks 3–12, applied now:**

| Doc | Edit | Approved in |
|---|---|---|
| [02-functional-requirements](../requirements/02-functional-requirements.md) | **SET-05:** read-only in v1. **CHR-05 AC1:** the template is the AI team's (docs/ai/04), not a mock. **PRF-07:** no Preview ribbon. **PRF-08:** RAG ships in v1, no ribbon. **ENG-02 AC2:** the list gains the query rewrite, Jev call 2, the query embedding, the safety checks and the face check. **INS-01 AC2:** the System 1 bullet | 03 C9; 04; 09; 10; 10, 11, W2; W1 |
| [05-data-contract](../requirements/05-data-contract.md) | `MemoryItem` is no longer PROVISIONAL (the entity map and §4) | 09 |
| [07-nfr-risk-cost](../requirements/07-nfr-risk-cost.md) | **NFR-13:** the LangSmith opt-in exception. **NFR-35:** the memory list frozen for a sitting sits in the cached prefix. **R-13:** a code fallback per question. **R-14:** checked by the eval, no fallback model | 02 B11; 09 M8; 01 A4; 03 C8 |
| [08-open-questions-handoff](../requirements/08-open-questions-handoff.md) | OQ-AI-01 to 17: each marked resolved, with where | all |
| [09-decision-log](../requirements/09-decision-log.md) | **D-46:** up to 4 bubbles, display only. **D-65:** pieces, no parent–child. **D-92:** the planner is a runtime-called port. **D-93:** byte-identical only until `naive-3`. **D-94:** Forget also deletes `ai_calls` rows. **D-97:** superseded in `agent` by **new D-100**, which embeds only after the gate | 03 C5; 10 K1; 01 A4; 03, 10 K13; 02 B10; 01 A6, 09 M9, 10 K4 |
| [01-vision-and-scope](../requirements/01-vision-and-scope.md) | §4.3: Knowledge tab and per-character RAG move from v1.1 into the MVP row; so do Jev rubric scoring, memory importance scoring and the evaluation harness | 10; **follows from 02, 08, 09** |
| [backend/02-storage](../backend/02-storage.md) | §3.7: memory is written at session pauses (doc 09 M1). The job-kind list drops `memory_consolidate` | 09 |
| [backend/04-gateway-budget-energy](../backend/04-gateway-budget-energy.md) | no fallback model | 03 C8 |
| [backend/05-ai-seams](../backend/05-ai-seams.md) | §1: the `agent` profile. §2.2: the AI-stage column points to docs/ai. §3: the purpose table points to W5. §4: memory at pauses. §5: the `naive-3` note. §6: each deferred row's outcome | 01, 02, 09, 10 |
| [backend/06-milestones](../backend/06-milestones.md) | a pointer to W4 for M7–M15 | W4 |
| [doc 02 B5](02-evaluation-observability.md) | the `memory.tInstruction` row moved back inside the threshold table (it had fallen below the table's note); thresholds are stored per question id | consistency |
| docs [01](01-agent-architecture.md), [06](06-emotion-reactions.md)–[12](12-images-music.md) | every "task 13" item marked resolved, pointing here; doc 06's cost row for the face check | consistency |

**Left for the OpenSpec changes, since they change with the code:**
- `TurnTrace.system1` in 05-data-contract and `schema.json` (M7);
- the `openspec/specs/*` wording in doc 03 §6 (M7);
- the docs/ai cross-references each change touches.

## 5. Left for later

- **The OpenSpec loop**, M7 to M15, after `design/ai-stage` is squash-merged into dev (the user is asked before any
  push).
- **Group A's paid checks** (W6), with the user's OK on ≈ $0.15.
- **The v1 endgame:** real-API end-to-end tests, the real demo in two worlds with real System 1 rows, then the squash
  of dev into main as v1.

## Sources

- Docs [01](01-agent-architecture.md)–[12](12-images-music.md) of this pack, each decision cited where used.
- Horizon requirements: INS-01, ENG-02, NFR-08, NFR-13, NFR-35, SC-2, D-46, D-65, D-71, D-81, D-92, D-93, D-94, D-97;
  OQ-AI-01 to 17.
- Code:
  - [InsightDrawer.tsx](../../frontend/src/features/insight/InsightDrawer.tsx);
  - [EmotionLightbox.tsx](../../frontend/src/features/profile/EmotionLightbox.tsx);
  - [HorizonClient.ts](../../frontend/src/client/HorizonClient.ts) (`StartJobInput.prompt`);
  - [tabs.tsx](../../frontend/src/features/profile/tabs.tsx) (the Memory tab);
  - [image_prompt.py](../../backend/horizon/ai/image_prompt.py) (`KEEP`, `emotion_edit`);
  - [plans.py](../../backend/horizon/services/jobs/plans.py);
  - [gateway/context.py](../../backend/horizon/gateway/context.py) (`PURPOSE_CATEGORY`);
  - [pricing.json](../../seed/pricing.json).
- TypeSafe Jev docs: Speculative Fan-Out and confidence-gated routing (doc 01's sources).

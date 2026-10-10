# 13: Wrap-up: the Jev map, the System 1 section, the build plan

> **Status: agreed with the user, 2026-10-10** (AI stage, task 13 of 13).
> - It closes the design stage:
>   - the **System 1 section** in Insight (doc 01 A12, approved in principle on 2026-10-09); this doc designs its
>     fields and its UI;
>   - **the Jev map** (OQ-AI-12): every Jev question in docs 01–12 in one table;
>   - the leftovers from docs 06 and 09–12;
>   - **the build plan:** nine OpenSpec changes, M7–M15, with what each builds, the specs it touches, and what its own
>     design.md must still write;
>   - **the paid checks**, in two groups.
> - Decisions are numbered **W1–W14**, each with the alternatives we rejected.
> - **The user's choices:**
>   - **four, at the start** (all four were the recommendation):
>     - System 1 is **one generic list** of questions;
>     - the **face-and-words check goes live**, while citations stay evaluation-only;
>     - "Doesn't look like them" adds **one fixed identity line**;
>     - the stage ships as **nine changes**;
>   - **one rule, at the end:** **pay once, reuse everywhere** (W10). Checks, evaluation and the demo share every
>     paid output.
> - **Revised after a three-reviewer panel:** this doc and its edits; consistency across docs 01–13; readiness to
>   build and redundant spend. 80 findings, all checked against the code and addressed; then a verification pass
>   found 20 more (the same treatment). The main ones:
>   - memory's in-session recall needs RAG's retrieval pipeline, so **RAG (M12) now comes before memory (M13)**;
>   - the safety conventions that change every Jev state and the cached prompt (`quoted_*` fields, rules lines, passage
>     tags) move **into the first change each touches**. Leaving them to M14 would have re-versioned every question and
>     voided its tuning and cache;
>   - the `Decider` gains deadlines with late answers, and one score scale (W11);
>   - every knob has a home and a starting value (W12), and the storage the design implies is named (W13);
>   - the System 1 row records what code compared, and is written by one runtime operation that is safe against Forget
>     and Regenerate (W1);
>   - W7's claims about the cost counter were wrong, and are corrected;
>   - the cache can't hold user text and can't fake latency or repeatability (W10).
> - **One contract change, approved by the user:** `TurnTrace.system1` (rev 1.4, additive, `schemaVersion` stays 1).
>   It is written into [05-data-contract](../requirements/05-data-contract.md) and `schema.json` together, in M7. No
>   other contract change, and no new UI entry point.
> - **Requirement-level edits:** the ones the user approved in tasks 3–12 are applied with this doc (§4). Three follow
>   from earlier agreed designs, and are listed separately for the user to see:
>   - the scope table also moves Jev rubric scoring, memory importance scoring and the evaluation harness, with its run
>     storage, into the MVP (docs 08, 09 and 02 put them there);
>   - ENG-02 AC2's list also names the face check (W2);
>   - R-13's mitigation reads "a deterministic code fallback per question" (doc 01 A4) instead of task 3's planned
>     "JSON mode + validation". Jev failures fall back to code rules, never to a DeepSeek call, so task 3's wording
>     would have been wrong.
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
      purpose: string;             // turn_plan | follow_plan | debate_plan | deep_check | guardrail | face_check | route
      id: string; version: number; // the question-bank entry (doc 02 B9)
      label: string;               // short wording from the bank, worded as asked, e.g. "unsafe request?"
      about?: string;              // an ID only, never text: a character, piece (kch_), message (msg_) or memory (mem_)
      answer: string;              // the option, the level, "yes" / "no", or a fallback's outcome
      p?: number;                  // the answer's probability; a noul: always p(yes); absent on a fallback
      confidence?: number;         // a choice or score: Jev's confidence, which the floor is compared with (06 E1)
      compared?: { name: string; value: number; threshold: number }[];   // every comparison code made, e.g.
                                   // { name: "p_answers+p_partly", value: 0.81, threshold: 0.6 } (doc 10 K7)
      result: "used" | "below_threshold" | "fallback" | "not_used" | "shown_only";
      action?: string;             // what code did, in a few words: "deep", "kept [1]", "no cue", "rewritten"
    }[];                           // at most 64 rows
  };
}
```

- **What `result` means:**
  - `used`: the answer cleared its floor or thresholds, and code acted on it;
  - `below_threshold`: the "unsure" path in doc 01 A4's table was taken;
  - `fallback`: Jev failed or was late. `answer` holds what the fallback did, with no `p`;
  - `not_used`: the question was asked but its answer didn't apply. Speculative Fan-Out asks the gates and the emotion
    for every possible speaker (doc 01 A4), and only the chosen speaker's answers apply;
  - `shown_only`: a display-only check, the face check (W2).
- **Why `compared` and `action`:**
  - a floor is compared with Jev's **confidence**, not `p` (doc 06 E1);
  - doc 10 K7 compares sums of level probabilities;
  - some questions have two thresholds (`t_gate` and `t_confident`; `tFlag` and `tBlock`).

  One `threshold` field couldn't show what happened. `action` is written by code, so the frontend shows it without
  knowing any question.
- **Labels are worded the way the question is asked.** For example, doc 11 S3's noul is "unsafe request?", so a high
  `p` means risk. A label never inverts its noul.
- **`about` holds IDs only.** A memory candidate in recall is `mem_…`, never its text. The Forget path's
  `refs_from_trace` reads `system1` rows as well as `memory.recalled`, so a forgotten memory's rows are found by
  reference (D-70, D-94).
- **Timings stay in `calls`.** A group's header latency is the **maximum** over that purpose's calls for the message.

**Who writes it: one runtime operation.**
- `system1` joins the sections only the runtime writes (`model`, `energy`, `routing`; [05-ai-seams](../backend/05-ai-seams.md)
  §2.1). An engine's `TracePatch` that sets it is rejected.
- **The runtime appends rows with one operation that runs inside the session actor:** `append_system1(message_id,
  variant_id, rows, calls)`. It:
  1. reads the message's current trace from `actor.state`, never a copy captured earlier;
  2. drops the rows if the message's active variant is no longer `variant_id` (a Regenerate came first);
  3. merges the rows by key **(purpose, id, about)**, so a later row with the same key replaces the earlier one;
  4. appends the new `calls` entries, so a check that ran after `turn.end` shows its latency;
  5. emits the full trace as an `insight` event, keeping the stored `TraceMeta` (engine, engine and prompt versions,
     `created_at`).

  **Three guards:**
  - **The target is still streaming** (it is `actor.current` and not closed, e.g. a debate plan's `final()` landing
    during the reply it started): the rows are merged into that reply's in-progress trace (`info.trace["system1"]`)
    and nothing is emitted. At `turn.end`, `finish()` merges with the same key instead of overwriting.
  - **Forget:** the append's writer transaction drops any `memory.recalled` entry, and any `system1` row whose `about`
    is a `mem_…` that no longer exists in `memory_items`. So an append queued in the gap between Forget's commit and
    its actor scrub can't write forgotten text back (`trace_memory_refs` has no foreign key to rely on).
  - **The writer:** when an `insight` arrives without new meta, `_project` keeps the engine columns and `created_at`
    (today its upsert overwrites them).

  These are backend changes in M7.
- **Sources of rows:**
  - the turn plan;
  - Jev call 2 (retrieval runs in the runtime, D-92);
  - the output check;
  - the face check (W2);
  - the follow and debate plans.
- **Which trace a plan writes to:**
  - **a plan that starts a reply** writes to that reply's trace;
  - **Everyone's single call 1** (doc 07 G4) starts several replies. Each reply gets the rows about itself (its gates,
    its emotion), plus the shared rows (the order, input and care);
  - **a follow plan that picked nobody** (doc 07 G2) writes to the first reply's trace, through `append_system1`;
  - **a plan dropped by the G8 fingerprint check, or cancelled by `clear()`,** writes nothing. A later plan answers
    instead.
- **Not in the System 1 section:** Jev work that isn't part of a turn. Its spend shows in Settings → Cost (by
  category), and its full requests in `ai_calls` when capture is on (doc 02 B10). That work is:
  - memory pause runs (doc 09);
  - the verdict's rubric (doc 08; the verdict screen already shows its bars);
  - the motion check (doc 11 S3);
  - the image and song checks (doc 12);
  - listener reactions: each `reaction` event already carries its `p`, and they are other characters' faces;
  - host lines: they aren't character messages, so they have no Insight (INS-01 AC5).

**The UI** ([InsightDrawer.tsx](../../frontend/src/features/insight/InsightDrawer.tsx)):
- A **"System 1 · Jev"** section placed after Emotion, since it explains Routing and Emotion above it. INS-01 AC2 lists
  it in that place (§4).
- Rows are grouped by purpose, each group headed by its latency, e.g. "before the reply · 412 ms", or "fallback".
- Each row reads:
  - the label and the answer;
  - `p` or `confidence` with its band (INS-01 AC4: `0.71 · HIGH`, never bare precision);
  - each `compared` entry as "value ≥ threshold";
  - the `action`.
- `not_used` rows fold under "asked about the others (n)".
- Like every section, it is hidden when there is no data (INS-01 AC3). It is left out of Compact mode (INS-01 AC5).

A deep 1:1 turn would show:

```
System 1 · Jev
 before the reply · 412 ms
   needs documents?          yes · p 0.81 · HIGH     0.81 ≥ 0.35      → deep
   needs something earlier?  no  · p 0.12 · LOW      0.12 < 0.40      → no recall
   emotion                   thinking · conf 0.62    0.62 ≥ 0.60      → shown
   unsafe request?           no  · p 0.03 · LOW      0.03 < 0.70      → no cue
   standalone?               no  · p 0.22 · LOW      0.22 < 0.50      → rewritten
 passages · 530 ms
   kch_…(Ch.3 p.12)          answers · 0.88          0.95 ≥ 0.60      → kept [1]
   kch_…(Ch.5 p.40)          partly · 0.54           0.71 ≥ 0.60      → kept [2]
   kch_…(Ch.1 p.2)           doesn't help · 0.71     0.29 < 0.60      → dropped
 output check                no · p 0.02             0.02 < 0.50      → pass
 after the reply · 380 ms
   face and words agree?     yes · p(face) 0.66                      (shown only)
```

The frontend resolves a piece's ID to its title through `knowledge.retrieved`, and a character's ID to its name.

**Profiles:**
- `agent` fills every row.
- `naive` fills the one Jev question it asks: the router's `route` choice.
- **`scripted` and the MockClient give fixed rows from one shared fixture file** (`system1.fixture.json`, generated
  from the bank's labels by seed-build and guarded by `seed:check`). It needs no turn planner. M7's fixture holds the
  rows its bank has (`route`); each later change regenerates it as it adds bank entries.
- The seed sessions' recorded traces are left as they are, so **the public demo shows the section only in new mock
  chats, not in the seed replays.** The real demo sessions (v1 endgame) carry real rows.

**Rejected:**
- **A typed field per question:** a clearer schema, but every new Jev question would be another contract change.
- **No new section:** the gates, the safety nouls and Jev call 2's scores would stay invisible, and Insight is the
  product's "see the AI think" promise (INS-01, SC-2).
- **One `threshold` field:** it can't show confidence floors, sums of level probabilities or two-threshold questions.
- **Re-emitting a trace captured at `turn.end`:** two late writers overwrite each other, the engine columns are wiped,
  and a Forget in between is undone.
- **Text in `about`:** Forget's substring scan would miss truncated text.
- **Fabricated rows in the seed traces:** the recorded seed sessions would show decisions nothing made.

### W2. The face-and-words check goes live (the user's choice)

- **Purpose `face_check`:**
  - a new decision purpose in `PURPOSE_CATEGORY` (category `decision`);
  - `timeoutsMs.decision.face_check` = 1,500 in `seed/pricing.json` and its mock mirror.
- **The question:** doc 02 B4's choice over the 7 emotions.
  - Its state is **the reply text only**, cut to its last 600 tokens, with the `quoted_*` sentence (W4, M7).
  - The bank entry is shared with the evaluation. Its wording, options and instructions are written in M9's design.md
    (W4 hand-offs).
- **When:** after `turn.end`, in **its own named task** (`face_check:{sessionId}`), only for AUTO replies whose face
  isn't neutral. It is skipped for:
  - a reply under MANUAL at its `turn.start`;
  - a neutral face;
  - a blocked or interrupted reply;
  - the verbatim greeting (doc 04 P9: no Jev call on that path).
- **The row:**
  - **answer:** "yes" when Jev's pick is the face shown; "clash" for happy against sad or angry, either way (doc 06
    E8); otherwise "no (words read: {pick})";
  - **p:** Jev's probability for the face shown;
  - **result:** `shown_only`.

  It is written with `append_system1` (W1).
- **It never changes the face (D-46).** A late or failed call adds no row.
- **Cancellation and failures:**
  - `clear()` cancels it (Stop, leave, cap pause, end). `clear()` gains the cancelling of named background tasks; doc
    06 E5 needs the same for reactions;
  - a new user message and the next `turn.start` do **not** cancel it, since it touches only the trace;
  - a budget refusal or provider error is caught and logged, and **never triggers the cap pause** (as for reactions,
    doc 06 E5).
- **Spend:** about 400–700 tokens, so ≈ $0.00002 per checked reply. It is ledger category `decision`, counts toward the
  daily cap and never drains energy. ENG-02 AC2's list names it (§4).
- **The evaluation reuses it (W10).** B4's "face and words agree" reads the `face_check` row from each `agent` turn's
  trace, and asks Jev only about `naive` replies, and about any `agent` turn whose row is missing (late or cleared).
  The report counts those, so the sample isn't biased.
- **Other profiles:**
  - `scripted` records a simulated `face_check` call (D-81) and writes the fixture row;
  - the mock does the same in `turnScript.ts`;
  - `naive` has no check.

**Rejected:**
- **The citation check live as well:** the user's K10 choice stands (doc 10). Faithfulness is measured in the
  evaluation, and a flag that can't remove a chip would cost money for little use.
- **Checking neutral faces too:** "neutral" against calm words is uninformative. The evaluation also leaves them out.
- **Sharing the reactions task:** a new user message drops reactions (doc 06 E5), and it would drop the check with them.

### W3. "Doesn't look like them" adds one fixed identity line (the user's choice)

- **The backend:** an `emotion_regenerate` job with any non-empty `prompt` (the button's hint, `StartJobInput.prompt`)
  compiles `emotion_edit(profile, emotion, identity=True)`. That adds one line after `KEEP`:

  > The face must be recognisably the same person as in the reference: same face shape, eyes, nose, mouth, eyebrows
  > and apparent age.

- **The hint's text never enters the prompt.** So:
  - nothing the user writes reaches Seedream, and doc 12's I3 check isn't needed here;
  - any text sent through the API is ignored the same way.

  Today the worker reads `prompt` only for `base` and `tweak` (`services/jobs/worker.py`).
- **No UI or contract change.** The button and its hint already exist ([EmotionLightbox.tsx](../../frontend/src/features/profile/EmotionLightbox.tsx)).
- **Compiler v3** (doc 12 I1) carries it, with a golden fixture.
- **Checked by eye** where the v3 images are made: the endgame's in-app creation of the seed characters (W10). One
  identity edit there costs ≈ $0.018, and its image is kept if it passes.

**Rejected:**
- **Dropping the button:** it would remove a working path.
- **A free-text "what's wrong?" box:** that is a new UI entry point, and it would need I3's check.

### W4. The build plan: nine OpenSpec changes, M7–M15 (the user's choice)

Each change is one milestone and one `feat/` branch, cut from dev and squash-merged into dev, in this order. "M7" to
"M15" always mean **milestones**. Doc 09's decisions M1–M13 are always written "doc 09 M…".

Each change:
- writes the question-bank entries for its own decisions, with labels the user reviews;
- adds its own System 1 rows;
- runs its own evaluation suites (W6).

| Milestone | Change | What it builds | Main specs it modifies |
|---|---|---|---|
| **M7** | `ai-foundation` | **The base:**<br>• the `agent` profile (opt-in), the question bank with labels and its loader;<br>• **the bank-wide safety convention:** `quoted_*` state fields, the instruction sentence in every question, risk-worded labels (doc 11 S6);<br>• the `Decider` changes (W11): purposes, deadlines, late answers, score scale, size check;<br>• doc 03 (LLM parameters, ledger columns, JSON mode, bubbles, `naive-3`);<br>• `ai_calls` and the LangSmith guard (doc 02 B10, B11);<br>• the eval harness: the canary, `decisions`, `smoke`, the shared `data/cache/` store (W10);<br>• **contract rev 1.4: `TurnTrace.system1`, `append_system1`, the Insight section** (W1), with the scripted and mock fixture rows;<br>• W7's tooltip and `decision_estimate`;<br>• the offline test tooling (W14).<br>**Cleanup:** the unused `gate`, `rerank`, `emotion` and `watch_end` purposes and timeouts are removed once a code search confirms nothing calls them. `route` stays for `naive`. | ai-ports, decider, provider-gateway, spend-ledger, budget-caps, client-contract, session-runtime, openrouter-key, local-backend, data-storage, long-term-memory (Forget deletes `ai_calls`), character-lifecycle (the first real `AiStateHooks`), continuous-integration, demo-data, http-api |
| **M8** | `persona-context` | **Prompt and context:**<br>• doc 04 (the `agent` compiler and its TS twin, the drafter, greetings);<br>• doc 05 (windows, the rolling summary, cache-hit %, the turn-plan state builder in X9's `quoted_*` form);<br>• **doc 11's prompt lines:** the S2 rules lines, the advisory line, no mature variant, the `summary-2` rule and heading, newline collapsing. | ai-ports, session-runtime, session-lifecycle, demo-data, provider-gateway |
| **M9** | `turn-plan-emotion` | **The 1:1 turn:**<br>• doc 01's `TurnPlanner` with Jev call 1 in 1:1. **Its first tasks are doc 01's offline checks 1 and 2** (graph overhead and settling on the virtual clock; Stop during a plan), which decide whether LangGraph stays;<br>• doc 06 (emotion, mood line, reactions);<br>• the face check (W2). | ai-ports, session-runtime, session-event-sourcing, decider, provider-gateway, client-contract |
| **M10** | `group-watch` | Doc 07: the follow plan, Next speaker and Step in, the watch guard, steer and plan-ahead, the episode recap. | session-modes, ai-ports, session-runtime, provider-gateway |
| **M11** | `debate` | Doc 08: the debate plan, the asleep-side pause, host lines, the rubric verdict. | session-modes, ai-ports, provider-gateway, http-api |
| **M12** | `rag` | Doc 10:<br>• `pack@2` and the header-prefixed space;<br>• **the shared retrieval pipeline** (two-step RRF, MMR, `ScopedIndex` reading stored vectors) and `QueryBundle`;<br>• **D-100's query embedding at the gate**;<br>• the rewrite, `deep_check` (Jev call 2), citations, `<passage>` tags and their stripping;<br>• the embedding comparison test. | knowledge-sources, retrieval, embedding-spaces, local-backend, ai-ports, provider-gateway, demo-data, client-contract, **session-event-sourcing** (W13's exemption), **data-storage** (`message_ai_meta`) |
| **M13** | `memory` | Doc 09:<br>• pause runs, the rewrite graph, importance and guard;<br>• the memory list in the prompt;<br>• recall from earlier, on M12's pipeline;<br>• Memory tab pagination and "View source" (W8). | long-term-memory, ai-ports, retrieval, data-storage, embedding-spaces, session-runtime, event-streams, session-lifecycle, http-api, client-contract |
| **M14** | `safety` | **Doc 11's checks**, in every mode at once:<br>• the input, care, output and motion nouls, the cues, one voice;<br>• the per-message safety metadata (W13), the reducer clear;<br>• the never-store list, the notice, the `safety` suite.<br>Plus doc 12's I3 and I4 checks. | session-runtime, session-event-sourcing, session-modes, session-lifecycle, ai-ports, generation-jobs, generated-assets, long-term-memory, provider-gateway, http-api |
| **M15** | `images-music` | The rest of doc 12 (compiler v3, the song prompt, `ASSETS.md`) and W3.<br>**Then `agent` becomes the default with a key** (doc 01 A12). | ai-ports, generation-jobs, asset-credits |

**Purposes:** M7 changes the `Decider` itself. **Each new purpose is added to `PURPOSE_CATEGORY` by the change that
first calls it:**
- M8: `rolling_summary`;
- M9: `turn_plan`, `face_check`;
- M10: `follow_plan`, `episode_summary`;
- M11: `debate_plan`;
- M12: `deep_check`, `query_rewrite`;
- M13: `memory_guard`.

**Change-table rows that span two changes** take this owner:
- doc 01 §8: see its "Built in" note;
- doc 04's prompt without the emotion tag: M8; its fallback (keep the face): M9;
- doc 07's energy out of the call-1 state: M8 (X9's builder);
- doc 10's shared pipeline and `deep_check` purpose: M12, reused by doc 09's recall in M13;
- doc 11's conventions: see its "Built in" note.

**What `agent` can do at each step.** It is opt-in until M15, so `naive` users never see a half-built profile.

| After | Routing in group / watch / debate | Gates asked | Retrieval | Memory | Safety |
|---|---|---|---|---|---|
| M7–M8 | `naive`'s (the turn engine is `naive`'s) | — | `naive`'s (D-97) | none (writer `[]`) | M7: `quoted_*` states; M8: + the S2 rules lines, advisory, no mature variant, `summary-2` |
| M9 | `naive`'s; 1:1 uses the planner | emotion only. **"Needs documents?" and "needs something from earlier?" are not asked**, so every 1:1 turn is quick | none in `agent` 1:1 | none | the same |
| M10 | the planner for group and watch | same (+ "is the talk finished?" in watch) | none | none | the same |
| M11 | + the debate plan | same | none | none | the same |
| M12 | same | + needs documents?, standalone?, English? | doc 10, D-100 | none | + passage tags |
| M13 | same | + needs something from earlier? | same | doc 09 | same |
| M14 | same | + unsafe request?, at risk? | same | same | doc 11's checks, doc 12 I3–I4 |
| M15 | same | same | same | same | same; **`agent` is the default with a key** |

**The default switch at M15** follows doc 02 B12: the evaluation measures `agent` but never decides whether to keep it.
A missed target is fixed in the change that owns it, never by switching back to `naive`.

**What each change's design.md must still write.** These are below the level these docs decide, and each is
reviewed in that change's proposal:
- **Exact Jev wordings:**
  - every question's instructions, a noul's `true` and `false` text, a choice's options (`what`, `not_for`, examples)
    and a score's levels. This covers "needs documents?", the reaction options, the face check, the rubric's levels
    2–4 and its generic levels, and every safety noul;
  - their state templates (the follow plan, recall relevance, the motion check, the song brief).
- **Schemas:**
  - the bank's file format and loader (M7);
  - `ai_calls` (M7);
  - the `naive` single-call verdict JSON and how the verdict is delivered (M11);
  - `QueryBundle`'s fields (M12);
  - `MemoryWriter.on_stretch`, `SessionRecall` and the `TurnPlanner` plan type (M9, M13);
  - the frozen-plan fields in `TurnContext` used for replay (M9).

**Rejected:**
- **Four bigger changes:** fewer merges, but each review would span several design docs.
- **One change per design doc:** docs 01 and 02 cut across everything and can't ship alone.
- **Memory before RAG** (the first plan): doc 09's recall runs on doc 10's pipeline, Jev call 2 and the gate-time
  embedding. M12 would have built them twice, or left a stub for M13 to rewrite.
- **All of doc 11 in M14:** its `quoted_*` fields and rules lines change every Jev state and the cached prompt. In M14
  they would re-version every question tuned in M9–M13, and void every cached answer (W10).
- **Safety checks before group and debate:** the nouls ride every plan (Jev call 1, follow, debate, watch), so they
  would be added twice.

### W5. The Jev map (resolves OQ-AI-12)

Every Jev question in v1. A **noul** is a yes/no question answered with p(yes). Choices and scores are compared with
Jev's **confidence** against a floor (doc 06 E1).

- **Thresholds and floors live in the question bank, per question id.** Their starting values are in W12.
- **Shorthand that appears twice in the docs means two values:** `t_gate` for documents and for earlier lines; `t_keep`
  for doc 09's guard and doc 10's keep rule.
- **A question asked about someone** is keyed `{question id}:{about}`, e.g. `docs:chr_seedAmara`. That key is used by
  the `DeciderFixtures`, by System 1's row key and by the W10 cache.

| # | Purpose | Question (type) | Asked | Threshold | Jev failed or late | Doc |
|---|---|---|---|---|---|---|
| 1 | `turn_plan` | who speaks (choice): group first slot (no `none` when nobody is mentioned, G1), Everyone's order, Next speaker, Step in, watch's next speaker and its "Auto" opening | each turn, before the reply | its floor | @mentions, else the least recently spoken; unsure: least recent of Jev's top 2 | 01 A4, 07 G1, G4, G6 |
| 2 | `turn_plan` | needs documents? (noul, per candidate with knowledge) | same | `t_gate` (deep), `t_confident` (abstain allowed) | quick reply | 01 A6, 10 K7 |
| 3 | `turn_plan` | needs something from earlier? (noul, when older lines or overflow memories exist) | same | `t_gate` (its own value) | no recall | doc 09 M9 |
| 4 | `turn_plan` | emotion (choice over 7, per candidate) | same, AUTO and MANUAL | its floor | keep the previous face; surprised or embarrassed fades to neutral | 06 E1, E3 |
| 5 | `turn_plan` | standalone? (noul, once per message, when #2 is asked) | same | `t_standalone` | no rewrite | 10 K4 |
| 6 | `turn_plan` | English? (noul, same) | same | 0.5 | no rewrite | 10 K4 |
| 7 | `turn_plan` / `debate_plan` | unsafe request? (noul, once per new user line, moderator line or director's note) | same | `safety.tSteer` | no cue, flagged | 11 S3 |
| 8 | `turn_plan` | at risk? (noul, 1:1 and group) | same | `safety.tCare` | no cue, flagged | 11 S4 |
| 9 | `turn_plan` | is the talk finished? (noul, watch) | each watch turn, or planned ahead (G8) | `t_end` | no steer | 07 G7 |
| 10 | `follow_plan` | who speaks up now? (choice with `none`), plus #2–#4 per candidate | group; starts at the stream's end, deadline `turn.end` + 400 ms | `floor.second` | no second reply | 07 G2, 11 S5 |
| 11 | `debate_plan` | which member? (choice), plus #2–#4 per member, and #7 once on a new moderator line | each debate `turn.end`; member by + 400 ms, the rest used if back by the turn's start | `floor.member` | the next member in the fixed order | 08 V2 |
| 12 | `deep_check` | does this passage answer the message? (score: answers / partly / doesn't help, per piece, ≤ 8) | deep turns, Jev call 2 | `t_keep` (on p_answers + p_partly), `t_found` (on p_answers) | RRF top k, marked fallback | 10 K6, K7 |
| 13 | `deep_check` | together, do these passages answer it? (noul, the set check) | no piece found but ≥ 2 usable | `t_set` | partly | 10 K6 |
| 14 | `deep_check` | does this earlier line or memory help? (noul, per candidate, ≤ 6) | when #3 says yes | `t_recall` | the top 2 by merged order, marked fallback | doc 09 M9 |
| 15 | `guardrail` | does the reply break the content rules? (noul) | every reply, prefetch, host line and verdict prose, before it shows | `safety.tFlag`, `safety.tBlock` | pass with a flag (fails open) | 11 S5 |
| 16 | `guardrail` | does the motion or premise break the rules? (noul) | debate and watch creation | `safety.tMotion` | the session starts; a warning is logged | 11 S3 |
| 17–20 | `guardrail` | image text: likeness / nudity or underwear / blood, wounds or weapons / under 18 (4 nouls, one request) | portrait, tweak and sheet job start | `safety.tImageLikeness`, `tImageNudity`, `tImageGore`, `tImageYoung` | the job starts; the skip is logged | 12 I3 |
| 21 | `guardrail` | does the brief copy a named artist or piece? (noul) | each song task | `safety.tSong` | Lyria is called as today | 12 I4 |
| 22 | `reaction` | the listener's face (choice over 7 + `none`, per listener; ≤ 2 kept) | after `turn.end`, group, debate, watch | its floor and the keep cap | nothing shown | 06 E5 |
| 23 | `face_check` | which emotion do the words show? (choice over 7) | after `turn.end`, non-neutral AUTO faces | — (display only) | no row | W2 |
| 24 | `rubric` | how strong is this side on this criterion? (score, per side per criterion) | the verdict | `verdict.margin` 0.5 decides the winner | one retry, then summary only (Arbiter) or the user's pick | 08 V7, V8 |
| 25 | `importance` | how much will it matter to remember this? (score, 5 levels, per added or rewritten line) | memory pause runs | `memory.minImportance` 0.25 | from the writer's hint, else 0.5 | doc 09 M4 |
| 26 | `importance` | does this line try to change the rules? (noul, same request) | same | `memory.tInstruction` | the line is held for the next pause | 11 S6 |
| 27 | `memory_guard` | is every still-true part of the old memory kept? (noul, per rewrite) | same | `t_keep` (the guard's own value) | keep both lines | doc 09 M5 |
| — | `route` | who replies? (choice over the cast; `none` only when someone is mentioned, G1) | `naive` only, the yardstick | its floor | mentions, else round-robin | 05-ai-seams §3, 07 G1 |

**Cost per purpose** (off-peak; Jev input $0.042 / M tokens, output free). Each figure doubles if A1 finds the state
billed per question.

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

**What OQ-AI-12's table became:** every candidate in it ships in v1, Jev-first:
- emotion (Jev first, no tag in `agent`);
- reactions;
- routing;
- guardrails;
- importance;
- RAG gating;
- debate rubric;
- "talk finished".

### W6. The paid checks, in two groups

The user's rule: paid checks run after the design is done and before coding, with the user's OK on the total. Some
can't, because they need code that doesn't exist yet: the harness, the planner, the suites. So there are two groups.
**Every run saves its requests and responses (W10).**

**Group A: before M7, as plain scripts through the existing gateway (≈ $0.16 in all).** These are the checks that
could change the architecture. Their inputs are hand-built from the seed sessions (doc 06 seed transcripts), since the
eval datasets arrive in M7.

| # | Check | From | Cost |
|---|---|---|---|
| A1 | **Jev billing, limits and scale:**<br>• 1 vs 8 questions, small vs large state;<br>• **a 20-question mixed request** (choice, noul and score), group call 1's real size;<br>• the request size limit;<br>• the 8-question `rubric`;<br>• `importance` and `memory_guard` on 20 items each;<br>• `deep_check` on 20 pieces with 5 set checks;<br>• the standalone and English nouls on 20 messages;<br>• **how a score comes back** (W11's scale);<br>• **repeatability:** 20 items × 3, never served from the store. These 20 become B6's drift canary, so A1 is its baseline. | doc 01 check 4; doc 02 check 1; docs 08, 09, 10 | ≈ $0.03 |
| A2 | **Latency from Malaysia:**<br>• Jev with hand-built call-1 states (1:1, group of 5, debate), including the 20-question request;<br>• 50 follow-plan and 30 debate-plan states;<br>• hand-built `guardrail` (output check) and `deep_check` (8 pieces) states;<br>• DeepSeek to the first word.<br>It sets the starting value of the Jev deadlines it times (W12), and records the alpha endpoint's real response shape. The rewrite (a DeepSeek call) is timed in M12 | doc 01 check 3 (its Jev and first-word part); docs 07, 08, 10, 11 | ≈ $0.10 |
| A3 | **Thinking really off; JSON mode on 20 drafts.** The drafts are saved as the offline fake's canned drafter responses (W14) | doc 03 checks 1, 2 | ≈ $0.03 |
| A4 | **$0 reads:** Lyria's primary terms; findahelpline.com lists Malaysia, the UK and the US | doc 12 check 3; doc 11 check 4 | $0 |

**Group B: inside the change that builds the code, each asked for when it comes.**
- **Suites whose requests later changes don't touch** run once, when their change is accepted: `drafter`,
  `summary`, `debate`, `retrieval`, `memory`, `safety`, and the `decisions` slices.
- **The `conversations` suite runs once, at M15.** Its `agent` replies change with every change that adds to the
  prompt or Jev call 1: M12's passages, M13's memory list, M14's nouls. Running it earlier would buy it again. In
  M9–M14, conversation behaviour is checked by `smoke` (`agent` arm only, a few free runs).
- **The `naive` arms are paid once, at M15**, after the last `naive` change has landed. This covers the `naive`
  verdicts and the `naive` memory writer.
- M15's `all` serves every unchanged request from the store (W10).
- **A `smoke` allowance** of about $0.10 per change covers the runs made while work is in progress.

| Change | Runs | Cost |
|---|---|---|
| M7 | the canary; the corpus licence check and the label-review process (doc 02 checks 2, 3; labels are then reviewed per change) | < $0.001 |
| M8 | `drafter`; `summary` (rolling part); **`long`** (doc 05: the window and summary land here; doc 04 P8's repetition measures use it); the summary judge validation | ≈ $0.23 |
| M9 | the `decisions` slice for emotion and reactions; **E8's mood-line on/off run**, so the line is settled before later suites are tuned; the end-to-end 1:1 quick-turn timing against NFR-01 | ≈ $0.10 |
| M10 | the who-speaks slice; the episode recaps; the committed long watch history (≈ $0.02); **watch at Fast pace with the plan-ahead** (doc 07) | ≈ $0.07 |
| M11 | the debate member slice; the `debate` suite's `agent` part; its one-off debate and plant generation (≈ $0.09). **The 10 timed host bridges and 5 verdicts are saved and used as suite items** (doc 08) | ≈ $0.14 |
| M12 | `retrieval` with the comparisons; 10 rewrites; the standalone and English slice; **doc 10's check 2** (deep-turn and rewrite timing, which tunes `deepCheckMs` and `rewriteMs`) | ≈ $0.12 |
| M13 | the `memory` suite's `agent` part and its `decisions` slice. **Its 6 checked rewrite calls are taken from the suite's 24**; 10 pause runs; 10 recall turns (doc 09) | ≈ $0.16 |
| M14 | `safety` incl. doc 12's parts; **the output check's timing** (doc 11 check 2). Doc 11's check 3 (no second reply after a block) is tested offline instead (W14) | ≈ $0.08 |
| M15 | **`conversations`** (both profiles, ≈ $0.44); **the `naive` arms** of `debate` and `memory` (≈ $0.10); every other suite from the store; **the one must-pass latency run** (B8, NFR-01/02/29), after safety is in | ≈ $0.55 + latency ≈ $0.11 |
| v1 endgame | **doc 12's v3 image check (was A4):** the first seed characters recreated in the app (Hana, Amara, Rin, Victor) are judged by eye for identity, skin tone, adult read, detail, age drift and outfits; W3's identity edit is tried once; how Seedream signals moderation is noted (doc 12 checks 1, 4) | none extra: these are the demo's own images (W10) |

The group B runs total about **$1.55**, or **≈ $1.7 with group A**. The `smoke` allowance (≈ $0.9 over nine changes)
brings the stage to **≈ $2.6**, inside doc 02's "about $1–3". The figures assume Jev bills the state once per request;
A1 confirms it.

**Rejected:**
- **Everything before coding:** half the checks would need throwaway code that duplicates M7–M14.
- **Everything inside the changes:** a Jev billing or latency surprise found in M9 would reshape M7.
- **A full `all` at M15 on top of each change's runs:** it would pay for every suite twice.
- **`conversations` at each change:** M12–M14 change every `agent` request it sends, so the earlier runs would be
  bought again.
- **`naive` arms before M15:** the `naive` prompt changes in M7, M8, M10, M11, M12 and M13, and each change would buy
  its replies again.

### W7. Cost display: the session counter stays reply spend (pricing review)

- **The session's cost counter sums each message's `usage`, and that is the reply alone.** `reply_usage` filters on
  purpose `reply` (`services/ledger.py`), which is also the only purpose that drains energy (`gateway/context.py`).
  Everything else is outside it:
  - Jev call 1 and Jev call 2;
  - the rewrite and the embeddings;
  - the safety and face checks;
  - the summary, reactions and memory.
- **Its tooltip** (`SessionScreen.tsx`) gains: "Reply cost only. Planning, checks, summaries and memory count toward the
  daily cap: see Settings → Cost."
- **Settings → Cost** shows the spend by category, and the top characters and sessions (`CostTab.tsx`). There is no
  per-purpose list there; per-purpose cost is in the eval report (B12) and `ai_calls`.
- **`decision_estimate`** (the daily-cap reservation and the cost shown before spending, NFR-08) follows A1's billing
  answer.
- Both changes are built in M7.
- The deadlines and their homes are in W12.
- **The Jev price in `seed/pricing.json` is already right** ($0.042 in, $0 out; verified 2026-10-09).

**Rejected:**
- **Adding the other spend into the counter:** it would no longer match the energy charge shown beside it, and a
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
  - the MockClient's Memory tab applies the same rule, for parity;
  - SQLite can't add a foreign key to `memory_items` without rebuilding the table, which is why this is a read-time
    rule;
  - stored traces are not rewritten: what was streamed stays what is stored (writer.py), and nothing renders the
    trace's `sourceSessionId`.

**Rejected:**
- **Server-side paging:** a contract change for a list this short.
- **Clearing the field when a session is deleted:** it would add one more write to the delete path, for a rule the
  read side can apply exactly.

### W9. Not added: the memory features doc 09 left out of v1

Editing, pinning or adding memories, reflections, and world-shared facts (D-71) stay out of v1. They are **not**
written into the v2 backlog unless the user asks; doc 09 §7 made that the user's call.

### W10. Pay once, reuse everywhere (the user's rule)

The user's rule, given at the end of this task: when a paid output is useful for a check, the evaluation and the demo,
save it and reuse it. Never pay for the same result twice.

**The store, `data/cache/` (gitignored, built in M7):**
- **The format:**
  - each entry is keyed by the SHA-256 of the canonical JSON of {model, provider, parameters, body};
  - it holds `{response, usage, savedAt}`.

  The group A scripts write this format first, and M7 adopts it.
- **Who uses it:** a `ResponseStore` that **only `horizon eval` and the group A scripts inject into the gateway**, for
  replies and Jev answers. The live app never gets that view, so Regenerate and Retry always get something new. The
  live app gets an **embeddings-only view, limited to seed rows**, so "Index seed knowledge" after Reset demo reuses
  the vectors.
- **Embeddings are the one shared kind,** since an embedding is the same output for the same text. Seed indexing,
  `horizon space build`, the eval copies and the retrieval suite read and write the store, **for seed rows (`is_seed`)
  and corpus pieces only**. The user's documents, memories and messages are embedded without it. So:
  - a re-index after Reset demo (D-98) costs nothing;
  - doc 02 B7's per-run re-embedding stops;
  - Forget (D-70, D-94) has nothing to chase in the store.
- **Never served from the store:**
  - **latency runs and repeatability runs**, which bypass it (a cached answer has no latency, and is trivially
    repeatable);
  - **timeout and fallback rates**, which are computed only from uncached calls. The run report counts cache hits;
  - **`horizon eval capture` and `horizon eval import` runs, and the private safety items** (`private/evals/safety/`).
    These bypass it, because they may hold the user's text;
  - **the drift canary** (B6), which must reach Jev every time.
- **Staleness:** every Jev entry's key includes the canary's fingerprint, i.e. the hash of its last accepted answers.
  When the canary shows drift (B6), the fingerprint changes and every cached Jev answer is stale at once.
- **Doc 02 B7's reply and Jev caches move here** from the run folders, so pruning old runs (B7 keeps 20) never deletes
  them. A factory reset deletes the store.

**Reuse that this enables:**
- **A1's repeatability items become the drift canary** (B6). A1 is its baseline.
- **A3's saved drafts** and the other saved real responses seed the offline fake's canned responses (W14).
- **Each suite runs once, at its change** (W6), and M15's `all` reuses everything unchanged.
- **B4's face judge** reads the live `face_check` rows (W2).
- **Doc 08's timed host lines and verdicts** become debate suite items.
- **Doc 09's checked rewrite calls** come from the memory suite's 24.
- **Doc 04 P8's repetition measures** use the `long` suite's 1:1 runs, instead of three extra free runs.
- **If A1 shows the state billed once per request,** judge nouls that share a reply are sent in one request (B4).

**The demo and the endgame:**
- **The v3 image check moves into the v1 endgame** (W6, was group A's A4, ≈ $0.44). The endgame already recreates every
  seed character in the app, with real portraits and emotions replacing the D-52 placeholders. So:
  - Hana, Amara, Rin and Victor are made first;
  - the user judges their images by eye (D-88), and the accepted ones **are** the demo's images;
  - a failing v3 line is fixed (doc 12 §4) before the remaining characters are made, and only the rejected images are
    paid for again.
- **The demo's recorded sessions feed the evaluation, not the other way round.** Two endgame tools do it:
  - the planned tool that turns recorded sessions into seed files (the endgame plan's SWE gap);
  - `horizon eval import <sessionId>`, which lets the judge score those sessions as free runs, with no new replies.
    It is listed in doc 02 B7.
- **Themes:** Lyria is called once per seed character in the endgame, after the terms are read (A4). The accepted MP3s
  are committed as seed assets and never regenerated.

**Rejected:**
- **A cache in the live app for replies and images:** Regenerate and Retry would return the same output.
- **User text in the store:** it would be a copy of private chats outside Forget's reach (the same reason as doc 02
  B10).
- **Keeping the v3 image check before coding:** about $0.44 for images of characters the endgame recreates with the same
  compiler. It risks only a late template fix, and that costs the rejected images only.
- **Reusing A1's answers as `decisions` items:** A1 runs before the bank exists, so no request would match byte for
  byte.

### W11. The `Decider` in M7: deadlines, late answers, one score scale

- **Deadlines with late answers.** `start(state, questions, ctx, purpose=…, fallback=…) → DecisionCall`:
  - `await call.by(deadline)` returns the answers if they are back by an **absolute virtual-clock time**, else the
    fallback;
  - `await call.final()` returns the real answers whenever they land.

  There is one request and one ledger row. `ask()` stays as `start(…).by(now + timeout)`. This expresses:
  - doc 07 G2: the follow plan starts at the stream's end, with deadline `turn.end` + 400 ms;
  - doc 08 V2: the member is fixed at the deadline, and the gates and emotion are used if `final()` lands before the
    turn starts.

  Today's behaviour (record a late answer in the ledger, then discard it) stays the default.
- **One score scale.** Jev's score answer is parsed once, as an index into the levels: `0 … n−1`, which is what
  `decider.py` accepts today. Every consumer uses `unit = index / (n − 1)`:
  - doc 08 V7's bar = unit × 10;
  - doc 09 M4's importance = unit, so a 5-level score maps as (w − 1) / 4 did;
  - doc 10 K8's citation score = unit.

  A1 confirms how the raw value arrives; the parser absorbs any difference.
- **Per-question deadlines inside one purpose.** The `guardrail` purpose holds the output check (700 ms) and the
  prompt checks (1,500 ms). The prompt checks use `timeoutsMs.decision.guardrail_prompt` (W12) instead of a literal.
- **Keys:** `{question id}` or `{question id}:{about}` (W5).
- **The size check** covers state plus all questions (doc 01 A4), up to the limit A1 finds.
- **Offline:** `park_decision(n)` in the fake lets tests hold a decision past a deadline (W14).

**Rejected:**
- **Splitting the debate plan into two requests:** twice the round trips for the same state.
- **A 1–5 scale in some consumers and 0-based in others:** importance would go negative and the bars would shift, while
  the offline tests passed.

### W12. The knobs: one home and a starting value each

- **Homes:**
  - thresholds and floors live in the **question bank**, per question id;
  - Jev deadlines live in `seed/pricing.json` under `data.gateway.timeoutsMs.decision`, with the mock mirror in
    `pricing.config.ts`;
  - every other runtime knob lives in `seed/runtime.json`, generated from `runtime.config.ts`, which the mock reads.
- **Starting values are used until a change's own suite tunes them** (doc 02 B5, on the dev split). The suite that
  tunes each one is that question's change (W4).

| Knob | Home | Start | Tuned in |
|---|---|---|---|
| who-speaks, emotion, reaction floors; `floor.second`, `floor.member` | bank | 0.6 | M9–M11 |
| `t_gate` (documents) / `t_confident` | bank | 0.35 / 0.8 | M12 |
| `t_gate` (earlier lines) | bank | 0.4 | M13 |
| `t_standalone`; English | bank | 0.5; 0.5 (fixed) | M12 |
| `t_keep` / `t_found` / `t_set` (doc 10) | bank | 0.6 / 0.6 / 0.5 | M12 |
| `t_recall` | bank | 0.5 | M13 |
| `t_keep` (doc 09 guard) | bank | 0.7 | M13 |
| `t_end` | bank | 0.8 | M10 |
| `safety.tSteer` / `tCare` / `tMotion` | bank | 0.7 / 0.3 / 0.7 | M14 |
| `safety.tFlag` / `tBlock` | bank | 0.5 / 0.9 | M14 |
| `safety.tImage*` / `tSong` | bank | 0.5 / 0.6 | M14 |
| `memory.tInstruction` | bank | 0.7 | M14 |
| `verdict.margin` | bank | 0.5 (doc 08) | M11 |
| `turn_plan` deadline | pricing | 1,000 until A2, then A2's p90 | A2, M15 |
| `follow_plan` / `debate_plan` | pricing | 400 / 400 | A2, M10, M11 |
| `guardrail` / `guardrail_prompt` | pricing | 700 / 1,500 | A2 and M14 / — |
| `reaction` / `face_check` | pricing | 1,500 / 1,500 | — |
| `episode` / `verdict` (`timeoutsMs`, not decisions) | pricing | 30,000 / 30,000 (docs 07, 08) | — |
| `retrieval.agent.deepCheckMs` / `rewriteMs` | runtime | 700 / 1,500 (doc 10) | A2 and M12 / M12 |
| `debate.hostWelcomeWaitMs` / `hostBannerWaitMs` | runtime | 3,000 / 1,500 (doc 08 V6) | — |
| `emotion.fade` | runtime | `["surprised", "embarrassed"]` (doc 06 E3) | — |
| `persona.repeatHint` / `context.voiceReminder` | runtime | off / off (docs 04 P8, 05) | — |
| `memory.*`, `retrieval.agent.*` | runtime | doc 09 §6, doc 10 K5 | M12, M13 |

The noul starting values are chosen by each noul's cost of being wrong:
- low where a miss is worse than a false alarm (`tCare`, the gates);
- high where a false yes hurts (`tBlock`, `t_end`, the guard).

**Rejected:** leaving the starting values to each proposal. M9–M14 would ship behaviour nobody had chosen.

### W13. The storage the design implies

- **`message_ai_meta`** (M12 creates it; M14 adds a column):
  - columns: `message_id` (primary key, foreign key to messages, `ON DELETE CASCADE`), `rewrites` JSON (doc 10 K4:
    per speaker), `safety` JSON (doc 11 S3/S4: steer, care, pInput, pCare);
  - **AI-owned derived data, like `turn_traces`:**
    - it is not projected from events;
    - fork copies its rows with the messages it copies;
    - message deletion cascades;
    - it holds no memory text;
  - the `session-event-sourcing` spec gains that exemption in a delta.
- **`sessions.memory_seq`, `memory_reread`, `memory_tries`** (doc 09 M2, M13): runtime bookkeeping columns, set by the
  memory run and not by events. They are covered by the same exemption.
- **`ai_calls`** (doc 02 B10, M7): its schema is in M7's design.md.
- **`data/cache/`** (W10, M7) and `data/evals/` are both deleted by a factory reset (the `local-backend` spec).
- **Each change names its own Alembic migration.** The vec tables stay the SpaceManager's, never Alembic's.

### W14. Offline testing for every change

The project rule stands: tests make no network calls.
- **Canned real responses.** `FakeOpenRouter` (an httpx mock transport) sees only the HTTP request. So **in test mode
  the gateway adds an `X-Horizon-Purpose` header**, and the fake answers chat calls per purpose with recorded real
  responses:
  - group A's saved drafts and replies;
  - then each change's own recorded rewrite, verdict, host, episode and summary outputs.

  A test-control route picks them. Today the fake's chat answers "ok" whatever is asked.
- **`park_decision(n)`** holds Jev answers, so deadlines, late answers and timeouts are testable through the gateway.
  Today only images and embeddings can be parked.
- **The memory writer in tests:** test mode uses the `agent` writer with canned answers, unless the profile is
  `scripted`. Doc 09 M1's "`[]` in test mode" applies only to `scripted`.
- **CI and the private safety items:** in test mode the harness loads the committed harmless items and the manifest,
  and reports the skipped private items as a count.
- **Mock parity:**
  - `system1.fixture.json` (W1);
  - the second-`insight` behaviour in both reducers' fixtures;
  - G5 and V5 in `frontend/src/mock/engines/group.ts` and `debate.ts`;
  - W2 in `turnScript.ts`.
- **Doc 11's check 3** (no second reply after a block) is an offline test, with a forced block and `DeciderFixtures`.

## 3. Checks before this is locked

W6 holds every paid check. The offline checks, in M7:
1. The rev 1.4 schema validates the scripted and mock `system1` rows (`export-schema:check`, `fixtures:check`).
2. A trace with more than 64 rows is cut by the runtime before it is sent, `not_used` rows first.
3. `append_system1` after a Regenerate, and after a Forget, writes nothing back (W1).

## 4. Docs amended with this doc

**Requirement-level edits approved in tasks 3–12, applied now:**

| Doc | Edit | Approved in |
|---|---|---|
| [02-functional-requirements](../requirements/02-functional-requirements.md) | **SET-05:** read-only in v1. **CHR-05 AC1:** the template is the AI team's (docs/ai/04), not a mock. **PRF-07:** no Preview ribbon; AC2 for W8. **PRF-08:** RAG ships in v1, no ribbon. **ENG-02 AC2:** the list gains the query rewrite, Jev call 2, the query embedding, the safety checks and the face check. **INS-01 AC2:** the System 1 bullet, after Emotion | 03 C9; 04; doc 09, W8; 10; 10, 11, W2; W1 |
| [05-data-contract](../requirements/05-data-contract.md) | `MemoryItem` is no longer PROVISIONAL; `KnowledgeSource` is no longer "PLACEHOLDER, v1.1" | doc 09; 10 |
| [07-nfr-risk-cost](../requirements/07-nfr-risk-cost.md) | **NFR-13:** the LangSmith opt-in exception. **NFR-35:** the memory list frozen for a sitting sits in the cached prefix. **R-13:** a code fallback per question (see the status note). **R-14:** checked by the eval, no fallback model | 02 B11; doc 09 M8; 01 A4; 03 C8 |
| [08-open-questions-handoff](../requirements/08-open-questions-handoff.md) | OQ-AI-01 to 17: each marked resolved, with where | all |
| [09-decision-log](../requirements/09-decision-log.md) | **D-46:** up to 4 bubbles, display only. **D-65:** pieces, no parent–child. **D-92:** the planner is a runtime-called port. **D-93:** byte-identical only until the next `naive` version. **D-94:** Forget also deletes `ai_calls` rows. **D-97:** superseded in `agent` by **new D-100**, which embeds only after the gate | 03 C5; 10 K1; 01 A4; 03, 10 K13; 02 B10; 01 A6, doc 09 M9, 10 K4 |
| [01-vision-and-scope](../requirements/01-vision-and-scope.md) | §4.3: the Knowledge tab and per-character RAG move from v1.1 into the MVP row, and so do Jev rubric scoring, memory importance scoring, the evaluation harness and its run storage | 10; **follows from 02, 08, 09** |
| [backend/02-storage](../backend/02-storage.md) | §3.7: memory is written at session pauses (doc 09 M1). The job-kind list drops `memory_consolidate` | doc 09 |
| [backend/04-gateway-budget-energy](../backend/04-gateway-budget-energy.md) | no fallback model | 03 C8 |
| [backend/05-ai-seams](../backend/05-ai-seams.md) | §1: the `agent` profile. §2.1: `system1` is runtime-owned. §2.2: the AI-stage column points to docs/ai. §3: the purpose table points to W5. §4: memory at pauses. §5: the `naive` version note. §6: each deferred row's outcome | 01, 02, doc 09, 10, W1 |
| [backend/06-milestones](../backend/06-milestones.md) | a pointer to W4 for M7–M15 | W4 |
| docs [01](01-agent-architecture.md)–[12](12-images-music.md) | every "task 13" item marked resolved; every passage this doc supersedes annotated (W2's live check, W4's opt-in, D-100, W6's moved checks, W11's score scale, the build order); the reviewers' consistency fixes | consistency |

**Left for the OpenSpec changes, since they change with the code:**
- `TurnTrace.system1` in 05-data-contract and `schema.json` (M7);
- the `openspec/specs/*` deltas in W4's last column;
- the docs/ai cross-references each change touches.

## 5. Left for later

- **The OpenSpec loop**, M7 to M15, after `design/ai-stage` is squash-merged into dev (the user is asked before any
  push).
- **Group A's paid checks** (W6), with the user's OK on ≈ $0.16.
- **The v1 endgame:**
  - real-API end-to-end tests;
  - the real demo in two worlds, with real System 1 rows;
  - the session-to-seed tool and `horizon eval import` (W10);
  - then the squash of dev into main as v1.

## Sources

- Docs [01](01-agent-architecture.md)–[12](12-images-music.md) of this pack, each decision cited where used.
- Horizon requirements: INS-01, ENG-02, NFR-01, NFR-08, NFR-13, NFR-35, SC-2, D-46, D-65, D-70, D-71, D-81, D-88, D-92,
  D-93, D-94, D-97, D-98; OQ-AI-01 to 17.
- Code:
  - [InsightDrawer.tsx](../../frontend/src/features/insight/InsightDrawer.tsx);
  - [EmotionLightbox.tsx](../../frontend/src/features/profile/EmotionLightbox.tsx);
  - [HorizonClient.ts](../../frontend/src/client/HorizonClient.ts) (`StartJobInput.prompt`);
  - [tabs.tsx](../../frontend/src/features/profile/tabs.tsx) (the Memory tab);
  - [CostTab.tsx](../../frontend/src/features/settings/CostTab.tsx);
  - [image_prompt.py](../../backend/horizon/ai/image_prompt.py) (`KEEP`, `emotion_edit`);
  - [decider.py](../../backend/horizon/ai/decider.py) (timeouts, score range);
  - [actor.py](../../backend/horizon/sessions/actor.py) (`background`, `clear`);
  - [writer.py](../../backend/horizon/sessions/writer.py) (`_project`);
  - [ledger.py](../../backend/horizon/services/ledger.py) (`reply_usage`);
  - [plans.py](../../backend/horizon/services/jobs/plans.py);
  - [gateway/context.py](../../backend/horizon/gateway/context.py) (`PURPOSE_CATEGORY`);
  - [pricing.json](../../seed/pricing.json).
- TypeSafe Jev docs: Speculative Fan-Out and confidence-gated routing (doc 01's sources).

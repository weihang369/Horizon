# Proposal: safety (M14)

## Why

Horizon's only content check is a guardrail port that always says "pass". Under `agent`, nothing reads what the user
asks, nothing notices a user in distress, and nothing checks what DeepSeek actually wrote. DeepSeek is permissive in
role-play, and a public demo (SC-5) can drift on screen. Doc 11 (S1–S11) designs the answer, with the user's four
choices:
- an unsafe line is **steered in character**, not blocked;
- a user at risk gets a **Jev noul and a care cue**;
- every finished reply gets a **live Jev output check**;
- the provider's training permission is told in a **one-line notice**.

Doc 12 adds a Jev check on the text the user writes into an image prompt or a song brief (I3, I4). Doc 13 W4 makes
all of it M14.

**Why now:** every plan the nouls ride now exists: Jev call 1, the cast plan, the follow plan, the debate plan and
watch's plan-ahead (M9–M11). The importance request M13 built has a seam for the memory noul (memory D14, D38).
`message_ai_meta` (M12) has room for the safety column. M15's must-pass latency run is "after safety is in", so this
change has to land first.

**Much of doc 11 is already built.** The audit (design D1) found these were done by earlier changes:
- the `quoted_*` states (M7);
- the S2 rules lines, the advisory line and no mature variant (M8);
- S9's originality rule in the drafter (M8, persona-context D17);
- the passage tags (M12);
- newline collapsing and S7's never-store list in `memory-2` (M13);
- the `guardrail` deadlines (M7);
- the follow plan starting at the stream's end and being cancelled by a block (M10);
- ENG-02 AC2's "safety checks" (doc 13 §4).

What is left is the checks themselves, their storage, their effects, the notice and the evaluation.

**It lands as one change.** The parts share:
- the bank entries;
- the stored flags (written by the input and care nouls; read by the stay, regenerate and the memory filter);
- the trace merge;
- the `safety` suite, which measures every part against one item set and one cross-validation.

Split, the suite would be built and paid for twice. The phases are ordered so each ends green offline, and the paid
runs come last.

## What Changes

**Phase 0: the base (design D2)**
- Confirm M13's gates on 4f696ad.
- Offline storm tests for every new cancel path:
  - the nouls in a plan on Stop;
  - the output check on Stop, End, a cap pause, leave, delete and Reset demo;
  - a held prefetch, a held host line, held verdict prose;
  - the motion check;
  - `check_prompt` at job start and in the song task;
  - a failed memory noul;
  - the safety write on a cancelled turn, a fork and a regenerate;
  - the reducer clear after a reconnect.

**The bank and storage (design D3, D5, D13)**
- Ten new bank entries, each worded as the risk, with the `quoted_*` sentence and its W12 threshold:
  - `unsafe_request`, `at_risk`, `output_rules`, `motion_rules`;
  - `image_likeness`, `image_nudity`, `image_gore`, `image_young`;
  - `song_copy`, `instruction`.
- S1's two lists live in the instructions, never in the state.
- Migration `0006_safety`: `message_ai_meta.safety` (`steer`, `care`, `pInput`, `pCare`). Only Jev answers are
  stored.
- The fake answers safety nouls with a low p by default, so the existing `agent` tests keep their behaviour.

**Input and care, in every mode (doc 11 S3, S4; design D4–D8)**
- A new user line is asked "unsafe request?" (and, in 1:1, group and Step in, "at risk?") in the first plan request
  that sees it, until a Jev answer is stored:
  - 1:1 and group: Jev call 1;
  - debate: an Ask's face plan, else the next debate plan;
  - watch: the next cast plan or the plan made ahead.
- The steer and care cue sentences go in the dynamic tail, before every other cue. System message 1 is unchanged.
- On steer or care:
  - one speaker only, prefetches discarded, no follow plan;
  - the care face on every path, and no listener reactions;
  - the 2-message stay, read from the stored flags;
  - a regenerate reuses the flags.

**The output check (doc 11 S5; design D9–D12)**
- `AgentGuardrail`: one `guardrail` noul per reply, 700 ms. At or above `tBlock` it blocks, at or above `tFlag` it
  flags. When late or failed it passes with a flag (fails open).
- It runs:
  - at the stream's end for live replies;
  - before release for a finished prefetch;
  - after the fact for an interrupted reply;
  - inside the host-line and verdict tasks.
- A blocked reply keeps its trace (an `insight` is emitted; checks are merged by name).
- An `error` with `content_refused` and a `messageId` empties that message in both reducers, including the after-the-fact case.
- A `naive` guardrail passes with no checks. The scripted twin shows `output: pass` only, and the seed and fork
  fixtures are rebuilt.

**Creation checks (doc 11 S3; doc 12 I3, I4; design D14, D17)**
- The motion or premise check when a debate or watch is created. It is skipped for a motion or premise the world
  already used, and refusals answer 451 `content_refused`.
- `Guardrail.check_prompt` in agent:
  - four image nouls at `JobScheduler.start`, before any hold or row;
  - one song noul before the Lyria call, falling back to the procedural theme with `brief_refused` and its own note;
  - an in-memory answer cache.

**Memory (doc 11 S6, S7; design D15, D16)**
- `instruction:l{n}` rides the importance request through D14's seam. `importance` keeps its version.
- A missing answer fails the piece as a try, so the line is held for the next pause.
- The stretch drops the user lines the steer or care cue was on for, and the replies to them.

**The notice (doc 11 S8; design D18)**
- The Connection tab and the Knowledge drop zone each gain one line of fixed text.
- The README's privacy section gains what is sent where, and D-80's training permission.

**Evaluation (doc 11 S10, §5; doc 12 I7; W6's M14 row; design D19–D26)**
- The `safety` suite: input, care, care + method, output, motion, injection, honesty and advice, drafter, image text,
  song brief and drift.
  - Counts with Wilson intervals; thresholds cross-validated on a 0.1–0.9 grid.
  - The private items stay in `private/evals/safety/`. Their paid outputs are saved there too, so a re-cut never pays
    twice.
- Its judges are validated (B4) before they count.
- Doc 11 check 2 (the output check's latency) and the re-measure of `follow_plan` 483 ms and `debate_plan` 651 ms.
- The paid runs, each asked for with an estimate: ≈ $0.07–0.10 against W6's ≈ $0.08 (design D25).

**No contract change (design D18).** `TurnTrace.guardrail.checks`, `content_refused` (451), `contentRating`,
`advisory` and `licenseNote` already exist. W4 lists `http-api` and `generated-assets` for route- and asset-level
behaviour on existing wire shapes:
- `POST /sessions` and `POST /jobs` can now answer 451;
- the theme's `licenseNote` text depends on why it fell back.

No wire field, enum value, event or UI entry point is added.

## Capabilities

### New Capabilities
- `content-safety`:
  - the safety questions per profile;
  - the input and care checks, the cues, one voice and the stay;
  - the stored flags;
  - the output check and when it runs;
  - the motion check, the image and song prompt checks;
  - the privacy notice.

### Modified Capabilities
- `session-runtime`: a blocked reply still emits its `insight`; the after-the-fact check on an interrupted reply.
- `ai-ports`: the `naive` guardrail with no checks; the `agent` guardrail; `check_prompt`.
- `turn-plan`: Jev call 1 and the cast plan ask the safety questions about a new user line.
- `debate-plan`: the debate plan asks the input question about an unchecked moderator line.
- `watch-direction`: a director's note is checked by the next plan.
- `follow-plan`: no follow plan on a steered or care message.
- `persona-prompt`: the steer and care cue sentences in the tail.
- `speaker-emotion`: the care face.
- `listener-reactions`: no reactions while care is on.
- `system1-trace`: the input, care and output rows.
- `session-event-sourcing`: the safety flags are exempt AI-owned data; both reducers empty a refused message.
- `data-storage`: migration 0006.
- `long-term-memory`: the instruction noul and the held line; flagged talk is never mined.
- `question-bank`: the safety entries.
- `generation-jobs`: the image text check when a job starts.
- `generated-assets`: the song fallback's note by reason; `brief_refused`.
- `session-lifecycle`: the motion and premise check when a session is created.
- `http-api`: 451 from session create and job start.
- `evaluation-harness`: the `safety` suite, its private items, its thresholds, its judges and its timing.

## Impact

- **Backend:**
  - `ai/` (ports, profile, the new `agent/safety.py` and the guardrail, gates, planner, cast_plan, debate_plan,
    follow_plan, persona, turn, emotion, reactions, `memory/jev.py`, scripted ports, questions);
  - `sessions/` (turn, prefetch, debate_host, debate_verdict, lifecycle, plans, follow, watch_plan, the modes,
    after_turn);
  - `services/` (`ai_meta.py`, `memory/runs.py` and `stretch.py`, `jobs/scheduler.py` and `worker.py`,
    `theme.py`);
  - `gateway/fake.py`, `db/` (tables, migration 0006);
  - `evals/` (the new `safety_suite.py`).
- **Frontend:**
  - `engine/sessionReducer.ts` and the session's StreamingText;
  - `mock/script/turnScript.ts`;
  - `features/settings/ConnectionTab.tsx`, `features/profile/tabs.tsx`;
  - the rev12 and fork fixtures, and the rebuilt seed traces.
- **Config:** the bank's safety entries and their thresholds. No new `runtime.json` or `pricing.json` key: the
  `guardrail` and `guardrail_prompt` deadlines exist since M7.
- **Spend (under `agent` only):**
  - ≈ $0.00004 more per reply (the output check plus two nouls);
  - ≈ $0.00002 per checked image or song job;
  - `naive` users pay nothing new.
- **Docs:**
  - everything doc 11 §6 and doc 12 §5 list, plus doc 11's and doc 12's built notes;
  - W6's and W12's M14 rows;
  - the new `docs/ai/checks/m14.md`.
- **Not touched:**
  - the HTTP contract and wire schemas;
  - compiler v3, the song prompt and `ASSETS.md` (M15);
  - `conversations`, the `naive` arms and the blended latency run (M15).

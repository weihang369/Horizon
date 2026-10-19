# Proposal: images-music (M15)

## Why

M15 is the last of the nine AI-stage changes (doc 13 W4). It has two jobs.

1. **Finish doc 12.** M14 built the image and song text checks (I3, I4, I7). Three pieces are still open:
   - the image prompt still has no "original character" or "fully clothed" line, and its edits don't keep the
     apparent age (I1);
   - the song prompt still puts the character's name in front of Lyria (I2);
   - `ASSETS.md` doesn't name SynthID or Lyria's terms (I8).

   The "Doesn't look like them" button also sends a sentence that nothing reads (W3).
2. **Make `agent` the default with a key** (doc 01 A12), and pay for the runs that only make sense once every
   `agent` change is in (W6 group B):
   - the `conversations` suite, both profiles;
   - the `naive` arms of `debate` and `memory`;
   - the one must-pass latency run (B8, NFR-01/02/29), "after safety is in".

**Why now:** M14 is merged into local dev (a570f5f), so every Jev question in v1 now exists. Each earlier change
parked a measure "for M15's conversations" or "for M15's blended run". This change collects them and measures them
once. The AI stage then hands its saved requests to the Jev 1.14 comparison and its results to the v1 endgame.

**What the audit found (design D1):**
- **The `conversations` suite doesn't exist.** `horizon eval` has `freerun`, `long` and `memory --part layer3`. It has
  no `conversations` and no `all`.
- **Doc 02 B3's 20 frozen transcripts don't exist either.** Only the four long ones (M8) are committed. The
  committed watch and debate histories (M10, M11) can supply 9 of the 20; 7 short 1:1 and group transcripts are
  generated once with `naive` (design D9).
- **The pairwise judge never passed B4** (M9: 26/30 against 0.90). It is layer 3's main measure, so its set is
  rebuilt and validated first (its two orders swap the replies in the state, so each is a request of its own).
  Separately, the store key serves `decisions`' reversed-option request with the first order's answer, so M9's order
  bias was never measured (m9.md 9.1; design D13).
- **The honesty line isn't part of compiler v3.** m14.md assumed "system message 1 changes there anyway (compiler
  v3)". But compiler v3 is the image prompt compiler (`ai/image_prompt.py`). System message 1 is the persona
  prompt's standing lines (`ai/agent/persona.py`, with its TS twin). So the rewording is its own change of those
  bytes, and it moves every `agent` prompt label (design D5).
- **"Every other suite from the store" is not free.** M14's safety questions ride every `agent` plan request, M13's
  memory list and M15's honesty rewording change every `agent` reply request, and the store keys on the exact
  bytes. The old answers no longer match. A free probe reports what would be paid before anything is (design D13).
- **The default switch barely touches the tests.** Backend tests and e2e pin `HORIZON_AI_PROFILE=scripted` already.
  What it does reach: the profile unit tests, the memory writer's test-mode special case, a docstring that says
  `/health` lists the ports (it doesn't), and turns that read the key afresh at each step, so a key cleared mid-turn
  can mix profiles in one reply (design D3, D4).

**It lands as one change.** The parts share one evaluation pass:
- the rewording and the `naive` fix must land before `conversations` is paid;
- `conversations` needs the rebuilt pairwise judge;
- the latency run needs the final code and the default.

Split, a paid run would be bought twice or measure code that then changes. The phases are ordered so each ends
green offline, every product, config or prompt change comes to the user as a choice, and every paid run comes after
the code it measures is final.

## What Changes

**Phase 0: the base (design D2)**
- Confirm M14's gates on a570f5f.
- Offline storm tests for the new cancel paths:
  - a hinted `emotion_regenerate` cancelled, or its character deleted;
  - a song task cancelled after its prompt is built;
  - the key cleared or set mid-turn with a plan, an output check or a pause run in flight;
  - a `conversations` or `latency` run stopped mid-conversation.
- Run the drift canary before any paid run (< $0.001; a drift makes every stored Jev answer stale).

**Images and songs (doc 12 I1, I2, I8; W3; design D6–D8)**
- Compiler v3, worded exactly as I1:
  - the original-character and "Fully clothed in the outfit described." lines in `base` and `sheet`;
  - "childlike or teenage features" in the sheet's Avoid line;
  - the apparent-age line in `emotion_edit` and `tweak`;
  - `IMAGE_PROMPT_VERSION = "v3"`, the golden fixtures regenerated, a name-never-appears test.
- W3: a hinted `emotion_regenerate` adds the fixed identity line. The hint's text never reaches the prompt.
- The song prompt drops the title and gains the original-piece line (I2). The stored title, provenance and procedural
  theme don't change.
- `ASSETS.md` gains a "Generated music" section: SynthID, and Google's terms as group A A4 read them. No row is
  added, so `assets:check` is unaffected.

**Prompts, as the user's choices (design D5, D10)**
- The S2 honesty line reworded so a question asked inside the story is answered in the story. The candidate
  wordings and their re-measure come to the user before anything is paid. The new bytes move `agent-1`…`agent-8`
  to `agent-9`…`agent-16`.
- `naive`'s emotion-tag line forbids notes inside the tag (m11 D31.3), as `naive-9`…`naive-12` (every `naive` label moves by 4), if the user chooses it.

**The default (doc 01 A12, doc 02 B12; design D3, D4)**
- Without `HORIZON_AI_PROFILE`, the profile is `agent` when a key is set and `scripted` otherwise. `naive` stays
  one variable away and stays the evaluation's yardstick.
- A reply resolves its ports from the key status read once at its start. A key cleared mid-turn fails the reply's
  provider call on the existing error path. It never switches profile halfway.
- The memory writer's test-mode special case goes: the default already gives the `agent` writer.

**Evaluation (W6's M15 row; doc 02 B1–B4, B8; design D9–D17)**
- `horizon eval conversations`: layer 3 on 20 frozen transcripts.
  - Both profiles reply at each turn from the same stored history. Jev judges stays-in-character, the reply rules and
    agent-vs-naive in both orders.
  - A paired bootstrap runs over whole conversations.
  - It adds the four free runs per profile and folds in the parked measures: the Not-found rate, the live group
    rewrite, V11's debate targets, the memory list, voice drift and the citation judge's real failures.
- The pairwise judge's set is rebuilt and validated (B4). The store key keeps a reversed option order (for `decisions`' order-bias rows).
- `horizon eval all` becomes a free probe: it runs every suite against the store, sends nothing, and reports per
  suite what would be paid. Re-paying a suite is a choice for the user.
- The `naive` arms of the `debate` and `memory` suites.
- `horizon eval latency --part blended`, the must-pass run:
  - 100 quick and 100 deep 1:1 turns, the deep half with and without a rewrite;
  - 50 group, 50 debate and 25 deep watch turns;
  - warm-up discard, a recorded time window, the per-stage breakdown, and the blended p50/p90 at the real deep rate;
  - it also reports the `turn_plan` deadline, the output check's late rate under load, `follow_plan`, `debate_plan`,
    recall's tail and the provider cache hit.
- Sentence faithfulness on the 10 two-passage retrieval items, with its judge validated first.
- The emotion set grows by 40 items (E8's straddle rule).
- Saved for the Jev 1.14 comparison: a request manifest for every Jev set, with the exact bytes' hashes. The
  comparison can then prove it sent the same states.
- Paid runs, each asked for with an estimate from measured per-call costs: ≈ $0.70–0.85 in all, against W6's
  ≈ $0.66 (design D17).

**No contract change (design D18).** The default switch changes no wire type, and `/health` keeps its body. The
image provenance (`generation.prompt`) already carries the compiled text, so v3 adds no field. The button, its hint
and `StartJobInput.prompt` already exist.

## Capabilities

### New Capabilities
None. Every behaviour here belongs to an existing capability.

### Modified Capabilities
- `ai-ports`:
  - the default profile is `agent` with a key;
  - a reply resolves its ports once;
  - compiler v3 and the identity line;
  - the song prompt without the name;
  - `naive`'s tag line (if chosen).
- `generation-jobs`: a hinted `emotion_regenerate` compiles the identity edit, and never reads the hint's text.
- `asset-credits`: `ASSETS.md` names SynthID and the Lyria terms.
- `persona-prompt`: the honesty line answers in-story questions in the story; the prompt labels follow the new bytes.
- `response-store`: a reversed option order gets its own key; a probe never sends.
- `evaluation-harness`:
  - the `conversations` suite and its frozen transcripts;
  - the rebuilt pairwise judge;
  - `all` as a probe;
  - the `naive` arms;
  - the must-pass latency run;
  - sentence faithfulness;
  - the grown emotion set;
  - the request manifest.

## Impact

- **Backend:**
  - `ai/` (`image_prompt.py`, `profile.py`, `agent/persona.py`, `naive/creation.py`; `naive/prompt.py` if chosen);
  - `services/jobs/worker.py`;
  - `sessions/turn.py` and the per-reply port lookups (the key read once);
  - `evals/`:
    - new `conversations.py` and `transcripts` frozen-set loader;
    - `store.py` (the order salt, the probe);
    - `runner.py`, `cli.py`, `latency.py` (`--part blended`), `judges.py`, `debate_suites.py`, `memory_suite.py`,
      `retrieval_suite.py`, `stats.py`.
- **Frontend:** `domain/personaPrompt.ts` (the twin's honesty line and labels) and the shared persona fixtures. No UI
  change; the mock is unaffected.
- **Data:** `evals/transcripts/` gains 16 frozen transcripts (9 cut from committed histories, 7 generated);
  `evals/datasets/judges/` the rebuilt pairwise set and the faithfulness set; `evals/datasets/emotion/` 40 items;
  `evals/baselines/` the request manifest.
- **Config:** none, unless a deadline choice changes `seed/pricing.json` and its TS twin.
- **Spend:** no new live spend. `agent` users already pay the M9–M14 checks, and the default only changes who gets
  them.
- **Docs:**
  - everything doc 12 §5 lists, plus doc 12's and doc 13's built notes;
  - W6's and W12's M15 rows;
  - doc 01 A12 and doc 02 B12;
  - README, `docs/backend/05-ai-seams.md`, `evals/README.md`;
  - the new `docs/ai/checks/m15.md`, ending with "What the AI stage leaves".
- **Not touched:**
  - the HTTP contract and wire schemas;
  - the Jev model id (jev-1.13);
  - no image or song is generated (the v3 image check and W3's identity edit are the endgame's, by eye);
  - style reference images (v2).

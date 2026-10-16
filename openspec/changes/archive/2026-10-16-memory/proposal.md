# Proposal: memory (M13)

## Why

Characters remember nothing between sessions. `MemoryStore`, Forget and the vector tables have been in place since M5.
But both profiles ship `NoMemoryWriter`, so the only memories are the seed ones. Under `agent`, no memory reaches a
reply at all: planned turns skip `retrieve()`. Doc 13 W4's table says "Memory: none" through M12. Within a session,
whatever the rolling summary drops is gone for good. "What did I say the cake was called?" can't be answered once that
line has left the window.

Doc 09 (doc 09 M1–M13) designs the answer, and doc 13 W4 makes it M13:
- memories written at session pauses, from every character's point of view, by one DeepSeek call per pause;
- Jev scoring importance and guarding every rewrite, so no still-true fact is lost;
- the memory list frozen into each character's cached system prompt;
- recall from earlier, a hybrid search over the session's dropped lines and the memories ranked below the list. It
  is gated by Jev and checked by Jev call 2 on M12's pipeline.

**Why now:** M12 built everything recall runs on: the shared search pipeline, `deep_check`, the early query embedding,
and the gates in every plan (W4's rejected "memory before RAG"). M14 (safety) adds its nouls to the importance request
this change builds, so the request has to exist first.

**It lands as one change.** The parts are coupled:
- the writer produces the overflow that recall searches;
- the memory list decides what counts as overflow;
- the undo and Forget run through the writer's storage, the list and the stored rewrites;
- the layer-3 evaluation (two sessions) needs the writer, the list and recall together.

Split, the memory suite would be built twice and its two-session runs paid twice. The phases are ordered so each ends
green offline, and the paid runs come last.

## What Changes

**Phase 0: the base (design D2)**
- M12's gates are confirmed on 6ceb366:
  - backend 1841, with the load-sensitive keyword-search timing guard noted;
  - frontend 542 / http 62;
  - e2e 66.
- Offline storm tests for every new cancel path:
  - a run cut by a delete or Reset demo at each of its steps;
  - Forget during a run;
  - a regenerate during a run;
  - the window-drop embedding;
  - recall's search and `deep_check` on Stop;
  - the memory block's refresh;
  - shutdown with runs pending.

**Storage (design D5, D6)**
- Migration `0005_memory`:
  - `sessions.memory_seq`, `memory_reread` and `memory_tries`. Existing sessions start at their highest message `seq`;
  - `message_fts` (FTS5 over messages, kept by triggers).
- `message_vec__{space}`, partitioned by `session_id`, is created by the SpaceManager, never by Alembic.
- `Reinforce` also sets `last_recalled_at`.
- `build_space` gains the `message` kind (the seam rag D27 left).

**Pause runs (doc 09 M1, M2, M6; design D7–D12)**
- A run starts on any of these:
  - the last session-stream subscriber gone for 30 s, in any status;
  - `leave`, `end`, the debate verdict, or watch's `turn_cap`;
  - the kept turn's `turn.end`;
  - a session opening with a character who has pending lines elsewhere (it jumps the queue);
  - the start-up sweep;
  - the idle release.
- Runs are runtime-level `memory_run:{sessionId}` tasks:
  - ≤ 2 at once and one per session;
  - outside `llmConcurrency`;
  - cancelled by deletes and resets;
  - deferred without a usable key.
- The per-reply `_remember` queue is removed.
- The stretch builder covers:
  - the settled bound and the message kinds and labels;
  - the debate and watch header;
  - 6 context lines;
  - 8,000-token pieces.
- `MemoryStore.apply_run` commits every character's ops, the compare-and-set checkpoint and the re-read list in one
  transaction. It also handles the variant check, the sorted run locks and the Forget-race rule.
- Failures:
  - 3 tries, then the piece is skipped;
  - memory purposes never pause sessions at the daily cap.

**The writer (doc 09 M3–M5, M11; design D13–D19)**
- `MemoryWriter.on_stretch` replaces `after_turn`.
- Under `agent`, a LangGraph graph with no checkpointer:
  - one DeepSeek JSON call (`memory`) for everyone present;
  - then, per character, Jev `importance` ∥ `memory_guard` ∥ the duplicate check, then ops.
- `naive` runs the same call with no Jev. `scripted` writes nothing.
- New bank entries: `importance` (5 levels, unit) and `memory_guard` (a new decision purpose).
- Canned memory responses in the fake (W14).

**The undo and Forget (doc 09 M7; design D20, D21)**
- Regenerate or Continue on an already-read message undoes the still-current memories sourced from it and queues the
  message for re-reading.
- `_forget_derived` switches to the undo.
- Any memory removed through the Forget path also clears that character's stored query rewrites in that world. A
  rewrite was written with the memory list in its input (rag D27).

**The memory list (doc 09 M8, M10; design D22–D25)**
- Each character's `agent` system message 1 gains "# What you remember":
  - ranked by importance × recency × mode weight, filled to 1,000 tokens;
  - frozen for the sitting, refreshed only on a Forget or a live commit;
  - listed in `memory.recalled` with no score.
- The TypeScript persona twin gains the same input.
- The greeting adds up to 2 of the newest memories and one cue sentence.
- New `memory.*` knobs in `runtime.json` and its TS source.

**Recall from earlier (doc 09 M9; design D26–D34)**
- The window drop embeds the newly dropped lines in one batch.
- Forks copy those vectors; a regenerate re-embeds; scrubs and deletes zero them first.
- "Needs something from earlier?" (`earlier`) is asked per candidate when there is something to search, in every plan:
  Jev call 1, the cast plan, the follow plan, the debate plan and watch's plan-ahead.
- `retrieval.search` is generalised over a corpus. Documents keep identical results, and recall passes its own numbers.
- Per corpus, BM25 ∪ dense are fused by RRF; the two corpora are merged with weights; MMR picks 6.
- Jev call 2 (`deep_check`, a `recall` noul per candidate) keeps ≤ 3 lines within its own deadline.
- The tail blocks hold ≤ 400 tokens. The trace gets `contextInSession` and scored `memory.recalled`. System 1 gets
  `earlier` and `recall` rows.
- The next pause Touches each overflow memory recall used.

**The Memory tab (W8)**
- 50 memories at a time, with "Show more".
- A `sourceSessionId` whose session is gone is dropped at read time, in both clients.
- The "Preview" ribbon is removed (PRF-07).

**Evaluation (doc 09 M12, §5; W6's M13 row; design D35–D40)**
- `decisions` slices: importance (100), guard (~120), `earlier` (~120) and recall relevance (~120).
- The `memory` suite:
  - rewrite (24 stretches);
  - in-session and overflow recall (60 + 40 probes);
  - layer 3 (20 two-session pairs, the `agent` part only).
- B4's "Memory rewrite" and "Over-mention" judge rows.
- The recall-set comparisons: the query instruction, `dupCosine`, recall's λ and its deadline.
- Doc 09 checks 1–4.
- The paid runs, each asked for with an estimate. They total ≈ $0.27 against W6's ≈ $0.16 (design D40).

**No contract change (design D4).** `MemoryItem`, `memory.recalled`, `contextInSession` and the `memory` ledger
category already exist. W4 lists `http-api` and `client-contract` because the memory route's read-time "View source"
rule is behaviour both clients must match. No wire field, method, event or UI entry point is added.

## Capabilities

### New Capabilities
- `session-recall`: recall from earlier.
  - The `earlier` gate in every plan and the two corpora (dropped lines, the memory overflow).
  - Their indexing at window drops and the hybrid search.
  - Jev call 2's `recall` check and its fallback.
  - The tail blocks and the trace and System 1 rows.

### Modified Capabilities
- `long-term-memory`:
  - pause runs and their triggers, the checkpoint and stretch, the writer;
  - importance and the guard, the duplicate check;
  - `apply_run`, the undo, the Forget-race and stored-rewrite rules, the cap exemption, profiles, the Memory tab;
  - "Replies feed the memory writer after they end" is removed.
- `persona-prompt`: the memory list in `agent` system message 1, frozen per sitting; the greeting's newest memories;
  the twin's input.
- `turn-plan`: Jev call 1 and the cast plan ask `earlier`; a turn can be deep for recall alone.
- `follow-plan`, `debate-plan`, `watch-direction`: the `earlier` gate rides each plan and starts recall as each mode
  allows.
- `deep-turn`: the deep work runs documents and recall together on a shared query; a recall-only turn never rewrites.
- `retrieval`: the search runs over a corpus, with the same results for documents.
- `question-bank`: the `earlier`, `recall`, `importance` and `memory_guard` entries.
- `system1-trace`: `earlier` and `recall` rows; pause runs are never in System 1.
- `provider-gateway`: the `memory_guard` purpose; runs' calls are marked as never pausing sessions.
- `budget-caps`: memory purposes never pause live sessions at the daily cap.
- `session-runtime`: the stream-left, idle and turn-end triggers; runs live outside the actor; the start-up sweep.
- `event-streams`: the last subscriber leaving a session stream is noticed.
- `session-lifecycle`: `leave` and `end` start a run; a fork's checkpoint and its message vectors; deletes cancel
  runs.
- `session-event-sourcing`: the three run columns are exempt bookkeeping.
- `data-storage`: migration 0005; the message vector tables at startup.
- `embedding-spaces`: message vectors, and the build's `message` kind.
- `ai-ports`: `MemoryWriter.on_stretch`, `SessionRecall`, the writer per profile.
- `http-api`: the memory list drops a dangling `sourceSessionId`.
- `client-contract`: MockClient parity for that rule, in the portable suite.
- `evaluation-harness`: the `memory` suite, the new `decisions` slices and the two judge rows.

## Impact

- **Backend:**
  - `sessions/` (turn, commands, lifecycle, actor, manager, summary, deep, plans, follow, debate_plan, watch_plan);
  - `services/memory/` (store, forget, plus the new run, stretch and block modules);
  - `ai/` (ports, profile, retrieval, the new memory graph, `agent/` planner, cast_plan, follow_plan, debate_plan,
    deep, gates, persona, turn; questions);
  - `gateway/` (context, pipeline), `db/` (spaces, tables, migration 0005), `services/knowledge/build.py`,
    `api/streams.py`, `contract/mappers.py`, `runtime.py`;
  - `evals/`.
- **Frontend:**
  - `features/profile/tabs.tsx` (pagination, ribbon);
  - the MockClient's memory read;
  - `domain/personaPrompt.ts` (the twin);
  - `runtime.config.ts`.
- **Config:** `memory.*` and `retrieval.agent.recall*` in `runtime.json`; the bank entries.
- **Spend:**
  - `naive` users with a key start paying for one rewrite call per sitting (≈ $0.001, doc 09 M13);
  - `agent` adds Jev importance and guard (≈ $0.0002–0.0005 a sitting), and recall's Jev call 2 on gate-yes turns.
- **Docs:** everything doc 09 §6 lists, doc 09's built notes, W6's and W12's M13 rows, and the new
  `docs/ai/checks/m13.md`.
- **Not touched:**
  - the HTTP contract and wire schemas;
  - M14's nouls and `message_ai_meta.safety`;
  - the `naive` memory arm and `conversations` (paid at M15).

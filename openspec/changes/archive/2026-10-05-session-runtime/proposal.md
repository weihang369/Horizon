# Proposal: session-runtime (M3)

## Why

After M2, Horizon can spend money safely: it has the gateway, caps, ledger, energy writes and the Decider. It still can't hold a conversation, though. Every session write and every chat, debate and watch command on the `HttpClient` rejects with `later("M3")`, so the app running against the local backend can only replay recordings. M3 is the milestone that makes sessions live:
- a per-session actor that owns every session write;
- the turn loop that runs AI ports through the M2 gateway;
- the debate and watch machines;
- the session lifecycle (create, fork, end, delete);
- the `HttpClient` methods for all of it.

The design pack locks the shape (doc 01 §4.2–4.3, doc 05, doc 06 M3), and the MockClient is the behavioural oracle the backend must match.

## What Changes

- **SessionActor and LiveSessionManager.**
  - One asyncio actor per open session, with an inbox. **Every write to a session's rows goes through it.**
  - The actor owns the event and message `seq` counters. It ports the MockClient's `liveSession()` preconditions: what is refused before 202, and what is not (auto-resume; energy exhaustion arrives as an event).
  - The 8-step turn loop, with `messageId` allocated before the engine runs.
  - TracePatch merging, with the actor-owned sections protected, and the full `insight` with `TurnTrace.calls`.
  - Stop/pause within 500 ms. Prefetched openings (N ≤ 2) still drain energy when discarded (D-77). Token coalescing in which what is stored equals what was streamed.
  - Idle shutdown. One streaming session at a time (409 + `activeSessionId`).
- **Session lifecycle.**
  - Create, with cast-size, approval and same-world checks.
  - Fork, which cuts the events at `atSeq`, finishes the turn in flight at the playhead and re-reduces. It equals the MockClient's fork through a shared cross-language fixture.
  - Rename, delete (via the actor, then a purge-outbox row), leave (`navigated_away`), end.
  - Markdown export with citation footnotes (D-59).
- **Commands.** Every chat, debate and watch command in doc 03, all answered with 202 and their results delivered on the session stream:
  - the group responder policies with the Jev router;
  - the debate phase machine;
  - watch pacing and the turn cap through `clock.sleep`.
- **AI ports (`horizon/ai/ports.py`).**
  - `TurnEngine`, `Router`, `ReactionPredictor`, `DebateHost`, `WatchDirector`, `Summariser` and `Guardrail`, each over frozen Pydantic contexts, each with a deterministic scripted placeholder.
  - Naive real implementations: the **DeepSeek TurnEngine** (NFR-35 prompt order, a half-drop cache-friendly window, an inline `<e:label>` tag parser pinned by shared fixtures) and the **Jev Router** (400 ms, deterministic fallback).
  - `HORIZON_AI_PROFILE` selects the profile, with per-port overrides.
  - A no-op `AiStateHooks` plus the at-least-once `ai_purge_queue` worker.
- **Spend wiring.**
  - Every turn call goes through the M2 gateway with a turn-scoped `call_ctx`.
  - A reply drain becomes a stored session `energy` event.
  - Exhausted speakers are skipped, or get a note and an `energy_exhausted` error.
  - When the daily cap is reached mid-session, the live session pauses with `daily_budget`, and sends are refused until there is room (STATE-06).
  - The scripted profile bills **simulated** spend through the same pipeline, so caps, energy and Insight behave exactly as on the MockClient.
- **Virtual time for tests.** The test clock becomes a real virtual-time scheduler: `sleep` waits until `/_test/clock` advances past it, and an advance returns once the work it woke has settled. That's what lets the portable suite's `tick(ms)` drive live sessions over HTTP.
- **Test routes:** `/_test/ai-profile`, `/_test/decider-fixtures` (deferred from M2), and the scenarios `character_exhausted`, `rush_hour` and `stream_cut`.
- **One timing source.** The simulated-AI timings (`mock/timing.config.ts`) and the new runtime knobs (reply caps, window, coalescing, idle timeout) are emitted into `seed/runtime.json` by the seed build, so the backend and the mock read one table, and `seed:check` guards it.
- **HttpClient.**
  - `sessions` create/rename/delete/forkSeedSession/export/leave/end, plus `chat`, `debate` and `watch` in full.
  - The HTTP portable suite moves to `supports: "M3"`.
  - The knowledge-citation portable test is re-tagged M5, because retrieval and seed indexing arrive there.

There are no **BREAKING** changes. The contract stays additive (`schemaVersion` 1), `schema.json` is unchanged, and the MockClient's behaviour is unchanged.

## Capabilities

### New Capabilities
- `session-runtime`: the SessionActor and LiveSessionManager. It covers:
  - the write inbox, seq ownership and the command preconditions;
  - the turn loop, trace ownership and `insight`, and `message_citations`;
  - stop/pause timing, prefetched openings (D-77), token coalescing and idle shutdown;
  - the energy gate in turns, the cap pause (STATE-06), and the guardrail block scrub.
- `session-lifecycle`: session create, fork (cut + finish the turn in flight + re-reduce), rename, delete, leave, end and Markdown export.
- `session-modes`: what each command does per mode, covering
  - 1:1, and group responder policies and routing;
  - mentions, next-speaker and mute;
  - the debate phase machine, moderator commands and verdicts;
  - watch play/pause/step/pace/direct/step-in/extend/summarise and the turn cap.
- `ai-ports`: port protocols and frozen contexts, profile selection, the scripted placeholders, the naive DeepSeek TurnEngine (window, tag parser), the Jev Router, and `AiStateHooks` with the purge outbox worker.

### Modified Capabilities
- `session-event-sourcing`:
  - live sessions stay event-sourced, so the projection is updated in the same transaction as the events and replay equals live;
  - fork is pinned by a cross-language fixture.
- `event-streams`:
  - session-stream live delivery (register, replay, drain with no gaps or duplicates);
  - `entity.changed { kind: "session" | "usage" }` announcements;
  - `budget.warning` mirrored onto the live session's stream.
- `http-api`:
  - the session write routes and every session command route (202, with the pre-202 rejection list);
  - the test-only routes, which gain the virtual-time `clock` semantics, `ai-profile`, `decider-fixtures` and the M3 scenarios.
- `provider-gateway`: a scripted chat source. It runs simulated streams through the same paid-call pipeline, never reaches the network, and labels its ledger rows `provider: "scripted"`.
- `http-client`: the session, chat, debate and watch methods move off `later("M3")`, and the "not available yet" example moves to a later milestone.
- `client-contract`:
  - the HTTP portable run supports M3;
  - the knowledge-citation test is re-tagged M5;
  - assertions on events collected over a stream wait for delivery.

## Impact

- **Backend, new:**
  - `horizon/ai/{ports,contexts,profile,scripted,naive_turn,tag_parser,router,hooks}.py`;
  - `horizon/runtime_sessions/` (actor, manager, turn loop, coalescer, modes, fork, export; names settled in design);
  - `horizon/services/purge.py`;
  - `horizon/domain/vclock.py` (the virtual-time scheduler);
  - session and command routes in `api/routes.py`.
- **Backend, changed:**
  - `domain/clock.py`: `FrozenClock.sleep` waits for virtual time;
  - `runtime.py`: manager, purge worker, profile and the LLM semaphore;
  - `gateway/{context,pipeline}.py`: turn-scoped `call_ctx`, the scripted source;
  - `api/streams.py`: live drain;
  - the `/_test` router: scenarios, ai-profile, decider-fixtures;
  - the M1b `FrozenClock` unit test is rewritten for the new semantics.
- **Database:** no migration. The `sessions`, `participants`, `session_events`, `messages`, `turn_traces`, `message_citations`, `session_summaries`, `ai_purge_queue` and `usage_records.message_id` structures already exist.
- **Seed:** a new `seed/runtime.json`, generated by `frontend/scripts/seed-build` from `mock/timing.config.ts` plus a new `runtime.config.ts`, and checked by `seed:check`.
- **Shared fixtures:** `backend/tests/fixtures/{fork,tag_parser}/`, consumed by both the TS and Python tests.
- **Frontend:**
  - `client/http/HttpClient.ts` (all M3 methods);
  - `clientContract.http.test.ts` (`supports: "M3"`);
  - `clientContract.portable.ts` (the citation test re-tagged M5; stream-collected assertions wrapped in `eventually`);
  - a fork fixture test.
  - No UI changes, and no MockClient behaviour changes.
- **Out of scope:**
  - JobScheduler, character jobs and `characters.update` (M4);
  - knowledge retrieval, `QueryBundle` vectors, `MemoryStore.apply` and Forget (M5);
  - the `VITE_HORIZON_CLIENT` default flip and E2E on the HttpClient (M6);
  - `chat.continue`;
  - naive DebateHost/WatchDirector/Summariser/ReactionPredictor/Guardrail (AI stage).

# Tasks

> **Before starting:** confirm or override design.md OQ-1…OQ-14. The tasks below implement the recorded defaults.
>
> **Constraints for every task:**
> - no network in automated tests (the socket guard stays);
> - only obviously fake `sk-or-test-…` keys;
> - the contract stays additive and `schema.json` unchanged;
> - the MockClient's behaviour is unchanged;
> - commits without Claude attribution.
>
> **Slices (OQ-1).** Each numbered group ends with its own tests green. Commit at group boundaries when the gates pass.

## 1. Clock, config and scaffolding

- [x] 1.1 Implement virtual time (design D2):
  - `domain/vclock.py`: the timer heap, the `Activity` tracker with contextvar tokens, and `settle()` with a 10 s guard that names the busy holders;
  - `FrozenClock.sleep` waits;
  - `advance` is async;
  - `release` wakes pending timers.

  Rewrite `test_frozen_sleep_advances_virtual_time`. Verify with unit tests for:
  - ordered firing of same-instant timers;
  - settle waiting for a woken task's follow-up DB write;
  - the guard error naming a stuck holder;
  - release waking sleepers.
- [x] 1.2 Make `/_test/clock` await `advance`. Add `rt.spawn(name, coro)` (a task with an activity token). Add a test that fails if `horizon/sessions/**` or `horizon/ai/**` call `asyncio.create_task`. Verify: the existing M1b/M2 suites stay green, and the clock route scenario "Advance time" still passes.
- [x] 1.3 Add `frontend/scripts/seed-build/runtime.config.ts` and emit `seed/runtime.json` with `{ timing: DEFAULT_TIMING, runtime: {...} }` (design D9). Add `domain/runtime_config.py` to load it. Verify: `npm run seed:build` writes the file, `seed:check` passes and fails after a hand edit, and a Python test loads every field.
- [x] 1.4 Create the package skeletons `horizon/sessions/` and `horizon/ai/{scripted,naive}/`. Extend mypy strict to `horizon.sessions.*`, `horizon.ai.*` and `horizon.domain.vclock`. Verify that `uv run mypy` and `ruff` are clean.

## 2. Event writer and actor core

- [x] 2.1 Build `sessions/writer.py` `EventWriter`:
  - seq counters from `MAX`;
  - `append(events)` reduces with `services/runtime/reducer.py` and upserts the session, participants, messages, `turn_traces` (from `insight`) and `message_citations` in **one** writer transaction;
  - it publishes to the session channel only after commit.

  Verify: an integration test appends a scripted event list (from a seed session's events) to a fresh session and asserts that `reduce(GET events) == GET messages` and that the seqs are consecutive.
- [x] 2.2 Build `sessions/actor.py` `SessionActor`: the inbox, `submit(cmd) → Accepted | error` futures, the turn queue with front-insertion, a child turn task, the write lock, and activity tokens around every step. Verify: a unit test sends 20 concurrent `append` commands, and the stored seqs are strictly consecutive and not interleaved.
- [x] 2.3 Build `sessions/manager.py` `LiveSessionManager`: get-or-create under a lock, a `generating()` registry, `active_session_id`, and shutdown. Wire it into the Runtime start/stop and factory reset. Verify: an integration test where two `get` calls race returns one actor, and factory reset leaves no actor.
- [x] 2.4 Write `sessions/preconditions.py` (design D4): the generating vs plain command table, key/cap/seed/ended/mode/conflict/empty-text rules and the auto-resume decision. Verify with table-driven unit tests, one per rejection row in the `http-api` "Session command routes" requirement.
- [x] 2.5 Add the command routes skeleton in `api/routes.py` for every doc 03 command. Each route validates the body, calls `manager.submit` and returns 202 `{}`. Commands without a handler yet reject with a clear 501-style `validation`, which is removed by group 9. Verify with a route test: an unknown session gives 404, a seed session 409, and a missing key 400 `missing_key`.

## 3. Ports, contexts, profile and the scripted source

- [x] 3.1 Write `ai/contexts.py` and `ai/ports.py`: the frozen Pydantic `TurnContext`/`SessionContext` with `call_ctx(purpose)` bound to the session/world/character/message, the `TurnEvent` union, `TracePatch`, `RoutingDecision`, `QueryBundle` (text only) and every Protocol from doc 05 §2.2 that M3 uses. Verify: a JSON round-trip test, and that the contexts are immutable (an assignment raises).
- [x] 3.2 Write `ai/profile.py`: `HORIZON_AI_PROFILE` plus `HORIZON_AI_<PORT>` overrides (defaulting to naive when a key is set, scripted otherwise), and the OQ-3 rule that only `turn` and `router` have naive implementations. Add `POST /_test/ai-profile {profile, overrides?}`. Verify: unit tests for the defaults and an override, and a route test showing it is 404 outside test mode.
- [x] 3.3 Add the gateway's scripted source (design D10):
  - `Gateway.simulated_stream(ctx, spec)` and `Gateway.simulated_decision(ctx, tokens_in)` reuse preflight/record/settle/hook;
  - the in-process paced generator runs on the clock;
  - usage comes from the `turnScript.ts` formula, priced from the price table;
  - `provider: "scripted"`;
  - an optional `on_recorded(row_id)` callback on `chat_stream` and `simulated_stream`.

  Verify with integration tests (the provider-gateway "Scripted chat source" scenarios, with the socket guard on and a real-format fake key):
  - a ledger row is written and the drain applied;
  - a cap refusal happens before any chunk;
  - no socket is opened.
- [x] 3.4 Write `ai/scripted/bank.py` (deterministic Python bank: greetings, chat, debate per phase/side, scene, direction, `answerTo`) and the scripted ports: TurnEngine (emotion first, then paced tokens through the source), Router (the mock's scoring, billed through `simulated_decision`), ReactionPredictor, DebateHost (notes, narration, a `makeVerdict` port), WatchDirector, Summariser and Guardrail (pass). Verify: the determinism test (the `ai-ports` scenario "Same input, same reply") and unit tests per port.
- [x] 3.5 Add `ai/hooks.py` (no-op `AiStateHooks`) and `services/purge.py`: the worker wakes on insert and at startup, backs off with an injected sleeper and marks `done_at`. Verify with the `ai-ports` scenario "Retried after a crash" (insert a row, restart the runtime, and the hook is called once and marked done).

## 4. Turn runner and the 1:1 slice

- [x] 4.1 Build `sessions/turn.py` `TurnRunner` (design D5):
  - the speaker energy gate, `messageId` allocation and the preamble (`turn.next`, then `turn.thinking` after `thinkingMs`);
  - lazy `turn.start` and the `TurnEvent` mapping;
  - the owned-key `TracePatch` rejection and the full `insight`;
  - `usage`, `trace.model` and `trace.calls` from the ledger;
  - the `energy` event after the drain.

  Verify with integration tests for the `session-runtime` requirements "Turn order", "Trace ownership" (both scenarios) and "Reply drains energy as a session event".
- [x] 4.2 Add citation filtering at `turn.end` and the `message_citations` rows. Verify with the scenario "Unused citation dropped", using a test engine that yields a `CitationMap`.
- [x] 4.3 Implement session create in `sessions/lifecycle.py` (port `createSession`): cast validation, the per-mode defaults, the opening `session.state`, `energy` per participant, and greet/start through the queue. Add `POST /sessions` (201). Verify with the `session-lifecycle` scenarios "Wrong cast size", "Character from another world" and "1:1 greeting", the last driven by `clock.advance`.
- [x] 4.4 Write `sessions/modes/one_on_one.py`: send (user message, then the reply queued, auto-resume) and regenerate (a new variant). Verify:
  - the `session-runtime` scenario "1:1 reply events" (every event type, consecutive seqs);
  - "Regenerate keeps the original";
  - "Paused 1:1 auto-resumes";
  - the `session-event-sourcing` scenario "Live exchange reduces to the snapshot".
- [x] 4.5 Add the post-turn reactions (a scripted ReactionPredictor background task through `rt.spawn`, delays from the timing table) and the `turnGapMs` between queued turns. Verify: reactions arrive 300–800 ms of clock time after `turn.end`, and never delay the next speaker's `turn.next`.
- [x] 4.6 Implement the settings commands (`set-emotion`, `set-emotion-mode`, `set-responder-policy`, `set-music-policy`, `set-readable-mode`) and `mute`. Verify with the `session-modes` scenario "Readable mode on", plus a `set-emotion` test (no `messageId`, `source: "user"`).
- [x] 4.7 Implement the `http-api` "Accepted send" and "Retried command" scenarios: the user message is stored before 202, and a replay through the idempotency middleware stores one message. Verify with a route integration test.

## 5. Streaming, stop and idle

- [x] 5.1 Write `sessions/coalesce.py` (design D6) and wire it into the runner. Verify:
  - unit tests for each flush rule (48 characters, 50 ms of clock time, a non-token event, turn end, the trailing timer);
  - the `session-runtime` scenario "Replay equals live" over a naive-style 1-character-delta test engine.
- [x] 5.2 Session stream live delivery. Verify with integration tests over SSE for the `event-streams` scenarios "Live events during replay" and "Reconnect mid-reply" (drop at seq 30, reconnect with `Last-Event-ID`, assembled text == stored content). Fix `api/streams.py` only if a test shows a gap.
- [x] 5.3 Implement stop/pause/leave/end in the actor (design D3 `keepCurrentTurn` semantics): clear the queue, cancel the child task, and close the partial message as `interrupted`/`user`. Verify:
  - the "Stop mid-stream" scenario: content == streamed text, and the estimate ledger row is kept;
  - a real-time test with the SystemClock and a slow stream asserting a ≤ 500 ms deadline.
- [x] 5.4 Idle release: after 10 minutes of clock time with no subscribers or work, the actor stops; the next command re-creates it from storage. Verify with the `session-runtime` scenarios "Command after idle release" and "Restart continues the sequence".
- [x] 5.5 Add the `stream_cut` scenario and the one-shot fault in the runner (design D15). Verify with the `http-api` scenario "Stream cut": an `error(network)` event, then `turn.end { interrupted, interruptedBy: "error" }`, the partial text kept, and the estimate row recorded.

## 6. Energy, caps and the remaining scenarios

- [x] 6.1 Energy gate paths in modes: the 1:1/mention/Ask asleep note plus `energy_exhausted`, and the auto-turn skip with `routing.skipped`. Verify with the `session-runtime` scenarios "Mentioned character asleep" and "Threshold follows the period".
- [x] 6.2 Add the `character_exhausted` and `rush_hour` scenarios (design D15): a seed-only reset, the `exhausted_takeshi` patch and `mock.reset`; the test-mode `period_override`. Verify with the `http-api` scenario "Scenarios mirror the mock", and that a user-created fork keeps its messages afterwards (the portable "overlay scenario" test logic, run in Python).
- [x] 6.3 Implement the cap pause in the manager (design D7): on crossing or on a `daily_budget_exceeded` refusal, pause every active session with `daily_budget` (`keepCurrentTurn`); a refused turn leaves no message; generating commands are refused while the cap is still reached. Verify with the scenario "Cap reached by the greeting", plus a crossing test where the cap is raised mid-session and the sessions resume.
- [x] 6.4 Mirror `budget.warning` onto the live session's stream. Verify with the `event-streams` scenario "Warning inside a session".
- [x] 6.5 Announce `entity.changed { kind: "session" | "usage" }` after commits. Verify with the `event-streams` scenario "Session created", and a usage announcement after a reply.
- [x] 6.6 Add `POST /_test/decider-fixtures {set|clear}` on top of M2's `DeciderFixtures`. Verify with the `http-api` scenario "Decider fixture over HTTP": the router is naive by override and the fixture picks the speaker, with no route ledger row.

## 7. Group, router and prefetch

- [x] 7.1 Write `sessions/modes/group.py`: mentions first (`forcedSpeaker`), then the policies `auto`/`everyone`/`mentioned`, muted and exhausted skips, and the routing trace on every reply. Verify with the `session-modes` scenarios "Auto policy with a mention" and "Route call in the trace".
- [x] 7.2 Implement `everyone-answer` and `next-speaker` (nudge / random eligible), and route-call capture into `TurnTrace.calls` for every reply of a send (OQ-13). Verify with "Muted participant is skipped", and that two replies of one send both list the same `route` call.
- [x] 7.3 Write `ai/naive/router.py` (design D12): one Decider choice question, `queue` ≤ 2 above p 0.25, and the deterministic fallback (`fallback: true`, no candidates). Verify with respx/fake-provider tests: an answer is used, a 400 ms timeout gives the fallback with the late answer still recorded, and an invalid answer gives a partial fallback.
- [x] 7.4 Prefetched openings (design D5): N ≤ 2 for group `everyone-answer` and the debate opening round, buffered unsequenced, released at speaking pace, and `link_message` on release. Verify:
  - released prefetches produce the same events as non-prefetched turns;
  - `trace.calls` lists the reply;
  - `llm_slots` never exceeds 4.
- [x] 7.5 Implement the D-77 discard. Verify with the scenario "Stop during a debate opening": the prefetched row keeps `message_id` NULL, energy is drained, and no event mentions the discarded reply.
- [x] 7.6 Measure the preflight lock (OQ-7): log the p95 lock wait in the group/prefetch tests. Verify the number is recorded in the test output, and add a `spentToday` cache only if p95 > 20 ms (document the result in design.md).

## 8. Debate

- [x] 8.1 Write `sessions/modes/debate.py`: the phase machine (setup → phases → verdict → ended), `phaseOrder`, round notes and host narration, `forcedBy: "round_order"` and debate tags, auto-advance after `pauseMs`, and cursor rebuild for forks/resumes. Verify with the scenario "Quick debate to a verdict" (4 character messages, a `verdict` message, ended).
- [x] 8.2 Implement pause/resume/next/extend-round/skip-to-closing/interject/auto-advance. Verify with unit or integration tests for each: an extended phase repeats with `iteration` 2, and skip lands on closing at the boundary.
- [x] 8.3 Implement Ask at the boundary, from the queue front. Verify with the scenario "Ask lands at the boundary".
- [x] 8.4 Implement the verdict paths: arbiter (a billed `simulated_decision`, `Verdict` scores 0–10), user (wait for `pick`), none/panel, and `end(withVerdict)`. Verify with the scenario "User decides", plus an arbiter test checking rubric scores within 0–10.

## 9. Watch

- [x] 9.1 Write `sessions/modes/watch.py`: the premise `direction` message, round-robin from `openingSpeaker`, `paceMs` gaps on the clock, `turnsTaken` (`watch.state` + `session.state`) and the `turn_cap` pause. Verify with the scenario "Stop at the cap, then extend".
- [x] 9.2 Implement play/pause/step/pace/direct (2 turns)/step-in (pause, then up to 2 replies)/next-speaker/summarise (billed, a `summary` message), and the everyone-asleep pause. Verify with "Step while paused", plus tests for direct, step-in and the everyone-asleep note.
- [x] 9.3 Remove the remaining "not implemented" command stubs from task 2.5. Verify: a test iterates every doc 03 command route and none answers with the stub error.

## 10. Naive TurnEngine

- [x] 10.1 Write `ai/naive/tag_parser.py` and the shared fixtures `backend/tests/fixtures/tag_parser/*.json` (split tag, invalid label, no tag, stray mid-text tag, 32-character overflow, missing `>`), plus a TS reference parser test over the same files. Verify: the `ai-ports` scenarios "Tag split across chunks" and "Invalid label" pass in Python, and `npm test` runs the TS fixture test green.
- [x] 10.2 Write `ai/naive/prompt.py` (the scripted `PromptCompiler`: persona fields, SFW/adult clause, You card) and `ai/naive/window.py` (the `windowTokens` window, half drop, Summariser refresh into `session_summaries`). Verify with the scenarios "Window drops half at once" and "Prefix stays stable between drops".
- [x] 10.3 Write `ai/naive/turn.py`: one `chat_stream` with reasoning off and `max_tokens` from `replyMaxTokens`, the warm-prefix hash passed to `chat_estimate`, tag parsing, and mid-stream errors keeping the partial text. Verify with fake-provider integration tests: a streamed reply, the warm flag on a repeated prefix, and a mid-stream error ending `interrupted`.
- [x] 10.4 Implement the guardrail block scrub (design D13). Verify with the `session-runtime` scenario "Blocked after streaming", using an injected blocking Guardrail.
- [x] 10.5 Add the naive-mode live test (`tests/live/test_live_sessions.py`, `-m live`, manual): one 1:1 reply and one group send with the Jev router. It prints the summed `cost_usd` of `is_seed = 0` rows and asserts ≤ $0.05. Verify that it is deselected by default (`pytest -q` doesn't run it). The user runs it once with their `.env` key; record the result in the archive notes.
  - **Live run (2026-10-05): passed.** The DeepSeek 1:1 reply streamed with a valid tag (`thinking`, source `llm`); the Jev router picked Hana (p 0.76 vs 0.08, no fallback); total spend $0.000479 (limit $0.05).

## 11. Lifecycle: fork, export, rename/leave/end/delete

- [x] 11.1 Extract `forkEvents` into `frontend/src/engine/fork.ts`, and make `MockClient.fork` call it with no behaviour change. Add a generator script that writes `backend/tests/fixtures/fork/*.json` (seed sessions at several `atSeq`, including a mid-stream cut, with a fixed new session ID) and a TS fixture test. Verify: `npm test` is green, including the existing fork/mock tests.
- [x] 11.2 Write `sessions/fork.py` (an exact port) and `POST /sessions/{id}/fork` (201, key required, one transaction, then the opening `session.state` through the new actor). Verify:
  - the `session-event-sourcing` scenario "Fork fixture in both languages";
  - the `session-lifecycle` scenarios "Fork a debate at a third of the way" and "Resume a forked debate".
- [x] 11.3 Implement rename (`PATCH`), leave and end through the actor. Verify with the scenario "Send after end", a rename test (80-character trim, `titleIsCustom`, a `session.state` settings event for a live session), and that leave does nothing on a seed session.
- [x] 11.4 Implement delete: stop the actor, delete in one transaction, then a purge row and `entity.changed`. Verify with the scenario "Delete a streaming session": the ledger row remains and a purge entry with scope `session` exists.
- [x] 11.5 Write `sessions/export.py`, a byte-for-byte port of `exportMarkdown`/`footnoteCitations`, and `GET /sessions/{id}/export` (`text/markdown`). Verify with the scenario "Seed debate export", plus a byte comparison with the MockClient's export of the same seed session, through a fixture generated by the TS script from 11.1.
- [x] 11.6 Implement the "Interrupted streams at startup" scenario for live sessions: stop the runtime mid-reply, restart it, and the message is closed by stored events while the reduction still equals the snapshot. Verify with an integration test, reusing M1b's `close_interrupted_streams`.

## 12. HttpClient and the portable suite

- [x] 12.1 Implement `sessions.create/rename/delete/forkSeedSession/export/leave/end` in `HttpClient`, with text responses for export in `transport.ts`. Verify: `http.test.ts` unit tests for each method (route, method, `Idempotency-Key` on POSTs), and `npm run typecheck`.
- [x] 12.2 Implement every `chat`, `debate` and `watch` command in `HttpClient` (resolving on 202), and move the "not available yet" unit test example to `jobs.start` (`availableIn: "M4"`). Verify with the `http-client` scenarios "Send over HTTP", "Conflict surfaces with details" and "Sending a chat message in M1b" (updated), as unit tests.
- [x] 12.3 Edit the portable suite (design D16):
  - wrap the stream-collected assertions (`events`, `globals`, `got`) in `eventually`;
  - re-tag "knowledge (D-59): live replies cite indexed passages" as `"M5"`;
  - narrow `Milestone` in `HttpClient.ts` to `"M4"|"M5"|"M6"`.

  Verify: the MockClient portable run (`npm test`) still passes every test with none pending.
- [x] 12.4 Switch the HTTP harness to `supports: "M3"`. Verify: `npm run test:http` passes every M1b/M2/M3 test, and lists M4/M5/M6 (including the citation test) as pending, matching the `client-contract` scenario "HTTP run in M3".

## 13. Integration and gates

- [x] 13.1 Extend the leak sweep (`test_leak_sweep`) to session SSE frames, the Markdown export and `turn_traces` after a live exchange with a key set. Verify that no `sk-or-` string appears outside the redaction token.
- [x] 13.2 Run an end-to-end scripted pass in Python: 1:1, group, debate and watch each run to completion on the virtual clock in one test module, with `reduce(events) == messages` asserted for each and every response schema-validated. Verify that the module is green.
- [x] 13.3 Update the docs: `docs/backend/01-architecture.md` §4.7 (virtual-time `sleep` semantics), `docs/backend/05-ai-seams.md` §1 (per-port overrides, scripted spend is simulated), `docs/backend/06-milestones.md` (citation test → M5), and `docs/requirements/09-decision-log.md` (D-81 for scripted simulated spend, D-82 for virtual-time test clock semantics). Verify: the links resolve and `openspec validate session-runtime --strict` passes.
- [x] 13.4 Run the full gates:
  - backend: `uv run pytest -q`, `uv run ruff check`, `uv run mypy`;
  - frontend: `npm test`, `npm run typecheck`, `npm run lint` (no new warnings), `npm run test:http`, `npm run seed:check`, `npm run export-schema:check` (unchanged), and `npm run e2e` (MockClient).

  Verify that all are green, and record the counts in the final apply summary.

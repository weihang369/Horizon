# Design: session-runtime (M3)

## Context

See proposal.md for the motivation. This section records what M3 builds on.

- **From M1b:**
  - the SQLite schema for sessions, participants, events, messages, traces, citations, summaries and the purge queue;
  - `services/runtime/reducer.py`, a port of `sessionReducer.applyEvent` pinned by shared fixtures;
  - the EventBus and the session SSE route, which already registers the live queue, replays in pages and drains with `seq ≤ last` skipping;
  - startup closing of interrupted streams;
  - the idempotency middleware;
  - the `/_test/clock` and `/_test/scenario` routes. `SCENARIOS` is still empty.
- **From M2:**
  - the `Gateway` pipeline (`chat_stream`, `decide`, `paid`) with reservations, caps and the ledger, including the reply drain inside the ledger transaction;
  - `call_ctx(purpose)`, with `drains` derived from the purpose;
  - `LedgerWriter.calls_for_message` / `reply_usage`;
  - the `Decider` with fixtures;
  - `EnergyLocks` and `EnergyParams`;
  - `FakeOpenRouter` in test mode.
- **The oracle is the MockClient.** Its engines (`mock/engines/*`, `turnScript.ts`) define the event order, timing, preconditions, fork renaming and export format that the portable suite asserts.
- **Clock gap.** The portable suite drives time with `tick(ms)`, and over HTTP that is `POST /_test/clock {advanceMs}`. M1b's `FrozenClock.sleep` *advances* time instead of waiting for it. Live sessions over HTTP can't be tested until that changes (D2).

## Goals / Non-Goals

**Goals:**
- Every M3 portable test passes on the HttpClient against a test-mode backend, except the live knowledge-citation test, which is re-tagged M5 (OQ-2). Each one keeps passing on the MockClient.
- Live behaviour is deterministic under the frozen clock (scripted profile), so the tests are reproducible on Windows.
- AI ports are swappable without backend changes: the actor never inspects which implementation runs.

**Non-Goals:**
- No new contract types or `schema.json` changes.
- No changes to the MockClient's behaviour. Two refactors are allowed: extracting pure functions it already uses (the fork) and emitting its timing table into the seed.
- No naive DebateHost, WatchDirector, Summariser, ReactionPredictor or Guardrail (OQ-3).
- No retrieval: `QueryBundle` carries text only.

## Decisions

### D1. Module layout

| Module | Role |
|---|---|
| `horizon/sessions/actor.py` | `SessionActor`: the inbox, the command dispatch, the turn queue, stop/pause, idle release |
| `horizon/sessions/manager.py` | `LiveSessionManager`: get-or-create under a lock, the "who is generating" registry, cap pause fan-out |
| `horizon/sessions/writer.py` | `EventWriter`: appends events, runs the reducer and projects the session, participants, messages, traces and citations in **one writer transaction**, then publishes after commit |
| `horizon/sessions/turn.py` | `TurnRunner`: the doc 01 turn loop, mapping `TurnEvent`s to contract events, trace merging, usage from the ledger, energy event, prefetch buffer |
| `horizon/sessions/coalesce.py` | Token coalescer (D6) |
| `horizon/sessions/preconditions.py` | The pre-202 rules (D4) |
| `horizon/sessions/modes/{one_on_one,group,debate,watch}.py` | Mode logic, ported from the mock engines; it calls the TurnRunner and never writes rows directly |
| `horizon/sessions/{lifecycle,fork,export}.py` | Create/rename/leave/end/delete, fork (D8), Markdown export |
| `horizon/ai/ports.py`, `ai/contexts.py` | The Protocols and the frozen Pydantic contexts (`TurnContext`, `SessionContext`, `TurnEvent` union, `TracePatch`, `RoutingDecision`, `QueryBundle`) |
| `horizon/ai/profile.py` | `HORIZON_AI_PROFILE` + per-port overrides, settable at runtime by `/_test/ai-profile` |
| `horizon/ai/scripted/` | Placeholders for every port, the Python bank and the scripted provider source |
| `horizon/ai/naive/{turn,window,tag_parser,prompt,router}.py` | DeepSeek TurnEngine and Jev Router |
| `horizon/ai/hooks.py`, `services/purge.py` | `AiStateHooks` (no-op) and the purge worker |
| `horizon/domain/vclock.py` | The virtual-time scheduler behind `FrozenClock` (D2) |

The Runtime gains `sessions` (the manager), `ai` (the resolved ports), `llm_slots` (`asyncio.Semaphore(4)`, shared later with M4's JobScheduler) and the `purge` worker. All of them are started and stopped with the lifespan, and rebuilt by factory reset.

### D2. Virtual time (resolves OQ-10)

- **`FrozenClock.sleep` waits.** It registers a timer `(deadline, seq, future)` in a heap and awaits it.
- **`advance(ms)` becomes async.** It repeats the following until no timer is due at or before the target:
  1. pop the earliest due timer;
  2. set `now` to its deadline;
  3. resolve its future;
  4. `await settle()`.

  It then sets `now` to the target and settles once more. Timers that fall due at the same instant fire in registration order.
- **`settle()`** waits until the runtime's `Activity` counter reaches 0, using an `asyncio.Event` rather than polling, with a 10 s real-time guard that raises with the busy holders' names. Each actor, turn task and background task holds an activity token while it runs. A task releases its token while it waits on the inbox, on `clock.sleep`, or on `llm_slots`. A `contextvar` tells `sleep` which token to release. Tasks with no token (HTTP handlers, SSE generators) don't count.
- **The route.** `/_test/clock` awaits `advance`, so `tick(6000)` returns with the greeting already stored.
- **`set()`** (freezeAt) moves `now` without firing timers. Releasing the clock (`release: true`) wakes every pending timer with the new SystemClock, so nothing hangs.
- **Effect on M1b and M2.** The M1b unit test `test_frozen_sleep_advances_virtual_time` is rewritten for the new semantics. A test that only reads `now()` is unaffected. The M2 corrector uses an injected sleeper, so it is unaffected too.
- **Alternative rejected:** keeping self-advancing sleep and making the HTTP harness poll. Concurrent sleepers would push time forward in arbitrary amounts, and a watch with `paceMs` would race the turn cap. Time-driven tests would no longer be deterministic.

### D3. Actor, inbox and turn queue

- **Two layers.** The actor has two layers:
  - **the inbox**, where commands are handled one at a time and quickly;
  - **the turn queue**, a FIFO of turn tasks run one at a time as a child task. It mirrors the mock's `enqueue/pump`, where steering can go to the front.
- **Command handling.** A command runs its preconditions *inside* the actor, so they can't race. It then writes its immediate events (for example the user `message`) and resolves the caller's future with `Accepted` or a `HorizonHTTPError`. Only then does the route return 202. Work that generates is put on the turn queue.
- **One write path.** Every write goes through the actor's `EventWriter`, which holds the seq counters, initialised from `MAX(seq)` on activation. Turn tasks and reaction tasks call `actor.append(...)`, which takes the actor's write lock. That is the "one writer" rule.
- **Stop / pause / leave / end** run on the inbox immediately; they never queue behind a turn. They:
  1. clear the turn queue;
  2. cancel the child turn task (`keepCurrentTurn` semantics from the mock: `leave`, `end` and the cap pause let a turn that is already streaming finish, while `stop` cuts it);
  3. close the partial message with `turn.end { interrupted, interruptedBy: "user" }`.

  Cancelling the iterator closes the gateway stream, and M2 already records the estimate row. A test asserts the 500 ms deadline in real time with the SystemClock and a slow fake stream.
- **Idle release.** After 10 minutes of clock time with no subscriber, no queued work and no running turn, the actor stops and the manager drops it. The next command re-creates it from storage (seq from `MAX`). The manager checks subscriber counts through `bus.subscriber_count`.

### D4. Preconditions (port of `liveSession()` / `live()` / `command()`)

- **Generating commands** need a usable key (`missing_key` 400, `invalid_key` 401) and a cap below the limit (402):
  - `create`, `fork`;
  - `send`, `regenerate`, `everyone-answer`, `next-speaker`;
  - `debate/resume`, `debate/next`, `debate/ask`, `debate/extend-round`, `debate/end{withVerdict:true}`;
  - `watch/play`, `watch/step`, `watch/step-in`, `watch/extend`, `watch/summarise`.

  These match the commands the MockClient wraps in `this.live`.
- **Every other command** is a plain command: `stop`, `set-*`, `mute`, `debate/pause`, `debate/interject`, `debate/skip-to-closing`, `debate/auto-advance`, `debate/end{false}`, `debate/pick`, `watch/pause`, `watch/pace`, `watch/direct`, `rename`, `leave`, `end` and `delete`.
- **`liveSession()` checks** (seed → 409, ended → 409, another live session → 409 with `activeSessionId`, auto-resume of paused 1:1/group unless still capped) run for the same set as the mock.
- **Mode mismatch.** A debate command in a non-debate session, or a watch command in a non-watch session, → 409.
- **Empty text** → 422.
- **"Generating"** in the manager means a turn is running and the session isn't held, the same as the mock's `live.current && !live.held`.

### D5. The turn loop and the trace

`TurnRunner.run(speaker, opts)`:
1. **Speaker.** The mode or router has already chosen it.
2. **Message ID.** `messageId` (or `variantId` for a regenerate) is allocated.
3. **Energy gate.** The runner settles the speaker's energy with `EnergyParams`. Below `estReplyPoints[period]`, the caller's skip or asleep path runs: an asleep note plus `energy_exhausted`, or a skipped entry.
4. **Preamble.** `turn.next`, then `turn.thinking` after `thinkingMs`.
5. **Engine.** The runner builds the frozen `TurnContext` (with `call_ctx` bound to `message_id`, `character_id`, `session_id` and `world_id`), takes an `llm_slots` slot, and starts the engine. The reservation happens inside the gateway preflight.
   - **`turn.start` is emitted lazily, at the engine's first event.** A refusal before that (a cap, the key, credits) leaves no message. A cap refusal triggers the cap pause (D7). Other refusals become an `error` event with no `messageId`.
6. **Mapping.**
   - `Emotion` → `emotion` (the last one wins);
   - `Token` → the coalescer → `token`;
   - `CitationMap` → kept until the end;
   - `TracePatch` → deep-merged, rejecting the owned keys `model`, `energy`, `routing` and `calls` (logged, then dropped).
7. **End.**
   - `turn.end` is emitted with `status`, `usage` and the filtered `citations`. The citations are filtered to the `[n]` markers present in the content (D-59), and `message_citations` rows are written in the same transaction.
   - `usage` comes from `ledger.reply_usage(messageId)`, which M2 provides: the actual cost, or the estimate for a stopped stream.
   - Then come the `energy` event (settled energy after the drain, plus `spent`) and `insight`, with the full trace.
8. **Trace.**
   - The runner builds `model` from the ledger row and `energy` from the drain.
   - `routing` comes from the router decision.
   - `calls` = the turn-level calls captured for this send (`route`; OQ-13) + `calls_for_message(messageId)`.
   - Post-turn checks (the guardrail) can add a later `insight`, which the reducer already lets replace the first.
9. **Post-turn work.** Reactions (the scripted `ReactionPredictor`, with the chance and delays from the timing table) are scheduled as a background task that appends through the actor and never delays the next speaker. `turnGapMs` passes before the next queued turn.

**Prefetched openings:**
- At most 2 `TurnEngine` runs ahead for the debate opening round and for group `everyone-answer`.
- Their `TurnEvent`s are buffered in memory with no `seq`, and the message ID is allocated but unannounced. They are released through steps 6–8 when the slot comes.
- They hold `llm_slots` and reservations.
- Their calls run with a context that carries no message ID, so their ledger rows start with `message_id` NULL. The drain still happens, since the purpose is `reply`.
- **On release**, the runner sets the row's `message_id` to the released message, a one-row ledger update through `LedgerWriter.link_message(row_id, message_id)`. `reply_usage` and `calls_for_message` then work unchanged. The gateway surfaces the row ID through an optional `on_recorded` callback on `chat_stream`.
- **On Stop**, discarded prefetches are never linked. Their rows keep `message_id` NULL and their drain stands (D-77).

### D6. Token coalescing (resolves OQ-5)

- Deltas are buffered. The coalescer flushes one `token` event when the buffer reaches **48 characters**, or **50 ms of clock time** has passed since its first delta, or the engine yields a non-token event, or the turn ends.
- A trailing flush timer (`clock.sleep(0.05)`) covers an idle stream.
- The flushed event is persisted and then published as the same object, so **stored == streamed by construction**.
- Scripted chunks (`tokensPerEvent: 3`, about 12 characters every 75 ms) mostly pass through one by one. Naive DeepSeek deltas (1–4 characters) shrink about 10×, which keeps the per-subscriber queue (1,000) and SQLite write rate comfortable.

### D7. Energy, caps and the pause (resolves OQ-11)

- **Drain.** The reply drain stays inside M2's ledger transaction. The runner reads the settled energy afterwards and emits the session `energy` event, which the reducer stores on the participant. `entity.changed character` is already published by M2.
- **Pausing at the cap.** After any recorded call, the manager compares `spent_after` with the cap. On crossing it, or when any session's call is refused with `daily_budget_exceeded`, every active live session is paused with `session.paused { reason: "daily_budget" }` through its actor (`keepCurrentTurn`).
- **`budget.reached`** stays as M2 specifies it: it is published only when a call is refused, so `budget-caps` is unchanged. The portable cap test reaches the cap through a refused greeting, because its estimate is already larger than the $0.00005 cap.
- **`budget.warning`.** When M2's gateway publishes `budget.warning` for a call carrying a `session_id`, the manager also appends it to that session's stream. This mirrors the mock.

### D8. Fork (cross-language)

- `forkEvents(events, base, atSeq, newSessionId) → { events, session, messages }` is extracted from `MockClient.fork` into `frontend/src/engine/fork.ts`; it's a pure function. `MockClient.fork` then calls it, with no behaviour change.
- The Python `sessions/fork.py` ports it exactly:
  - extend the cut to the in-flight turn's `turn.end`;
  - rename the session ID;
  - rename message IDs to `msg_<sid>m<i>` in reducer order;
  - rename event IDs to `evt_<sid>e<i>`;
  - renumber `seq` from 1;
  - re-reduce;
  - title ` · live`, `continuedFrom`, `isSeed: false`.
- A TS generator writes `backend/tests/fixtures/fork/*.json` from seed sessions at several `atSeq` values, including a mid-stream cut, with a fixed `newSessionId`. Both languages assert the fixtures.
- The fork is written in one transaction. The live opening `session.state` (paused for debate/watch, active for 1:1/group, nothing if ended) is then appended through the new session's actor.

### D9. One timing and runtime table (resolves OQ-4)

The seed build emits `seed/runtime.json`:
- `timing`: `DEFAULT_TIMING` from `mock/timing.config.ts`, which stays the TS source of truth and keeps the mock unchanged.
- `runtime` from a new `scripts/seed-build/runtime.config.ts`:

```
replyMaxTokens: { one_on_one: 350, group: 250, watch: 220, debate: { short: 200, medium: 320, long: 480 } }
windowTokens: 6000            # history window; drop the oldest half when full
coalesce: { maxChars: 48, maxMs: 50 }
idleReleaseMs: 600000
prefetchMax: 2
llmConcurrency: 4
```

`seed:check` covers the file. The backend reads it through `domain/runtime_config.py`. Demo speed (×2/×4) stays mock-only.

### D10. Scripted placeholders and simulated spend (resolves OQ-9, OQ-12)

- **The scripted provider source** (`ai/scripted/source.py`) gives the scripted ports their "provider":
  - `stream_reply(ctx, text, spec)` → `gateway.simulated_stream(...)`. It runs the M2 pipeline steps (preflight, reserve, record, settle, drain, hook) around an in-process generator. The generator sleeps `firstTokenMs`, then yields `tokensPerEvent` chunks every `1000·tokensPerEvent/tokensPerSec` ms on the clock.
  - Usage follows the `turnScript.ts` formula (system 900 + persona + mode + user + history; the cached share), priced with `prices.chat` and the period.
  - `simulated_decision(ctx, tokens_in)` does the same for the scripted router (600 tokens, matching `ROUTE_DECISION_TOKENS`), the arbiter verdict and the watch summary.
  - Rows carry `provider: "scripted"` and `cost_source: "provider"`.
  - **No network, ever.** A unit test runs it with the socket guard and a real-looking key.
- **Why simulate:** the portable tests (energy drain, `usage.byCategory.chat > 0`, the cap pause, `trace.calls`) and the doc 06 scripted acceptance need priced turns. Free scripted turns would make five M3 portable tests impossible on the backend.
- **Banks.**
  - The Python bank (`ai/scripted/bank.py`) is deterministic: `random.Random(f"{sid}:{turn}")`.
  - Greetings are the character's `profile.greeting`.
  - Chat replies are short generic lines keyed by simple tags.
  - Debate lines come per phase and side; scene and direction lines too.
  - Replies are not byte-identical to the mock, and no portable test needs them to be.
- **Scripted engine.** Emits `Emotion(source="llm")` first, then the paced tokens. On a 1:1 reply, about 70 % of turns get emotion-timing variety ("before"), which is enough for the UI.
- **Scripted router.** Uses mentions, then the mock's scoring (random p in [0.2, 0.75] + a name bonus, policy cut-off). Its decision is billed (above).
- **Scripted DebateHost:** `ROUND n · LABEL` notes, host narration lines, and a verdict built like `makeVerdict`.
- **Scripted WatchDirector:** round-robin.
- **Scripted Summariser:** the last N lines.
- **Scripted Guardrail:** pass, with the mock's two checks.
- **Scripted ReactionPredictor:** `reactionChance` and the mock's emotion list.

### D11. Naive TurnEngine

- **Prompt order** (NFR-35):
  1. a system message from the scripted `PromptCompiler` (persona fields joined, plus the SFW/adult clause and the You card);
  2. a `session_summaries` rolling summary message;
  3. the history window: active variants only, the speaker's lines as `assistant`, others prefixed with their name.
- **Window.** Messages are added until the token count (`count_tokens`) passes `windowTokens`. Then the oldest half is dropped in one step, and the scripted Summariser writes a new `rolling` summary at that `upto_seq`.
- **Warm cache.** The engine keeps the SHA-256 of the system and summary prefix per `(session, speaker)`. `warm=True` is passed to `chat_estimate` when it matches the previous call, which fixes M2's always-`False` default.
- **Request.** `reasoning: {enabled: false}`, `max_tokens` from `replyMaxTokens`, and pinned routing (M2).
- **Tag parser** (`naive/tag_parser.py`). A small state machine implements doc 05 §5. Shared fixtures in `backend/tests/fixtures/tag_parser/` cover:
  - a split tag;
  - an invalid label;
  - no tag;
  - a stray mid-text tag;
  - a 32-character overflow;
  - `>` never arriving.

  The TS side gets a test-only reference parser, so the fixtures are proven language-neutral. The scripted engine's output also passes through the parser.
- **Errors.** Provider errors map through M2. A mid-stream error keeps the partial text (`turn.end interrupted`, `interruptedBy: "error"`, plus an `error` event), the same as `stream_cut`.

### D12. Jev Router

- **The question.** One Decider `choice` question over the eligible cast + `none`. The state is compact: the cast (`id`, name, role, last-spoke turn) and the last 6 lines truncated.
- **Group `auto`.** The top choice is selected. Then `queue` = the next options whose probability is above `0.25`, up to a total of 2.
- **Fallback** (Decider fallback, 400 ms): @mentions, then least-recently-spoken round-robin, `fallback: true` in `calls`, and no `candidates`.
- **Billing.** The route call's ledger row has `message_id` NULL. The runner attaches the call summary to every reply of that send (OQ-13). The fixtures work over HTTP through `/_test/decider-fixtures` (`{ purpose, question, answer }` set/clear).

### D13. Guardrail block scrub (resolves OQ-8)

- A post-turn output check returns `block`.
- The runner then:
  1. appends `error { content_refused, messageId }` and `turn.end { status: "error" }`;
  2. in the same transaction, rewrites the stored `token` events for that `message_id` to an empty delta;
  3. sets the message's content to `""`.
- The scrub runs through the actor's writer, so it is a write like any other.
- Memory exclusion is a no-op until M5.
- Blocking is tested with an injected test Guardrail. The scripted one always passes.

### D14. Lifecycle, export, purge

- **Create** ports `createSession`: defaults per mode from settings, the opening `session.state` and one `energy` per participant, then greet/start through the queue.
- **Delete:**
  1. stop the actor;
  2. delete in one writer transaction (FK cascade);
  3. insert `ai_purge_queue {scope:"session", ids:[sid]}`;
  4. publish `entity.changed session`.
- **The purge worker** wakes on insert and at startup. It calls `hooks.on_delete(scope, ids)`, then marks `done_at`, retrying with backoff on failure. The backoff uses an injected sleeper, the same pattern as the M2 corrector.
- **Export** ports `exportMarkdown` + `footnoteCitations` byte for byte. Seed citations are already stored on the seed messages.

### D15. Test routes and scenarios

- `/_test/ai-profile {profile, overrides?}`.
- `/_test/decider-fixtures {set:[…]} | {clear:true}`.
- `SCENARIOS` gains three entries:
  - **`character_exhausted`:** reset-demo semantics (seed-only, user sessions kept), then apply the `exhausted_takeshi` variant's energy patch, then `mock.reset`.
  - **`rush_hour`:** a test-mode `period_override = "peak"` read by `Clock.pricing_period`, cleared by factory reset.
  - **`stream_cut`:** a one-shot fault (`afterTokens: 24`) consumed by the next character turn. The runner raises `ProviderError("network")` after that many tokens. That cancels the gateway stream, so the estimate row stays, and the turn ends `interrupted`/`error`.

### D16. HttpClient and the portable suite

- **HttpClient.** Every `later("M3")` is replaced by a route call. The transport gains text responses for `export`. Commands post with an `Idempotency-Key` and resolve on 202.
- **Harness.** `supports: "M3"`, and `Milestone` becomes `"M4"|"M5"|"M6"`.
- **Portable suite.** Assertions on `events` / `globals` / `got` collected from subscriptions go through `eventually(...)`. The MockClient delivers synchronously, so its results don't change. The live knowledge-citation test is re-tagged `"M5"`.

### D17. Tooling

- mypy strict on `horizon.sessions.*`, `horizon.ai.*` and `horizon.domain.vclock`.
- The leak sweep gains session SSE frames, the Markdown export and `turn_traces`.
- A pytest helper `drive(rt, ms)` wraps `await clock.advance(ms)` for integration tests.

## Risks / Trade-offs

- [The virtual-time settle deadlocks or misses work (a task without an activity token)] → `settle` raises after 10 s real time, naming the busy holders. Background tasks are created only through `rt.spawn(name, coro)`, which attaches a token. A lint-style test fails if `sessions/` or `ai/` call `asyncio.create_task` directly.
- [The rewritten `FrozenClock.sleep` breaks an existing M1b or M2 test] → grep the existing users in task 1. Only the M1b clock unit test relies on the old semantics, and it is rewritten.
- [SSE delivery is real-time while the clock is virtual, so HTTP tests flake] → `eventually` for stream-collected assertions. State assertions read snapshots, which are consistent by D2.
- [SQLite write load from tokens] → coalescing (D6) and one transaction per flush. A naive reply is about 20–60 writes.
- [Stop within 500 ms on Windows] → cancelling the child task is immediate. Closing the HTTP stream happens in M2's shielded record. A real-time test checks the deadline.
- [The prefetch accounting edge (usage linked by row ID)] → covered by a dedicated D-77 integration test.
- [Simulated scripted spend consumes a real user's daily cap if they pick `scripted` with a real key] → it is opt-in (`HORIZON_AI_PROFILE=scripted`) and labelled `provider: "scripted"` in Usage. The default with a key is `naive`.
- [Scope size: 64 tasks, the largest milestone] → vertical slices (OQ-1). Each slice ends green, and the work can be committed at slice boundaries.

## Migration Plan

- There is no database migration, since every table exists. `seed/runtime.json` is a new seed file and `seed:check` guards it.
- **Rollback:** revert the squash commit. The M2 behaviour and data are untouched (no schema change). Sessions created live under M3 stay readable by M1b/M2 code, which replays only.

## Open Questions

Recommended defaults are recorded here; confirm or override them before apply. The tasks implement the defaults.

| # | Question | Default (implemented) | Why |
|---|---|---|---|
| OQ-1 | One change or a split? | **One change**, ordered as vertical slices: core + 1:1 → SSE/stop → group/router/prefetch → debate → watch → fork/export/lifecycle → HttpClient + portable. Split only if tasks.md grows past ~80 during apply. | The slices share the actor, writer and runner, and splitting would duplicate the scaffolding. tasks.md has 64 tasks. |
| OQ-2 | Live knowledge citations | Re-tagged **M5**. The scripted engine emits no `CitationMap` until retrieval exists. Export footnotes are still tested on the seed debate. | Seed knowledge is `keyword_only`, and retrieval plus "Index seed knowledge" are M5 scope. |
| OQ-3 | Naive versions of the other ports | **Scripted in both profiles.** Naive spend is DeepSeek replies + Jev routing only. | Doc 06 lists only those two as M3 naive deliverables, and the rest are AI-stage designs. |
| OQ-4 | Pacing source | **`seed/runtime.json`** emitted from `timing.config.ts` + `runtime.config.ts` (D9). | One table, guarded by `seed:check`. The mock stays untouched. |
| OQ-5 | Coalescing | **48 characters / 50 ms of clock time / any non-token event / turn end** (D6). | Stored equals streamed by construction, and about 10× fewer rows for naive streams. |
| OQ-6 | `missing_key` under scripted | **Generating commands need a key in every profile** (doc 03). The harness sets `sk-or-test-0001`. | Keeps one rule. The portable "live actions without a key" test agrees. |
| OQ-7 | Preflight lock contention | **Measure it** in the group/prefetch tests (p95 lock wait is logged). Add a `spentToday` cache only if p95 > 20 ms. **Measured during apply:** p95 0.002 ms over the group/prefetch load (`test_preflight_lock_wait_is_measured`), so no cache was added. | Single user. M2 noted it as a possibility, not a problem. |
| OQ-8 | Guardrail scrub scope | **Only the message's own content and token events.** The memory side is a no-op until M5 (D13). | Forget and memory are M5. |
| OQ-9 | Scripted spend | **Simulated and billed** through the pipeline, `provider: "scripted"` (D10). | Portable parity with the mock (energy, caps, trace). Free scripted turns would fail five M3 tests. |
| OQ-10 | Test clock semantics | **`FrozenClock.sleep` waits for `advance`**, and `advance` settles (D2). The M1b test is rewritten. | The only way `tick(ms)` can drive live sessions over HTTP deterministically. |
| OQ-11 | Cap crossing vs `budget.reached` | **Pause on crossing or refusal.** `budget.reached` stays refusal-only (M2 `budget-caps` unchanged). A refused turn leaves no message (lazy `turn.start`). | Keeps M2's spec intact and still meets STATE-06 and the portable cap test. |
| OQ-12 | Scripted reply text | **A Python-native deterministic bank**, not byte-identical with the mock. | No test compares text. Porting the TS banks would add a seed artifact for nothing. |
| OQ-13 | The route call's message link | **Ledger row `message_id` NULL.** The runner adds the route call to `TurnTrace.calls` of every reply in that send. | The route is decided before any `messageId` exists (doc 01 order). |
| OQ-14 | `/_test/ai-profile` shape | `{ profile, overrides? }`, so a test can pair the Jev router with the scripted turn engine. | Needed by the Decider-fixtures-over-HTTP scenario. |

# Design: turn-plan-emotion (M9)

## Context

See proposal.md for the why. Docs 01 (A1–A14), 06 (E1–E9) and doc 13 W1, W2, W4–W14 fix *what* M9 builds. This
document fixes *how*, and settles the places where those docs are vague or where the code contradicts them. Every
locked item listed in the request (W1–W14, E1–E9, A1–A14, M7's and M8's decisions, group A) stands. Where a decision
here touches one, it says so and stays inside it.

**Facts in the code today that shape the approach:**

- **No planner exists.** `TurnContext` has no plan field (`ai/contexts.py`). `TurnRunner.run` builds the context
  after `turn.thinking`, retrieves (M5, D-97), then runs the engine (`sessions/turn.py`). The capture row already
  reserves `"plan": None`.
- **`agent` has one agent port.** `AGENT_PORTS = {"turn"}` (`ai/profile.py`). Every other port falls back to naive,
  then to scripted. `reactions` has no naive implementation, so **`naive` with a key already runs
  `ScriptedReactions`**. The same chain would give `naive` a scripted planner and a scripted face check.
- **The agent engine holds the face** through `AgentTagParser._decide`, which always returns `(previous, "default")`
  (M8 D4).
- **`turn.start` is emitted lazily** at the engine's first event, in its own `actor.emit`, and the `emotion` event in
  another. Each emit takes the writer lock separately, so a background `reaction` emit can land between them.
- **Reactions are synchronous and random.** `_reactions` calls `predict` inside `finish`, using the turn's frozen
  `ctx.session` participants. It then plays them in `actor.background("reactions", …)`.
- **`clear()` cancels nothing in the background.** It cancels timers, queued turns and unreleased prefetches. Only
  `stop()` cancels background tasks. So a late reaction can land on a speaker who is streaming (doc 06 §2 finding 1,
  `ses_seedDinner` seq 25).
- **The Decider already has deadlines and late answers.** It has `start(...).by(at)`, `final()`, `cancel()`, the
  size check, 429s on the hot path, and `park_decision` in the fake (M7 D4–D9, W11). The `turn_plan` (700),
  `reaction` (1,500) and `face_check` (1,500) deadlines are already in `seed/pricing.json` and the mock mirror.
  `PURPOSE_CATEGORY` already maps `reaction` to `decision`, but not `turn_plan` or `face_check`.
- **The bank compiles instructions verbatim.** Only dynamic options are templated (`ai/questions/__init__.py`).
  `check_state` admits free text only in `quoted_*` fields, and `label` fields of at most 40 characters on one line.
- **The plan-state builder exists** (`ai/agent/plan_state.py`, M8 D22), with no caller.
- **The System 1 fixture** holds the `route` row only. Scripted rows take fixed values and "the answer filled from
  what happened" (its own note).
- **The scripted profile bills simulated calls through `gateway().simulated_call`.** A real ledger row is written,
  at the decision price.
- **`langgraph` is not a dependency** (`backend/pyproject.toml`).
- **The activity tracker** (`domain/vclock.py`) counts one token per `rt.spawn` task. A task created by other code
  inherits its creator's holder through the context, but holds no token of its own.
- **"View as prompt"** (`PromptPreview.tsx`) shows system message 1 only, compiled by the TS twin.
- **The frozen transcripts** store each turn's user line, replies, `summary` and `summary_upto`. So a turn's history
  can be rebuilt exactly. There are four: Amara 1:1 English (91 turns), Amara 1:1 Malay, and the Meridian and Sunny
  Hollow groups.

## Goals / Non-Goals

**Goals:**
- Every item in W4's M9 row, Windows first. Each phase in tasks.md ends with the offline gates green.
- **Our side stays fast.** The plan overlaps the thinking delay. Nothing new waits before the first word except Jev
  call 1 (A13). Reactions and the face check run after `turn.end`.
- **`naive` doesn't move** (the user's choice, D34), except the event grouping in D14, which is identical on the wire.
- **Every paid output is saved** in the store, except the latency run, which W10 forbids from using it.

**Non-Goals:**
- Anything from M10–M15 (proposal's scope), including Jev emotion in group, watch and debate (D34).
- Tuning the `turn_plan` deadline (W12: M15).
- Re-validating `judge_voice` (D34).
- Doc 11 S4's care-cue amendments to E3 and E5. They are recorded in the code as the hook points, and built in M14.

## Decisions

### D1. The `langgraph` dependency

- **Only `langgraph`** is added (A8). It brings `langchain-core` (and `langsmith`) as dependencies of its own. No
  LangChain model class is imported, and every model call goes through our gateway and `Decider`.
- **Pinned exactly in `uv.lock`.** The version is the newest release on PyPI that is at least two weeks old when
  phase 1 starts (1.x is expected). It is named to the user and installed only after their OK, because adding it is a
  download (the user's rule).
- **Chosen at phase 1:** `langgraph` 1.2.12, approved by the user 2026-10-12. Its own new dependencies are held to
  releases at least two weeks old with `[tool.uv] exclude-newer-package`. A global `--exclude-newer` would also have
  downgraded packages that were already locked.
- **`langsmith` becomes a required install** (through `langchain-core`). The privacy guard never depended on it being
  absent: `guard_env()` forces tracing off without `HORIZON_LANGSMITH=1`. The `tracing` group stays, but it's now
  redundant, and the opt-in-tracing spec's "missing install" scenario is updated (delta).
- **No checkpointer** (A9). `data/graph.db` stays unused.
- **LangSmith stays off.** M7's guard (B11) already refuses tracing unless the opt-in flag is set. A test asserts
  that a graph run opens no socket with the flag unset.

**Rejected:** writing the plan in plain code now and adding LangGraph in M12. W4 places the checks first in M9, so
that M10–M14 build on a settled base.

### D2. Doc 01's checks 1 and 2 are phase 1, and a gate

The checks run as ordinary tests on the scripted gateway and the virtual clock ($0). Their numbers go in
`docs/ai/checks/m9.md`.

- **Check 1, overhead.** The same plan (D3's nodes, fixture answers) runs 200 times through the compiled graph and
  200 times as the same node functions called in a row. The difference in real wall time, measured on Windows, must
  be under 50 ms p95 per run.
- **Check 1, settling.** 100 planned 1:1 turns run on the virtual clock, with Jev answers parked and released at set
  virtual times. Every advance must settle without `SettleTimeout`, and two runs must produce identical event logs.
- **Check 2.** Each of Stop, leave, a cap pause and the session's end arrives while (a) the plan's decision is parked
  and (b) the reply streams. In each case:
  - the turn is gone within 500 ms of virtual time;
  - the clock settles;
  - `Activity.busy` is empty once the parked decision is released;
  - the decision's ledger row records outcome `cancelled`.
- **The failure mode to look for.** LangGraph may run a node in a task it creates itself. That task inherits the
  plan task's holder but holds no token. If such a node waits on a clock timer (the Decider's `by(deadline)`) while
  the outer task keeps its token, the count never reaches zero, and `settle()` times out. So does a node run in a
  worker thread.
- **If either check fails, phase 1 stops.** The user gets the choices:
  1. **Keep the graph, move the clock wait out.** The `ask` node only starts the call, and the deadline wait runs in
     the plan task itself.
  2. **Wrap LangGraph's task creation** so every task is made by `rt.spawn`.
  3. **Plain code** behind the same port, as doc 01 §7 allows.
  4. Another path the user names.
  No later phase starts before that choice.

**Rejected:** running the checks after the planner is wired: a failure would then rewrite phases 2–3.

### D3. A graph for a one-call plan, built to its final shape

By A7's own rule ("one call → plain code"), M9's plan is a single Jev call and needs no graph. Building it as a graph
anyway is still right, for two reasons:
- check 1 must measure the real structure;
- M12 adds the quick/deep branch to this graph, not to plain code.

So the graph has its final shape now:

```
state ──▶ ask ──▶ decide ──▶ route ──quick──▶ END
                                  └──deep───▶ (M12: embed → search → Jev call 2 → keep)
```

- **`state`:** builds the X9 state with `build_turn_plan_state`, imported from `ai/agent/plan_state.py`, unchanged.
- **`ask`:** Jev call 1 (D7).
- **`decide`:** code: the face (D12, D13) and the System 1 rows.
- **`route`:** always returns `quick` in M9, since no gate is asked.

The graph's input and output are plain frozen values. Each run records its node path once, as `graph.path`, which the
runtime merges into the trace (A12: one writer per graph).

**Rejected:**
- **plain code in M9:** see D1;
- **a deep stub node that raises:** dead code that tests can't reach.

### D4. The `TurnPlanner` port and the frozen plan

```python
class TurnPlanner(Protocol):                       # ai/ports.py
    async def plan(self, req: PlanRequest) -> TurnPlan: ...   # never raises except CancelledError
```

- **`PlanRequest`** (frozen) holds:
  - `session: SessionContext`, `speaker_id` and `kind` (`reply` | `greeting`);
  - `latest` (the user's text, without regenerate's " (again)") and `turn_index`;
  - `base_face`, `manual: bool` and `started_at` (the absolute virtual time the deadline counts from).
- **`TurnPlan`** (frozen, JSON-serialisable, in `ai/contexts.py`) holds:
  - `seed`, which is `"{session seed}:{turn index}"`, i.e. `system1.seed`;
  - `kind`;
  - `emotion`, a `PlannedFace` or `None`. It is `None` from the scripted planner, whose reply picks its own face;
  - `rows`: the System 1 rows, including `not_used` rows;
  - `calls`: the `turn_plan` call as a `TurnTrace.calls` entry, or none on a fixture or cancel;
  - `graph_path`, `state_tokens` and `dropped_gates`.
- **`PlannedFace`** holds:
  - `face` and `source` (`classifier` | `default`);
  - `pick` and `p`; `confidence` with `compared`;
  - `candidates`: the top 3 for `TurnTrace.emotion`;
  - `outcome`: one of `jev`, `none`, `below_floor`, `fallback`, `late` or `cancelled`;
  - `faded: bool` and `base`.
- **`TurnContext.plan: TurnPlan | None = None`.** This is W4's "frozen-plan fields used for replay" (A9: replay from
  JSON). The agent engine reads only `ctx.plan`, so a stored context replays with no Jev call (spec scenario "Replay
  from JSON").
- **Capture:** `capture.on_turn` records `plan = ctx.plan.model_dump()` instead of `None`.
- **`branch` (added in phase 3):** `TurnPlan.branch` is `"quick"` | `"deep"` | `None`. The Jev planner sets it from
  `route`. A planner that doesn't decide retrieval (the scripted one) leaves it `None`, and the runtime then keeps
  `naive`'s retrieval. So D9's "no retrieval" follows the plan, not a check of which implementation runs.

**Rejected:**
- **the plan in `TurnSpec`:** not frozen, and not part of what the engine and replay see;
- **separate fields on `TurnContext` per answer** (`face`, `mood`, …): M12 and M13 would keep adding top-level fields.
  One `plan` object grows instead.

### D5. Profile resolution: explicit no-ops for `naive`

`PORTS` gains `planner` and `face_check`, with `HORIZON_AI_PLANNER` and `HORIZON_AI_FACE_CHECK`.

| Port | `agent` (key) | `naive` (key) | `scripted` or no key |
|---|---|---|---|
| `planner` | `JevTurnPlanner` (the graph) | `NoPlanner` (returns `None`) | `ScriptedTurnPlanner` (simulated call, fixture rows) |
| `face_check` | `JevFaceCheck` | `NoFaceCheck` | `ScriptedFaceCheck` |
| `reactions` | `JevReactions` | `ScriptedReactions(simulate=False)` | `ScriptedReactions(simulate=True)` |

- **The trap this closes:** the fallback chain ("agent → naive → scripted") would hand `naive` the scripted planner,
  face check and reaction charge. All three record **simulated spend in a real ledger** with a key set: a fake
  `turn_plan` row on every `naive` 1:1 reply, and fake `reaction` rows in every `naive` group (D21). So `planner` and
  `face_check` get **naive no-op implementations**, and the scripted reaction predictor is told whether it may
  simulate.
- **When simulated spend is allowed:** only when the profile is `scripted` or no key is set (ai-ports spec). A
  per-port override to `scripted` under a key does not simulate.
- **The same trap already exists elsewhere:** under `naive` with a key, the scripted debate verdict (and the watch
  episode summary, if it falls back the same way) records simulated spend. M10 (the episode recap) and M11 (the
  verdict) replace both, so M9 doesn't touch them. The finding is recorded in m9.md for those changes.

**Rejected:**
- **checking `impl == "agent"` at each call site:** it spreads profile logic into `sessions/`, which never inspects
  the implementation (ai-ports);
- **letting `naive` bill the simulated rows:** the user's daily cap would count calls never made.

### D6. Where the runtime calls the planner, and the timeline

Only in `TurnRunner.run`, only for 1:1, and only when the resolved planner isn't `NoPlanner`, the line isn't verbatim
and there is no prefetch (1:1 has none). The order is:

1. Allocate the IDs as today.
2. **Spawn the plan task** (`rt.spawn("plan:{sid}", …)`). It builds the session context, the `PlanRequest`
   (`started_at = now`) and runs the planner.
3. Emit `turn.next`, sleep `thinking_ms`, then emit `turn.thinking`, as today.
4. Await the plan task. The deadline counts from step 2, so the thinking delay overlaps Jev.
5. Build `TurnContext(…, plan=plan, max_tokens=reply_cap(...))`, which is the quick cap (D9).
6. Run the engine.

- **`base_face`:**
  - AUTO: the speaker's current face (`ParticipantView.emotion`);
  - MANUAL (E2): the `emotion` of the speaker's latest message in this session, else `neutral`.
- **`kind`:** `greeting` for a generated greeting (`LineHint(kind="greeting")`, not verbatim). Otherwise `reply`,
  including regenerate, whose kind is its original's.
- **The derived seed** is `actor.seed` and `actor.mode.turn`, as the route row uses (W1). A regenerate is a new turn
  index, so it gets a new seed.

- **Waiting on the plan task (found in phase 3):** the worker awaits it with `vclock.join(task)`, which gives the
  worker's activity token up while it waits. Awaiting it directly kept the token, so a parked Jev answer stopped the
  virtual clock from ever settling: D2's failure mode, but in our runtime rather than LangGraph.

**Rejected:**
- **starting the plan after `turn.thinking`:** it adds `thinking_ms` to every first word for nothing;
- **starting it at `chat.send`:** a queued turn might never run (Stop, asleep), and the plan would bill for it.

### D7. Deadlines, late answers and failures

The `ask` node calls `decider.start(state, questions, ctx.call_ctx("turn_plan"), purpose="turn_plan")`, then
`by(started_at + timeout_for("turn_plan"))`.

- **Fallback plan** (outcome `fallback`, row result `fallback`, no `p`) for:
  - a timeout (`late`);
  - a 429, which on the hot path falls back with no retry (M7 D8);
  - `too_large`;
  - any `ProviderError`, including a budget refusal;
  - an invalid answer.
- **A late answer is billed and discarded** (W11's default). No row is rewritten from it, because the face shown
  can't change (D-46).
- **A budget refusal of Jev call 1** doesn't pause the session. The reply's own preflight meets the same cap a moment
  later and takes the existing cap-pause path (D7 of `session-runtime`). So there is exactly one pause, from the
  reply.

### D8. Stop during a plan

The turn worker awaits the plan task.

- **When the worker is cancelled** (Stop, leave, a cap pause, the end), it cancels the plan task. The `ask` node's
  `CancelledError` handler calls `call.cancel()`, so readers detach and the request still settles: the ledger row is
  written, with outcome `cancelled` (M7 D6).
- **Nothing is started** for the turn, so no `turn.start` and no message (A11), and `close_interrupted` already
  handles a turn that never started.
- **`clear(keep_current=True)` keeps only a turn that has started streaming (found in phase 3).** A cap pause, leave
  and end use it so that a streaming reply finishes. Before, it also kept a turn still in its preamble or plan, which
  then ran its reply after the pause. A turn cut before `turn.start` now marks itself closed, so `actor.current`
  never holds a stale turn.
- **LangGraph cancellation** is part of what check 2 verifies (D2): a cancelled run must start no more nodes and
  leave no task behind.

### D9. `agent` 1:1 retrieves nothing in M9

W4's table: retrieval is "none in `agent` 1:1" and every 1:1 turn is quick, because "needs documents?" and "needs
something from earlier?" aren't asked until M12/M13. D-100: `agent` embeds the query only after the gate. So under
`agent`:
- `one_on_one.send` starts no `start_query`;
- `TurnRunner` skips `retrieve()` for a planned turn;
- the reply cap is the quick cap.

**The consequence, stated plainly:** an `agent` 1:1 reply sees no knowledge passages and no retrieved memories until
M12/M13. `agent` is opt-in, so no default user is affected. `naive` 1:1 keeps D-97's retrieval.

**Rejected:** keeping `naive`'s retrieval in `agent` 1:1 until M12. It pays for an embedding every message with no
gate, which D-100 replaced, and it makes the M9 latency run measure a path M12 deletes.

### D10. The emotion bank entries

Two entries: one per turn kind M9 asks (E1). Watch, debate and the opening get their own entries in M10/M11, with
their E1 wording.

| | `emotion_reply` | `emotion_greeting` |
|---|---|---|
| purpose / type | `turn_plan` / choice, static, `shuffle: true` | same |
| label | "emotion" | "emotion" |
| instructions | "Which face fits how {name} feels on reading quoted_latest? Choose none when nothing in it changes how they feel." | "Which face fits how {name} feels on meeting quoted_user again? Choose none when nothing calls for a change of face." |
| state | `mode` label; `quoted_user`, `quoted_cast`, `quoted_latest`, `quoted_recent`, `quoted_documents` quoted | same |
| floor | 0.6 (W12) | 0.6 |
| deadline | `turn_plan` | `turn_plan` |
| fallback | `keep_then_fade` | `keep_then_fade` |

- **The keys** are `emotion_reply:{characterId}` and `emotion_greeting:{characterId}` (W5). E1's `{user_name}`
  becomes a reference to the `quoted_user` field, the way `route` names its fields ("answer quoted_message"). The
  user's name then stays inside quoted text.
- **The options** (shared by both entries). `what` and `not_for` are E1's, verbatim. The examples are new short lines
  the character reads, and the overlap check keeps them out of every dataset item:

| key | examples |
|---|---|
| neutral | "What time does the shop open?" · "I'll be there at six." |
| happy | "I passed my exam, first try!" · "We saved you the last slice." |
| sad | "Our old dog died this morning." · "I'm moving away next month." |
| angry | "I read your diary while you were out." · "Honestly, your idea was stupid." |
| surprised | "I'm engaged!" · "Guess who's standing outside your door." |
| thinking | "Should I take the job or stay?" · "What would you change about the plan?" |
| embarrassed | "Everyone saw you trip on stage." · "You're honestly the best person I know." |
| none | `what`: "No clear change: keep the current face." · `not_for`: "A line that clearly calls for one of the faces above." · "Ok." · "And then?" |

- **Reviewed by the user** before any paid run, with the labels (B2). Wording changes after that bump the version.

### D11. A `{name}` placeholder in bank instructions

E1 words every question about a named candidate ("how {name} feels"), and the per-candidate questions of M10 need
it. The bank can't put a name in instructions today. So:
- an entry's `instructions` may hold `{name}`;
- `bank.question(qid, …, name=…)` fills it;
- a placeholder with no name raises `BankError`.

The value must pass the bank's `label` rule: at most 40 characters, one line.

**Why this doesn't break doc 11 S6:**
- the name is the user's own character's display name;
- it is already admitted, as a label, everywhere `check_state` allows short labels;
- the same name sits in `quoted_cast` as quoted text;
- the S6 sentence still follows every instruction.

Entries without the placeholder compile exactly as before, so M7's and M8's lock hashes are unchanged. This is an
addition to the loader, not a change to the locked format.

**Rejected:**
- **referring to the candidate by position** ("the first person in quoted_cast"): A3 rule 7 says no counting for
  Jev, and it gets worse with 5 candidates;
- **one entry per character:** the bank would grow with the user's cast;
- **free `.format` of any key:** a second placeholder could carry longer user text.

### D12. The `neutral` + `none` merge, and what meets the floor

E1 says that when the current face is neutral, code adds the two probabilities "before the floor is applied". But
the floor is compared with Jev's **confidence**, not `p` (E1, B5), and Jev's confidence belongs to Jev's own pick. The
rule:

1. Read the probabilities `p(·)`, Jev's pick and its confidence `c`.
2. **If the base face is `neutral`:**
   - set `p'(neutral) = p(neutral) + p(none)` and drop `none`;
   - the merged pick is `argmax p'`.
   - **If the merged pick is `neutral`,** the value compared with the floor is `p'(neutral)`, named
     `p_neutral+p_none`.
   - **Otherwise** it is `c`, named `confidence`.
3. **Otherwise,** there is no merge: compare `c` with the floor.
4. **Decide:**
   - a merged pick that reaches the floor is used, source `classifier`;
   - `none` (base not neutral) is used as "keep", source `default`;
   - anything below the floor is "unsure", and the base face is kept, source `default`.

**Why:** a 0.38 / 0.35 split between `none` and `neutral` on a neutral face is a confident "stay neutral". Comparing
Jev's 0.38 confidence would call it unsure. E1's stated intent is exactly that this split doesn't count as unsure.
On a neutral base, "unsure" and "classifier neutral" show the same face, so the merge changes only the source label,
the System 1 row and the evaluation.

### D13. The face rule, its rows and the fade

`ai/agent/emotion.py` is pure, and both the planner and the evaluation call it:

```
decide_face(answer | None, outcome, base, fade_set, floor, manual) -> PlannedFace
```

- **A kept face:** the base, or `neutral` when the base is in `emotion.fade`. A faded face has `faded = True`.
- **The row,** per candidate:

| Case | `answer` | `result` | `action` |
|---|---|---|---|
| a Jev pick at or above the floor | the pick | `used` | "shown" |
| Jev said `none` | `none` | `used` | "kept" or "faded to neutral" |
| a Jev pick below the floor | the pick | `below_threshold` | "kept" or "faded to neutral" |
| late, failed or invalid | "kept {face}" or "faded to neutral" | `fallback` (no `p`) | the same |

  Under MANUAL, the action becomes "recorded (MANUAL)".
- **`not_used`:** a candidate who didn't speak. None in 1:1; this is for M10.
- **`emotion.fade`** goes in `runtime.config.ts` → `seed/runtime.json` → `domain/runtime_config.py`, set to
  `["surprised", "embarrassed"]` (W12).

### D14. The face reaches the screen in one write

- **The engine:** `AgentTagParser._decide` returns `ParsedEmotion(plan.face, plan.source)` when `ctx.plan` has a face,
  else today's `(previous, "default")`. The parser's hold already emits it before the first visible text. The
  `agent` engine moves to `version = "2"` and `prompt_version = "agent-2"` (D16).
- **The runtime, for every profile:** when the engine's first event is an `Emotion` and `turn.start` hasn't been
  emitted, `_stream` appends `turn.start` and that `emotion` event **in one `actor.emit`**. The event order and
  payloads are what they were, so the wire and the stored log are unchanged for `naive` and `scripted`. Only the
  transaction grouping changes, which closes the reaction race for every profile.
- **The agent path never sets `turn.start.emotion`** (E2).
- **The reducers** already hold an early face until the first token (CHAT-03 AC4), so the face shows with the first
  word.
- **A refused reply** fails in the gateway's preflight inside the first `__anext__`, before any event. So no
  `turn.start` and no face change (spec scenario).

**Rejected:** a separate "start with emotion" event or field (E2 rejects a contract change).

### D15. Trace candidates and Insight's "kept" chip

- **`TurnTrace.emotion`** is `{chosen, source, candidates}`, with candidates the top 3 of the merged distribution
  (D12), `none` left out. It is set by the engine's trace patch from the plan, since `emotion` is a port-writable
  section. There are no candidates on a fallback.
- **Insight** (`InsightDrawer.tsx`, shared by both clients):
  - when `candidates[0].label !== chosen`, show the chip **"kept"** instead of the source, and drop the band next to
    `chosen`;
  - with no candidates, it shows the source label, as today;
  - display only.

### D16. The mood line, `agent-2` and byte-identity

- **Where:** `persona.py` gains `MOOD_PHRASES` and `mood_line(face, manual) -> str | None`, with the TS twin
  `moodLine()` in `personaPrompt.ts`.
- **The line:** E4's exact sentence and table. `None` for `neutral` and for MANUAL.
- **Shared fixtures:** `backend/tests/fixtures/mood_line/cases.json` (built note: not under `persona_prompt/`, whose
  runners in both languages read every `.json` there as a persona case).
- **The tail order** (P2 and E4): retrieval block → mood line → repeat hint → voice reminder → cue → language cue
  (D35). In M9 the retrieval block is always absent on planned turns (D9).
- **The version.** M8's design and E4 call the line part of `agent-1`, but `agent-1` shipped without it. The
  requests change on non-neutral turns, so the engine says **`agent-2`**. This changes nothing that is cached:
  - system message 1 and the summary message don't change, so the provider's prefix cache is unaffected;
  - a neutral or MANUAL turn's request is byte-identical to `agent-1`'s, so M8's stored answers still serve.
- **Proof.** Before the engine changes, phase 4's first task records an `agent-1` request fixture for a planned-
  shape 1:1 turn. The test then asserts:
  - the `agent-2` `neutral` request equals it byte for byte;
  - the `happy` request differs only in the tail.

**Rejected:** keeping `agent-1` for a request that changed. Traces and the ledger's `prompt_version` would then
mislabel M9's replies against M8's.

### D17. "View as prompt" gets one note line

E4 says the phrase table lives with the compiler "so View as prompt shows it". But P10's preview is system message 1
only, and the mood line is never in it. A per-turn line inside the system prompt view would misstate what is cached.
So:
- the preview keeps showing system message 1, unchanged;
- one fixed note goes under it: "Each AUTO reply also gets one mood line, e.g. “Your mood right now: a bit low. Let
  it show in how you word this reply; don't name the feeling.”", built from the TS twin's `moodLine("sad")`.

It isn't a new entry point and has no contract effect.

**Rejected:**
- **a "per turn" tab in the preview:** new UI;
- **no note:** the wizard would hide a line every AUTO reply carries.

### D18. `JevReactions`

`ai/agent/reactions.py` implements the async port:

```
ReactionPredictor.predict(req: ReactionRequest) -> list[Reaction]
```

- **`ReactionRequest`** holds:
  - `session`, `message_id`, `speaker_id` and `line` (the reply text);
  - `before` (the previous line, as `Name: text`);
  - `listeners: [ListenerView{id, name, about_source, face, side_label}]`;
  - `seed`.
- **One bank entry, `reaction`:**
  - purpose `reaction`, choice, static, `shuffle: true`, label "reaction", floor 0.6 (W12);
  - instructions: "How does {name} react to quoted_line? Choose none when they show no visible reaction.";
  - options: the 7 emotions with E1's `what` / `not_for` and their own examples, plus `none` with `what` "No visible
    reaction: the line doesn't move them." and `not_for` "A line aimed at them, or one that clearly pleases, hurts or
    startles them.";
  - state: `mode` label; `quoted_line` (`"Name: reply"`, cut to 600 as first 450 + last 150), `quoted_before` (cut to
    300) and `quoted_listeners` (`[{name, about, face, side?}]`), all quoted. `about` is cut to 60 with M8's
    helpers, and `side` is "same side as the speaker" or "the other side" in debate.
  - The merge (D12) applies per listener whose face is `neutral`. The seed is
    `"{actor.seed}:{turn index}:react:{listenerId}"` (E5).
- **The keep rule, in code** (E5): a pick that isn't `none`, with confidence at or above the floor, whose face
  differs from the listener's face. The 2 most confident are kept. Then E3's fades go outside the cap (D20 re-checks
  "differs" at append).
- **`delay_ms`:** each kept reaction gets a seeded value in `reactionDelayMs`, counted from `turn.end`. It plays at
  `max(turn.end + delay, answer time)`. The call has a 1.5 s deadline (`timeoutsMs.decision.reaction`).
- **On failure:** a late or failed call returns fades only, never an exception, since fades need no Jev.

### D19. Where reactions run in M9

- **Under `agent`, `JevReactions` runs in group, debate and watch,** after every completed AUTO reply with listeners
  (E5, MULTI-04 AC3's guard, `TurnSpec.reactions`). Routing there stays `naive`'s, and the speaker's face is M8's held
  face (D34), but the listeners' reactions are Jev's. Both are honest: reactions don't depend on the plan.
- **1:1 has no listeners,** so no call.
- **`naive` keeps the random reactions,** with no spend (D5).

### D20. Named after-turn tasks, the drop rules and the locked re-check

- **The actor's background registry** becomes `name → set[Task]`. `background(name, coro)` is unchanged for callers.
  `cancel_background(*names)` cancels and forgets the named tasks.
- **`clear()`** gains `cancel_background("reactions", "face_check")` (E5, W2). It leaves `summary` and `memory`
  running: M8's single-flight summary must finish its boundary, and the memory writer is `[]`.
- **Drops, with their triggers:**

| Trigger | What is dropped | Where |
|---|---|---|
| Stop, leave, a cap pause, the end | all reactions and face checks | `clear()` |
| a new user message (any mode) | all reactions | each mode's send path, through one helper `on_user_message(actor)` |
| MANUAL switched on | all reactions | `commands._emotion_mode` |
| the listener's own turn starts | that listener's reaction | the locked re-check below |

- **The locked re-check.** A new `actor.emit_checked(event, check)` runs `check(state)` **under the writer lock**,
  just before appending. For a reaction, the check passes only if:
  - the session is AUTO;
  - the listener is present and unmuted;
  - the listener isn't the author of the streaming message;
  - the listener has no message newer than the reacted one;
  - their current face differs from the reaction's face (fades: their face is still in the fade set).

  A failed check drops that reaction silently.
- **Why under the lock:** a check made before taking the lock can pass. The listener's `turn.start` and emotion
  (D14, one write) can then land, and the reaction would follow them. E6's reducer rule hides the face, but the event
  would still be wrong in the log.

**Rejected:**
- **a per-turn-start registry of pending reactions:** the state the check reads is already in `actor.state`;
- **dropping every reaction at the next `turn.start`:** E5 rejects it.

### D21. Scripted reactions: async, and simulated spend only when allowed

- `ScriptedReactions.predict` becomes async and keeps its seeded randomness (same seeds, same output).
- With `simulate=True` (D5), it records one simulated `reaction` call per message with listeners, at the decision
  price (E5, D-81).
- **E5 says** "scripted … records a simulated `reaction` call" **and** "`naive` keeps resolving to the scripted one".
  Read together, every `naive` group message with a key would write a fake `reaction` row and count against the real
  daily cap. `simulate=False` under `naive` closes that.
- **The MockClient** (`turnScript.ts`) charges the same simulated call through `h.charge`. It applies the drop rules
  in D20: a user message, MANUAL, the listener's own turn, and `clearLive`.

### D22. Both reducers keep the streaming speaker's face (E6)

- **Python** `reducer.py` `_apply_reaction` and **TS** `sessionReducer.ts` `case "reaction"` record the reaction on
  its message, as today. They skip the face when `state.streamingId`'s message author is the reacting character.
- **Fixtures** in `backend/tests/fixtures/reducer/`:
  - `reaction-speaker-before-first-token`;
  - `reaction-speaker-after-first-token`;
  - `reaction-listener-still-applies`;
  - `seed-dinner-seq25`, the seed case.
- **The seed equivalence check is re-run.** Final states are unchanged; only the derived face between seq 24 and the
  first token differs (E6).

### D23. The face-check bank entry

`face_check`:
- purpose `face_check`, type choice, static, `shuffle: true`;
- label "face and words agree?";
- the 7 emotions with no `none`, and no floor (display only);
- deadline `face_check`;
- state: `quoted_reply` only (W2), the reply's last 600 tokens.

**Instructions:** "Which emotion do the words of quoted_reply show? Judge only the words, not what you guess the
speaker's face is."

**Options:** each `what` describes how the words read, not how a line affects someone:

| key | `what` |
|---|---|
| neutral | "Calm, matter-of-fact words with no strong feeling." |
| happy | "Pleased, warm, amused or relieved words." |
| sad | "Low, sorry, hurt or missing someone." |
| angry | "Annoyed, sharp, offended or defensive." |
| surprised | "Caught off guard: disbelief, sudden questions." |
| thinking | "Weighing, unsure, working something out." |
| embarrassed | "Flustered, shy, deflecting praise or a slip." |

Each also gets a `not_for` and two examples written in phase 6 under the overlap rule.

The evaluation reads the same entry (W2, W10).

### D24. The face check at runtime

- **`sessions/after_turn.py`** owns both after-turn tasks (reactions, the face check), so `finish` stays short.
- **At `_start`, the runtime records `info.auto`** (the emotion mode at `turn.start`). Each `Emotion` it emits also
  updates `info.face`.
- **After `finish` emits `turn.end` and the trace**, it starts `actor.background("face_check", …)` only if all of
  these hold (W2's skip list):
  - the status is `complete`, not scrubbed and not verbatim;
  - `info.auto` is true;
  - `info.face` isn't `neutral`;
  - the resolved checker isn't `NoFaceCheck`.
- **The task:**
  - asks with `ask(…, deadline "face_check")`;
  - builds the W2 row (`yes` / `clash` / `no (words read: {pick})`, `p` = p(face shown), `shown_only`);
  - calls `actor.append_system1(mid, vid, [row], [call])`, which guards a regenerate and a streaming target (M7);
  - catches every exception, logs it, and adds nothing.
- **Also for `agent` group, watch and debate replies,** whose faces are M8's held faces. W2 doesn't limit the check to
  planned turns, and a held non-neutral face is exactly what the check is for.
- **`ScriptedFaceCheck`:**
  - waits `faceCheckMs` (a new timing-table value, 300);
  - records a simulated `face_check` call when simulation is allowed;
  - appends the fixture row with answer `yes`.

  The MockClient does the same in `turnScript.ts`.

### D25. The scripted and mock System 1 rows

The fixture gains rows for `emotion_reply`, `emotion_greeting` and `face_check`, and still none for judges or
`reaction` (W1: reactions have no rows).

- **The scripted planner** records one simulated `turn_plan` call (D-81, so the ledger and the cap see what `agent`
  would) and returns `emotion = None` with the fixture row.
- **At `finish`,** the runtime fills that row's answer from the face the reply actually showed (`info.face`). It
  follows the fixture's own rule, "the answer filled from what happened".
- **The MockClient's 1:1 engine** does the same.

As a result, scripted and mock 1:1 replies show a System 1 section with the "emotion" row, and, after a non-neutral
AUTO reply, the face-check row. The system1-trace spec's "No rows" scenario moves to `naive` 1:1.

**Rejected:**
- **switching scripted's face source to `classifier`:** it changes every scripted and mock face event, and the
  portable tests built on them, to fake a source;
- **no turn_plan charge in scripted:** W2 charges the face check, and leaving the plan out would make the no-key
  demo's cost view inconsistent.

### D26. The `decisions` policies for emotion and reactions

`evals/policies.py` scores an item exactly as live, using the same pure functions (`decide_face`, the reaction keep
rule).

- **Emotion:**
  - the policy answer is the face `decide_face` returns for the item's base face (fade and merge applied);
  - an item is correct when that face is in its acceptable set, or it is the kept or faded base and keep is allowed;
  - **the baseline** is "always keep" (with the fade).
- **Reactions:**
  - the policy answer is the face shown, or `none` when nothing shows (single listener, so no cap);
  - an item is correct when that answer is in its acceptable set;
  - **the baseline** is "always `none`".
- **Floors** are chosen on dev, over {0.5, 0.6, 0.7, 0.8, 0.9}, using each item's live seeded order only. They must
  beat "no floor" and "fallback only" (B5). Both orders still run (B6), for the lean report only.
- **Reported:**
  - accuracy with a Wilson interval;
  - the paired difference from the baseline, with an exact McNemar test (B1);
  - coverage;
  - calibration;
  - the `neutral` + `none` merge rate;
  - for reactions, the share of messages that would get a reaction (E8).
- **The chosen floors** are written into the bank, as a version bump with a re-lock, and recorded in m9.md.

### D27. The two datasets, English first

The user's rule: English must work well; other languages need only the right language and face, and their quality
is v2. So:

| Set | Items | Split | Spread |
|---|---|---|---|
| `emotion` | 100 | hash rule (≈ 67 dev / 33 test) | turn kinds: 1:1 reply 55, group reply 30, greeting 15; language: English 80, Malay 10, Chinese 5, mixed 5 |
| `reactions` | 90 | 60 / 30 (E8) | group 40, debate 25, watch 25; English 75, others 15 |

- **The keep cap:** 20–30 emotion items list keep (or `neutral` from a neutral base) as acceptable (E8). At most 27
  reaction items have `none` acceptable.
- **The targets** apply to the whole test split, as E8 states. English is also reported alone. Non-English items get
  no separate target; they show the direction only.
- **Sources:**
  - real contexts from the committed frozen transcripts and M8's `long` scripts, which hold the user line and the
    recent lines;
  - hand-written lines where those lack a kind (greetings, surprise, embarrassment, debate lines).

  Each item stores its built plan state or reaction state, the values, the seed, the previous face, its acceptable
  faces, `keep_ok`, and its source.
- **Labelling discipline** (M8 D38, kept):
  - labels are written blind, before any Jev answer is seen, under a rule written first in
    `evals/reviews/m9-labels.md`, and committed before the first paid run;
  - `horizon eval overlap` must pass against the bank's examples;
  - B2's review sample (max(15, ⌈n/5⌉) per set) goes to the user. If the user delegates it again, as in M8, I do a
    recorded pass, and the held-out test split is the safeguard.

### D28. "Names the feeling", and its validation

`judge_names_feeling`:
- purpose `eval_judge`, noul, threshold 0.5;
- label "names the feeling?";
- instructions: "Does quoted_reply state the speaker's own feeling outright, such as saying they are happy, sad,
  angry or embarrassed?";
- `true`: "Yes: the reply names the speaker's own feeling.";
- `false`: "No: the feeling only shows through what is said, or the feeling named is someone else's.";
- state: `quoted_reply`.

**The validation set (B4 plus E8's rule):**
- **Real items:** 30 saved replies from M8's runs (`agent` long runs and `naive` transcripts), labelled blind. A code
  search for first-person feeling statements ("I'm so happy", "I feel …") puts every real "yes" it finds into the
  set, up to 8. The rest are clean.
- **Planted items:** 30 clean replies with a first-person feeling sentence inserted by code, in varied positions and
  forms.
- **Pass:**
  - B4's rule (real ≥ 85 %, all 60 above the commonest-answer baseline, planted ≥ 90 %);
  - **at most 1 false alarm** among the real clean items.

  E8 wrote "30 clean real replies". If all 30 real items were clean, the commonest-answer baseline would be 100 % on
  them and B4's rule could never pass. Hence the mix.

### D29. Choice judges: the pairwise judge, and the face check reused

E8's decision rule needs "the pairwise judge in both orders". It isn't built yet, and the question-bank spec allows
only noul judges.

**`judge_pairwise`:**
- purpose `eval_judge`, choice, static, `shuffle: false` (the harness asks both orders itself);
- label "better reply?";
- instructions: "Which reply is the better next line from {name} in this chat: quoted_reply_a or quoted_reply_b?
  Judge how well it fits the character and answers the latest line.";
- options: `a` "Reply A is better.", `b` "Reply B is better.", `same` "About the same.";
- state: `quoted_recent` (the last 2 turns), `quoted_reply_a` and `quoted_reply_b`.

**Its numbers** follow B4: the primary number is the mean p(ON better) over both orders.

**Validation:** 30 pairs with a known winner, made by code from saved real replies. Each pairs a real reply with a
persona-swapped reply (the other world's character, M8's `CLASH` map) or a reply to a different user line. The judge
is right when the order-averaged probability favours the known winner. Pass at ≥ 90 % (B4).

**The face check** is read by the evaluation under its own purpose and entry (W2, question-bank delta).

### D30. The mood-line on/off run

`horizon eval moodline [--limit N]` (default 100).

- **Items:** walk the three English transcripts (Amara 1:1, Meridian group, Sunny Hollow group) at evenly spaced user
  turns. For each turn:
  - rebuild the stored history (window, `summary` and `summary_upto`) and run Jev call 1 for that turn's speaker, as
    live (store on);
  - keep the turn if the face is a non-neutral `classifier` pick, until N items.

  The Malay transcript is left out (English first). Item order and blocks are fixed by the transcripts.
- **The arms:** one `agent-2` reply request per item, with the mood line (ON) and without it (OFF). Otherwise the two
  are byte-identical (spec scenario), at `reply.chat`'s temperature 1.0 (M8 D34). Each is a single call, so the store
  replays it exactly (M8's finding 7 only concerns multi-turn runs).
- **The checks per reply:**
  - "names the feeling?";
  - the `face_check` entry: exact match with the item's face, and clash;
  - the pairwise judge, ON vs OFF in both orders.
- **The statistics.** E8 asks for a paired bootstrap **per conversation**, but there are 3 conversations, which can't
  give an interval. So the unit is **a block of 10 consecutive items within one transcript**, about 10 blocks.
  Blocks of 10 spaced turns are far apart in their chat, which is close enough to independent for this read. There
  are 2,000 seeded resamples. The run reports:
  - the exact-match difference (ON − OFF) with its 95 % interval;
  - the mean pairwise p(ON better) with its interval;
  - the ON arm's "names the feeling" pass rate (target ≥ 95 %, every failure listed);
  - the clash rate (≤ 5 %).
- **The verdict** follows E8 as written:
  - **keep** if exact match rises and pairwise reaches 0.5;
  - **reword once** if it rises but the replies are judged worse;
  - **propose dropping** otherwise.

  A drop or a rewording comes to the user first (the user's rule).

### D31. The `latency` suite (the 1:1 part of doc 01 check 3)

`horizon eval latency [--limit N]` (default 100).

- **Where:** an isolated copy under `agent` with the real key, and **the store bypassed** (W10).
- **The turns:** 100 English sends across the six seed characters' 1:1 sessions, about 17 each. The lines come from
  the long scripts' pools.
- **Each turn** is driven through the API like the `long` suite (M8 D29). The suite sends Stop on the first `token`.
- **Measured:**
  - time from send to the `emotion` event and to the first `token`, as p50 and p90 with order-statistic intervals,
    against NFR-01 (2 s p50, 4 s p90);
  - `turn_plan` latency from the ledger;
  - the deadline-fired rate, from outcome `late`;
  - the `classifier` share.
- **Not tuned here.** The `turn_plan` deadline is tuned in M15 (W12). This run only reports.

### D32. The paid runs and their estimates

Off-peak only. Each run is asked for separately, with its estimate, when it comes. All but latency go through the
store.

| Run | Calls | Estimate |
|---|---|---|
| `decisions --set emotion` | 100 items × 2 orders | ≈ $0.009 |
| `decisions --set reactions` | 90 × 2 | ≈ $0.008 |
| judge validation (`names_feeling` 60, `pairwise` 30 × 2) | ≈ 120 Jev | ≈ $0.003 |
| `moodline` (100) | ≈ 150 plans, 200 replies, ≈ 600 judge asks | ≈ $0.11 (≈ $0.07 at 60) |
| `latency` (100) | 100 plans + 100 replies stopped at the first word | ≈ $0.03 |
| **Total** | | **≈ $0.16**, plus up to $0.10 of smoke |

**Why over W6's $0.10:**
- W6's figure assumed X6's 80 % cache hit;
- M8 measured 19–56 % in English (its finding 4), which roughly doubles the reply part of `moodline`;
- the pairwise judge and its validation weren't counted (D29).

The user can pick `moodline --limit 60` when it is asked.

### D33. Docs amended in this change

- **Doc 06 §6:** the rows M9 builds are marked built, with these decision numbers.
- **Doc 01:**
  - §8: the `TurnPlanner` row and the 1:1 entry points are built;
  - A4: the emotion fallback, as fade;
  - A5: built in M9;
  - A7: the graph's M9 shape (D3).
- **OQ-AI-07** resolved (Jev first; keep and fade).
- **Doc 02:**
  - B2: the emotion and reaction sizes and spread, English first (D27);
  - B4: the pairwise judge's entry and the "names the feeling" mix (D28, D29);
  - B5: the floors found;
  - B7: the `moodline` and `latency` commands and their costs;
  - B8: the 1:1 timing figures.
- **ENG-02 AC2's list** gains `face_check` (W2).
- **`docs/ai/checks/m9.md`:** checks 1–2, the runs, the findings, and what M10 inherits.

### D34. The user's three choices (2026-10-12)

- **The `naive` emotion word** ("Sad — …") is left as it is. M15 makes `agent` the default, and the `naive` arms are
  paid at M15 and measured as they are. D37's rejection stands.
- **`agent` faces in group, watch and debate keep M8 D4's held face** until M10's follow plan and M11's debate plan
  ask the emotion. No stopgap call is built.
- **`judge_voice` stays unvalidated,** with X5 off, until M15's `conversations` run gets a fresh held-out set.

### D35. A refused after-turn decision pauses nothing (the user's choice, 2026-10-12, found in phase 5)

**Found while building 5.6:** the gateway's daily-cap refusal publishes `budget.reached`, and the session manager's
hook pauses every live session for it. A refused `reaction` request would therefore pause sessions, against the
listener-reactions requirement "SHALL never pause the session".

**Decision (the user chose it):** for the after-turn purposes `reaction` and `face_check`, the refusal still publishes
`budget.reached` but does not call the pause hook (`_reached(..., sessions=False)`, as a refused job estimate already
does). The next reply's own preflight meets the same cap and takes the usual cap-pause path, so the one pause comes
from a reply, as D7 reasons for Jev call 1. Spend that *crosses* the cap when recorded still pauses as before.

**Rejected:** keeping the pause and narrowing the scenario to "the reactions task emits nothing itself": the user
would see a pause caused by a background face.

### D36. The emotion floor grid reaches down to 0.2 (the user's choice, 2026-10-12, found in 9.1)

B5's grid {0.5 … 0.9} only removed right answers: Jev's confidences over 8 options sit low (median 0.58) while its
picks are mostly right. The emotion grid adds 0.2, 0.3 and 0.4; dev chose 0.2 and the test split read 0.82 (m9.md).
Both emotion entries are v2 with floor 0.2. **Rejected:** keeping floor 0.5 with test at 0.75 below target; growing
the set first (E8's +40 follows anyway, in M15).

### D37. The reaction state shows no face (the user's choice, found in 9.2)

With each listener's current face in the state, Jev answered that face in 83 of 90 items, so reactions never
showed. The state now holds the listener's name, card line and debate side only; code still uses the face for
"differs" and for the fades. The listener-reactions requirement "One Jev request per message" changes with it.
**Rejected:** rewording the instructions and keeping the face; keeping random reactions for `agent`.

### D38. Order bias is "not measured" for shuffled choices (the user's choice, found in 9.1)

The response store's key sorts JSON keys, so a choice asked with its options reversed hits the first order's stored
answer; B6's order-bias line has read 0 for every shuffled choice since M7. The report now says "not measured" for
them, with the reason. Live calls are unaffected (Jev gets the shuffled order). Fixing the key changes W10's locked
rule, so it is its own change, with the user's OK. **Rejected:** fixing the key in M9.

### D39. Jev reactions ship at floor 0.2, below E8's accuracy target (the user's choice, 9.2)

On a fresh 90-item set labelled blind (the first set's calm debate lines were labelled with reactions to meet the
`none` cap), the extended grid picked floor 0.2 on dev and the test split read 0.61 against 0.80, +0.31 over "always
none" (p 0.001), with 39 % of messages showing a reaction; random reactions score about 0.24. `reaction` is v2 with
floor 0.2 and stays in `AGENT_PORTS`. The miss is recorded and revisited in M15. **Rejected:** random reactions for
`agent` until M15; another rewording now (the test split would have been read twice).

### D40. The mood line ships off (the user's choice, 9.5: "I want the best performance")

E8's on/off run (34 non-neutral English turns, every candidate used) showed no gain in exact match (+0.00, 95 %
−0.17 to +0.09), a pairwise toss-up (0.51, unvalidated) and more replies naming the feeling with the line (5/34
against 2/34). The pre-set rule said "propose dropping"; the user asked for the best performance, which the data puts
with the line off. So `persona.moodLine` (runtime.json, default false) gates it; off, the request is `agent-1`'s byte
for byte and the engine reports `agent-1`; on, `agent-2` as D16 built it. The `moodline` suite forces it on for its ON
arm. View-as-prompt's note (D17) is removed. **Rejected:** keeping the line until M15 (underpowered but no sign of a
gain, and a sign of harm); a rewording now.

### Built notes (phases 5–8)

- **Splits (D27).** Both sets keep the hash rule, which gave `emotion` 72 dev / 28 test and `reactions` 65 / 25 (E8's
  60 / 30 is the expected ratio, not a quota; choosing item ids to hit it would game the rule).
- **`reactions` labels.** Exactly 27 items accept `none` (the cap). The listener's face now is never in its own
  acceptable set (a same-face reaction doesn't show); the builder asserts it.
- **Previous faces (`emotion`).** The table gives each one; for keep-false items marked neutral the builder rotates the
  face over the other six (skipping acceptable ones) until 34 of 100 start neutral, as the labelling rule says.
- **Judge sets (D28, D29).** The real items come from the committed frozen transcripts (the M8 paid runs' raw folders
  are not kept). The code search's hits include the leaked "Sad —" labels on some `naive` replies; 8 real "yes" items
  are used. The pairwise judge's both orders swap the two replies (its options never shuffle).
- **`moodline` (D30)** calls the live planner and engine in process, and gives each transcript a session row written
  with `create`'s helpers but never opened (the ledger names a session; no actor, greeting or turn runs). History
  numbers messages from 1 in order, and keeps the lines after the turn's `summary_upto`.
- **`latency` (D31)** reads each session's events from the run's database while it polls, and is in the runner's
  store-bypass list.
- **`smoke`** runs one `moodline` item and one `latency` turn under `agent`; in test mode a Decider fixture gives the
  item's Jev call 1 a confident face.

## Risks / Trade-offs

- **[LangGraph doesn't settle on the virtual clock]** → D2 measures it first and stops with choices. The plan's port
  doesn't depend on LangGraph, so swapping the inside doesn't touch phases 3+.
- **[A new dependency pulls `langchain-core` and `langsmith`]** → pinned in `uv.lock`; M7's tracing guard and a
  no-socket test; the user approves the version.
- **[Jev slower than group A's 420 ms from the user's network]** → the deadline fallback keeps the face, and the
  reply is never delayed past 700 ms + `thinking_ms`. The latency run reports it, and W12 tunes it in M15 (the user's
  rule: accept a slow Jev and measure it).
- **[`agent` 1:1 loses knowledge and memories until M12/M13]** → it's opt-in, stated in D9, and it's what W4's table
  locks.
- **[Scripted and mock 1:1 now bill simulated `turn_plan` and `face_check` calls]** → the portable spend tests change
  in both clients together. The session's reply-cost counter is unaffected (W7).
- **[Block bootstrap over ~10 blocks is coarse]** → reported with its unit and count. E8 already says these sets catch
  gross effects only.
- **[Labels drafted by the same AI that writes the wording]** → labels blind and committed first, the overlap check,
  B2's review, and test-split discipline (M8 D38).
- **[The one-write `turn.start` + `emotion` changes transaction grouping for every profile]** → the wire order and
  payloads are unchanged. The stored-equals-streamed and seed equivalence tests run on it.
- **[The face check can append after a later turn has started]** → `append_system1` targets the checked message only.
  Its guards (regenerate, streaming target, Forget) are M7's and tested.

## Migration Plan

- **No migration.** No new table or column. The events, traces and fixtures use existing fields.
- **Rollback:** `HORIZON_AI_PROFILE=naive`, the default, never touches the planner, the face check or `JevReactions`.
  `HORIZON_AI_PLANNER=naive` turns the plan off for `agent` alone.
- **Order inside the change:** the LangGraph gate first (D2). The paid runs come only after every offline phase is
  green.

## Open Questions

- **The exact `langgraph` version.** It is chosen at phase 1 by D1's rule, and the user approves it.

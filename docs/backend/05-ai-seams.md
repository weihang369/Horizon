# 05: AI Seams (ports, the Decider, hooks, placeholders)

> **v1.0.** This revision applies the review debate (Rounds 1–2, 2026-10-03).

The backend stage ships three things (D-72):
- **interfaces** for the AI team to implement;
- **scripted placeholders** (deterministic, offline, free);
- a few **naive real** implementations.

How the AI *thinks* is decided at the AI stage. The rule here is that **swapping in a LangGraph engine changes no backend code and no schema**, except adding an embedding space or the additive tables listed in §6.

## 1. Selection

`HORIZON_AI_PROFILE = scripted | naive | agent` (default `naive` when a key is set, `scripted` otherwise; `agent`, the AI stage's profile, becomes the default with a key at M15, [docs/ai/13](../ai/13-wrap-up.md) W4), with per-port overrides: `HORIZON_AI_TURN`, `HORIZON_AI_ROUTER`, `HORIZON_AI_REACTIONS`, `HORIZON_AI_HOST`, `HORIZON_AI_DIRECTOR`, `HORIZON_AI_SUMMARISER`, `HORIZON_AI_GUARDRAIL`, and from M4 `HORIZON_AI_DRAFTER`, `HORIZON_AI_IMAGE`, `HORIZON_AI_SONG` (e.g. `HORIZON_AI_TURN=scripted`). The turn engine, the router (M3), the profile drafter and the image generator (M4) have naive implementations; every other port is scripted in both profiles. The creation port is named `drafter` because `HORIZON_AI_PROFILE` is the selector itself. **`agent` is opt-in until M15** (M7, `ai-foundation` D12): `AGENT_PORTS` is still empty, so with a key every port resolves to its `naive` implementation (else `scripted`), and to `scripted` without a key; a per-port override still wins. The start-up log and every `horizon eval` report list each port's resolved implementation, so the opt-in can't hide what actually runs. Tests and the HTTP contract run use `scripted`; `/_test/ai-profile { profile, overrides? }` changes the selection at runtime (e.g. the Jev router with the scripted turn engine).

**Scripted spend is simulated and billed (D-81).** Scripted ports never open a connection, but their calls (replies, route decisions, verdicts, summaries) run through the same gateway pipeline as real ones: preflight with caps and reservations, one ledger row priced from `seed/pricing.json` (`provider: "scripted"`), the reply drain and the budget events. Energy, caps and Insight therefore behave exactly as on the MockClient. Picking `scripted` with a real key spends simulated amounts against the real daily cap; the default with a key is `naive`.

## 2. Ports (`horizon/ai/ports.py`)

All ports are async `typing.Protocol`s. They receive **frozen, JSON-serialisable Pydantic context models** (`TurnContext`, `SessionContext`, `JobContext`), never ORM rows, so an evaluation harness can build them from fixtures without the actor. They reach the network only through the gateway, using a `CallContext` that the context itself builds (`ctx.call_ctx(purpose)`).

### 2.1 The turn engine (the main seam)

```python
class TurnEngine(Protocol):
    def run(self, ctx: TurnContext) -> AsyncIterator[TurnEvent]: ...

TurnEvent = (
    Emotion(emotion: Emotion, source: EmotionSource, candidates: list[{label, p}] | None)
        # may be yielded more than once (e.g. an early tag, then a validator); the last one wins.
        # The actor re-emits a contract `emotion` event each time.
  | Token(delta: str)                     # control tags already stripped by the engine
  | CitationMap(entries: list[{n, chunkId, sourceId, title, locator?, quote, score?}])
        # with or after the first visible event (any event starts the message, and a refusal must leave none);
        # the actor keeps only the n's that appear in the final content (interrupted replies too)
        # and resolves them into `turn.end.citations` + `message_citations`
  | TracePatch(sections: dict)            # deep-merged by the actor
)
```

- **The actor owns** `messageId`, sequence numbers, persistence, energy, budget, `Message.usage` (from the ledger), timings, and the trace sections `model`, `energy` and `routing` (and, from the AI stage, `system1`, written through `append_system1`: docs/ai/13 W1). A `TracePatch` that sets any of those is rejected.
- **Insight.** The actor merges patches and emits the **full** trace as `insight`. Post-turn hooks (output guardrail, citation faithfulness, emotion validator) also return `TracePatch`es. A later `insight` for the same message replaces the earlier one (rev 1.3 note), which is already reducer behaviour.
- **`turn_traces.engine`, `engine_version` and `prompt_version`** are set from the engine's declared metadata.
- **Stop:** the actor cancels the iterator. The engine must hold no resources beyond the gateway stream, which is closed when the iterator is cancelled.

### 2.2 Port catalogue

*AI stage:* the last column's OQ references are resolved in [docs/ai](../ai/13-wrap-up.md): `TurnEngine` and the new `TurnPlanner` (01 A4–A6), `Router`/`WatchDirector` (07), `DebateHost` (08), `ReactionPredictor` (06 E5), `Summariser` (05 X3, 07 G10), `MemoryWriter` (`on_stretch` at session pauses), `MemoryRetriever` and the new `SessionRecall` (09 M1–M9), `KnowledgeIndexer`/`KnowledgeRetriever` (10 K1–K7), `Guardrail` (+ `check_prompt`, 11 S3–S5, 12 I3–I4), `ImagePromptCompiler` (12 I1, 13 W3).

| Port | Signature (abridged) | Scripted | Naive real (backend stage) | AI stage |
|---|---|---|---|---|
| `ProfileDrafter` | `draft(seed, intent, world, ctx) → DraftResult{profile, appearance.attributes, appearanceSummary, paletteId}`; `regenerate_field(character, field, ctx)` | Bank template | One DeepSeek structured-output call | OQ-AI-16 |
| `PromptCompiler` | `system_prompt(character, world, mode) → str` | Field join + adult/SFW clauses | + You card | OQ-AI-02/16 |
| `ImagePromptCompiler` | `base(appearance, age, preset)`, `emotion_edit(emotion)`, `tweak(text)` | **Real** (TESTING.md template + v2 fixes) | = | OQ-AI-09/10 |
| `ImageGenerator` | `generate(prompt, refs, seed?, ctx) → ImageResult` | Placeholder file | **Seedream 5.0 Flash** | D-61 |
| `SongBriefWriter` / `SongGenerator` | the brief comes from the `ProfileDrafter`'s draft (or the user's edit in the job input); `theme(seed, brief, title)` | **The procedural theme** (`.proc.json`, `themeSpecFromBrief`; free, D-83) | **Lyria 3 Clip** (`google/lyria-3-clip-preview`, D-87): one instrumental prompt compiled from the brief, a 30 s MP3 at $0.04; on a provider fault (error, timeout, refusal, rate limit, unusable audio) the task falls back to the procedural theme (creation-followups design D7) | OQ-AI-11 |
| `TurnEngine` | §2.1 | Bank lines, `Emotion` first | **One DeepSeek stream** (§5) | OQ-AI-02/04/07/13 |
| `Router` | `next(ctx) → RoutingDecision{selected, queue: list[str], candidates[{id,p}], forcedBy?, skipped[]}` | Mentions, then round-robin | **Jev choice** over the cast + `none`; `queue` ≤ 2 for group auto | OQ-AI-06/17 |
| `ReactionPredictor` | `react(ctx, listeners) → [{characterId, emotion, p}]` | None | **Jev:** one choice per listener, one call | OQ-AI-12 |
| `DebateHost` | `narrate(ctx) → AsyncIterator[TurnEvent]`; `verdict(ctx) → Verdict` | Fixed phases + canned lines; verdict `none` | DeepSeek narration; structured verdict | OQ-AI-05 |
| `WatchDirector` | `next_beat(ctx) → {speakerId, direction?, end_p?}`; `summarise(session, ctx)` | Round-robin; canned summary | Jev speaker choice; DeepSeek summary | OQ-AI-06 |
| `Summariser` | `rolling(ctx, upto_seq) → str`, stored in `session_summaries` | Last N lines | DeepSeek at block boundaries (§5) | OQ-AI-02 |
| `MemoryWriter` | `after_turn(ctx, perspective_character_id, message_id) → list[MemoryOp]` (port `memory_writer`) | `[]` | `[]` (scripted in both profiles) | OQ-AI-01 |
| `MemoryRetriever` | `recall(index: ScopedIndex, query: QueryBundle, k) → [MemoryHit{id, kind, text, source_session_id, score}]`; current (not superseded) items only | Most recent k | FTS5 only | OQ-AI-01 |
| `DocumentConverter` | `convert(path, mime) → ConvertedDoc{markdown_with_page_markers, pages}` | Plain-text read; placeholder passages for PDF/DOCX (the mock's rule) after 0.8 s on the runtime clock, so in-flight states are testable | **Docling (CPU, spawned process)**. Not chosen by the profile or the key: real conversion by default, scripted by default in test mode, `HORIZON_AI_CONVERTER` overrides (D-96) | D-62 |
| `KnowledgeIndexer` | `chunk(doc) → [Section{text, heading_path, pages, children[{text, locator, heading, offsets}]}]` + `tokenizer_id` | Heading split + fixed windows | Same (sizes are AI-stage tunables) | OQ-AI-03 |
| `KnowledgeRetriever` | `retrieve(index: ScopedIndex, query: QueryBundle, k) → [KnowledgeHit{chunk_id, source_id, title, type, locator, text, section_text, score}]`; `uses_vectors` gates the query embedding | FTS5 top k | FTS5 20 ∪ vector KNN 20, RRF (k = 60), score in [0, 1] | OQ-AI-03 (MMR, Jev rerank) |
| `Embedder` | `embed(texts, kind: "query"\|"document", space: EmbeddingSpace, ctx, hooks?) → Embedded{vectors, cached}` (LRU keyed by `(space.id, kind, sha256(text))`; per-batch hooks store vectors in the ledger row's transaction) | Hash → unit vector, billed as simulated spend (D-81) | **Qwen3 Embedding 8B** with the active space's model and dimensions (D-95); query instruction from the space; truncate + renormalise | D-64 |
| `Guardrail` | `check_input(text, ctx)` / `check_output(text, ctx) → [Check{name, verdict, p}]` | Pass | **Jev noul**, fail-open with a flag | OQ-AI-08 |

```python
MemoryOp = Insert(draft) | Supersede(old_ids: list[str], draft) | Reinforce(id, importance) | Touch(ids)
# Applied by the backend's MemoryStore.apply(character_id, ops) in ONE transaction (row + FTS + vec);
# drafts carry kind, text, importance, source_* ids incl. source_variant_id, source_mode, about_character_id.

QueryBundle = { text: str, vectors: dict[space_id, list[float]] }
# Built ONCE per triggering user message. naive/scripted (D-97): the actor starts the query embedding as soon as `send` arrives, in
# parallel with routing, and only when it can pay off (a vector retriever, a key, a responder with vectors). It is
# reused by every responder of that message; a reply waits for it at most `retrieval.queryEmbedWaitMs`.
# agent (D-100): started at the gate, only when Jev call 1 asks for search; waited for at most 400 ms (docs/ai/10 K4).

ScopedIndex  # services/knowledge/index.py: read-only, built by the RUNTIME per turn for the speaker's world and
# character. Every keyword and vector query binds the character (the vec0 partition key) and re-checks world and
# character on the join back (NFR-23). Retrievers are policy only: which candidates, how to fuse them.
```

**Retrieval runs in the runtime (D-92).** Before a turn's engine runs, the runtime builds the `ScopedIndex`, calls the configured `MemoryRetriever` and `KnowledgeRetriever` (k from `retrieval.knowledgeK` / `retrieval.memoryK`, 5 and 3) and freezes the hits into `TurnContext.knowledge` / `.memory` (with `.query`, the text used). Engines receive plain data and never query storage, so a context still round-trips through JSON and an evaluation harness can replay a turn with exactly the passages it saw.

**Guardrail block after streaming** (backend rule): `turn.end` with `status:"error"` and `content_refused`. The content and its persisted `token` events are scrubbed (the Forget path, by `message_id`), and the reply is excluded from memory.

## 3. Decider (Jev)

**Jev first (D-66):** every bounded decision is a Jev question. `horizon/ai/decider.py` is the only way to ask one.

```python
class Decider:
    def start(self, state: dict, questions: dict[str, Question], ctx: CallContext, *,
              purpose: str, fallback: Callable[[], Awaitable[Answers]] | None = None) -> DecisionCall
    async def ask(self, state, questions, ctx, *, purpose, timeout_ms=None, fallback=None) -> DecisionResult
        # == start(...).by(now + timeout); the timeout is the call's, else the bank questions' deadline key, else the purpose's

class DecisionCall:
    async def by(self, at: datetime) -> DecisionResult   # answers if back by that clock instant, else the fallback (run once)
    async def final(self) -> DecisionResult               # the real answers whenever they land
    def cancel(self) -> None                              # readers get DecisionCancelled; the sent request still settles
# DecisionResult.answers[q] = ChoiceAnswer | NoulAnswer | ScoreAnswer, each with source: "jev" | "fallback" | "fixture"
```

*Rewritten in M7 (`ai-foundation`, [docs/ai/13](../ai/13-wrap-up.md) W11, group A).*

- **Calling.**
  - It calls `typesafe/jev-1.13` (pinned, never `~latest`). **All independent questions about one state go in one call**, because they're answered in parallel. Questions come from the question bank (`horizon/ai/questions/`, docs/ai/02 B9), which declares each one's state fields; a state with an undeclared field, or free text outside a `quoted_*` field, is refused before sending.
  - **The size check:** state + the longest question ≤ 30,000 tokens (UTF-8 bytes ÷ 3), and at most 64 questions. Over either, nothing is sent, reserved or recorded, and the fallback answers with reason `too_large`. Jev reports an oversized request as HTTP 429, so this must refuse first ([group A](../ai/checks/group-a.md) A1).
  - Each request runs as an `rt.spawn` task, and deadlines are read on the runtime clock (virtual in tests). Calls may run concurrently; there is no Decider semaphore below 4.
- **Validation.** Each answer is checked against its declared type and option set. If only some answers are invalid, the fallback runs **just for those questions**.
- **Failure, a missed deadline or a rate limit:**
  - use `fallback()` if one was given (run once, however many readers);
  - otherwise raise `DecisionUnavailable`, and the caller takes its hold path (R-13).
  - A late answer is still recorded in the ledger (`finish_reason: "late"`) and stays readable through `final()`.
  - A 429 falls back at once on the hot path; `importance`, `memory_guard` and `rubric` wait max(1 s, Retry-After) up to 5 s and send once more if their deadline allows.
  - Off the hot path, the fallback may be a DeepSeek call (category `decision`, never drains energy). **On the hot path the fallback is always deterministic.**

*AI stage:* the `agent` profile's purposes, questions, deadlines and fallbacks are the Jev map in [docs/ai/13](../ai/13-wrap-up.md) W5; this table is the backend stage's (`naive` keeps `route`).

| Purpose | Deadline | Deterministic hot-path fallback |
|---|---|---|
| `route` | 400 ms | @mention, else round-robin over eligible speakers (least recent first); trace marks the fallback, with no `candidates` |
| the `agent` purposes | per question deadline key, `seed/pricing.json` → `timeoutsMs.decision` (docs/ai/13 W12) | docs/ai/13 W5 |
| `reaction`, `importance`, `rubric`, … | 1.5 s / 3 s | Skip (reactions are optional) / a rule |

*M7 removed `gate`, `rerank`, `emotion` and `watch_end`: nothing called them, and the `agent` purposes replace them (W5).*

- **Traces and the ledger.** Probabilities flow into `TurnTrace` (`emotion.candidates`, `routing.candidates`, `guardrail.checks[].p`, `knowledge.retrieved[].score` = rerank p). Every call appears in `TurnTrace.calls[]` and the ledger (`category: decision`, `purpose`).
- **Thresholds** are config per purpose, tuned at the AI stage on labelled data. `confidence` measures how peaked the distribution is, not accuracy.
- **Debate rubric:** Jev `score` has at most 10 levels, and `Verdict.scores` runs 0–10. The mapping is the expected value over the levels, scaled to 0–10 (AI stage defines the levels).

## 4. AI state hooks and what the backend guarantees

```python
class AiStateHooks(Protocol):            # implemented by the AI layer; called from the ai_purge_queue outbox worker
    async def on_forget(self, memory_item_ids: list[str], character_id: str, message_ids: list[str]) -> None: ...
    async def on_delete(self, scope: Literal["message", "session", "character", "world"], ids: list[str]) -> None: ...
# A Forget's queue row carries {memoryItemIds, characterId, messageIds} (scope 'memory') and goes to on_forget (M5).
```

- **Delivery.** Lifecycle services commit, then write an `ai_purge_queue` row. The worker calls the hooks **at least once**, with retries at startup, so hook implementations must be idempotent.
- **Rule:** `graph.db` and any AI cache store **IDs, never memory text**. A test greps `graph.db` for forgotten text after Forget.

**What the backend guarantees:**
- **A frozen `TurnContext`** with:
  - the session, participants (with energy state), recent messages (active variants only), the latest `session_summaries` and the You card;
  - the mode config and state;
  - the `world_id`/`character_id` scope;
  - **the retrieved hits** (`knowledge`, `memory`, `query`), already bound to that scope by the runtime (NFR-23, D-92) instead of pre-bound retrievers;
  - `call_ctx(purpose)`.
- **A post-turn queue per character** for memory ops; reactions go through the session actor. *AI stage: memory is written at session pauses by `memory_run` tasks instead ([docs/ai/09](../ai/09-memory.md) M1).*
- **Storage:** memory (+ `MemoryStore.apply`), knowledge sections and chunks, embedding spaces (+ dual-write while building), `session_summaries`, traces with version columns, `message_citations`, the ledger with `purpose`.
- **`data/graph.db`**, reserved for LangGraph checkpoints, which are closed and deleted correctly by Factory reset.
- **Caps, reservations and energy** enforced around every call; `gateway.on_call` is the hook for evaluation logging.

**Built in M7 (`ai-foundation`):**
- **`ai_calls` capture** (`services/capture.py`, off unless `HORIZON_CAPTURE_AI_CALLS=1`). The gateway builds redacted bodies only when capture is on (chat messages and text, Jev state, questions and answers; never embedding inputs or vectors, image or audio bytes). `on_call` appends to a bounded queue (2,000; overflow counted in the next row's `dropped_before`), and a `rt.spawn` writer flushes every 2 s of clock time or at 200 rows. `TurnRunner.finish()` adds one `turn` row with the frozen `TurnContext` and the routing/Decider fallback flags. Retention: 7 days, then the newest 20,000.
- **Forget and capture:** Forget marks the queue and deletes the character's rows (and the world's rows with no character) inside its own transaction.
- **The first real hooks:** `CompositeHooks([CaptureHooks])`. Character and message deletes remove their rows, session and world deletes cascade by FK and repeat harmlessly, and `on_forget` is a no-op for capture.
- **System 1 rows** (contract rev 1.4): `SessionActor.append_system1(message_id, variant_id, rows, calls)` adds rows after a turn inside the actor, with three guards: Regenerate (an inactive variant's rows are dropped), streaming (rows wait for `finish()`), and Forget (rows and recalled entries about deleted memories are removed inside the writer transaction). An insight with no engine metadata keeps the stored engine columns and `created_at`.

## 5. Naive real `TurnEngine` (backend deliverable, M3)

- **Prompt order (NFR-35):** static persona and system prompt (+ You card) → `session_summaries` (rolling) → history → dynamic blocks.
- **Prompt v2 (M5, D-93; `PROMPT_VERSION = "naive-2"`).** When the runtime retrieved anything, **one** system message goes after the history (dynamic last, so the cached prefix is untouched):
  - "Passages you can use…" with `[n] Title, locator: section text`, one per section (child hits of the same section share a number), each ≤ 1 200 chars;
  - "Things you remember about this world…" with up to 3 memories;
  - one line: cite a passage with its `[n]` only when you rely on it.

  The engine yields a `CitationMap` for every numbered passage; the runtime keeps only the markers the reply wrote. After the stream it sets `trace.knowledge.retrieved` (`cited` from its own output), `trace.memory.recalled` (which writes the Forget refs) and `context.used.memory/knowledge`. **With nothing retrieved the request is byte-identical to v1** (until `naive-3`, [docs/ai/03](../ai/03-llm-parameters.md), [docs/ai/10](../ai/10-rag.md) K13).
- **Prompt v3 (M7, `naive-3`, [docs/ai/03](../ai/03-llm-parameters.md) C1–C7).** Each reply takes its `runtime.llm.calls` row (`reply.chat` 1.3 / `reply.debate` 1.0, thinking off) and a shorter cap chosen after the plan; the system prompt ends with the session's length line ("1–3 short messages, each on its own line, about 70 words" in 1:1); `stop` holds `
<Name>:` for everyone else and `
[<kind>]`; a leading `<own name>:` is dropped before or after the tag; a history ending on the speaker's own line gets a trailing cue; an empty reply is retried once before anything shows (the face waits for the first word). JSON calls repair stray inner quotes locally before their one paid retry.
- **Scripted citations (D15).** The scripted engine ports the mock's `liveCitations` with its own RNG stream (`{seed}:{turn}:cite`): about 55 % of replies with hits cite 1–2 passages, one more is retrieved but uncited, and replies without hits are unchanged. It never uses memory hits (parity with the mock).
- **Cache-friendly history window.** The window grows until it is full, then **drops the oldest half in one step**, with the summary refreshed at that block boundary. A one-message sliding window would change the prefix every turn and miss the cache.
- **Inline emotion tag** (OQ-AI-07 A): the model is asked to start with `<e:label>`. The parser:
  - buffers up to 32 characters or until `>`, and handles a tag split across chunks;
  - accepts only the 7 labels;
  - if no valid tag appears in the buffer, releases the text and yields `Emotion(source="default")` (keeping the previous face);
  - strips stray tags anywhere before tokens are yielded.

  These rules are also encoded in the scripted engine's fixtures.
- **Parameters:** reasoning off and `max_tokens` from the per-mode reply caps (config). Model pinning and the routing above.

## 6. Deferred to the AI stage (additive; no rework)

| Item | Why it can wait |
|---|---|
| `ai_calls` evaluation table (request/response per call, retention, scrubbed by Forget) | **Built in M7** (§4): capture, retention, Forget and the delete hooks ([docs/ai/02](../ai/02-evaluation-observability.md) B10) |
| `memory_consolidate` job | The job kind is TEXT. **Withdrawn:** nothing is merged automatically ([docs/ai/09](../ai/09-memory.md) M5) |
| `message_fts` (in-session keyword recall) | Additive virtual table. **Designed:** [docs/ai/09](../ai/09-memory.md) M9 |
| `knowledge_chunk_redirects` | Only needed once content is re-chunked. **Withdrawn** ([docs/ai/10](../ai/10-rag.md)) |
| Trigram FTS tokenizer for CJK text | An FTS rebuild. **Withdrawn:** `porter unicode61` stays; CJK search is in the [v2 backlog](../v2/README.md) §3 ([docs/ai/10](../ai/10-rag.md) K11) |
| Prompt layout and budgets, memory policy, chunk sizes, MMR, rerank thresholds, **the embedding comparison test** (final model and dimensions), emotion validation, debate rubric, guardrail policy, LangGraph graphs, evaluation harness | AI design (OQ-AI-01…17). **Designed:** [docs/ai/01–13](../ai/13-wrap-up.md); the embedding comparison test is [docs/ai/10](../ai/10-rag.md) K3. **The evaluation harness is built (M7):** `horizon/evals/` (runner, canary, decisions and smoke suites, metrics, data checks, stats) and the shared response store (`data/cache/`, the eval view for `horizon eval` runs, the seed view for seed knowledge embeddings); see [evals/README.md](../../evals/README.md) |

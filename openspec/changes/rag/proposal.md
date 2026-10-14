# Proposal: rag (M12)

## Why

A character can hold up to 20 documents, but under `agent` every turn is quick: no gate is asked, nothing is
searched, and nothing is cited (doc 13 W4: "none in `agent` 1:1" until M12). `naive` and `scripted` still retrieve as
M5 built them, with weaknesses doc 10 found:
- `para@1` makes heading-only pieces that embed to nothing;
- the query is the raw message, so follow-ups like "and nights?" and non-English questions miss;
- every hit reaches the prompt unchecked (course notes 6.14's "weak matches presented as answers");
- `naive`'s quote is the piece's first 400 characters, which often misses the cited fact.

Doc 10 (K1–K15) designs the fix, and doc 13 W4 makes it M12:
- `pack@2` and the header space;
- the shared search pipeline;
- D-100's embedding at the gate;
- the rewrite;
- Jev call 2;
- deterministic citations;
- `<passage>` tags.

**Why now:** M9–M11 built every plan this needs (Jev call 1, the cast plan, the follow plan, the debate plan) and left
a `route → deep` edge waiting in the plan graph. M13 (memory) runs its recall on this pipeline, so the pipeline has to
come first (W4's rejected "memory before RAG").

**It lands as one change, the largest so far.** The pieces depend on each other in a straight line:
- the chunker and the space feed the pipeline;
- the gates feed the query;
- the query feeds the search;
- the search feeds Jev call 2;
- Jev call 2 feeds the block and the citations.

The evaluation's comparisons (piece size, header, space, rewrite) need all of them together. Split, the retrieval suite
would be built twice and paid twice. The phases are ordered so each ends green offline, and the paid runs come last.

## What Changes

**Phase 0: the base (design D2)**
- M11's gates are confirmed on a16a5ec (backend 1648, frontend 529 / http 62, e2e 66).
- M12 then adds offline storm tests for each new cancel path:
  - the rewrite;
  - the query-embedding wait;
  - the 8 `deep_check` requests and the set check;
  - the `message_ai_meta` write;
  - a reindex or space build while a turn searches.

**The pieces (doc 10 K1, K12; design D3)**
- **`pack@2` replaces `para@1`:**
  - structure first, then recursive cuts;
  - ≈ 300 tokens, never over 400;
  - headings carried forward;
  - `pp. N–M` for a piece that runs over a page break;
  - tables cut between rows, with the header row repeated.
- **One `CHUNKER_VERSION`,** imported by `sources.py`. The mock's `paragraphs()` becomes its twin, and the shared
  portable test changes with it.
- **Existing sources:** seed sources keep their authored pieces; a `para@1` source keeps working until it is
  reindexed. There is no automatic sweep.

**The space (K3; design D4, D5)**
- **Each document piece is embedded with a header:** the title without its extension, then the heading path (left out
  when it equals the locator).
- **The plumbing:**
  - `SpaceSpec.doc_template`, persisted;
  - a knowledge kind in the embedder;
  - the LRU keyed on the request text.
- **The new default space and instruction:** `qwen3-emb-8b@1024+h`, with the instruction "Given a chat message,
  retrieve passages that help answer it".
- **`horizon space build`:** a new CLI command that estimates the cost, asks, then builds, copying vectors that don't
  change. Fresh installs start in the new space; an existing install keeps its space until the command is run.

**The gates and the query (K4; W5 rows 2, 5, 6; D-100; design D6–D10)**
- **"Needs documents?"** is asked per candidate with searchable knowledge in every plan:
  - Jev call 1 in 1:1;
  - the cast plan (group, watch);
  - the follow plan;
  - the debate plan.
- **"Standalone?" and "English?"** are asked once per message, only in 1:1 and group (debate and watch never rewrite).
- **The rewrite:** new purpose `query_rewrite`, DeepSeek with this speaker's cached prefix, at temperature 0.0.
  - Its deadline is `rewriteMs`, and its output is checked.
  - It is stored per message and speaker in the new `message_ai_meta` table, reused on regenerate and cancelled
    with the turn.
- **Everything starts at the gate, in parallel:** BM25, the message embedding (D-100), and the rewrite.
- **`QueryBundle`** gains the query texts, the keyword terms, the vectors per text and the query's source.
- **Keyword terms improve:**
  - stop words dropped;
  - terms ordered by rarity;
  - at most 24 terms when the query was rewritten.

**The search, Jev call 2 and the keep rule (K5–K7; W5 rows 12, 13; design D11–D14)**
- **One pipeline, shared with M13's recall:**
  - BM25 20 + dense 20 per query text;
  - two-step RRF, then min–max normalisation;
  - MMR (λ 0.7) down to 8 pieces;
  - `ScopedIndex` reads stored vectors for MMR.
- **Jev call 2:** new purpose `deep_check`, one request per piece with three written levels, plus the set check when
  nothing is found but 2 or more pieces are usable. Its deadline is `deepCheckMs`.
- **The keep rule:** found / partly / not found, with k = 3 in 1:1 and 2 elsewhere. Debate and watch never abstain.
  The fallback carries no citation score and is marked `fallback: true`.
- **Where the deep work runs:** one deep graph is shared by every mode.
  - In 1:1, it runs on the plan graph's deep edge.
  - In group, watch and debate, it runs per speaker once the plan has fixed the speaker.
  - It runs ahead during watch's wait and during a debate opening's prefetch.

**The reply (K8, K9, K13; doc 11 S6; design D15–D18)**
- **The `agent` tail gains:**
  - the documents block, at most 1,400 tokens, with each passage wrapped in a `<passage>` tag and the tags stripped
    from piece text and titles;
  - the partly line;
  - the not-found line, at the quick length.
- **Citations:** built in Python from the kept list, with the quote window. `TurnTrace.knowledge` has `trigger
  "gated"` and the query searched.
- **System 1:** rows for the gates and the passages.
- **`naive`'s next prompt version** reads a 1,200-character slice centred on the hit piece.
- **The Knowledge tab:** its "Preview" ribbon is removed (PRF-08).

**Evaluation (K14; W6's M12 row; doc 10 §5; design D19–D24)**
- **The retrieval suite (`horizon eval retrieval`), 205 questions** over the corpus and the seed:
  - 100 answerable (10 needing two passages);
  - 40 unanswerable;
  - 30 follow-ups;
  - 15 non-English;
  - 20 naming a document.
- **What it reports:** its metrics, K7's cross-validated thresholds, and the comparisons:
  - the spaces;
  - the piece target;
  - MMR λ;
  - the query instruction;
  - rewrite vs none;
  - header vs none.
- **New layer-1 sets:**
  - "needs documents?" (≈ 120 items, B2), which the prompt didn't list but B5's `t_gate` and `t_confident` need;
  - "standalone?" (100);
  - "English?" (40).
- **The "Not-found reply" judge,** validated by B4 before it counts.
- **Doc 10 §5's checks:**
  - check 2: deep-turn timing;
  - check 3: 10 rewrites;
  - check 4: `pack@2` run locally;
  - check 5: `deep_check` and the noul probe.
- **Offline tests and smoke cover all of the above.** Paid runs need the user's OK each time, off-peak; W6 says
  ≈ $0.12.

**Docs:** everything doc 10 §6 lists, and the results in `docs/ai/checks/m12.md`.

**No contract change** (design D25).
- The wire types doc 10 needs already exist: `Citation.score`, `KnowledgeChunk`, `TurnTrace.knowledge` with `query`
  and `trigger "gated"`, and `calls[].fallback`.
- W4 lists `client-contract` because the portable contract suite's chunking test changes with `pack@2`. That is a
  test, not a requirement, so there is no delta.
- No route, field or event is added.

**Not in M12:**
- recall from earlier, "needs something from earlier?", the memory list and `dupCosine` (M13);
- safety nouls and the output check (M14);
- conversations and the `naive` arms (M15).

The `agent` profile stays opt-in.

## Capabilities

### New Capabilities

- `deep-turn`: an `agent` reply that uses the speaker's documents. It covers:
  - the query built at the gate (D-100, the rewrite, `QueryBundle`);
  - Jev call 2;
  - the keep rule and its outcomes per mode;
  - the fallback;
  - the kept passages frozen into the plan;
  - deterministic citations;
  - the rewrite's storage.

### Modified Capabilities

- `knowledge-sources`: pieces come from `pack@2` (locators, heading carry, page ranges, tables), and a `para@1`
  source is re-chunked on reindex.
- `retrieval`:
  - the query embedding at send stays `naive`'s and `scripted`'s (D-97), while `agent` embeds at the gate (D-100);
  - the shared search pipeline and the keyword terms;
  - `naive`'s centred slice.
- `embedding-spaces`: the header template and knowledge kind, the request-text cache key, the new default space and
  instruction, and a build that copies unchanged vectors.
- `local-backend`: the `horizon space build` command.
- `turn-plan`: Jev call 1 and the cast plan ask the gates; the plan graph's deep branch; the plan carries the kept
  passages.
- `follow-plan`: the follow plan asks the gates for its candidates.
- `debate-plan`: the debate plan asks "needs documents?" per member, and the deep work starts once the member is
  fixed.
- `watch-direction`: a plan made ahead also starts its speaker's deep work.
- `ai-ports`: the `agent` reply engine reads its passages from the plan, never from a retriever.
- `provider-gateway`: `deep_check` and `query_rewrite` are labelled and timed; a refused `deep_check` falls back at
  once.
- `question-bank`: the M12 entries (`docs`, `standalone`, `english`, `passage`, `passage_set`) and their thresholds.
- `system1-trace`: gate rows and passage rows.
- `persona-prompt`: the documents block with `<passage>` tags, the partly and not-found lines, and the prompt labels.
- `session-event-sourcing`: the `message_ai_meta` exemption (W13).
- `data-storage`: migration 0004, `message_ai_meta`.
- `demo-data`: the mock's `pack@2` twin, and the System 1 fixture's M12 rows.
- `evaluation-harness`: the retrieval suite, the M12 layer-1 sets, the Not-found judge, the deep-turn timing and the
  space comparison.

## Impact

- **Backend, the knowledge services:**
  - `ai/chunker.py`, `services/knowledge/{sources,pipeline,build,index}.py`, `db/spaces.py`, `ai/embedder.py`;
  - a new `ai/agent/deep.py` (the deep graph), `ai/agent/rewrite.py` and `ai/agent/keep.py`;
  - `ai/retrieval.py` (the pipeline, the terms, `QueryBundle`);
  - `sessions/retrieve.py` and `sessions/turn.py`.
- **Backend, the plans and prompts:**
  - `ai/agent/{planner,plan_graph,cast_plan,follow_plan,debate_plan,persona,turn}.py`;
  - `ai/naive/prompt.py`;
  - `ai/contexts.py` (`TurnPlan` gains its kept passages and outcome);
  - `gateway/context.py`.
- **Storage and config:**
  - migration `0004_message_ai_meta`, `sessions/lifecycle.py` (fork copies its rows);
  - the question bank (5 new entries) and `questions.lock.json`;
  - `seed/runtime.json` with `runtime.config.ts` (the `retrieval.agent` knobs);
  - `seed/system1.fixture.json`.
- **Evaluation:** `evals/` (new suite and sets), `horizon/evals/`.
- **Frontend:**
  - `mock/engines/knowledge.ts` (`pack@2` twin), `clientContract.portable.ts` (the chunking test);
  - `features/profile/tabs.tsx` (the ribbon);
  - `scripts/seed-build/runtime.config.ts`.
- **Spend:** about $0.12 of paid runs (W6), each asked for with an estimate.
- **Dependencies:** none new. Two PDFs for check 4 need the user's OK before download (design D22).

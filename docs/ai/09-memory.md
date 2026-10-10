# 09: Long-term memory

> **Status: agreed with the user, 2026-10-10** (AI stage, task 9 of 13).
> - It resolves **OQ-AI-01** (memory architecture) as the BA's option B, built in our own code: memories in SQLite
>   with keyword and vector search (already built in M5), written by a LangGraph graph whose decisions are Jev's.
>   It also settles what earlier docs left here: **the memory policy** (doc 01 §9), **the memory graph and whether it
>   needs `graph.db`** (doc 01 A7, A9), **the memory-extraction prompt and schema** (doc 03 §7), **"last time we
>   talked about…" greetings and memory in the prompt** (doc 04 §7), **points of view across sessions** (doc 05 §7)
>   and **the memory sets and labels** (doc 02 §8).
> - Decisions are numbered **M1–M12**, each with the alternatives we rejected.
> - It builds on [01-agent-architecture](01-agent-architecture.md) (A1–A14),
>   [02-evaluation-observability](02-evaluation-observability.md) (B1–B12),
>   [03-llm-parameters](03-llm-parameters.md) (C1–C9),
>   [04-persona-prompt-drafter](04-persona-prompt-drafter.md) (P1–P12),
>   [05-context-engineering](05-context-engineering.md) (X1–X10),
>   [06-emotion-reactions](06-emotion-reactions.md) (E1–E9),
>   [07-turn-taking-energy](07-turn-taking-energy.md) (G1–G13) and [08-debate](08-debate.md) (V1–V12).
> - **No contract change and no requirement change.** `MemoryItem` keeps its shape and its four kinds; Insight's
>   `memory.recalled` and the ledger's `memory` category already exist. The changes are backend-only (two session
>   columns, a new port signature, the runtime triggers) plus removing the Memory tab's "Preview" ribbon.

## 1. The question

The rolling summary and the history window (doc 05) already carry what was said **inside** one session. Long-term
memory is what a character carries **into the next one**: that Kai quit coffee, that Hana sold his bouquet to a
nervous proposer, that Mei lost last week's debate on four-day weeks. Task 9 decides **when memories are written,
who forms them, how they stay tidy, how they reach a reply, and how all of it is measured**, within D-71 (every mode,
each character's own point of view; the user can only view and forget).

**The user's decisions (2026-10-10):**
- **Memories are written only when a session pauses, not during the chat** (M1). The user's reasoning: inside a
  session the prompt already holds the history, word for word or summarised, so a memory written mid-chat pays for
  something nobody can use yet. It is about 4× cheaper and sees each sitting whole. Three additions make it safe:
  a pause also covers 1:1 and group sessions that never "finish"; opening a new session with the same character runs
  the old one's pending part first; a sweep at start-up catches a crash.
- **Everyone present forms memories, each from their own point of view, in one call** (M3), as D-71 asks.
- **Recall is a small core block on every reply plus a search when Jev says the reply needs memories** (M8).
- **Memory stays tidy because Jev compares each new memory with its nearest old ones when it is written** (M5):
  same → reinforce, replaces → supersede, otherwise insert. No background job, no automatic deletion: only the user
  forgets.

## 2. What Horizon already has

From the code:

1. **Storage and Forget are finished (M5).** `memory_items` holds `kind`, `text`, `importance`, the source session,
   message and variant, `source_mode` (D-71), `about_character_id`, `last_recalled_at`, `recall_count` and
   `superseded_by`, with FTS5 and a `memory_vec__{space}` table per embedding space
   ([02-storage §3.7](../backend/02-storage.md)). `MemoryStore.apply(character_id, world_id, ops)`
   ([store.py](../../backend/horizon/services/memory/store.py)) applies `Insert | Supersede | Reinforce | Touch` in
   one transaction under a per-character lock, validates the whole batch (a `Supersede` of a memory that is no longer
   current fails), and embeds new texts before taking the writer lock. Forget
   ([forget.py](../../backend/horizon/services/memory/forget.py)) removes the memory's whole supersede chain
   (`chain_of`), zeroes its vectors, scrubs its text from traces and insight events, and truncates the WAL (D-94).
2. **Nothing is ever remembered today.** The post-turn queue (`_remember` in
   [turn.py](../../backend/horizon/sessions/turn.py)) calls `MemoryWriter.after_turn` after every complete reply, for
   the **speaker only**, as a task in the **actor's** background set. Both profiles use `NoMemoryWriter`
   ([scripted/ports.py](../../backend/horizon/ai/scripted/ports.py)), which returns `[]`. The only memories are the 5
   seed ones ([06-seed-data §5](../requirements/06-seed-data.md)).
3. **Recall is minimal.** `ScriptedMemoryRetriever` returns the 3 newest memories; `NaiveMemoryRetriever` the top 3
   FTS matches for the turn's query text ([retrieval.py](../../backend/horizon/ai/retrieval.py)); the naive prompt shows them as
   "Things you remember about this world…". `ScopedIndex` has `memory_fts` and `memory_recent` but **no vector search
   over memories**, although `MemoryStore` writes the vectors. Importance, recency and `source_mode` are never used.
   `Touch` exists but nothing calls it.
4. **Regenerate ignores memory** (finding). A regenerate streams a new variant into the same message; any memory taken
   from the old variant would stay. No live bug today, since nothing is written.
5. **Real "session finished" signals already exist** in [lifecycle.py](../../backend/horizon/sessions/lifecycle.py):
   - `leave`, which the client sends when it leaves an active session screen
     ([sessionRuntime.ts](../../frontend/src/client/sessionRuntime.ts)), pausing it with `navigated_away`;
   - `end`, which sets `status: "ended"`; a debate also ends after its verdict, and watch reaches `turn_cap`;
   - the actor's **idle release** after 10 minutes of quiet (`idleReleaseMs` 600,000,
     [actor.py](../../backend/horizon/sessions/actor.py)), which stops the actor **and cancels its background set**.
     A memory task in that set would be killed by the very pause that should start it.
6. **Requirements:** D-71 (all modes, own point of view, source mode tagged for down-weighting; view and forget only,
   no edit, pin or add); CHAT-06 AC1 (only the active variant counts for context and memory); ENG-02 AC2 (memory work never
   drains energy, it counts against the daily cap only); PRF-07 (the tab shows text, kind, source session, date and an
   importance badge, with View source and Forget); INS-01 (Insight's Memory section lists long-term items recalled);
   NFR-23 (no memory crosses worlds); NFR-35 (memory is dynamic and goes last in the prompt).
7. **The gateway already has** purposes `memory` (ledger category `memory`) and `importance` (`decision`)
   ([context.py](../../backend/horizon/gateway/context.py)); doc 03 C1 has the `memory` row (thinking off, 0.7, JSON).

**Course notes, 7.1.8:** long-term memory is facts kept in a database and filtered by user (Mem0, Zep); systems
write and compress **on a hard-coded rule, not when the model chooses to**; and good systems **edit** memory
entries rather than rewrite the whole store, so good old entries are not lost (ACE). M1, M5 and M6 follow all three.

## 3. The design in one picture

```text
 during the chat                     a pause                               the next session
 ───────────────                     ───────                               ────────────────
 replies use:                        leave · end · verdict · watch cap     core block: top 5 memories
  - core block (top 5)               · 10 min idle · new session with      on every reply (≤ 320 tokens,
  - search when Jev says             the same character · start-up sweep   in the tail)
    "needs memories?"                          │                           + search when Jev says
 nothing is written                            ▼                             "needs memories?"
                                  the memory graph (LangGraph), once,
                                  over the messages since the checkpoint
                                  1. DeepSeek JSON: memories for everyone
                                     present, each from their own view
                                  2. Jev score: importance (drop the lowest)
                                  3. nearest 3 old memories → Jev choice:
                                     same / replaces / both stay true
                                  4. ops + checkpoint in one transaction
```

## 4. Decisions

### M1. Memories are written when a session pauses, not after each reply (the user's decision)

**Decision:**
- **A pause run** handles every message since the session's memory checkpoint (M2). It starts when:
  1. the user **leaves** the session screen (`leave`, `navigated_away`);
  2. the session **ends**: the End command, a debate after its verdict, watch at `turn_cap`;
  3. the actor's **idle release**, after 10 minutes of quiet; this catches a closed browser tab, which sends no
     `leave`;
  4. **a session opens with a character who has pending messages in another session** (create, or an actor started
     for a resume): the other session's run starts at once, so a new chat with Amara two minutes after the last one
     already knows it (fix 2 below);
  5. **start-up**: a sweep finds every non-seed session with messages after its checkpoint and queues their runs; a
     clean shutdown never waits on DeepSeek, it leaves them to this sweep (fix 3).
- **Nothing is written during the chat**, and the per-reply `_remember` queue is removed.
- **Runs belong to the runtime, not the actor:** each goes through `rt.spawn` as `memory_run:{sessionId}`, so the
  idle release that triggers it can't cancel it. At most **2 runs at once** (`memory.maxConcurrent`); one run per
  session at a time, and a trigger during a run marks the session to run again after it.
- **The minimum worth a run:** at least one user message, or at least 4 character lines (watch and debate have no
  user lines). Below that the checkpoint advances with no call.
- **Seed sessions** are replay-only and never run. **Test mode and the `scripted` profile** run the same triggers with
  a writer that returns nothing, so no call is made.

**Why:** inside a session, memory adds nothing the history and the summary don't already give (the user's point). One
pass over a whole sitting costs about a quarter of per-exchange writing (M12), sees the full story, and writes fewer,
more complete memories. Regenerate only works on the last character message, so by a pause every earlier variant is
final.

**The three additions, and why each is needed:**
- **1:1 and group never "finish":** `leave`, `end` and the idle release together cover every way a user stops.
- **Freshness:** without trigger 4, leaving a chat and opening a new one with the same character would race the run;
  with `leave` the run has usually started already, and trigger 4 covers two tabs or a lost `leave`.
- **Durability:** the checkpoint commits with the memories (M6), so a crash loses no work and repeats none.

**Rejected:**
- **after every reply, with or without a Jev gate** (my first recommendation): about 4× the cost for memories nobody
  can use until the next session, and regenerate must undo them;
- **only the 10-minute idle release:** a new chat soon after the last one wouldn't know it, and a killed process would
  lose the sitting;
- **a separate shorter quiet timer:** a second timer next to the idle release, for little gain once `leave` triggers.

### M2. The pause run: what it reads, the checkpoint and pieces

**Decision:**
- **Two new session columns** (backend only, an Alembic migration): `memory_seq` (the event `seq` up to which memory
  has been taken; 0 for a new session, and for existing sessions at migration time their last `seq`, so old history
  is not mined in one burst) and `memory_tries`.
- **The stretch** is every message with `seq` in (`memory_seq`, the last settled message], where "settled" excludes a
  turn still streaming:
  - user and character messages, **active variant only**;
  - **not** system notes, narration or host notes, and **not** interrupted, failed or blocked replies (as today's
    post-turn rule);
  - debate: the motion, each debater's side, the phase of each argument and the verdict (when there is one) go in a
    header; watch: the premise.
- **Context lines:** the 6 messages before the stretch are included, marked "already processed, context only", so
  "he" and "that" resolve.
- **Pieces:** a stretch over **8,000 tokens** (`count_tokens`, `memory.pieceTokens`) is split at message boundaries
  and run piece by piece in order, each piece committing its own checkpoint. A resumed chat that has grown for weeks
  gets several ordinary runs, never one huge call.
- **Who is present:** the session's participants who are not deleted (muted and asleep characters still hear the
  room). Each session is one room, so everyone present heard every line.

**Rejected:**
- **extracting from the rolling summary instead of the lines:** cheaper, but the summary drops exactly the small
  details memory exists for (a cake flavour, a nickname);
- **mining old sessions at migration:** a surprise bill on upgrade for history the user already lived through.

### M3. Extraction: one DeepSeek JSON call for everyone present (the user's decision)

**Decision:**
- **One call per piece**, purpose `memory`, `runtime.llm.calls.memory` (doc 03 C1: thinking off, 0.7, JSON mode),
  **`max_tokens` 1,500**, validated, one retry (doc 03 C7). The instructions are a fixed system message, so repeated
  runs hit DeepSeek's cache for them.
- **The input:** the world's name, the You-card name, the mode, the characters present as numbers with name and role,
  the debate or watch header, the context lines and the numbered new messages as `Name: text`, all marked as quoted
  content, never instructions (doc 01 A3 rule 8).
- **The output:**

  ```json
  {"memories": [
    {"for": 1, "kind": "about_user", "about": "user", "text": "Kai quit coffee last month.", "source": 12, "weight": 4},
    {"for": 2, "kind": "event", "about": 1, "text": "Amara told Kai his headaches should ease within a week.", "source": 13, "weight": 3}
  ]}
  ```

  `for` is the character who remembers; `about` is `"user"`, a character number or `null`; `source` is a new
  message's number; `weight` (1–5) is a hint used only when Jev fails (M4). Code maps numbers to IDs, so the model
  never copies an ID.
- **The rules in the prompt:**
  - write each memory **from that character's point of view**, about what happened in the room; never what another
    character privately thought;
  - one self-contained sentence, **≤ 30 words**, with names instead of pronouns, in **the language most of the new
    messages use** (doc 05's rule for the summary);
  - keep what lasts: facts about people (work, family, plans, health, likes), notable events, **promises the
    character made**, relationships that changed, in a debate the side argued, the strongest opposing point and the
    outcome;
  - skip greetings, small talk, anything true only in the moment, hypotheticals and role-play asides;
  - **never** store passwords, keys, card, bank or ID numbers, or an exact home address (task 11 may extend the list);
  - at most **5 memories per character per piece**, one per fact.
- **Kinds** (the existing four): `about_user` (a fact about the user), `preference` (anyone's likes and dislikes),
  `event` (something that happened), `fact` (anything else lasting, including a position argued).
- **Code checks:** `for` is present; `kind` is one of four; `about` is valid; `source` is a new message; text is not
  empty and is cut at 40 words; extras past 5 per character drop by lowest `weight`; exact duplicates (case-folded)
  within the run are merged. The draft carries `source_session_id`, `source_message_id`, `source_variant_id`,
  `source_mode` and `about_character_id`, as the storage expects.

**Why:** one call over the room is cheaper than one per character and keeps everyone's memories consistent with each
other; D-71 asks for every mode and every point of view.

**Rejected:**
- **only the speaker remembers:** listeners would forget what they plainly heard;
- **only facts about the user, copied to everyone:** characters would never remember each other or events;
- **one call per character:** N times the input for the same transcript.

### M4. Importance: a Jev score

**Decision:**
- **One Jev request per character per piece** (`Decider` purpose `importance`), one **score** question per candidate
  (≤ 5). State (≤ 1,500 tokens): the character's name, role and first personality sentence, the user's name, and the
  candidates. Question: "How much will it matter for {name} to remember this in future conversations?"
- **Five levels:** "not at all, small talk" · "a little" · "somewhat" · "a lot" · "it is central to who they are or what
  they share". The importance is **(w − 1) / 4** from the weighted position w, so the badge runs 0–1 as the contract
  expects; a candidate under **0.25** (`memory.minImportance`) is dropped.
- **Jev failed:** importance = (weight − 1) / 4 from the extraction hint; no hint, 0.5. Marked in the run's log.

**Why:** importance is a bounded judgement on an ordered scale, which is what a Jev score is for (maximise Jev); the
BA's recommendation was importance-gated memory.

**Rejected:**
- **DeepSeek's own number:** an LLM's self-rated importance clusters in the middle; it stays only as the fallback;
- **no importance:** the core block (M8) and the badge (PRF-07) need it.

### M5. Keeping memory tidy: Jev compares each new memory with its nearest ones (the user's decision)

**Decision:**
- **Neighbours:** for each kept candidate, the character's **3 nearest current memories**: vector KNN over the
  candidate's embedding (`embed_doc`, computed once and reused by the write) with cosine ≥ **0.5**
  (`memory.neighbourMin`), merged with FTS matches by RRF. No neighbours → **insert** with no Jev call.
- **One Jev request per candidate** (`Decider` purpose **`memory_compare`**, a new decision purpose), one **choice**
  per neighbour: "Old memory: … New memory: … How does the new one relate to the old one?" with three options:
  **says the same thing** · **replaces it, the old one is no longer true** · **both stay true**.
- **Code decides:**
  - any confident "same" → **`Reinforce`** that memory to the higher of the two importances; the new text is dropped;
  - else any confident "replaces" → **`Supersede`** those memories with the new one (the tab shows only the new one,
    and Forget on it removes the chain, as today);
  - else → **`Insert`**;
  - **unsure (below the floor) → keep both** (insert). A wrong "replaces" hides a true memory; a duplicate is visible
    and the user can forget it.
- **Jev failed:** cosine ≥ 0.95 or equal case-folded text → reinforce; otherwise insert.
- **No background job:** `memory_consolidate` stays unused, and **nothing is deleted automatically**. Old, unused
  memories only sink in ranking (M8).
- **Example:** Amara's seed memory "Kai cut back on coffee recently" + new "Kai quit coffee last month" → "replaces" →
  supersede.

**Rejected:**
- **DeepSeek picks the changes in the extraction call** (Mem0's ADD / UPDATE / DELETE / NOOP): one call fewer, but
  the decision moves from Jev to the LLM, and the extraction prompt grows with every character's neighbours;
- **insert only, plus a merge job:** duplicates sit in the Memory tab until the job runs, and the job is a second
  writer to reason about;
- **automatic forgetting by age:** D-71 leaves forgetting to the user.

### M6. Writing: one transaction with the checkpoint; failures and retries

**Decision:**
- **`MemoryStore.apply_run(world_id, ops_by_character, session_id, upto_seq)`**: every character's ops **and**
  `sessions.memory_seq = upto_seq` in **one transaction**, taking the per-character locks in sorted order (no
  deadlock with `apply`). Embeddings are computed before the lock, as today, for every non-retired space.
- **A memory forgotten while the run was thinking** (its `Reinforce` or `Supersede` target is gone): a `Reinforce` of
  it **drops the candidate** (the user just forgot that fact; writing it back would undo Forget); a `Supersede` of it
  becomes an `Insert` (the new memory is new information). Re-validated once; any other validation failure fails the
  piece.
- **A character deleted, or the session or world deleted, during the run:** that character's ops are dropped, or the
  run is dropped; delete and both resets cancel running `memory_run` tasks, as they stop indexing today.
- **Failures:** if the extraction fails after its retry, or the gateway refuses it, nothing is written, the checkpoint
  stays and `memory_tries` grows; the next trigger retries. **After 3 failed tries on the same checkpoint**
  (`memory.maxTries`) the piece is skipped (checkpoint advanced, a warning logged), so a poison stretch can't bill
  forever. **A daily-cap refusal doesn't count as a try**, and a run never triggers the session's cap pause.
- **Never twice:** a stretch is read once, because the checkpoint commits with its memories. So a forgotten memory
  comes back only if the user says it again later.
- **`Touch`:** the run also touches the memories that the **search** (not the core block) recalled in the stretch,
  read from `trace_memory_refs`, updating `last_recalled_at` and `recall_count`. Core memories are not touched, so the
  core block can't keep itself on top.
- After the commit: `entity.changed { kind: "memory", id: characterId }` per character, as today, so an open Memory
  tab refreshes. Leaving a chat for the profile page shows the new memories a few seconds later.

**Rejected:**
- **one transaction per character, then the checkpoint:** a crash between them repeats part of a run;
- **an internal job row per run** (which I mentioned in chat): the checkpoint already gives durability and retries,
  and `memory_tries` is the only bookkeeping needed.

### M7. Regenerate, blocked replies and Forget

**Decision:**
- **Regenerate after a run** (only the last character message can be regenerated): the memories whose
  `source_message_id` is that message are **removed through the Forget path for those memories only** (vectors zeroed,
  refs scrubbed), the memories they superseded become current again, and `memory_seq` moves back to just before that
  message, so the next pause reads the new variant. Memories sourced from the user's own line before it stay.
- **A blocked reply** is scrubbed at `turn.end`, before any pause, and the stretch skips blocked messages; today's
  `_forget_derived` stays as a guard.
- **The user's Forget** is unchanged (D-70, D-94), plus M6's rules for a run in flight.

**Rejected:** forgetting the whole chain on regenerate (as a block does): it would destroy older memories from other
sessions that were only superseded.

### M8. Recall: a core block on every reply, plus a search when Jev asks (the user's decision)

**Decision:**
- **The core block:** the speaker's top **5** current memories (`memory.coreK`) by **importance × recency**,
  `about_user` and `preference` first on ties. It is read by the runtime at turn start (one indexed query, D-92: the
  engine never queries storage) and goes in **the dynamic tail** on every turn, quick or deep, in every mode:

  ```text
  # What you remember (bring one up only when it fits the moment; never list them)
  - Kai quit coffee last month.
  - Kai's favourite cake is yuzu.
  ```

  Each line ≤ 30 words; the block, with any searched memories, **≤ 320 tokens**. With no memories, no block.
- **The search**, when Jev call 1's "needs memories?" says yes (doc 01 A4):
  - the gate is asked **only when the character has more than 5 current memories**, since otherwise the core block
    already holds them all;
  - keyword (FTS) top 10 ∪ vector KNN top 10 over the speaker's current memories, **excluding the core ones**, with
    the turn's shared query embedding (D-97); RRF (k = 60) normalised to r ∈ [0, 1];
  - **rank = r × (0.5 + 0.5 × importance) × recency × mode weight**; the top 6 go to Jev call 2 as **memory
    candidates**, each with the noul "Would {name} naturally draw on this memory in replying to this?", in parallel
    with any passage scores; keep up to **3** (`retrieval.memoryK`) at p ≥ `t_memory`;
  - Jev call 2 failed or late: keep the top 2 by rank, marked as a fallback.
- **Recency** = max(0.5, 0.5^(days / 30)) from the later of `created_at` and `last_recalled_at`
  (`memory.halfLifeDays` 30, `memory.recencyFloor` 0.5): old facts sink but never vanish. **Mode weight** (D-71's
  down-weighting): 1:1 and group 1.0, debate 0.85, watch 0.7 (`memory.modeWeight`).
- **The trace:** core and searched memories both go in `TurnTrace.memory.recalled` (searched ones with their score,
  core ones without), so Insight shows them and Forget finds them through `trace_memory_refs`, as today. `context.used
  .memory` counts the whole block (doc 05 X7).
- **Memory never cites** (doc 01 A6). Jev call 1 failed → no search, but the core block still shows.

**Why:** with search alone, "hi again!" or small talk would never draw on memory, and that is exactly when a
character feels like it remembers. The tail is uncached, but 320 tokens cost about $0.00005 a reply (M12).

**Rejected:**
- **search only** (doc 01 as written): a returning user is greeted by a stranger unless they mention the topic;
- **search on every reply, no gate:** irrelevant memories in most prompts, and more over-mentioning;
- **the core block in the cached system message 1:** it would save about $0.00005 a reply, but it changes after every
  pause run, every Forget and every early flush, and NFR-35 puts memory in the dynamic tail.

### M9. The greeting: "last time…"

**Decision:**
- A later 1:1 chat's generated greeting (doc 04 P9) gets the core block **plus up to 2 of the newest memories from the
  last session with the user**, and its cue gains one sentence: "If something from last time fits, you may mention it
  in a short phrase."
- **If a pause run for this character is still running** (trigger 4, or a `leave` seconds ago), the greeting waits for
  it **at most 4 s** (`memory.greetWaitMs`, set by check 2), then goes ahead with what is stored.
- The first chat still uses the stored greeting word for word (P9); it has no memories to mention.

**Rejected:** a "last session summary" block: a second, larger thing to keep in sync, when the newest memories carry
the same thread.

### M10. Profiles

| | `scripted` (the mock's twin) | `naive` (the yardstick) | `agent` |
|---|---|---|---|
| Triggers, checkpoint, `apply_run`, M7's rules | shared runtime | shared runtime | shared runtime |
| Writer | returns nothing; no call, no cost (the mock never writes memories) | **the same extraction call (M3)**, insert only, importance from the hint, exact-duplicate skip | the memory graph (M3–M5) |
| Recall | the 3 newest (unchanged) | FTS top 3 on the query (unchanged) | core block + gated search (M8) |

- **The port changes:** `MemoryWriter.after_turn(ctx, perspective_character_id, message_id) → list[MemoryOp]`
  becomes `on_stretch(stretch) → dict[character_id, list[MemoryOp]]` (internal, [05-ai-seams §2.2](../backend/05-ai-seams.md)).
- **The `agent` writer is a LangGraph graph** (doc 01 A7): extract → per character, importance ∥ neighbour search →
  compare → ops. **No checkpointer:** the session checkpoint lives in SQL, so `graph.db` stays unused (this closes A9's
  open point).
- `naive` shares M3's call so the evaluation measures exactly what Jev's importance and compare steps add.

### M11. Evaluation additions

**Decision** (fits doc 02's layers; every new Jev question is validated as B4 describes before it is trusted):
- **Layer 1:**
  - **memory importance:** 100 candidates labelled 1–5 (≥ 30 that should be dropped); targets: keep-or-drop balanced
    accuracy ≥ 85 %, within one level ≥ 80 %;
  - **memory compare:** 120 pairs (40 same, 40 replaces, 40 both true); targets: "replaces" precision **≥ 90 %** (a
    wrong one hides a true memory), "same" precision ≥ 85 %; the floor comes from B5's grid;
  - **memory relevance** (M8's noul): 80 items, 40 relevant; `t_memory` = the lowest threshold with precision ≥ 85 %;
  - the existing **needs memories?** set (B2, ~120 items) is relabelled to mean "needs a memory **beyond the core
    block**".
- **New `memory` suite:**
  - **extraction:** 24 stretches (1:1 × 8, group × 8, watch × 4, debate × 4), split 12 dev / 12 test, each with
    labelled expected memories per character, plus 6 planted secrets and 6 small-talk-only stretches. Targets:
    expected memories covered ≥ 80 % (Jev noul per expected memory); every written memory supported by the transcript
    ≥ 95 % (noul); memories for an absent character **0** (code); planted secrets stored **0** (code + noul);
    small-talk stretches ≤ 1 memory each;
  - **two sessions:** 10 pairs on both profiles. Session 1 plants 3 facts and pauses; session 2 has 2 probes that need
    them and 2 unrelated turns. Targets for `agent`: the probe reply uses the fact correctly ≥ 80 % (doc 05's recall
    noul); **over-mentioning** ≤ 10 % of unrelated turns (a noul: "the reply drags up a memory that doesn't fit");
    duplicates left in the tab ≤ `naive`'s.
- **B4 judge rows:** "Memory extraction" (covered · supported) and "Over-mention".
- **Cost:** the `memory` suite ≈ **$0.10** (extraction shared by both profiles and cached; two-session replies; Jev
  checks); `decisions` grows by ~300 requests to ≈ $0.11. `all` becomes **≈ $0.91 off-peak, ≈ $1.35 at peak,
  ≈ $0.62 once `naive` is cached.**

### M12. Speed and cost in one place

- **Nothing on the reply path waits for memory writing.** Recall adds one indexed read for the core block (< 5 ms);
  the search rides the deep path (shared query embedding, Jev call 2 in parallel with passages).
- **A pause run** takes about 5–10 s (extraction 3–8 s, Jev ~1 s, embedding ~0.5 s); check 2 measures it.
- **Cost of writing, per sitting** (off-peak; peak doubles the DeepSeek part):

  | Sitting | Extraction | Jev (importance + compare) | Total |
  |---|---|---|---|
  | 1:1, 20 exchanges (~3,500 tokens in, ~400 out) | ≈ $0.0008 | ≈ $0.0002 | **≈ $0.001** (≈ $0.0018 at peak) |
  | Group of 4, 30 messages | ≈ $0.0015 | ≈ $0.0005 | ≈ $0.002 |
  | Debate, standard format | ≈ $0.0012 | ≈ $0.0003 | ≈ $0.0015 |

  Writing after each exchange would have cost about $0.004 for the same 1:1 sitting.
- **Cost of recall, per reply:** the block ≈ 320 uncached tokens ≈ **$0.00005**; on a deep turn, ≤ 6 memory nouls in
  Jev call 2 ≈ $0.00005.
- **Ledger and caps:** the extraction is `memory`, the Jev calls `decision`, the embeddings `embedding`; none drains
  energy (ENG-02 AC2); all count against the daily cap.

## 5. Checks before this is locked

Collected for the paid-check step after all 13 tasks (the user's rule), not run now:

| # | Check | Pass | If it fails |
|---|---|---|---|
| 1 | **5 real extraction calls** (1:1, group, watch, debate, one 8,000-token piece; ≈ $0.01): valid JSON, output size, the perspective and language rules | all valid; output well under `max_tokens` | tighten the prompt; raise `max_tokens` or lower the per-character cap |
| 2 | **10 pause runs end to end**: time from the trigger to the commit | p90 recorded | `memory.greetWaitMs` = min(the p90, 4 s); slower runs simply land after the greeting |
| 3 | Doc 01 check 4 (extended): Jev `importance` and `memory_compare` on 20 items each; billing per request or per question; the score's weighted position runs 1–5 | recorded | the cost table and M4's mapping follow the real scale |

## 6. Changes this design needs (each approved at its OpenSpec change)

None changes the HTTP contract or a requirement.

| Change | Kind | Why | Decision |
|---|---|---|---|
| Pause triggers (`leave`, `end`, debate end, watch `turn_cap`, idle release, session open with a shared character, start-up sweep); runtime-level `memory_run` tasks via `rt.spawn`, ≤ 2 at once, one per session; cancelled by deletes and resets; the per-reply `_remember` removed | backend | finding 5 | M1 |
| `sessions.memory_seq` and `memory_tries` (Alembic migration; existing sessions start at their last `seq`); the stretch builder with context lines and 8,000-token pieces | backend | | M2 |
| `MemoryWriter.on_stretch`; `naive`'s single extraction call; the `agent` memory graph (LangGraph, no checkpointer); the extraction prompt and schema; `runtime.llm.calls.memory` `max_tokens` 1,500 | backend + config | finding 2 | M3, M10 |
| Jev purposes `importance` (exists) and **`memory_compare`** (added to `PURPOSE_CATEGORY` as a decision); their questions and floors in the question bank | backend | | M4, M5 |
| `MemoryStore.apply_run` (all characters + checkpoint in one transaction, sorted locks, the Forget-race rules, `Touch` of searched memories) | backend | | M6 |
| Regenerate undo (remove the message's memories, restore what they superseded, move the checkpoint back) | backend | finding 4 | M7 |
| `ScopedIndex.memory_knn`; the core-block read and the ranking; memory candidates in Jev call 2; "needs memories?" only past `coreK`; the memory lines in the `agent` tail; the greeting's extra memories, cue and wait; `memory.*` knobs in `runtime.json` (`coreK` 5, `halfLifeDays` 30, `recencyFloor` 0.5, `modeWeight`, `minImportance` 0.25, `neighbourMin` 0.5, `pieceTokens` 8,000, `maxTries` 3, `maxConcurrent` 2, `greetWaitMs` 4,000) | backend + config | finding 3 | M8, M9 |
| The Memory tab's "Preview: final design by AI team" ribbon removed (PRF-07; the shape is final) | frontend | | M10 |
| Eval: the importance, compare and relevance sets; the relabelled needs-memories set; the `memory` suite; two B4 judge rows | evals | measure it | M11 |
| **Docs to amend:** OQ-AI-01 resolved; [05-ai-seams](../backend/05-ai-seams.md) §2.2 (`MemoryWriter`, `MemoryRetriever`) and §4 (the post-turn queue); [02-storage](../backend/02-storage.md) §3.7 (writes at pauses) and the contract's `MemoryItem` "PROVISIONAL" note; doc 01 A4, A7, A9, §9; doc 02 B2, B4, B7, §8; doc 03 C1 and §7; doc 04 §7; doc 05 X1 and §7 | docs | consistency | all |

## 7. Left for later tasks

- The final embedding model and dimensions (task 10); memory vectors follow the active space like knowledge.
- Prompt injection inside quoted transcripts, sensitive categories beyond M3's never-store list, and a user trying
  to plant memories in a character (task 11).
- How the pause runs and their Jev decisions show in Insight's System 1 section (task 13).
- Not in v1 (D-71): editing, pinning or adding memories; reflections that merge memories into higher-level ones; facts
  shared by every character in a world. Added to [docs/v2](../v2/README.md) at task 13 if the user wants them.

## Sources

- Horizon requirements: D-70, D-71, D-94 ([09-decision-log](../requirements/09-decision-log.md)); PRF-07, INS-01, ENG-02
  AC2, CHAT-06 AC1 ([02-functional-requirements](../requirements/02-functional-requirements.md));
  NFR-23, NFR-35 ([07-nfr-risk-cost](../requirements/07-nfr-risk-cost.md)); OQ-AI-01
  ([08-open-questions-handoff](../requirements/08-open-questions-handoff.md)); `MemoryItem`
  ([05-data-contract](../requirements/05-data-contract.md)).
- Code: [turn.py](../../backend/horizon/sessions/turn.py) (`_remember`, `_forget_derived`),
  [lifecycle.py](../../backend/horizon/sessions/lifecycle.py) (`leave`, `end`),
  [actor.py](../../backend/horizon/sessions/actor.py) (idle release), [store.py](../../backend/horizon/services/memory/store.py),
  [forget.py](../../backend/horizon/services/memory/forget.py), [retrieval.py](../../backend/horizon/ai/retrieval.py),
  [index.py](../../backend/horizon/services/knowledge/index.py), [scripted/ports.py](../../backend/horizon/ai/scripted/ports.py),
  [context.py](../../backend/horizon/gateway/context.py), [tabs.tsx](../../frontend/src/features/profile/tabs.tsx),
  [sessionRuntime.ts](../../frontend/src/client/sessionRuntime.ts), [runtime.json](../../seed/runtime.json).
- Course notes: 7.1 Agents §7.1.8 (four kinds of memory; long-term facts in a store filtered by user; compress on a
  hard-coded rule; edit entries, don't rewrite).
- Chhikara et al., [Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory](https://arxiv.org/abs/2504.19413)
  (extract, then compare with similar memories: add, update, delete or nothing).
- Park et al., [Generative Agents](https://arxiv.org/abs/2304.03442) (recall by relevance × importance × recency).
- Packer et al., [MemGPT](https://arxiv.org/abs/2310.08560) (a small core memory always in context, plus searched
  archival memory).
- [LangGraph: memory concepts](https://langchain-ai.github.io/langgraph/concepts/memory/) (writing memories in the
  background rather than on the hot path).
- [TypeSafe: confidence-gated routing](https://docs.typesafe.ai/patterns/confidence-routing.md).

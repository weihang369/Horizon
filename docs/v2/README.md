# v2 backlog

> Ideas deliberately **left out of v1**, kept here so they are not lost. Nothing here is scheduled or approved. Each
> entry says why it was deferred and what it would need, so a v2 design can start from it. Add an entry whenever a
> feature is moved out of v1.

## 1. Custom models (user-chosen chat, decision, image, music and embedding models)

**Deferred by:** [docs/ai/03-llm-parameters.md](../ai/03-llm-parameters.md) C9 (2026-10-09).

**v1 behaviour:** Horizon is tuned for its pinned models (DeepSeek V4.1 Flash, Jev 1.13, Qwen3 Embedding 8B, Seedream
5.0 Flash, Lyria 3 Clip). Settings → Models is a read-only "Models in use" panel with each model's price and a Test
button. The contract field `AppSettings.modelOverrides` exists but nothing reads it.

**Why it was deferred:** every AI setting is tuned for the pinned models, so a different model would silently lose
that tuning. The tuned settings include:
- temperatures and length targets (03);
- Jev confidence floors and thresholds (02 B5);
- the cache-friendly prompt layout (NFR-35);
- the DeepSeek provider pin (D-41).

Before v1.0, a model override changed only what the Test button probed.

**What v2 would need:**
1. **Per-model settings rows.**
   - The tuned row stays for the pinned model.
   - Any other model gets safe defaults: no temperature (so Anthropic's 0–1 range can't be exceeded), thinking off,
     `max_tokens` only.
   - Read each model's `supported_parameters` from OpenRouter's model list, because `require_parameters: true` rejects
     unsupported ones.
2. **Real prices.** Read the model's pricing from OpenRouter when the override is saved, so the energy estimate,
   reservations and the daily cap are right. A frontier model can cost 30–100× more per reply.
3. **Routing.** Pin the provider only for DeepSeek models; other models use OpenRouter's normal routing.
4. **JSON.** Use strict `structured_outputs` where the model supports it, otherwise JSON mode with validation (03 C7).
5. **Caching.** Some providers (for example Anthropic) cache only with explicit `cache_control` breakpoints. Without
   them, every turn pays full input price.
6. **Decision and embedding models.**
   - A different decision model is not Jev, so the `Decider` questions (choice, noul, score) need an LLM fallback
     implementation.
   - A different embedding model needs a new embedding space and a re-embed (D-64, D-95), never an in-place switch.
7. **Evaluation.** Run `horizon eval` (02 B7) on the new model and show the user its quality and cost next to the
   default before they switch.
8. **UI.** Make the Models tab editable again (SET-05). Show the "Unverified model" warning, the per-reply cost
   estimate, and a Reset to defaults button.

## 2. "Forget everywhere" for a memory about the user

**Deferred by:** [docs/ai/09-memory.md](../ai/09-memory.md) (task 9, the user's choice, 2026-10-10).

**v1 behaviour:** every character present forms memories from their own point of view (D-71), so a fact about the
user ("Kai quit coffee") can live in several characters' lists. The Memory tab's Forget removes it from **one**
character; the user repeats Forget on each character's tab. D-71 limits v1 to view and forget.

**Why it was deferred:** a cross-character Forget is a new contract command and a new UI action, which go back
through the SWE side, and per-character Forget already keeps the "Forget means gone" promise for each list.

**What v2 would need:**
1. **Finding the copies:** memories written by the same pause run share `source_message_id`; later rewrites keep the
   chain through `superseded_by`. A match by source message, plus a Jev noul "is this the same fact?" for rewritten
   lines in other characters' lists, finds them.
2. **A contract command** (for example `forgetMemoryEverywhere(memoryItemId)`) returning the forgotten IDs, and a
   confirmation that names the characters affected.
3. **One transaction** running today's Forget (vectors zeroed, traces scrubbed, WAL truncated, D-94) for every copy,
   with each live session refreshing its memory list (doc 09 M8).

## 3. Keyword search for Chinese, Japanese and Korean

**Deferred by:** [docs/ai/10-rag.md](../ai/10-rag.md) K11 (task 10, the user's choice "focus on English",
2026-10-10).

**v1 behaviour:**
- `knowledge_fts`, `memory_fts` and `message_fts` use `porter unicode61`. It treats a run of CJK characters as one
  token, so BM25 can't match a Chinese, Japanese or Korean word inside a sentence.
- Such text is found by the dense (vector) half.
- A non-English question is rewritten into an English query (doc 10 K4), so English documents are still matched by
  keyword.

**Why it was deferred:** the demo's documents and most chats are in English, and the vector half plus the rewrite
cover the rest well enough for v1.

**What v2 would need:**
1. **Bigram indexing in our own code** (the Lucene / Elasticsearch CJK method).
   - Every CJK run becomes overlapping 2-character tokens in a derived search column ("咖啡因" → "咖啡 啡因"), and the
     query is split the same way.
   - It needs no new dependency, and 2-character words match.
   - SQLite's trigram tokenizer was rejected, because it can't match 2-character words.
2. **An FTS rebuild** of the three tables, with a new `tokenizer` value so that reindex re-runs from that layer.
3. **Evaluation:** Chinese and Japanese questions over Chinese documents in the retrieval suite, run with and without
   bigrams.

## 4. A mature content rating

**v1 behaviour:** `contentRating` is the literal `"sfw"` (NFR-27). The prompt rules, the input steer and the output
check all use doc 11 S1's SFW definition.

**Why it was deferred:** a second rating needs a contract value, an age gate and a second set of tuned thresholds, and
the v1 launch is a public demo.

**What v2 would need:**
1. A contract value (`"mature"`) and a settings control behind an adult confirmation.
2. A second rules wording for the prompt (doc 11 S2) and the Jev checks (S3, S5), with its own thresholds.
3. A mature half of the `safety` suite (doc 11 S10), so the SFW thresholds don't drift.

## 5. A "no training" switch for chat

**v1 behaviour:** chat routing allows data collection (D-80), so DeepSeek's own endpoint stays eligible. Users are told
by a notice in Settings → Connection and in the Knowledge tab, and in the README (doc 11 S8). The README explains how
to set `deny` in the local config.

**Why it was deferred:** it is a new control, and `deny` routes chat to third-party hosts (≈ 1.2–2× the price, and
without DeepSeek's first-party cache price), against the speed-and-cost headline.

**What v2 would need:**
1. A Settings switch that sets `data_collection: "deny"` for chat, with the price difference shown first (NFR-08).
2. The ledger's `provider` column already shows where each call went; Insight shows it per reply.
3. A latency and cost check on the third-party route before it is offered.

## 6. Style reference images for a cast-wide look

**v1 behaviour:** the art style is locked by the style preset's prompt fragment in every base and sheet prompt;
`StylePreset.referenceImageUrls` stays empty, and the locked base is the only reference for emotion edits (doc 12 I6).

**Why it was deferred:** a reference portrait in a base call can leak its face into a new character (against the
original-character rule and identity), and the real seed portraits don't exist yet (D-52). The D-61 run already scored
the style 5/5 with text alone.

**What v2 would need:**
1. Real seed portraits to reference, or style-only images with no face.
2. A paid test (≈ $0.15): one reference for two new characters, scored by eye (D-88) for face leaks and style match.
3. If it passes, `referenceImageUrls` filled per preset and sent as extra `input_references` in base and sheet calls
   (Seedream takes up to 14, free).

## 7. An LLM-written context line per knowledge piece

**v1 behaviour:** each piece's vector is built from the piece with its document title and heading path as a header
(docs/ai/10 K1, K3).

**Why it was deferred:** the header is free; a written context line per piece costs one LLM call per piece at upload.

**What v2 would need:** a retrieval-suite comparison showing the header falls short (Recall@8), then a per-piece
context line written at ingestion, in a new embedding space.

## 8. An approximate vector index

**v1 behaviour:** exact flat KNN per character partition (D-64), fine within D-65's limits (≤ 3,000 pieces per
character).

**Why it was deferred:** at v1's sizes an exact search is fast enough and has no recall loss (docs/ai/10 K3).

**What v2 would need:** if D-65's limits rise past about 100k pieces per partition, an IVF or HNSW index, with a recall
check against the flat search. The user's wish (2026-10-22): **detect it automatically**: keep flat KNN by default, and when a character's
partition passes a size threshold, build an IVF-flat index for it (sqlite-vec's IVF, or a side index) and search through
it; drop back to flat below the threshold. The threshold is set from a measured latency curve (flat vs IVF, recall@20
against flat as the gold).

## 9. Theme songs that loop seamlessly

**Deferred by:** the user's manual test of v1 (2026-10-21): a character's theme doesn't loop.

**v1 behaviour:**
- The audio engine plays a theme as a looping buffer over the **whole** file (`src.loop = true` in
  `frontend/src/audio/engine/index.ts`, `setMusic`), with no loop points.
- A generated song never gets a loop region: the backend stores `loop: null` when a song job finishes
  (`services/jobs/apply.py`), and the seed's songs have none either. The Theme tab draws a loop zone only when one
  exists.
- Lyria 3 Clip writes a ~30 s piece with its own intro and ending. Our prompt asks for "a 30-second piece that loops
  cleanly", but the model doesn't guarantee it, so the repeat is heard as the song stopping and starting again.

**v1's stopgap (the user's choice, same review):** each pass fades instead of cutting. Before a generated theme loops,
the engine trims its near-silent edges, fades the first 1.5 s in and the last 3 s out (`frontend/src/audio/engine/edges.ts`),
so every repeat goes quiet and comes back up. Procedural system tracks are built to loop and are left as they are.

**Why it was deferred:** the theme plays and repeats with soft edges; making the seam inaudible is audio work (finding
loop points, crossfading), not needed for the v1 launch.

**What v2 would need:**
1. **Loop points per song.** When a song job finishes, find a loop region: trim leading and trailing silence, then
   pick a start and end on a beat (the brief's BPM gives the bar length) where the waveform and loudness match.
   Store it in the existing `loop` field.
2. **The engine uses them.** Set `loopStart` / `loopEnd` on the buffer source from `song.loop`, or crossfade the end
   into the start (a short equal-power overlap) when no clean point is found.
3. **A check by ear** (D-88: the user judges generated media by eye and ear) on the 7 seed themes before shipping.

## 10. Rewriting a changed fact below the prompt's list

**Deferred by:** the user's review of the memory pipeline (2026-10-22, U-78): "no need perfect, put it in v2".

**v1 behaviour:**
- The rewrite call (doc 09 M3) shows DeepSeek each character's top memories only, the same ~30 lines (1,000 tokens)
  as the prompt list (M8). A `rewrite` or `confirm` can only target a line it was shown.
- The duplicate check (M5) reaches every current memory: an add whose nearest memory is at or above `dupCosine`
  (0.85) goes to Jev `same_fact`, and the same fact reinforces that memory. So a **repeated** fact below the list is
  caught and climbs back.
- A **changed** fact below the list is not. If memory #45 says "Kai lives in KL" and Kai now says "I moved to
  Penang", DeepSeek adds the new line, `same_fact` rightly says it is not the same fact, and the new line is written
  beside the old one. The guard never sees it (it checks rewrites only), so the stale line stays current. The new line
  ranks into the list and the old one sinks, but the overflow recall (M9) can still bring the old one back, and the
  Memory tab shows both until the user forgets one.

**Why it was deferred:** it needs a character with more memories than the list holds (roughly 10–20 sittings) and a
changed fact that sits below rank ~30; the result is visible and the user can forget the stale line. The M13
evaluation measured "rewritten, not duplicated" (92 %) only for facts inside the shown list.

**What v2 would need:**
1. **Measure it first:** overflow items in the `memory` suite's rewrite part (a changed fact planted below the
   list), so the rate is known before a fix is chosen.
2. **Show DeepSeek the near overflow lines** (preferred): before the call, search the character's memories outside
   the list against the stretch (the hybrid search M9 already has) and add the few closest as extra numbered lines,
   so the model can `rewrite` or `confirm` them like any other. Costs one search per character per run and a few
   hundred input tokens.
3. **Or turn a near "not the same" into a guarded rewrite:** when `same_fact` says no above `dupCosine`, ask whether
   the add replaces the old line, and if so run the guard and Supersede. Riskier: an extension ("likes tea" → "likes
   green tea") would go through it too.

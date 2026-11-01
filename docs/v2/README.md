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

**Deferred by:** [docs/ai/09-memory.md](../ai/09-memory.md) (task 9, the maintainer's choice, 2026-10-10).

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

**Deferred by:** [docs/ai/10-rag.md](../ai/10-rag.md) K11 (task 10, the maintainer's choice "focus on English",
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

**v1's stopgap (the maintainer's choice, same review):** each pass fades instead of cutting. Before a generated theme loops,
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

## 11. Small items from the v1.1 code audit (27 Oct 2026)

**Deferred by:** the v1.1 code audit (six clusters, each finding checked against the code). Each item below works
correctly in v1 or is invisible to users; none fixes wrong behaviour a user sees. They are kept as one list, by area.

### 11.1 Platform and money

#### Warn and pause on an upward cost correction (A-07 part 2)
- Why deferred: estimates for stopped streams use `max_tokens`, so corrections almost always go down; the next preflight already reads the corrected sum.
- v1 behaviour: a correction updates the row, energy and (now) the Spend view; no `budget.warning`, no session pause from the correction itself.
- What v2 needs: after an upward correction, run `budget.crossed` on before/after and the gateway's `on_spend`/`on_budget` hooks.

#### Re-embed only after the key check (A-11 part 1)
- Why deferred: needs a rejected key and keyword-only user sources at once; the pipeline falls back to keyword-only.
- v1 behaviour: `PUT /settings/key` stores the key (status `set`), which starts the re-embed of keyword-only user sources before `GET /key` answers 401.
- What v2 needs: start the re-embed after the check in the route, or on the first successful paid call.

#### Test-mode spend bias in post-call checks (A-14)
- Why deferred: test mode only; preflight refuses every call when the bias reaches the cap.
- v1 behaviour: `LedgerWriter.record`'s `spent_before/after` omit `clock.spend_bias_usd`.
- What v2 needs: add the bias in `record`, as `spent_today()` does.

#### Config: relative data/seed/static dirs and the port (A-16)
- Why deferred: npm scripts run from the repo root; only manual runs from backend/ differ.
- v1 behaviour: relative `HORIZON_DATA_DIR` / `SEED_DIR` / `STATIC_DIR` resolve against the cwd; a non-number `HORIZON_PORT` stops start-up with a traceback.
- What v2 needs: resolve relative paths against `root`; validate the port with a message naming the setting.

#### Capture on the frozen clock (A-17)
- Why deferred: test mode with capture on only.
- v1 behaviour: `Capture.run` sleeps 2 s of clock time, so a 24 h virtual advance fires 43,200 flush timers; `FrozenClock.set` backwards leaves timers at their old deadlines.
- What v2 needs: an injected real-time sleeper for capture (like the corrector and purge worker), or coalesced recurring timers.

#### Mock/HTTP energy parity (A-18)
- Why deferred: demo-mode-only drift in `fullAt`; the fixtures pin MYT.
- v1 behaviour: `energy.ts` has no `utcOffsetMin`; frozen `withMax` computes `fullAt` from now while the backend's `read_energy` uses `asOf`; `characters.energy_day` is written, never read.
- What v2 needs: the offset in `EnergyOpts`, frozen `fullAt` from `asOf` in both `withMax`s, and either read or drop `energy_day`.

#### Cost tab money fields (A-19), Spend titles (A-20), mode radiogroup keys (A-26)
- Why deferred: polish; no wrong state is stored.
- v1 behaviour: out-of-range caps get the backend's 422 toast but the field keeps the typed text; Enter + a quick blur can send the same PATCH twice; Spend fetches whole session snapshots for titles; the mode cards have no arrow keys.
- What v2 needs: bound the field to the schema (0.01–1000 / 100) and resync after a failed save; commit on blur only; read titles from the session lists; roving tabIndex + arrows.

#### Explicit LangSmith client (A-13 part 2)
- Why deferred: the key stays in this process's environment; nothing leaves the machine except to LangSmith, as opted in.
- v1 behaviour: `switch_on` puts `LANGSMITH_API_KEY` in `os.environ`; `trace()` uses langsmith's default client.
- What v2 needs: `langsmith.Client(api_key=…)` passed to `trace(client=…)`, per opt-in-tracing spec.

#### MP3 sniffing (A-25)
- Why deferred: hardening; no provider has sent such a clip.
- v1 behaviour: `is_mp3` accepts a single frame and needs the frame right after the ID3 tag.
- What v2 needs: resync like `mp3_duration` and require two frames.

### 11.2 Turn engine and safety

#### Exact separator budget in `head_tail` and `clip`
- Why deferred: off by 2 or 3 tokens on very long lines, with nothing a user sees. Fixing it changes Jev's state bytes.
- v1 behaviour: a clipped history message can be 4,003 tokens (cap 4,000), and a cut `quoted_latest` can be 602 (cap 600).
- What v2 needs: subtract the separator's bytes from the head and tail budgets, as `cut_tokens` and `cut_to` do.

#### A smarter JSON quote repair
- Why deferred: the repair's documented scope is "a stray nickname in quotes". Other cases fall through to the one paid
  retry by design, and nothing invalid is applied.
- v1 behaviour: `He said "hi", then left` inside a string isn't repaired, which costs one small paid retry.
- What v2 needs: after a candidate closing quote followed by `,`, require the next token to start a JSON value or key.
  After `:`, require object-key position.

#### Wait for a cancelled call's cleanup in the naive summariser and verdict
- Why deferred: no visible effect. The gateway's ledger write is shielded, and nothing reads it right after.
- v1 behaviour: `task.cancel()` then raise or return.
- What v2 needs: `await asyncio.wait((task,))` after the cancel on the timeout branch, as `decider.py` does.

#### Compile the persona once per agent turn
- Why deferred: pure and below a millisecond.
- v1 behaviour: `reply_prefix` and `trace_patch` each call `compile_persona(persona_input(ctx))`.
- What v2 needs: return the token counts with the prefix, or cache them on the request.

### 11.3 Memory, knowledge and generation

#### A regenerated read reply alone never clears `memory_reread` on ended or scripted sessions (C-P1-1)
- Why deferred: no paid call and no wrong memory; only a free no-op run request at each open/sweep.
- v1 behaviour: the ID waits for a run with a user line (by design, doc 09 M2); on an ended session or the scripted
  writer it waits forever, and `opened()`/`sweep()` keep requesting a run that notes "below minimum".
- What v2 needs: in `MemoryRuns._one`, advance (clear the re-read list) when the session is ended or the writer is
  scripted even when `upto == from_seq`.

#### Writer de-duplication inside one piece (C-P1-7, C-P2-10)
- Why deferred: needs a repetitive LLM answer; effects are ±0.05 importance or one duplicate line; changing it moves
  the measured memory suite.
- v1 behaviour: a confirm and a duplicate add both reinforce from the old importance; a rewrite and a same-text add
  both write; a Reinforce can land on a row superseded in the same piece; an exact duplicate below `minImportance` is
  dropped instead of reinforcing.
- What v2 needs: per-character in-piece state in `_judge` (skip targets already superseded, sum reinforcements, de-dup
  adds against queued drafts, check exact duplicates before the importance floor), then a memory-suite re-run.

#### vec0 `k` headroom in recall (C-P2-7)
- Why deferred: a recall quality change; thresholds were measured with paid runs.
- v1 behaviour: `Overflow.knn` asks for `limit + exclude` rows, and superseded memories (which keep vectors for undo)
  can fill them; `SessionLines.knn` asks for `limit` with lines past `upto` in the partition.
- What v2 needs: headroom for superseded rows / later lines (or a filtered partition), then re-measure recall.

#### Space build estimate on a resumed build (C-P2-8)
- Why deferred: only over-estimates (safe), and both shipped spaces share one price.
- v1 behaviour: `plan_build` counts everything in the active space even when the target space is half built.
- What v2 needs: exclude rids already in the building space's tables, and price by the space's model.

#### Small wizard and profile polish (C-P2-4, C-P2-5, C-P3-2, C-P3-3)
- Why deferred: no wrong result, only small UX gaps.
- v1 behaviour: Lock/Palette rely on `save()` or the SSE refresh to update the cached character; brief edits live for
  the app session only (by design); PasteText's error stays while typing; example chips replace typed seed text.
- What v2 needs: `putResource` after lock/pick; a stored brief (contract field) if wanted; clear the error on change;
  confirm before a chip replaces custom text.

#### Smaller backend items (C-P2-1, C-P3-1, C-C01)
- Why deferred: test-mode only, API-only, or unreachable from the UI.
- v1 behaviour: fault plans skip `blink_frame` (mock and backend alike); a PATCH can store an unknown `pal_` id
  (rendering falls back); retrying a failed sheet via the API re-runs the sheet but slices nothing.
- What v2 needs: `blink_frame` in both fault plans (with the spec); check `paletteId in rt.palettes`; on a sheet
  retry, re-queue its `skipped` emotions too.

### 11.4 Modes and the session screen

#### Follow plan: start the second reply's deep work the moment the plan lands (D-01)
- Why deferred: no wrong behaviour; at most the overlap with the first reply's output check (≤ 0.8 s) is lost.
- v1 behaviour: the second reply's deep work starts when its turn starts (before its `turn.next`), after the first
  reply's `turn.end`. `FollowRequest.message_id` is not set (nothing reads it).
- What v2 needs: start `deep.attach` from `_wait_follow` when the plan resolves early (as `watch_plan._plan_ahead`
  does), and pass `message_id` for consistency.

#### O12 Ask…/Interject hold without touching the saved auto-advance (D-02 part 3)
- Why deferred: needs a contract command; the stall and the double chain it caused are fixed.
- v1 behaviour: opening O12 turns `config.autoAdvance` off and closing it turns it back on, so the switch flips while
  O12 is open, and a reload with O12 open leaves auto-advance off.
- What v2 needs: a transient hold (`debate/hold` on/off, or the actor's held flag) that never writes the config.

#### Watch transport after Step in and after an early Stop (D-09, D-10)
- Why deferred: UI polish; the buttons work.
- v1 behaviour: "Resume the scene" stays the label on every later pause once the user has stepped in; after Stop and
  Esc on O17 the rail shows the turn counter, and ■ reopens O17.
- What v2 needs: a signal that the scene is waiting after a Step in (a watch-state flag or the seq of the last
  `session.resumed`), and an "ended early" state that keeps Episode end ▸.

#### O12 Send and Verdict actions show the key badge (D-13)
- Why deferred: polish; without a key, the click already opens O05 and keeps the draft.
- v1 behaviour: plain Send / Rematch buttons; the `missing_key` answer opens O05.
- What v2 needs: `keyLocked={demo}` on O12 Send (Ask…, Step in) and on Rematch / Continue as group chat.

#### The VS splash on a slow first mount (D-19)
- Why deferred: cosmetic.
- v1 behaviour: if the debate screen mounts after the opening has begun (> 1.6 s on a cold or slow machine), the
  first ceremony is skipped.
- What v2 needs: a "just created" mark (the route or the slot) so the first mount within the opening's first turn
  still plays the VS, while reopening mid-debate doesn't.

### 11.5 API, client and shell

#### Idempotency middleware buffers keyed bodies
- Why deferred: no user-visible fault; the upload paths are capped, and the app is local.
- v1 behaviour: a POST with `Idempotency-Key` is read whole before the route (≤ 5 MB / 10 MB + 64 KB on the upload paths,
  uncapped elsewhere), so the uploads' "never spooled in full" (`uploads.py` docstring) holds only without a key.
- What v2 needs: hash while streaming (or cap non-upload paths at the JSON limit, 256 KB) so uploads never sit in RAM.

#### Cover upload pre-check in the HttpClient
- Why deferred: the World editor already refuses > 5 MB and wrong types before calling it.
- v1 behaviour: a direct `worlds.uploadCover` over 5 MB can come back as `network` (proxy reset) instead of `validation`.
- What v2 needs: the same pre-check as `addKnowledge` (`HttpClient.ts:104-108`) with the 5 MB limit.

#### Router polish
- Why deferred: no wrong screen; `hashchange` already recovers.
- v1 behaviour: Back pressed during a transition re-navigates with "fade" instead of "slash-back"; a route with an explicit
  default (`tab: "roster"`, `card: 1`) and the same route without it count as different (one extra history entry).
- What v2 needs: `onPop` compares with `pending ?? route`; `formatRoute` drops default values.

#### Session stream subscriber edge cases
- Why deferred: the session runtime is the only subscriber and ignores late events.
- v1 behaviour: a subscriber that leaves before its backlog loads still gets it (`sse.ts:154-159`); overlapping
  `Controller.start()` calls can leave one extra subscription (E-C01); `refreshFields` can briefly apply an older GET.
- What v2 needs: `release` checks `cur.subs.has(sub)`; `start()` carries a generation number and drops stale results.

#### Usage `sinceDays` validation
- Why deferred: no caller passes `sinceDays`.
- v1 behaviour: `sinceDays=0` means "all" (backend and mock agree); `1e9`, `inf`, `nan` give a 500.
- What v2 needs: `Query(ge=0, le=36500, allow_inf_nan=False)`; decide whether 0 means "today" in both clients.

#### Multipart and pasted-text edge cases
- Why deferred: only hand-made requests reach them.
- v1 behaviour: two `file` parts are concatenated; pasted-text JSON over 10 MB is refused with a "file" message.
- What v2 needs: refuse a second `file` part; read pasted-text JSON with the 256 KB JSON cap.

#### MockClient kept in the HTTP bundle
- Why deferred: local bundle size only.
- v1 behaviour: `client/index.ts:15` uses `instanceof MockClient`, so the mock engine and seed fixtures ship in the HTTP
  build, though line 4 says the unused client is dropped.
- What v2 needs: decide `mockDev` from `import.meta.env.VITE_HORIZON_CLIENT`, not `instanceof`.

#### Title screen before settings load
- Why deferred: a narrow window; Onboarding is skippable.
- v1 behaviour: a key press before `GET /settings` answers sends a new browser with a backend key to Onboarding.
- What v2 needs: wait briefly for settings (or decide on World Select) when they haven't loaded.

### 11.6 Mock and evaluation core

#### Decisions suite: resolve every noul threshold key (F-01)
- Why deferred: latent. Every noul question in today's decisions datasets uses a listed key, or `t_same` = 0.5, which equals the fallback.
- v1 behaviour: `Decisions.run` reads the threshold from `("t", "t_end", "t_gate", "t_standalone", "english", "t_keep", "t_recall")` and otherwise uses 0.5.
- What v2 needs: name each noul entry's primary threshold in the bank, or take the only key when there is one. A future dataset for a question with another key (`t_same` ≠ 0.5, `tSteer`, …) would otherwise be scored at 0.5.

#### Decisions estimate counts already-measured questions (F-02 part 2)
- Why deferred: it only over-estimates, so the prompt and the 1.5× cap are higher than needed. It never under-caps.
- v1 behaviour: `Decisions.plan` prices every item; `run` then skips the unchanged questions.
- What v2 needs: `plan` reads `decisions-measured.json` (via the run's data dir) and leaves out the unchanged questions, as `run` does.

#### `horizon eval all`: probe each suite only under the profiles it supports (F-08)
- Why deferred: `all` is a $0 probe. The extra rows (agent-only suites under `naive`, profile-free suites twice, `long`) send and spend nothing.
- v1 behaviour: every suite not in `NEVER_PROBED` is probed under both `agent` and `naive`.
- What v2 needs: a per-suite profile list (e.g. `frozen.py`'s naive sets), and a decision on whether `long` belongs in the probe table.

#### Dead `Options.repeat` (F-09)
- Why deferred: dead code, no behaviour.
- v1 behaviour: nothing sets it, and `store_for` checks it.
- What v2 needs: remove it, or wire a `decisions --repeat` if one is ever specified.

#### A crashed paid eval run leaves no spend line (F-C01)
- Why deferred: dev tooling. The spend is still in the run's own ledger, and the folder is kept.
- v1 behaviour: `Runner.run` writes `report.md`, `run.json` and the `spend.jsonl` line only after `_execute` returns.
- What v2 needs: read the run's spend in `_execute`'s `finally`, and append the `spend.jsonl` line (status `failed`) even when the suite raises.

#### The mock engines' twin of the debate and watch double chain
- Why deferred: the online demo never takes a key, so no live debate or watch runs there; only `npm run dev:mock` with a
  mock key reaches it. The backend is fixed.
- v1 behaviour: in the mock, turning auto-advance off and on (or Pause then Play) inside a debate's pause, or Pause then
  Play inside a watch's pace wait, starts a second chain of turns; Play while Step-in replies stream starts none.
- What v2 needs: mirror the backend's `kick` in `mock/engines/debate.ts`, `mock/engines/watch.ts` and
  `MockClient.setAutoAdvance`: queue one step only when nothing is queued and no pause timer that will step is pending.

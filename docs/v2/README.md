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

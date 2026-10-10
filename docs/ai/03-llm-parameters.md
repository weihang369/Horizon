# 03: LLM parameters

> **Status: agreed with the user, 2026-10-09** (AI stage, task 3 of 13). **Revised after an independent review** (it
> checked the code and the provider docs; 14 findings, all addressed).
> - It resolves OQ-AI-13 (main LLM parameters).
> - Decisions are numbered **C1–C9**, each with the alternatives we rejected.
> - It builds on [01-agent-architecture](01-agent-architecture.md) (A1–A14) and
>   [02-evaluation-observability](02-evaluation-observability.md) (B1–B12). It does not change the architecture; it
>   sets the knobs on every DeepSeek call that architecture makes.
> - The model stays **DeepSeek V4.1 Flash** (`deepseek/deepseek-v4.1-flash`, D-41). Jev, the embedding model and the
>   image and music models are not covered here.

## 1. The question

Doc 01 gives DeepSeek one job: **write the words**. Jev makes every bounded decision. This task decides how each
DeepSeek call is configured:
- does it think;
- how random is it;
- how long does it write, and how is the reply shown;
- how does it return JSON;
- what happens when DeepSeek's own endpoint is down;
- can the user swap the model.

**The user's decisions:**
- **Follow DeepSeek's own temperature guidance; no A/B test.** "DeepSeek set that, of course they already tried many
  times." This saves the ≈ $0.10 temperature check (C3).
- **Cost comes before strict schemas.** JSON mode plus validation is good enough for a new model (C7).
- **A chat reply should read like texting:** separate bubbles, not one block (C5).
- **Only V4.1 Flash.** No older model as a fallback (C8).
- **No custom models in v1.** "I will optimise for the current model set-up." The Models tab becomes read-only, and
  custom models are recorded for v2 in [docs/v2](../v2/README.md) (C9).

## 2. What Horizon already has

From the code:

- **`ChatRequest`** ([chat.py](../../backend/horizon/gateway/chat.py)) already carries `temperature`, `reasoning`,
  `response_format`, `stop`, `logprobs` and `extra`. Only the fields that are set go into the body.

  Small gateway changes are still needed:
  - remove the fallback model (C8);
  - keep `finish_reason` and reasoning tokens (C2, C4);
  - map error finish reasons (C4).

  Today `parse_usage` drops `completion_tokens_details.reasoning_tokens`. The stream raises only on refusals
  (`REFUSALS`); any other finish reason ends the reply as complete.
- **Every request** carries the pinned routing block from `seed/pricing.json`:
  - provider order `["DeepSeek"]`;
  - `require_parameters: true`;
  - `allow_fallbacks: true`;
  - quantizations `bf16, fp16, fp32, unknown`;
  - `data_collection: "allow"` (D-80).

  It also carries `models: [chat model, "deepseek/deepseek-v4-flash"]` as a model fallback.
- **The naive reply** ([naive/turn.py](../../backend/horizon/ai/naive/turn.py)) sends `reasoning: {enabled: false}`,
  no temperature (so the provider default, 1.0), and `max_tokens` from `runtime.replyMaxTokens`:

  | Mode | Today's `max_tokens` |
  |---|---|
  | 1:1 | 350 |
  | group | 250 |
  | watch | 220 |
  | debate short / medium / long | 200 / 320 / 480 |

  The prompt only says "reply in character, briefly, in plain text". The debate cue says "stay under a few sentences".
  The cap is the only real length control, so a reply that hits it stops mid-sentence.

  The cap is computed **before** the turn is planned (`ReplyCaps.for_mode(mode)` in `sessions/turn.py` and
  `sessions/prefetch.py`), and `TurnContext.max_tokens` defaults to 350. The naive engine skips content-less chunks,
  so the final chunk's `finish_reason` is thrown away.
- **The seed files are generated.** `seed/pricing.json` and `seed/runtime.json` are built by
  `frontend/scripts/seed-build` from TypeScript sources, and `seed:check` guards them. The sources are:
  - `frontend/src/mock/pricing.config.ts` (with `fallbackModel`, typed as required in `frontend/src/domain/cost.ts`);
  - `frontend/scripts/seed-build/runtime.config.ts` (`replyMaxTokens`).

  Tests pin today's values:
  - `tests/unit/test_runtime_config.py` (350 / 250 / 220);
  - `tests/sessions/test_naive.py` (`max_tokens == 350`);
  - `tests/unit/test_chat_client.py` (the `models` fallback list);
  - `tests/knowledge/test_naive_prompt.py`.
- **How replies are displayed.**
  - 1:1 and group render a chat bubble.
  - Watch renders a **script row** (`variant="script"`, no bubble).
  - A chat reply longer than `READABLE_CHARS` (600) switches to the **Readable** panel by itself
    ([MessageRow.tsx](../../frontend/src/features/session/MessageRow.tsx),
    [sessionContext.ts](../../frontend/src/features/session/sessionContext.ts)).
  - Seed transcripts and the mock banks are single-block lines.
- **The emotion tag parser** ([tag_parser.py](../../backend/horizon/ai/naive/tag_parser.py)) releases the start of the
  stream as soon as it can't be the start of `<e:`. It does **not** buffer a name prefix.
- **The largest cast is 5 characters** (`sessions/lifecycle.py`: group, watch and debate allow 2–5).
- **The history** renders other speakers as `user` messages prefixed with their name (`Mei: …`, see
  [window.py](../../backend/horizon/ai/naive/window.py)). So the model sometimes continues with the next speaker's line.
- **The naive drafter** ([naive/creation.py](../../backend/horizon/ai/naive/creation.py)) uses JSON mode
  (`response_format: json_object`, the schema in the system prompt), reasoning off, `max_tokens` 2,400.
- **Host lines, the verdict and the rolling summary** are scripted-only today (doc 01 §8). Their DeepSeek calls arrive
  in tasks 5 and 8, and they use the settings in C1.
- **Model overrides.** Settings → Models (SET-05) lets the user type a different model slug, saved as
  `modelOverrides`. **Only the Test button reads them** ([probes.py](../../backend/horizon/services/probes.py)).
  Today, typing another model there changes nothing a user can see.
- **There are two sources for the chat model.**
  - Replies use `prices.chat.model` (`seed/pricing.json`).
  - The drafter and the probe use `settings.models.chat` (`seed/settings.json`).

  They agree today only because both are generated with the same value.
- **The chat probe** sends no `reasoning`, so it runs with thinking on.

## 3. What the provider docs say (checked 2026-10-09)

- **F1. Thinking is on by default on DeepSeek V4.1 Flash, at high effort.** While it is on, `temperature`,
  `presence_penalty` and `frequency_penalty` are **silently ignored** (no error). With thinking off, `top_p` is fixed
  at 1.0. So "reasoning off" must be sent explicitly on every call, or the temperatures below do nothing.
- **F2. DeepSeek's own endpoint has no strict JSON schemas.** It supports JSON mode (`json_object`: valid JSON, any
  shape), not `structured_outputs`. Our routing sets `require_parameters: true`. A strict-schema request would
  therefore skip DeepSeek and land on a third party: no implicit cache, and up to 2× the price. JSON mode needs:
  - the word "json" in the prompt;
  - an example of the output;
  - a `max_tokens` large enough not to cut the JSON.

  DeepSeek admits it "may occasionally return empty content".
- **F3. `deepseek/deepseek-v4-flash`, our configured fallback model, is no longer served by DeepSeek.** It has 17
  third-party endpoints, several of them fp4 or fp8, and only one (Azure) with *implicit* caching.

  During a DeepSeek outage, OpenRouter first tries **V4.1 Flash on other providers** anyway, because
  `allow_fallbacks` is true.
  - **The pool is smaller than it looks.** No V4.1 endpoint declares bf16, fp16 or fp32, so our quantization list
    admits only the 12 endpoints marked `unknown`, DeepSeek included.
  - `require_parameters` then removes the ones missing a parameter we send. DigitalOcean lacks `stop`, so it can't take
    replies. Relace lacks `response_format`, so it can't take JSON calls.
  - "Unknown" means undisclosed precision, not NFR-33's "full precision". That is a gap in the existing D-41 routing,
    noted here and not changed by this task.
- **F3b. Repetition penalties.** DeepSeek's own API reference marks `presence_penalty` and `frequency_penalty` as no
  longer supported, even though OpenRouter still lists them on the DeepSeek endpoint.
- **F3c. Stop sequences.** DeepSeek accepts up to 16 stop strings.
- **F3d. Turning reasoning off.** OpenRouter documents `reasoning.effort: "none"` as the way to turn reasoning off.
  Horizon sends `reasoning: {enabled: false}`, which the M2 live run accepted. Check 1 confirms that no reasoning
  tokens are produced, and switches to `effort: "none"` if any are.
- **F4. DeepSeek's recommended temperatures:**

  | Use | Temperature |
  |---|---|
  | coding / maths | 0.0 |
  | data analysis | 1.0 |
  | general conversation, translation | 1.3 |
  | creative writing | 1.5 |

  The default is 1.0.
- **F5. Doc 01 means DeepSeek never has to decide anything.** Jev answers who speaks, quick vs deep, the emotion, the
  passage scores, the verdict rubric and memory importance. The thinking that reasoning would buy has already been
  done by System 1.

## 4. Decisions

### C1. One settings row per call type, in config

**Decision:** a table `runtime.llm.calls`, keyed as below. It holds `thinking`, `temperature` and the output kind.
Code never hard-codes these values. Every DeepSeek call looks up its row.

The table lives in the seed-build source `frontend/scripts/seed-build/runtime.config.ts`, which generates
`seed/runtime.json`. The length targets are in C4.

| Key | Call | Thinking | Temperature | Output | Built in |
|---|---|---|---|---|---|
| `reply.chat` | Character reply, 1:1 / group / watch | off | **1.3** | stream | naive today, agent profile |
| `reply.debate` | Debate argument | off | 1.0 | stream | task 8 (doc 08 V4) |
| `host` | Debate host lines, `max_tokens` 120, shown whole | off | 1.0 | text | task 8 (doc 08 V6) |
| `verdict` | Debate verdict prose, `max_tokens` 1,200 | off | 0.7 | JSON | task 8 (doc 08 V8) |
| `summary` | Rolling summary | off | 0.7 | text | task 5 (doc 05 X3) |
| `episode` | Watch's "Summarise" recap, `max_tokens` 400 | off | 0.7 | text | task 7 (doc 07 G10) |
| `memory` | Memory rewrite at a session pause, `max_tokens` 300 × characters present + 200 (≤ 3,000) | off | 0.7 | JSON | task 9 (doc 09 M3) |
| `query_rewrite` | A deep turn's search query, written with the speaker's cached prompt when the message isn't standalone or isn't in English, `max_tokens` 60; precise output, stored and reused on regenerate | off | 0.0 | text | task 10 (doc 10 K4) |
| `profile` | Profile draft, regenerate one field | off | 1.0 | JSON | naive today |
| `probe` | Settings → Test, 1 token | off | none | text | today |

Why these temperatures:
- **Replies use 1.3**, DeepSeek's value for conversation (F4). The user chose not to A/B test it.
- **Debate and host use 1.0:** arguments must stay on the motion and answer the other side. **The verdict prose uses
  0.7** (doc 08 V8): like a summary, it must be faithful to what was argued.
- **Summary and memory use 0.7, below DeepSeek's 1.0 for analysis:** they must be faithful to what was said, never
  inventive.
- **The profile drafter uses 1.0:** this keeps the JSON valid while the draft can still be creative.

**Parameters we do not send:**
- `top_p` (fixed when thinking is off, F1);
- `presence_penalty` and `frequency_penalty` (DeepSeek no longer supports them, F3b; repetition is a prompt problem for
  task 4);
- `seed` (DeepSeek doesn't support it);
- `logprobs` (not needed).

**Rejected:**
- Values hard-coded in each engine: tuning would mean code changes, and the eval (B7) could not vary them.
- One temperature for everything: summaries and arguments need less randomness than chat.

### C2. Thinking is off everywhere, including deep turns, behind a switch

**Decision:** every call sends `reasoning: {enabled: false}`. Each row in C1 has a `thinking` field (`off | low |
high`), default `off`, so it can be turned on later without code.

A **deep** turn means **"looks things up"** (Task 1's R1: search, then Jev call 2 scores the passages). It does not mean
"thinks longer".

Why not think on deep turns:
- **Speed.** Thinking writes hidden tokens before the first visible word. A short think of 300–800 tokens adds roughly
  3–10 s (an estimate; the B8 latency suite measures it if the switch is ever turned on). Deep turns already take
  about 1.5–3.5 s before the first word (doc 01 A6), so NFR-01 (2 s p50 / 4 s p90) would fail on every deep turn.
- **The deciding is already done.** Jev call 2 scored every passage, and code kept only the ones that answer the
  question. DeepSeek only has to say it in character (F5).
- **Cost and energy.** Thinking tokens are billed as output, at the higher price, and they drain the speaker's energy.
- **The voice.** In thinking mode the temperature is ignored (F1), so the persona's voice would flatten.

If the switch is ever turned on:
- the reasoning text is **never shown or stored**;
- only its token count is kept, in a new nullable `usage_records.tokens_reasoning` ledger column (internal; no
  contract change; `parse_usage` reads `completion_tokens_details.reasoning_tokens`);
- the B8 latency suite must pass again before it ships.

The same column also catches a silent failure: if a call with thinking "off" ever reports reasoning tokens, B7 flags
it.

The one case where thinking may help is a question that combines several documents ("compare the 2019 and 2023
policies"). Task 10 may revisit this with eval data. Doc 10 K14: it stays off unless sentence faithfulness on the two-passage
questions falls below 90 %.

**Rejected:**
- Thinking on for deep turns: it breaks NFR-01 for a gain Jev already gives.
- Thinking at low effort for host, verdict and profile (OQ-AI-13's recommendation): the verdict is decided by Jev's
  rubric scores (doc 01, verdict graph), so DeepSeek only writes prose.

### C3. Temperatures follow DeepSeek's guidance, with no A/B test

**Decision:** the values in C1 ship as they are. The ≈ $0.10 temperature comparison proposed in discussion is dropped,
by the user's decision. B7 can still vary a row later if a quality problem shows up.

**Rejected:** a 1.0 vs 1.3 eval run. DeepSeek publishes these values after its own testing, and the user wants the
budget low.

### C4. Length: a target in the prompt, `max_tokens` only as a safety net

**Decision:** the prompt tells the model how long to write, per mode. `max_tokens` becomes a ceiling at about 1.5–2×
the target, so a cut-off is rare.

| Mode | Target in the prompt | Safety net (`max_tokens`) | Today |
|---|---|---|---|
| 1:1, quick turn | 1–3 bubbles, ≈ 70 words | 200 | 350 |
| 1:1, deep turn | 2–4 bubbles, ≈ 120 words | 300 | 350 |
| Group | 1–2 bubbles, ≈ 50 words | 150 | 250 |
| Watch | 1–2 bubbles, ≈ 50 words | 150 | 220 |
| Debate short / medium / long | ≈ 80 / 140 / 220 words, one bubble | 200 / 320 / 480 | same |

- **Where the length lines go (NFR-35).**
  - The **per-mode** line ("1–3 short messages, one per line") is fixed for the whole session, so it sits in the cached
    system prompt.
  - The **per-turn** line (the deep target) changes from turn to turn, so it goes in the **dynamic tail**, inside the
    retrieval block that deep turns already add after the history, next to A5's mood line. A quick turn adds nothing.

  So the cached prefix never changes when a turn flips between quick and deep.
- **The cap is chosen after the plan.**
  - `replyMaxTokens` gains a `one_on_one_deep` entry, and `ReplyCaps.for_mode` gains a `deep` argument.
  - `sessions/turn.py` and `sessions/prefetch.py` compute the cap once the turn plan (doc 01 A6) says quick or deep.
  - Debate opening prefetch is never deep, so its cap is known up front.
  - A deep group turn uses the group cap, because group replies stay short.
- **The cut-off rate is measured:** the share of replies whose `finish_reason` is `length`. B7 reports it, and the
  target is **under 2 %** per mode. Above that, we raise that mode's safety net.
- **Where `finish_reason` is kept.** It goes in a new nullable `usage_records.finish_reason` ledger column, internal
  with no contract change, which B7 reads.
  - The naive engine stops discarding the final, content-less chunk.
  - A cut-off reply keeps its streamed text.
  - The Insight trace does not show the finish reason in v1. Showing it would be a `TurnTrace` contract change, left
    for later if wanted.
- **Error finish reasons.** A stream that ends with `finish_reason` `error`, or DeepSeek's
  `insufficient_system_resource`, is treated like a mid-stream provider error: the reply ends `interrupted`, keeps its
  text and can be retried. Today these end as complete.

  Whether OpenRouter passes DeepSeek's value through unchanged is unverified. Check 1 looks.
- **Why shorter than today:**
  - chat replies read like chat;
  - each reply finishes streaming sooner, which helps the group and watch pacing;
  - the energy reservation shrinks, because `expected_out` is capped by `max_tokens`.

  Output tokens dominate the cost once the prefix is cached (OQ-AI-13).
- The exact prompt wording is task 4's. Two lines in today's naive prompt change with it:
  - "in plain text" stays, and gains "one short message per line";
  - the debate cue's "stay under a few sentences" becomes the debate word targets.

**Rejected:**
- `max_tokens` as the only control (today): replies stop mid-sentence, and the model doesn't know its budget.
- Trimming a cut-off reply back to its last full sentence: the text has already been streamed to the screen, so
  removing it later would look like a glitch.
- OQ-AI-13's 120 / 180 / 250-word caps: they are longer than texting-style bubbles need.

### C5. Chat replies are shown as bubbles, split on the model's line breaks

**Decision:**
- In **1:1, group and watch**, the model writes each bubble on its own line: "write like texting, one short message per
  line".
- The UI draws each line as its own bubble. **Display only:** the turn is still **one message with one emotion**, one
  trace, one energy charge, one regenerate and one copy.
- **Debate arguments and host lines stay one bubble.** An argument cut into pieces reads badly.

UI rules (frontend, see §6):
- A new bubble opens while streaming, when a line break arrives.
- Blank lines collapse.
- No split inside a fenced code block or a Markdown list. The chat prompt asks for plain text, so these are a safety
  net only.
- At most **4 bubbles**: any further lines join the 4th.
- Citation chips sit under the last bubble.
- **Watch** has no bubbles. It renders script rows, so each line becomes its **own script line under the one name
  tape**: same split rules, script styling.
- **Readable.**
  - When the user switches Readable on, the reply shows as one unsplit panel, as today.
  - The **automatic** switch to Readable (a reply over `READABLE_CHARS`, 600 characters) applies in bubble modes only
    when a **single bubble** is over 600 characters. Otherwise a ≈ 120-word deep reply (≈ 700 characters) would
    always flip to Readable and never show bubbles.
- The user's own messages are never split.
- **Demo parity (doc 01 A12).** The seed transcripts, the mock banks and the scripted engine's lines get line breaks
  in their 1:1, group and watch replies. Otherwise the free demo would never show bubbles.

Why line breaks and not full stops:
- **The model groups naturally:** "Haha. Yeah, I know." stays one bubble.
- **Full stops break text.** Splitting on them cuts "Dr. Lee", "3.5", "…" and URLs, and it gives one-word bubbles like
  "Okay."
- **Line breaks work in every language,** including Chinese `。`.

**D-46 is kept in substance, but its wording needs a change.** D-46 says "one message with one emotion per character
turn (no multi-bubble replies)", and it rejected "up to 3 bubbles per turn". Its reasons were:
- the contract;
- NFR-29;
- one trace per message;
- the seed transcripts were already fixed.

The first three still hold, because the message model doesn't change. The seed transcripts are updated for demo parity
(above). Only "no multi-bubble replies" becomes "one message, which chat modes may display as up to 4 bubbles". The wording change is listed in §6.

**Rejected:**
- Splitting at full stops (above).
- Separate messages per bubble: that is the D-46 alternative. It breaks one-trace-per-message and the contract.
- Bubbles in debate: a split argument reads badly.

### C6. Stop sequences keep the speaker from writing other people's lines

**Decision:**
- Every reply sends `stop` with the same prefixes the history uses (`window.py`):
  - `"\n<Name>:"` for every other participant;
  - `"\n<You name>:"` for the user;
  - `"\n[<kind>]"` for each non-character line kind the history renders (for example host lines).

  Never a bare `"\n["`: a line may legitimately start with a citation marker `[n]`.
- **The limit never binds.** The largest cast is 5, so at most 4 other names + the user + a few kinds, well under
  DeepSeek's 16 (F3c).
- **Stripping the speaker's own name.** The engine also strips a leading `<own name>:` from the reply, before or after
  the emotion tag (`Mei: <e:happy>Hi` and `<e:happy>Mei: Hi`).
  - Today's tag parser can't do this: it releases the head as soon as it can't be `<e:`, and on the tag-fallback path
    that loses the emotion.
  - So the parser gains a **short name-prefix buffer**, holding at most the name's length plus 2 characters, and the
    shared parser fixtures (`backend/tests/fixtures/tag_parser/`) gain these cases.
- A reply that ends on a stop sequence reports `finish_reason: "stop"`. That is a normal end, not a cut-off.

**Rejected:**
- A prompt rule alone: models still continue the transcript format they are shown.
- Cleaning up after the stream ends: the extra line would already be on screen.

### C7. JSON calls use JSON mode, validation and one retry

**Decision:** for every DeepSeek call that returns JSON (profile draft, field regenerate, and task 9's memory
extraction):
1. Send `response_format: {type: "json_object"}`. The prompt says "json" and gives the schema and **one example** (F2).
2. Use a `max_tokens` large enough for the full object (the drafter's 2,400 stays).
3. Validate with the Pydantic model.
4. If the result is empty, unparsable or invalid, **retry once**. The retry appends the validation error to the
   messages; the prefix stays the same, so it is cached.
   - Retry **only** on that parse or validation failure. Timeouts, transport errors, refusals and budget errors keep
     their existing handling, so we never pay twice for an unknown outcome (D-84).
5. If the retry also fails, use the port's existing failure path (the creation job's error and Retry).

**Billing.** Both attempts are billed and get their own ledger row, under the creation cap for creation calls.

**How this fits the creation job hooks** (`services/jobs/worker.py`). Today validation runs in `after_response`,
after the call is billed. `before_send` marks `provider_called_at` on each call, and `commit_with` overwrites the
task's `cost_usd` with the last call's cost. So:
- the retry runs inside the same task attempt;
- each call keeps its own ledger row;
- the task's `cost_usd` becomes the **sum** of both calls.

**Rejected:**
- Strict `json_schema` / `structured_outputs`: DeepSeek's own endpoint doesn't support it, so `require_parameters`
  would move the call to a third party with no cache, at up to 2× the price (F2). The user ruled that cost comes
  first.
- More than one retry: the cost grows, and a second failure usually means a prompt bug, which should show up.

### C8. Only V4.1 Flash; drop the fallback model

**Decision:**
- Remove `gateway.fallbackModel` from `seed/pricing.json`. The chat client stops sending `models: [...]`.
- Provider fallback stays as it is: `allow_fallbacks: true` with the same quantization list.
- So during a DeepSeek outage, OpenRouter runs **the same model, V4.1 Flash, on another provider**:
  - the Insight trace's `model.provider` names the provider that actually answered (the `provider_warning` text
    exists only on non-streamed results today, and `TurnTrace` has no warnings field; no contract change);
  - the ledger records the real (higher, uncached) cost;
  - the budget gate and energy apply as usual.
- If every V4.1 provider fails, the turn ends with the existing provider error and the user can retry.

**Rejected:**
- Keeping `deepseek-v4-flash`: DeepSeek no longer serves it, it runs only on third parties (several fp4 or fp8), and
  it changes the characters' voice mid-session (F3).
- No provider fallback at all: one DeepSeek outage would stop every chat.

R-14's mitigation ("v4-flash as fallback") becomes: persona quality is checked by the eval (B1, B4). If V4.1 ever
fails it, a developer changes the pinned model in config and re-runs the eval.

### C9. Tuned for one model set: the Models tab becomes read-only in v1

**Decision:**
- Horizon v1 is tuned for its pinned models: V4.1 Flash, Jev 1.13, Qwen3 Embedding 8B, Seedream 5.0 Flash and Lyria 3
  Clip. Everything in tasks 1–3 depends on them: the temperatures, the length targets, the Jev floors tuned in B5 and
  the cache layout.
- **Settings → Models becomes a read-only "Models in use" panel.** For each role it shows:
  - the model slug and what it is for;
  - its price;
  - the **Test** button.

  A line says: "Tuned for these models. Custom models are planned for v2."
- **Where the price comes from.** `AppSettings` carries no prices (only `pricing.period` and `nextChangeAt`), and
  adding them would be a contract change. So the panel reads the price table **bundled with the frontend**: the same
  `pricing.config.ts` that generates `seed/pricing.json`. Both come from one source, so they can't drift in a build.
- **One source for the chat model.** The drafter and the probe switch from `settings.models.chat` to
  `prices.chat.model`, the one the replies use. Startup logs an error if `settings.models.chat` differs from it, so a
  developer who edits one file but not the other finds out.
- **Test.**
  - It probes the model the app actually uses, **ignoring any stored override**, so an old override can't make Test
    pass on a model chat never uses.
  - The chat probe sends `reasoning` off (row `probe` in C1).
  - The places that pin today's override behaviour change with it:
    - `openspec/specs/openrouter-key/spec.md`;
    - `backend/tests/integration/test_settings_key.py` (`test_model_probe_echoes_the_override`);
    - `frontend/src/mock/MockClient.ts`.
- The `modelOverrides` field **stays in the contract, unused**, so there is no contract change, and v2 can use it.
- Developers can still change models by editing the seed config. That is not a user feature, and the eval must be
  re-run.

What v2 needs before overrides can work is written down in [docs/v2/README.md](../v2/README.md):
- per-model settings rows with safe defaults (no temperature, thinking off, `max_tokens` only);
- the model's real price from OpenRouter's model list, so energy estimates are right;
- routing pinned only for DeepSeek;
- JSON mode only where the model supports it;
- prompt caching for models that need explicit cache breakpoints;
- an eval run per model.

**Rejected:**
- Keeping the editable tab: an override that silently does nothing is worse than no setting.
- Wiring overrides properly in v1: real work across params, pricing, routing and eval, for a feature the user wants in
  v2.
- Hiding the tab completely: open-source users need to see which models run and to test their key against each one.

## 5. Checks before this is locked

1. **Thinking is really off, and error finish reasons come through (paid, ≈ $0.01, needs the user's OK).** *Done
   ([group A](checks/group-a.md) A3): `enabled: false` gives 0 reasoning tokens (the default gave 20); `stop` and
   `length` pass through, with a matching `native_finish_reason`; served by DeepSeek. A group reply began with
   "Takeshi: …", so C6's own-name strip is needed.*
   - Send one reply request through the gateway with `reasoning: {enabled: false}`, `temperature: 1.3` and the C6
     `stop` list.
   - Read the **raw** `usage`. Expect `completion_tokens_details.reasoning_tokens = 0`, no `reasoning` deltas, and the
     provider still `DeepSeek` (no `require_parameters` reroute).
   - If any reasoning tokens appear, repeat with `reasoning: {effort: "none"}` (F3d) and use whichever form gives 0.
   - Note the `finish_reason` values OpenRouter passes through.
2. **JSON mode (paid, ≈ $0.02, needs the user's OK).** Run 20 profile drafts. Count the empty or invalid results before
   and after the retry. The target is ≥ 99 % valid after one retry. *Done (A3): **19/20**, with the same failure on
   retry: a nickname in unescaped double quotes (`"Loretta "Rhett" Kowalski"`). **The user's fix (2026-10-10, built
   in M7):** every JSON prompt says to use single quotes inside text values, and a free local repair pass escapes
   stray inner quotes before the one paid retry.*

   **Two reply rules from A2's empty streams (built in M7):**
   - a reply request whose history ends with the speaker's own line always carries a trailing cue (2 of 4 such
     requests came back empty; 0 of 40 1:1 turns ending on the user's line did);
   - an empty reply (`finish_reason: stop`, no content) is a retryable failure, retried once before any text is
     shown.
3. **The cut-off rate and bubble count** come from the B7 conversation layer, at no extra cost:
   - the share of `finish_reason = length` per mode, read from the new ledger column;
   - bubbles per reply against the C4 targets.

   B7's cached naive replies are invalidated by the prompt-version bump (§6), so the first run after this change pays
   for fresh naive replies once.

(The stop-string limit is settled: DeepSeek allows 16, and Horizon needs at most about 8, F3c.)

## 6. Changes this design needs (each approved at its OpenSpec change)

| Change | Where | Kind |
|---|---|---|
| The `runtime.llm.calls` table; `replyMaxTokens` new values plus `one_on_one_deep`; then `seed:build` | `frontend/scripts/seed-build/runtime.config.ts` → `seed/runtime.json`; `domain/runtime_config.py` (`ReplyCaps.for_mode(mode, turn_length, deep)`) | config |
| The cap is chosen after the turn plan | `sessions/turn.py`, `sessions/prefetch.py`; `TurnContext.max_tokens` default | backend |
| Replies, drafter and probe read their row: thinking, temperature, stop | `ai/naive/turn.py`, `ai/naive/creation.py`, `services/probes.py`, the agent engines | backend |
| The name-prefix buffer, before and after the emotion tag, plus the shared fixtures | `ai/naive/tag_parser.py`, `backend/tests/fixtures/tag_parser/` | backend |
| Length targets (per mode in the prefix, per turn in the dynamic tail) and one-message-per-line; the debate cue's wording; **`PROMPT_VERSION` naive-2 → naive-3** | `ai/naive/prompt.py` (wording in task 4) | backend |
| JSON helper: validate, retry once only on parse or validation failure, then the existing failure path; the task's `cost_usd` = the sum | `ai/naive/creation.py`, `services/jobs/worker.py` (later task 9's memory extraction) | backend |
| Remove `fallbackModel`; send `models` only when configured | `frontend/src/mock/pricing.config.ts`, `frontend/src/domain/cost.ts` (make it optional) → `seed/pricing.json`; `gateway/types.py`, `gateway/chat.py` | backend + config |
| Keep `finish_reason` (stop dropping the final chunk); map `error` / `insufficient_system_resource` to interrupted; parse `reasoning_tokens` | `gateway/chat.py`, `gateway/types.py` (`parse_usage`), `ai/naive/turn.py` | backend |
| Ledger columns `finish_reason` and `tokens_reasoning` (nullable; Alembic migration; internal, not contract) | `db/tables.py`, the gateway pipeline | backend |
| One chat-model source: drafter and probe use `prices.chat.model`; startup error log on mismatch; Test ignores `modelOverrides` | `services/jobs/worker.py`, `services/probes.py`, `runtime.py`; `openspec/specs/openrouter-key/spec.md`; `tests/integration/test_settings_key.py`; `frontend/src/mock/MockClient.ts` | backend + frontend |
| Tests that pin today's values: 350 / 250 / 220, `max_tokens == 350`, the `models` fallback list, the naive prompt | `tests/unit/test_runtime_config.py`, `tests/sessions/test_naive.py`, `tests/unit/test_chat_client.py`, `tests/knowledge/test_naive_prompt.py` | tests |
| Bubble rendering for 1:1 / group (bubbles) and watch (script lines); the auto-Readable rule per bubble | `frontend/src/features/session/MessageRow.tsx`, `sessionContext.ts`, the stream text | frontend |
| Demo parity: line breaks in seed transcripts, mock banks and scripted lines | `frontend/scripts/seed-build/data`, `frontend/src/mock/banks`, `ai/scripted` | frontend + seed |
| Settings → Models becomes read-only, with prices from the bundled `pricing.config.ts`, and Test | `frontend/src/features/settings/ModelsTab.tsx` | frontend |
| Wording changes: SET-05 is read-only in v1; D-46 "may display as up to 4 bubbles"; R-14 mitigation (C8); R-13 "DeepSeek structured-output fallback" becomes "JSON mode + validation" (applied instead as "a deterministic code fallback per question": Jev failures fall back to code rules, [doc 13](13-wrap-up.md) status note); OQ-AI-13 resolved; doc backend/04's "fallback model" line; D-93 and 05-ai-seams' "byte-identical to v1" note (no longer true after naive-3); `openspec/specs/ai-ports` (naive reply engine) and `http-api` where they state caps, the fallback or the probe override | `docs/requirements/02, 05, 07, 08, 09`, `docs/backend/04, 05`, `openspec/specs/*` | docs |
| Doc 01's failure-mode table says "structured output"; it becomes "JSON mode + validation + one retry" (C7) | `docs/ai/01-agent-architecture.md` §6 | docs (done with this doc) |

**No contract change.** `finish_reason` and reasoning tokens live in the internal ledger. The provider shows through the
existing `model.provider`. Prices come from the bundled config. `modelOverrides` stays, unused.

## 7. Left for later tasks

- ~~The exact prompt wording for length, bubbles and repetition (task 4).~~ Resolved by doc 04 P5, P6, P8.
- ~~The debate argument and host prompts (task 8).~~ Resolved by doc 08 V4, V6 and V8.
- ~~The summary and memory-extraction prompts and schemas (task 9).~~ Resolved by doc 05 X3 (summary) and doc 09 M3
  (memory extraction).
- ~~Whether a multi-document deep question should ever think (task 10, with eval data).~~ Resolved by doc 10 K14:
  off, revisited only on eval data.
- Custom models (v2, [docs/v2](../v2/README.md)).

## Sources

- DeepSeek API docs:
  - [Parameter settings (temperature)](https://api-docs.deepseek.com/quick_start/parameter_settings)
  - [Thinking mode](https://api-docs.deepseek.com/guides/thinking_mode)
  - [JSON output](https://api-docs.deepseek.com/guides/json_mode)
- OpenRouter endpoints:
  - [DeepSeek V4.1 Flash](https://openrouter.ai/api/v1/models/deepseek/deepseek-v4.1-flash/endpoints)
  - [DeepSeek V4 Flash](https://openrouter.ai/api/v1/models/deepseek/deepseek-v4-flash/endpoints)
- Secondary sources:
  - [promptfoo: DeepSeek provider](https://www.promptfoo.dev/docs/providers/deepseek)
  - [Huawei Cloud: DeepSeek-V4 parameters](https://support.huaweicloud.com/intl/en-us/model-call-maas/model-call-021.html)

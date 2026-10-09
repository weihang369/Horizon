# 03: LLM parameters

> **Status: agreed with the user, 2026-10-09** (AI stage, task 3 of 13).
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
  `response_format`, `stop`, `logprobs` and `extra`. Only the fields that are set go into the body. So nothing in this
  task needs a gateway change, except removing the fallback model (C8).
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

  The prompt only says "reply in character, briefly". The cap is the only real length control, so a reply that hits
  it stops mid-sentence.
- **The history** renders other speakers as `user` messages prefixed with their name (`Mei: …`, see
  [window.py](../../backend/horizon/ai/naive/window.py)). So the model sometimes continues with the next speaker's line.
- **The naive drafter** ([naive/creation.py](../../backend/horizon/ai/naive/creation.py)) uses JSON mode
  (`response_format: json_object`, the schema in the system prompt), reasoning off, `max_tokens` 2,400.
- **Host lines, the verdict and the rolling summary** are scripted-only today (doc 01 §8). Their DeepSeek calls arrive
  in tasks 8 and 9, and they use the settings in C1.
- **Model overrides.** Settings → Models (SET-05) lets the user type a different model slug, saved as
  `modelOverrides`. **Only the Test button reads them** ([probes.py](../../backend/horizon/services/probes.py)):
  - replies use the model pinned in `seed/pricing.json`;
  - the drafter uses `settings.models.chat` (the default, not the override).

  Today, typing another model there changes nothing a user can see.

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
  third-party endpoints, several of them fp4 or fp8, and only one with implicit caching. During a DeepSeek outage,
  OpenRouter first tries **V4.1 Flash on other providers** anyway, because `allow_fallbacks` is true. Those are the
  31 endpoints, filtered by our quantization list and `require_parameters`.
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

**Decision:** a table `runtime.llm.calls` in `seed/runtime.json`, keyed by purpose. It holds `thinking`,
`temperature`, the output kind and the length target. Code never hard-codes these values. Every DeepSeek call looks up
its row.

| Call (purpose) | Thinking | Temperature | Output | Built in |
|---|---|---|---|---|
| Character reply, 1:1 / group / watch (`reply`) | off | **1.3** | stream | naive today, agent profile |
| Debate argument (`reply`, debate mode) | off | 1.0 | stream | task 8 |
| Debate host lines and verdict prose (`host`, `verdict`) | off | 1.0 | stream | task 8 |
| Rolling summary (`summary`), memory extraction (`memory`) | off | 0.7 | text / JSON | task 9 |
| Profile draft, regenerate one field (`profile`) | off | 1.0 | JSON | naive today |

Why these temperatures:
- **Replies use 1.3**, DeepSeek's value for conversation (F4). The user chose not to A/B test it.
- **Debate and host use 1.0:** arguments must stay on the motion and answer the other side.
- **Summary and memory use 0.7, below DeepSeek's 1.0 for analysis:** they must be faithful to what was said, never
  inventive.
- **JSON calls use 1.0:** this keeps the output valid while the drafter can still be creative.

**Parameters we do not send:**
- `top_p` (fixed when thinking is off, F1);
- `presence_penalty` and `frequency_penalty` (one cloud host says V4 doesn't support them, and repetition is a prompt
  problem for task 4);
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
- only its token count goes into the trace;
- the B8 latency suite must pass again before it ships.

The one case where thinking may help is a question that combines several documents ("compare the 2019 and 2023
policies"). Task 10 may revisit this with eval data.

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

- `replyMaxTokens` gains a `one_on_one_deep` entry. The deep group turn uses the group cap, because group replies stay
  short.
- **The cut-off rate is measured:** the share of replies whose `finish_reason` is `length`. B7 reports it, and the
  target is **under 2 %** per mode. Above that, we raise that mode's safety net.
- A cut-off reply keeps its streamed text. The trace records `finishReason: "length"`.
- **Why shorter than today:**
  - chat replies read like chat;
  - each reply finishes streaming sooner, which helps the group and watch pacing;
  - the energy reservation shrinks, because `expected_out` is capped by `max_tokens`.

  Output tokens dominate the cost once the prefix is cached (OQ-AI-13).
- The exact prompt wording is task 4's.

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
- No split inside a fenced code block or a Markdown list.
- At most **4 bubbles**: any further lines join the 4th.
- Citation chips sit under the last bubble.
- The **Readable** panel and the user's own messages are never split.

Why line breaks and not full stops:
- **The model groups naturally:** "Haha. Yeah, I know." stays one bubble.
- **Full stops break text.** Splitting on them cuts "Dr. Lee", "3.5", "…" and URLs, and it gives one-word bubbles like
  "Okay."
- **Line breaks work in every language,** including Chinese `。`.

**D-46 is kept in substance, but its wording needs a change.** D-46 says "one message with one emotion per character
turn (no multi-bubble replies)", and it rejected "up to 3 bubbles per turn". Its reasons were:
- the contract;
- NFR-29;
- one trace per message.

All three still hold, because the message model doesn't change. Only "no multi-bubble replies" becomes "one message,
which chat modes may display as up to 4 bubbles". The wording change is listed in §6.

**Rejected:**
- Splitting at full stops (above).
- Separate messages per bubble: that is the D-46 alternative. It breaks one-trace-per-message and the contract.
- Bubbles in debate: a split argument reads badly.

### C6. Stop sequences keep the speaker from writing other people's lines

**Decision:**
- Every reply sends `stop` with `"\n<Name>:"` for every other participant and the user's display name. These are the
  same prefixes the history uses.
- If the cast is larger than DeepSeek's limit on stop strings, it keeps the most recent speakers first.
- The engine also strips a leading `<own name>:` from the reply. The tag parser already buffers the start of the
  stream.
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
5. If the retry also fails, use the port's existing failure path (the creation job's error and Retry).

Both attempts are billed to the ledger as normal, under the creation cap for creation calls.

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
  - the trace shows the existing provider warning;
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
  - its price from `seed/pricing.json`;
  - the **Test** button.

  A line says: "Tuned for these models. Custom models are planned for v2."
- Test probes the model the app actually uses, **ignoring any stored override**. That way an old override can't make
  Test pass on a model chat never uses.
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

1. **Thinking really is off (paid, ≈ $0.01, needs the user's OK).** Send one reply request through the gateway with
   `reasoning: {enabled: false}`. Expect `reasoning_tokens = 0` in `usage` and no `reasoning` deltas. Repeat with
   `temperature: 1.3` and `stop`: expect no `require_parameters` routing change (the provider is still `DeepSeek`).
2. **JSON mode (paid, ≈ $0.02).** 20 profile drafts. Count the empty or invalid results before and after the retry.
   The target is ≥ 99 % valid after one retry.
3. **The cut-off rate and bubble count** come from the B7 conversation layer, at no extra cost: the share of
   `finish_reason = length` per mode, and bubbles per reply against the C4 targets.
4. **Stop-string limit.** Confirm DeepSeek's maximum number of `stop` strings on the endpoint (check 1's request can
   send 16).

## 6. Changes this design needs (each approved at its OpenSpec change)

| Change | Where | Kind |
|---|---|---|
| The `runtime.llm.calls` table; `replyMaxTokens` new values plus `one_on_one_deep` | `seed/runtime.json`, `domain/runtime_config.py` | config |
| Replies, drafter and later calls read their row: thinking, temperature, stop | `ai/naive/*`, the agent engines | backend |
| Length targets and the one-bubble-per-line instruction in the prompt (wording in task 4) | prompt compiler | backend |
| JSON helper: validate, one retry with the error, then the existing failure path | `ai/naive/creation.py` (later task 9's memory extraction) | backend |
| Remove `fallbackModel`; send `models` only when configured | `seed/pricing.json`, `gateway/types.py`, `gateway/chat.py` | backend |
| Test ignores `modelOverrides` | `services/probes.py` | backend |
| Bubble rendering for 1:1 / group / watch (C5 rules) | `frontend/src/features/session/MessageRow.tsx` and the stream text | frontend |
| Settings → Models becomes read-only with prices and Test | `frontend/src/features/settings/ModelsTab.tsx` | frontend |
| `finishReason` in the trace's model block | `TurnTrace` | check at the OpenSpec change whether it fits an existing field; if not, **ask the user** (contract) |
| Wording: SET-05 read-only in v1; D-46 "may display as up to 4 bubbles"; R-14 mitigation; OQ-AI-13 resolved; doc backend/04 "fallback model" line | `docs/requirements/02, 05, 07, 08, 09`, `docs/backend/04` | docs |
| Doc 01's failure-mode table says "structured output"; it becomes "JSON mode + validation + one retry" (C7) | `docs/ai/01-agent-architecture.md` §6 | docs (done with this doc) |

## 7. Left for later tasks

- The exact prompt wording for length, bubbles and repetition (task 4).
- The debate argument and host prompts (task 8).
- The summary and memory-extraction prompts and schemas (task 9).
- Whether a multi-document deep question should ever think (task 10, with eval data).
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

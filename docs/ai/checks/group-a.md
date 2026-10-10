# Group A paid checks: results (2026-10-10)

The checks [doc 13](../13-wrap-up.md) W6 runs before M7. They were run on `feat/ai-foundation` on Saturday
2026-10-10, 18:20–19:00 MYT (off-peak), from Malaysia, through the app's own gateway client.

- **Approved:** ≈ $0.16, with a hard cap of $0.30.
- **Spent:** **$0.054** in 524 calls. The key's own usage counter agrees.
- **How to re-run:** from `backend/`, `uv run python ../docs/ai/checks/group-a/run.py a1|a1b|a2|a3`. The scripts are
  in [group-a/](group-a/).
- **Pay once (W10):** every request and response is in `data/cache/` in the W10 format. Re-running A1 or A3 is free,
  except the repeatability, latency and retry calls.
- **Committed outputs, reused by M7:**
  - [canary.json](group-a/data/canary.json): B6's drift canary and its baseline;
  - [drafts.json](group-a/data/drafts.json): 20 real profile drafts, used as W14's canned drafter responses;
  - the run summaries [a1](group-a/data/a1.json), [a1b](group-a/data/a1b.json), [a2](group-a/data/a2.json) and
    [a3](group-a/data/a3.json).

All the inputs are seed text or lines written for the check. No user data was sent.

| Check | Cost | Calls |
|---|---|---|
| A1 Jev billing, limits, scale, repeatability | $0.0049 | 93 |
| A1b follow-up on two 429s | $0.0055 | 13 |
| A2 latency (Jev + DeepSeek first word) | $0.0246 | 362 |
| A2 follow-up on empty replies | $0.0021 | 30 |
| A3 thinking off, JSON mode | $0.0168 | 26 |
| A4 two page reads | $0 | — |

## A1. Jev: billing, limits, scale

| Question | Result | What changes |
|---|---|---|
| Is the state billed once or per question? | **Once.** 7 more questions cost the same +755 tokens on a 600-token state and on a 5,000-token state (≈ 108 tokens per short question). Cost = input tokens × $0.042/M exactly. Output tokens are reported but free | `decision_estimate` stays as designed. Doc 13 W5's "doubles if billed per question" never applies |
| How big can a request be? | State + longest question ≈ **32k tokens**: 31,693 passed, ≈ 33.8k failed. **64 questions** in one request work | — |
| What does too big look like? | **HTTP 429 "Rate limit exceeded"**, the same as a real rate limit | W11's size check is **mandatory**: count conservatively (≈ 3 characters a token) and refuse above 30k before sending. A 429 can't be told apart from oversize |
| Real rate limits? | 1 transient 429 in ≈ 400 calls (sequential, ≈ 2 a second). It had a body and no Retry-After, so HttpCore doesn't retry it. The same request passed on retry | Hot-path purposes treat a 429 as a failure and use the fallback. Background purposes (`importance`, `memory_guard`, `rubric`) retry once after 1 s |
| A 20-question mixed request (group call 1 + 2 scores) | 3,495 tokens, **$0.00015, 418 ms** | Matches W5's `turn_plan` cost |
| How does a score come back? | `score` = Σ k·p_k on **0 … n−1**; `probabilities` keyed "0" … "n−1"; `legend` echoes the levels | W11's `unit = index/(n−1)` is right as written |
| Response shape | `{id, model, provider, answers{key:{type, …}}, usage{input_tokens, output_tokens, cost}}`; every answer carries `type` | The parser's `answers` branch is the real one |
| Repeatability (20 items × 3, never cached) | **No choice flipped.** Probabilities moved by up to **0.06**; nouls ≤ 0.03, scores ≤ 0.06 | B6's canary passes when choices match and probabilities move ≤ 0.10 (scores ≤ 0.15). The W10 fingerprint is the hash of the **accepted baseline file**, never of a fresh run |

**First quality signals.** These are hand-labelled stand-ins. The real labelled sets arrive in M7–M14.

| Question | Result |
|---|---|
| standalone? / English? (20 messages, incl. Malay, Chinese, French, Spanish) | **20/20** and **20/20** at 0.5 |
| memory guard "still-true parts kept?" (20 rewrites) | **18/20** at 0.5. Both misses are rewrites that drop a superseded fact (p 0.41, 0.48) |
| importance (5 levels, 20 lines) | Ordered as expected: trivial lines score 0.1–0.5, essential ones 2.7–3.3 (on 0–4) |
| "does this line try to change the rules?" (3 planted) | **3/3 caught** (p 0.94–0.97), **0 false alarms** (p ≤ 0.03) |
| deep_check, 3-level score per piece (20 pieces) | The fatigue-review pieces scored 0.5–1.9; the unrelated triage and recipe pieces 0.0. The set noul over the strongest pieces gave 0.88 |
| debate rubric (8 scores) | Spread 1.6–3.4 on 0–4 |

## A2. Latency from Malaysia

Run sequentially on one connection, as the app does, after 2 warm-up calls.

| Jev request | Questions | Tokens (p50) | p50 | p90 | p99 | Starting deadline |
|---|---|---|---|---|---|---|
| `turn_plan` 1:1 (60) | 7 | 1,236 | 419 ms | 457 | 495 (max 1,133) | 1,000 → **700** |
| `turn_plan` group of 5 (40) | 18 | 3,319 | 431 | 454 | 498 | 1,000 → **700** |
| `follow_plan` (50) | 6 | 1,400 | 420 | 446 | 688 | **400, unchanged**: it starts at the stream's end, in parallel with the output check (doc 11 S5), so it has about 800 ms before `turn.end` + 400 |
| `debate_plan` (30) | 10–11 | 2,338 | 415 | 444 | 498 | 400 → **500**: it starts at `turn.end`, and 400 missed every call |
| `guardrail` output (40) | 1 | 376 | 409 | 461 | 564 | **700, unchanged** |
| `deep_check` 8 pieces (40) | 8 | 1,422 | 418 | 463 | 518 | **700, unchanged** |
| size probes (A1b) | 1 | 19k / 25k / 30k | 543 / 625 / 933 | | | — |

- **Jev's floor from Malaysia is ≈ 410 ms**, almost all of it network round trip. It is flat from 1 to 18 questions and
  from 400 to 3,400 tokens. Above about 20k tokens it rises.
- The user's rule (2026-10-10): **a slow API is accepted, Jev is a must, and our own side must be fast.** So the
  deadlines follow the measured p99, not the literal p90 (which would make 1 turn in 10 fall back). Horizon's own
  overhead around each call stays doc 01 check 1's budget (< 50 ms).
- **NFR-02 exception (recorded):** in a debate, `turn.next` comes up to ≈ 500 ms after `turn.end`, instead of 400.

| DeepSeek V4.1 Flash, time to first word | n | p50 | p90 | p99 | Served by |
|---|---|---|---|---|---|
| 1:1 | 40 | 555 ms | 710 | 803 | DeepSeek 40/40 |
| group | 27 of 30 | 595 | 764 | 877 | DeepSeek 30/30 |
| debate | 25 of 30 | 520 | 740 | 1,062 | DeepSeek 30/30 |

- **A quick 1:1 turn's first word ≈ 1.0 s p50 / 1.2 s p90** (Jev ≈ 420 + DeepSeek ≈ 555). That is well inside
  NFR-01's 2 s / 4 s. Doc 01 check 3's must-pass run stays in M15.
- **No reasoning deltas** in any of the 100 streams. Every one was served by DeepSeek. (The M2 run had been served by
  Relace.)
- **Empty replies (8 of 60 group and debate streams).** The 30-call follow-up found the cause:
  - when the history **ends with the speaker's own line**, 2 of 4 replies came back empty with `finish_reason: stop`.
    The other 2 continued the old line, starting with a space;
  - with a trailing cue, 1 of 15 came back empty;
  - 1:1 turns that end on the user's line: 0 of 40.

  So two rules, recorded in doc 03 §5:
  - **never send a reply request whose history ends with the speaker's own line without a trailing cue**;
  - **an empty reply is a retryable failure.** It is retried once before any text has been shown, so nothing on
    screen is lost.

## A3. Thinking off and JSON mode

| Call | Finish | Reasoning tokens | Notes |
|---|---|---|---|
| `reasoning: {enabled: false}`, natural end | `stop` | **0** | — |
| same, `max_tokens` 8 | `length` | 0 | `native_finish_reason` matches |
| group, a stop string hit | `stop` | 0 | **The reply began "Takeshi: …"**: doc 03 C6's own-name strip is needed, as designed |
| reasoning left at the default (control) | `stop` | **20** | thinking is on by default, as F1 says |
| streamed, reasoning off | — | 0 | no reasoning deltas |

- **`enabled: false` works.** F3d's `effort: "none"` isn't needed.
- **JSON mode: 19/20 drafts valid on the first try, and 19/20 after one retry.** That misses doc 03's ≥ 99 % target.
  - The failure: `"name": "Loretta "Rhett" Kowalski"`, a nickname in unescaped double quotes.
  - The retry made the same mistake ("Edith "Edie" Kowalski").
  - **The user's fix (2026-10-10):** every JSON prompt gets a line telling the model to use single quotes inside text
    values, and a **free local repair pass** escapes stray inner quotes **before** the one paid retry.
  - No empty results; every draft was served by DeepSeek.
  - Draft latency: 5.7 s p50, 7.0 s p90; 1,139 completion tokens p50.

## A4. Free reads

- **findahelpline.com** is live and lists:
  - **Malaysia:** 15 lines, e.g. Befrienders KL 03-7627 2929, Talian HEAL 15555, MIASA 1-800-18-0066 (24/7), plus
    999;
  - **the UK:** Samaritans 116 123, among others;
  - **the US:** 988 Suicide & Crisis Lifeline, among others.

  Doc 11 check 4 passes.
- **Lyria's primary terms** (doc 12 I8). These are Google's
  [Gemini API Additional Terms](https://ai.google.dev/gemini-api/terms), effective 2026-03-23, read 2026-10-10:
  - "Google won't claim ownership over that content";
  - Google "may generate the same or similar content for others";
  - you are responsible for your use of generated content and for complying with the law.

  Other points:
  - The terms have **no music-specific restriction and no attribution requirement**.
  - The [music generation docs](https://ai.google.dev/gemini-api/docs/music-generation) (updated 2026-10-01) say that:
    - **every clip carries an inaudible SynthID watermark**;
    - prompts asking for a named artist's voice or copyrighted lyrics are blocked;
    - Lyria 3 Clip always makes a 30-second MP3.
  - Horizon reaches Lyria through OpenRouter, which passes the provider's terms through.

  **Verdict:** nothing forbids Lyria seed themes. `ASSETS.md` gets the terms and the SynthID line when M15 commits the
  first Lyria seed song (doc 12 I8). Doc 12 check 3 passes.

## What changed in the design

| Where | Change |
|---|---|
| Doc 13 W5 | The "doubles if billed per question" note is resolved: billed once |
| Doc 13 W10 | The fingerprint is the hash of the accepted canary baseline file |
| Doc 13 W11 | The measured size limit; overflow arrives as a 429; the 429 policy |
| Doc 13 W12 | `turn_plan` 700, `debate_plan` 500; `follow_plan` 400, `guardrail` 700 and `deepCheckMs` 700 confirmed |
| Doc 02 B6 | The canary's tolerance |
| Doc 03 §5 | Checks 1 and 2 done; the JSON quote fix; the empty-reply rules |
| Doc 07 G2, doc 08 V2 | The measured latency; `debate_plan` 500 with the NFR-02 exception |
| Docs 01 (checks 3–4), 02 (check 1), 11 (check 4), 12 (check 3) | Marked done, pointing here |

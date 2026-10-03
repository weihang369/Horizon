# Image model test

**Decision (D-61):** the default image model is **`bytedance-seed/seedream-5-0-flash`** (OpenRouter `POST /api/v1/images`). It does both jobs:
- generates the base portrait from text;
- creates each emotion as an instruction edit of the locked base portrait.

The prompts and the scorecard are in [TESTING.md](TESTING.md).

## Run 1: Hana, 2026-10-03

Results are in [2026-10-03-seedream-5-0-flash-hana/](2026-10-03-seedream-5-0-flash-hana/). Open `index.html` for the contact sheet; `run.json` holds the prompts, costs and latencies.

| | |
|---|---|
| Setup | 1K, 3:4. The neutral base is text-to-image; 7 emotions are edits, each using the base as its only `input_references` image |
| Output | 832×1110 JPEG, ~210 KB each |
| Cost | **$0.018 / image**; $0.144 for all 8. A Lean character (base + 4) ≈ $0.09 |
| Latency | Base ~17 s; each edit ~8 s |
| Score | **≈ 37 / 40** (S1 4 · S2 4 · S3 5 · S4 4 · S5 5 · S6 5×2 · S7 5) |

**What works**
- **Identity across edits (S6).** Only the face changes; hair, outfit, crop and background stay almost pixel-identical. The 300 ms emotion crossfade will read as a change of expression, not a jump.
- **The blink frame lines up**, so it passes the alignment check for the exhausted portrait (D-56).
- **The background is plain**, and there are no hands.
- **Rin's adult read (S5)** passes.

**Prompt fixes for the compiler (v2)**
1. **Neutral reads cool and aloof** for a warm character. Use `Appearance.baselineExpression`: soft → "gentle relaxed expression with a faint warm smile", neutral → as-is, sharp → "composed, slightly intense gaze".
2. **Thinking reads as suspicious.** Use: "eyes looking up and to the side, brows relaxed with one slightly raised, curious pondering look".
3. **Angry has a blush** and drifts toward embarrassed. Drop "faint flush" from angry; blush is for embarrassed only.
4. **Compound hair colours lose their base colour** ("pink-tinted chestnut" came out salmon pink). Put the base colour first: "chestnut-brown hair with a soft pink tint".
5. **Sad added small tears** despite the instruction. Acceptable; keep it.

**Still to verify before the Seed Asset Sprint** (≈ $0.40):
- Hana v2, to confirm the fixes;
- **Amara**: dark skin must not be lightened (fairness check);
- **Rin**: adult read;
- **Victor**: fine detail.

The last three need only the base plus angry, embarrassed and blink.

## Re-running

```
cp docs/ai/image-model-test/.env.example docs/ai/image-model-test/.env   # add the key; .env is gitignored
node docs/ai/image-model-test/run.mjs --dry-run                          # prompts only, no calls
node docs/ai/image-model-test/run.mjs [--model …] [--emotions a,b] [--budget 0.60] [--base neutral.png]
```

The script has no dependencies and never prints the key. It stops before it would exceed `--budget`, using `usage.cost`. Output goes to `output/` (gitignored); copy a run worth keeping next to this README.

## Models ruled out

**Recraft V4 / V4 Styles / V4.1:**
- they have only strength-based image-to-image (the whole image is redrawn);
- they have no inpainting (V3 only) and no instruction edits;
- so they can't keep a face across emotions. At most they could draw a base portrait for a hybrid setup, which we don't need.

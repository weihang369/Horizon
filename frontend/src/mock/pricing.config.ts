// Mock pricing table (CHR-13 / doc 06 §8, chat prices from doc 05 §8). The seed build writes it to seed/pricing.json.
// Image prices: Seedream 5.0 Flash (D-61). Jev: $0.042/M input, output free (D-66). Embedding: Qwen3 Embedding 8B (D-64).
import type { PricingTable } from "../domain/cost";

const SEEDREAM_PER_IMAGE = 0.018;

export const PRICING: PricingTable = {
  chat: {
    model: "deepseek/deepseek-v4.1-flash", provider: "DeepSeek",
    inputPerM: 0.15, cachedInputPerM: 0.003, outputPerM: 0.6,
  },
  decision: {
    model: "typesafe/jev-1.13", provider: "TypeSafe",
    inputPerM: 0.042, cachedInputPerM: 0.042, outputPerM: 0,
  },
  embedding: {
    model: "qwen/qwen3-embedding-8b", provider: "Nebius",
    inputPerM: 0.01,
  },
  generation: {
    portrait: SEEDREAM_PER_IMAGE,
    emotionEdit: SEEDREAM_PER_IMAGE,
    tweak: SEEDREAM_PER_IMAGE,
    expressionSheet: SEEDREAM_PER_IMAGE,
    song: 0.04,
    profileDraft: 0.002,
    blinkFrame: SEEDREAM_PER_IMAGE,
  },
  // DeepSeek first-party peak (R-23, D-41): Mon–Fri 09:00–12:00 and 14:00–18:00 Malaysia time, ×2. Same as rushHour.ts.
  peak: { multiplier: 2, tz: "Asia/Kuala_Lumpur", windows: [[540, 720], [840, 1080]] },
  // Backend gateway (doc backend/04 §1, NFR-33, D-80): pinned routing for the main LLM, per-purpose timeouts, embedding batches.
  gateway: {
    routing: {
      order: ["DeepSeek"], require_parameters: true, allow_fallbacks: true,
      quantizations: ["bf16", "fp16", "fp32", "unknown"], data_collection: "allow", // D-80
    },
    // No fallback model (docs/ai/03 C8): V4.1 Flash only; provider fallback stays (`allow_fallbacks`).
    embeddingProvider: "Nebius",
    embedBatch: 32,
    timeoutsMs: {
      chatFirstToken: 20_000, chatIdle: 30_000, image: 180_000, music: 120_000, embedding: 30_000, meta: 10_000,
      episode: 30_000, // M10 (group-watch D19): the watch recap, one non-streamed call
      verdict: 30_000, // M11 (debate D13): the verdict's prose, one non-streamed JSON call, the whole call
      // Jev deadlines (docs/ai/13 W12, measured by group A A2 from Malaysia: Jev ≈ 420 ms p50 / 500 p99).
      decision: {
        route: 400, turn_plan: 700, follow_plan: 483, debate_plan: 651, guardrail: 700, guardrail_prompt: 1_500,
        reaction: 1_500, face_check: 1_500, default: 3_000,
        rubric: 10_000, // M11 (debate D12): a background purpose; a fallback costs the whole score
        importance: 30_000, // M13 (memory D14): a background purpose; doc 09 M13 bounds only the run
        memory_guard: 30_000, // M13 (memory D15)
      },
    },
  },
};

export const MODELS = {
  chat: PRICING.chat.model,
  decision: PRICING.decision.model,
  image: "bytedance-seed/seedream-5-0-flash",
  music: "google/lyria-3-clip-preview", // D-87: OpenRouter lists the -preview ID
  embedding: PRICING.embedding.model,
};

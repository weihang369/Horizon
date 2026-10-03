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
};

export const MODELS = {
  chat: PRICING.chat.model,
  decision: PRICING.decision.model,
  image: "bytedance-seed/seedream-5-0-flash",
  music: "google/lyria-3-clip",
  embedding: PRICING.embedding.model,
};

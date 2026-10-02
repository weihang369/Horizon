// Mock pricing table (CHR-13 / doc 06 §8, chat prices from doc 05 §8). The seed build writes it to seed/pricing.json.
import type { PricingTable } from "../domain/cost";

export const PRICING: PricingTable = {
  chat: {
    model: "deepseek/deepseek-v4.1-flash", provider: "DeepSeek",
    inputPerM: 0.15, cachedInputPerM: 0.003, outputPerM: 0.6,
  },
  decision: {
    model: "typesafe/jev-1.13", provider: "TypeSafe",
    inputPerM: 0.02, cachedInputPerM: 0.002, outputPerM: 0.02,
  },
  generation: {
    portrait: 0.036,
    emotionEdit: 0.039,
    tweak: 0.039,
    expressionSheet: 0.04,
    song: 0.04,
    profileDraft: 0.002,
    blinkFrame: 0.039,
  },
};

export const MODELS = {
  chat: PRICING.chat.model,
  decision: PRICING.decision.model,
  image: "qwen/qwen-image-3",
  music: "google/lyria-3-clip",
};

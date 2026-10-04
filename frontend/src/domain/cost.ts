// Chat/generation cost maths (doc 05 §8 worked example, doc 06 §8 mock pricing table).
import type { PricePeriod } from "./rushHour";
import { periodMultiplier } from "./rushHour";
import { pointsForCost, USD_PER_POINT } from "./energy";

export interface ChatPrice {
  model: string; provider: string;
  /** USD per million tokens, off-peak. Peak = × 2. */
  inputPerM: number; cachedInputPerM: number; outputPerM: number;
}

export interface GenerationPrices {
  portrait: number; emotionEdit: number; tweak: number; expressionSheet: number; song: number; profileDraft: number;
  blinkFrame: number;
}

/** rev 1.3: embeddings bill input tokens only (D-64). */
export interface EmbeddingPrice { model: string; provider: string; inputPerM: number }

/** DeepSeek peak pricing (R-23, ENG-06): windows are [start, end) minutes of the day in `tz`, Mon–Fri. */
export interface PeakConfig { multiplier: number; tz: string; windows: [number, number][] }

/** Backend-only gateway config (doc backend/04 §1): pinned routing, timeouts, embedding batching. The mock ignores it. */
export interface GatewayConfig {
  routing: {
    order: string[]; require_parameters: boolean; allow_fallbacks: boolean;
    quantizations: string[]; data_collection: "allow" | "deny";
  };
  fallbackModel: string;
  embeddingProvider: string;
  embedBatch: number;
  timeoutsMs: {
    chatFirstToken: number; chatIdle: number; image: number; embedding: number; meta: number;
    decision: { route: number; gate: number; rerank: number; emotion: number; default: number };
  };
}

export interface PricingTable {
  chat: ChatPrice;
  decision: ChatPrice;
  embedding: EmbeddingPrice;
  generation: GenerationPrices;
  /** M2 additive: read by the backend's pricing clock and estimates. */
  peak?: PeakConfig;
  /** M2 additive: read by the backend gateway only. */
  gateway?: GatewayConfig;
}

/** Typical Jev routing question size (state + one choice question). Output is free (D-66). */
export const ROUTE_DECISION_TOKENS = 600;

/** Cost of one Jev decision call: input tokens only (no output charge, no peak multiplier). */
export function decisionCostUsd(tokensIn: number, price: ChatPrice): number {
  return round6((tokensIn * price.inputPerM) / 1e6);
}

/** Cost of embedding `tokens` input tokens (no output, no peak multiplier). */
export function embeddingCostUsd(tokens: number, price: EmbeddingPrice): number {
  return round6((tokens * price.inputPerM) / 1e6);
}

export interface TokenUsage { tokensIn: number; tokensCached?: number; tokensOut: number }

/** Cost of one chat call. Uncached input = tokensIn − tokensCached. */
export function chatCostUsd(u: TokenUsage, price: ChatPrice, period: PricePeriod = "off_peak"): number {
  const cached = u.tokensCached ?? 0;
  const uncached = Math.max(0, u.tokensIn - cached);
  const raw = (uncached * price.inputPerM + cached * price.cachedInputPerM + u.tokensOut * price.outputPerM) / 1e6;
  return round6(raw * periodMultiplier(period));
}

export function chatEnergy(u: TokenUsage, price: ChatPrice, period: PricePeriod = "off_peak", usdPerPoint = USD_PER_POINT): number {
  return pointsForCost(chatCostUsd(u, price, period), usdPerPoint);
}

export const round6 = (n: number) => Math.round(n * 1e6) / 1e6;

/** Rough token estimate for mock text (≈ 4 chars per token). */
export const estimateTokens = (text: string): number => Math.max(1, Math.round(text.length / 4));

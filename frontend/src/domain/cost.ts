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

export interface PricingTable {
  chat: ChatPrice;
  decision: ChatPrice;
  generation: GenerationPrices;
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

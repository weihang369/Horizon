// O26's "Go to verdict now (≈ $x)" estimate (MULTI-07 AC4), kept out of EndDebate.tsx so that file only exports
// components (fast refresh).
import { chatCostUsd, decisionCostUsd } from "../../domain/cost";
import { PRICING } from "../../mock/pricing.config";
import type { PricingTable } from "../../domain/cost";
import type { PricePeriod } from "../../domain/rushHour";

/** M11 (debate D16): one estimate for the dearer of the real verdicts, `agent`'s: Jev's rubric scores (≈ 6,000 tokens on
 *  the decision price, no peak multiplier) plus DeepSeek's prose (≈ 6,000 in and 300 out on the chat price, which the
 *  peak multiplier raises). `naive`'s single call is about $0.0011, so "≈" holds for both. */
export const VERDICT_JEV_TOKENS = 6000;
export const VERDICT_PROSE = { tokensIn: 6000, tokensOut: 300 };

export function verdictEstimateUsd(period: PricePeriod, pricing: PricingTable = PRICING): number {
  return decisionCostUsd(VERDICT_JEV_TOKENS, pricing.decision) + chatCostUsd(VERDICT_PROSE, pricing.chat, period);
}

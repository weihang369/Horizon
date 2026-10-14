// M11 (debate D16; debate-verdict "Peak prices the prose higher"): the early-end estimate follows the price table and
// the period, with the peak multiplier on the DeepSeek part only.
import { describe, expect, it } from "vitest";
import { chatCostUsd, decisionCostUsd } from "../../domain/cost";
import { PRICING } from "../../mock/pricing.config";
import { VERDICT_JEV_TOKENS, VERDICT_PROSE, verdictEstimateUsd } from "./verdictEstimate";

describe("the early-end verdict estimate", () => {
  it("is Jev's part plus the prose's, the prose priced by the period", () => {
    const jev = decisionCostUsd(VERDICT_JEV_TOKENS, PRICING.decision);
    expect(verdictEstimateUsd("off_peak")).toBeCloseTo(jev + chatCostUsd(VERDICT_PROSE, PRICING.chat, "off_peak"), 9);
    expect(verdictEstimateUsd("peak")).toBeCloseTo(jev + chatCostUsd(VERDICT_PROSE, PRICING.chat, "peak"), 9);
    expect(verdictEstimateUsd("peak") - verdictEstimateUsd("off_peak")).toBeCloseTo(
      chatCostUsd(VERDICT_PROSE, PRICING.chat, "peak") - chatCostUsd(VERDICT_PROSE, PRICING.chat, "off_peak"), 9);
  });

  it("reads about $0.0014 off-peak and $0.0026 at peak (D16's rounded figures, within 10 %)", () => {
    expect(Math.abs(verdictEstimateUsd("off_peak") / 0.0014 - 1)).toBeLessThan(0.1);
    expect(Math.abs(verdictEstimateUsd("peak") / 0.0026 - 1)).toBeLessThan(0.1);
  });
});

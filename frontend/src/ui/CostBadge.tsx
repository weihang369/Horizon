import s from "./Tags.module.css";
import { cx } from "./cx";

import { formatUsd } from "../domain/format";

export { formatUsd };

export interface CostBadgeProps {
  usd: number;
  /** Prefix with ≈ (estimates). Default true. */
  approx?: boolean;
  tone?: "ink" | "paper" | "brand";
  className?: string;
}

/** `≈ $0.04` (CHR-13). */
export function CostBadge({ usd, approx = true, tone = "ink", className }: CostBadgeProps) {
  const text = `${approx ? "≈ " : ""}${formatUsd(usd)}`;
  return (
    <span className={cx(s.cost, s[`cost_${tone}`], className)} aria-label={`${approx ? "about " : ""}${formatUsd(usd)}`}>
      {text}
    </span>
  );
}

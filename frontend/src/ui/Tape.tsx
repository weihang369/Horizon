import type { HTMLAttributes, ReactNode } from "react";
import s from "./Tags.module.css";
import { cx } from "./cx";

export type TapeTone = "brand" | "primary" | "ink" | "paper" | "ok" | "warn" | "error" | "prop" | "opp";

export interface TapeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: TapeTone;
  size?: "sm" | "md" | "lg";
  /** Extra rotation in degrees (e.g. −3). */
  rotate?: number;
  children: ReactNode;
}

/** Skewed tape label. Text on brand/signal tapes is always ink (NFR-18). PROP = brand, OPP = paper (R9). */
export function Tape({ tone = "brand", size = "md", rotate, className, style, children, ...rest }: TapeProps) {
  return (
    <span
      className={cx(s.tape, s[`tape_${tone}`], s[`tape_${size}`], className)}
      style={rotate ? { ...style, transform: `rotate(${rotate}deg)` } : style}
      {...rest}
    >
      <span className={s.tapeText}>{children}</span>
    </span>
  );
}

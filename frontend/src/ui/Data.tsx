// ProbBar, StackedBar, Skeleton, ScanLoader, HalftoneDevelop, Tooltip (spec §3.7). Owner: VMD.
import {
  cloneElement, isValidElement, useId, useState,
  type CSSProperties, type ReactElement, type ReactNode,
} from "react";
import s from "./Data.module.css";
import { cx } from "./cx";
import { Tape } from "./Tape";
import { probBand, type ProbBand } from "../domain/format";

// ── ProbBar ──────────────────────────────────────────────────────────────────
export { probBand, type ProbBand };

export interface ProbBarProps {
  label: ReactNode;
  /** 0..1 */
  p: number;
  /** Fill colour (defaults to --c-primary). */
  color?: string;
  /** Show `FORCED BY YOU` instead of the probability. */
  forced?: boolean;
  className?: string;
}

/** `0.71 · HIGH` probability row (Insight drawer). */
export function ProbBar({ label, p, color, forced, className }: ProbBarProps) {
  const v = Math.max(0, Math.min(1, p));
  const band = probBand(v);
  return (
    <div className={cx(s.prob, className)} role="group">
      <span className={s.probLabel}>{label}</span>
      <span
        className={s.probTrack}
        role="meter"
        aria-valuemin={0}
        aria-valuemax={1}
        aria-valuenow={v}
        aria-valuetext={forced ? "forced by you" : `${v.toFixed(2)}, ${band}`}
      >
        <span className={s.probFill} style={{ "--p": forced ? 1 : v, "--prob-c": color } as CSSProperties} />
      </span>
      <span className={s.probValue}>
        {forced ? (
          <Tape tone="brand" size="sm" className={s.forced}>
            Forced by you
          </Tape>
        ) : (
          <>
            {v.toFixed(2)} · <span className={cx(s.band, s[`band_${band}`])}>{band}</span>
          </>
        )}
      </span>
    </div>
  );
}

// ── StackedBar ───────────────────────────────────────────────────────────────
export interface StackedSegment {
  key: string;
  label: string;
  value: number;
  color: string;
}

export interface StackedBarProps {
  segments: StackedSegment[];
  /** Total capacity (e.g. context budget). Defaults to the sum. */
  total?: number;
  /** Value formatter for the legend (default: thousands → `1.2K`). */
  format?: (n: number) => string;
  label: string;
  className?: string;
}

const kfmt = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}K` : String(Math.round(n)));

/** One horizontal stacked bar (context budget: system / persona / memory / knowledge / history / user / mode). */
export function StackedBar({ segments, total, format = kfmt, label, className }: StackedBarProps) {
  const sum = segments.reduce((a, b) => a + b.value, 0);
  const cap = Math.max(total ?? sum, 1);
  const summary = segments.map((x) => `${x.label} ${format(x.value)}`).join(", ");
  return (
    <div className={cx(s.stack, className)}>
      <div className={s.stackBar} role="img" aria-label={`${label}: ${summary}; ${format(sum)} of ${format(cap)}`}>
        {segments.map((x) => (
          <span key={x.key} className={s.seg} style={{ width: `${(x.value / cap) * 100}%`, background: x.color }} />
        ))}
      </div>
      <ul className={s.legend} aria-hidden="true">
        {segments.map((x) => (
          <li key={x.key}>
            <i style={{ background: x.color }} />
            {x.label} <b>{format(x.value)}</b>
          </li>
        ))}
        <li className={s.stackMeta}>
          {format(sum)} / {format(cap)}
        </li>
      </ul>
    </div>
  );
}

// ── Skeleton & loaders (no spinners) ─────────────────────────────────────────
export interface SkeletonProps {
  lines?: number;
  /** Width per line (CSS); cycles if shorter than lines. */
  widths?: string[];
  height?: number;
  className?: string;
  label?: string;
}

export function Skeleton({ lines = 3, widths = ["100%", "92%", "64%"], height = 14, className, label = "Loading" }: SkeletonProps) {
  return (
    <div className={cx(s.skeleton, className)} role="status" aria-label={label}>
      {Array.from({ length: lines }, (_, i) => (
        <span key={i} className={s.skelLine} style={{ width: widths[i % widths.length], "--skel-h": `${height}px` } as CSSProperties} />
      ))}
    </div>
  );
}

/** Scanning stripe loader with an optional caption. */
export function ScanLoader({ label, width = 160 }: { label?: ReactNode; width?: number }) {
  return (
    <span className={s.scanWrap} role="status">
      <span className={s.scan} style={{ "--scan-w": `${width}px` } as CSSProperties} aria-hidden="true" />
      {label ? <span>{label}</span> : <span className="sr-only">Loading</span>}
    </span>
  );
}

/** Halftone "develop" loader: an area of palette dots that slowly develops (portraits generating). */
export function HalftoneDevelop({ label, className, style }: { label?: ReactNode; className?: string; style?: CSSProperties }) {
  return (
    <div className={cx(s.develop, className)} style={style} role="status">
      <span className={s.developDots} aria-hidden="true" />
      <span className={cx(s.developDots, s.developDots2)} aria-hidden="true" />
      {label ? (
        <Tape tone="ink" size="sm" className={s.developLabel}>
          {label}
        </Tape>
      ) : (
        <span className="sr-only">Generating</span>
      )}
    </div>
  );
}

// ── Tooltip ──────────────────────────────────────────────────────────────────
export interface TooltipProps {
  content: ReactNode;
  placement?: "top" | "bottom";
  children: ReactElement<{ "aria-describedby"?: string }>;
}

/** Hover/focus tooltip. The child gets aria-describedby. */
export function Tooltip({ content, placement = "top", children }: TooltipProps) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const child = isValidElement(children) ? cloneElement(children, { "aria-describedby": open ? id : undefined }) : children;
  return (
    <span
      className={s.tipWrap}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocusCapture={() => setOpen(true)}
      onBlurCapture={() => setOpen(false)}
      onKeyDown={(e) => e.key === "Escape" && open && (e.stopPropagation(), setOpen(false))}
    >
      {child}
      {open && (
        <span role="tooltip" id={id} className={cx(s.tip, placement === "bottom" && s.tip_bottom)}>
          {content}
        </span>
      )}
    </span>
  );
}

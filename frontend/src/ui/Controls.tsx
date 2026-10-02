// Chip, ChipGroup, Tabs, Toggle, Segmented, Slider, Swatch (spec §3.7). Owner: VMD.
import { useId, useRef, type ButtonHTMLAttributes, type CSSProperties, type KeyboardEvent, type ReactNode } from "react";
import type { Palette } from "../contract/types";
import s from "./Controls.module.css";
import { cx } from "./cx";
import { Tape } from "./Tape";

// ── Chip ─────────────────────────────────────────────────────────────────────
export interface ChipProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  selected?: boolean;
  size?: "sm" | "md";
  /** Render as radio (single-select groups) instead of a toggle button. */
  radio?: boolean;
  children: ReactNode;
}

export function Chip({ selected = false, size = "md", radio, className, children, type = "button", ...rest }: ChipProps) {
  const a11y = radio ? { role: "radio" as const, "aria-checked": selected } : { "aria-pressed": selected };
  return (
    <button type={type} className={cx(s.chip, size === "sm" && s.chipSm, className)} {...a11y} {...rest}>
      {children}
    </button>
  );
}

export interface ChipOption<V extends string = string> {
  value: V;
  label: ReactNode;
  disabled?: boolean;
}

interface ChipGroupBase<V extends string> {
  label: string;
  /** Visually hide the legend (still announced). */
  hideLabel?: boolean;
  options: ChipOption<V>[];
  size?: "sm" | "md";
  className?: string;
}
export interface ChipGroupSingleProps<V extends string> extends ChipGroupBase<V> {
  multiple?: false;
  value: V | null;
  onChange: (value: V) => void;
}
export interface ChipGroupMultiProps<V extends string> extends ChipGroupBase<V> {
  multiple: true;
  value: V[];
  /** Max selections (e.g. accessories ≤ 3). Further chips disable. */
  max?: number;
  onChange: (value: V[]) => void;
}
export type ChipGroupProps<V extends string> = ChipGroupSingleProps<V> | ChipGroupMultiProps<V>;

export function ChipGroup<V extends string>(props: ChipGroupProps<V>) {
  const { label, hideLabel, options, size, className } = props;
  const ref = useRef<HTMLDivElement>(null);
  const onKey = (e: KeyboardEvent) => {
    if (props.multiple) return;
    if (!["ArrowRight", "ArrowLeft", "ArrowDown", "ArrowUp"].includes(e.key)) return;
    const btns = [...(ref.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)") ?? [])];
    const i = btns.indexOf(document.activeElement as HTMLButtonElement);
    if (i < 0) return;
    e.preventDefault();
    const next = btns[(i + (e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : btns.length - 1)) % btns.length];
    next.focus();
    next.click();
  };
  const count = props.multiple ? props.value.length : 0;
  return (
    <div
      ref={ref}
      role={props.multiple ? "group" : "radiogroup"}
      aria-label={label}
      className={className}
      onKeyDown={onKey}
    >
      <div className={cx(s.groupLegend, hideLabel && "sr-only")}>
        {label}
        {props.multiple && props.max !== undefined && (
          <span className={s.chipCount}>
            {count}/{props.max}
          </span>
        )}
      </div>
      <div className={s.chipGroup}>
        {options.map((o) => {
          if (props.multiple) {
            const on = props.value.includes(o.value);
            const full = props.max !== undefined && count >= props.max && !on;
            return (
              <Chip
                key={o.value}
                size={size}
                selected={on}
                disabled={o.disabled || full}
                onClick={() => props.onChange(on ? props.value.filter((v) => v !== o.value) : [...props.value, o.value])}
              >
                {o.label}
              </Chip>
            );
          }
          const on = props.value === o.value;
          return (
            <Chip
              key={o.value}
              radio
              size={size}
              selected={on}
              disabled={o.disabled}
              tabIndex={on || (props.value === null && o === options[0]) ? 0 : -1}
              onClick={() => props.onChange(o.value)}
            >
              {o.label}
            </Chip>
          );
        })}
      </div>
    </div>
  );
}

// ── Tabs ─────────────────────────────────────────────────────────────────────
export interface TabItem<V extends string = string> {
  id: V;
  label: ReactNode;
  badge?: ReactNode;
  disabled?: boolean;
}
export interface TabsProps<V extends string> {
  label: string;
  tabs: TabItem<V>[];
  value: V;
  onChange: (id: V) => void;
  /** Base for ids: tab = `${idBase}-tab-${id}`, panel = `${idBase}-panel-${id}`. */
  idBase?: string;
  className?: string;
}

export function tabIds(idBase: string, id: string) {
  return { tab: `${idBase}-tab-${id}`, panel: `${idBase}-panel-${id}` };
}

/** WAI-ARIA tabs (arrow keys, Home/End). Consumers render panels with role="tabpanel" + tabIds(). */
export function Tabs<V extends string>({ label, tabs, value, onChange, idBase, className }: TabsProps<V>) {
  const auto = useId();
  const base = idBase ?? auto;
  const ref = useRef<HTMLDivElement>(null);
  const onKey = (e: KeyboardEvent) => {
    const enabled = tabs.filter((t) => !t.disabled);
    const i = enabled.findIndex((t) => t.id === value);
    let next: TabItem<V> | undefined;
    if (e.key === "ArrowRight") next = enabled[(i + 1) % enabled.length];
    else if (e.key === "ArrowLeft") next = enabled[(i - 1 + enabled.length) % enabled.length];
    else if (e.key === "Home") next = enabled[0];
    else if (e.key === "End") next = enabled[enabled.length - 1];
    if (!next) return;
    e.preventDefault();
    onChange(next.id);
    ref.current?.querySelector<HTMLButtonElement>(`#${CSS.escape(tabIds(base, next.id).tab)}`)?.focus();
  };
  return (
    <div ref={ref} role="tablist" aria-label={label} className={cx(s.tabs, className)} onKeyDown={onKey}>
      {tabs.map((t) => {
        const ids = tabIds(base, t.id);
        const on = t.id === value;
        return (
          <button
            key={t.id}
            id={ids.tab}
            type="button"
            role="tab"
            aria-selected={on}
            aria-controls={ids.panel}
            tabIndex={on ? 0 : -1}
            disabled={t.disabled}
            className={s.tab}
            onClick={() => onChange(t.id)}
          >
            {t.label}
            {t.badge !== undefined && <span className={s.tabBadge}>{t.badge}</span>}
          </button>
        );
      })}
    </div>
  );
}

// ── Toggle ───────────────────────────────────────────────────────────────────
export interface ToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: ReactNode;
  /** Hide the visible label (aria-label still set when label is a string). */
  hideLabel?: boolean;
  disabled?: boolean;
  className?: string;
}

export function Toggle({ checked, onChange, label, hideLabel, disabled, className }: ToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={hideLabel && typeof label === "string" ? label : undefined}
      disabled={disabled}
      className={cx(s.toggle, className)}
      onClick={() => onChange(!checked)}
    >
      <span className={s.track} aria-hidden="true">
        <span className={s.knob} />
      </span>
      {!hideLabel && <span>{label}</span>}
    </button>
  );
}

// ── Segmented ────────────────────────────────────────────────────────────────
export interface SegmentedProps<V extends string> {
  label: string;
  options: { value: V; label: ReactNode }[];
  value: V;
  onChange: (v: V) => void;
  className?: string;
}

export function Segmented<V extends string>({ label, options, value, onChange, className }: SegmentedProps<V>) {
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const i = options.findIndex((o) => o.value === value);
    const d = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!d) return;
    e.preventDefault();
    const next = options[(i + d + options.length) % options.length];
    onChange(next.value);
    (e.currentTarget.querySelector(`[data-v="${CSS.escape(next.value)}"]`) as HTMLElement | null)?.focus();
  };
  return (
    <div role="radiogroup" aria-label={label} className={cx(s.segmented, className)} onKeyDown={onKey}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          data-v={o.value}
          aria-checked={o.value === value}
          tabIndex={o.value === value ? 0 : -1}
          className={s.segment}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// ── Slider ───────────────────────────────────────────────────────────────────
export interface SliderProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (v: number) => void;
  format?: (v: number) => string;
  disabled?: boolean;
  className?: string;
}

export function Slider({ label, value, min, max, step = 1, onChange, format = String, disabled, className }: SliderProps) {
  const id = useId();
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div className={cx(s.slider, className)}>
      <label htmlFor={id} className={s.sliderLabel}>
        {label}
      </label>
      <output htmlFor={id} className={s.sliderValue}>
        {format(value)}
      </output>
      <input
        id={id}
        type="range"
        className={s.range}
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        aria-valuetext={format(value)}
        style={{ "--fill": `${pct}%` } as CSSProperties}
        onChange={(e) => onChange(Number(e.currentTarget.value))}
      />
    </div>
  );
}

// ── Swatch ───────────────────────────────────────────────────────────────────
export interface SwatchProps {
  palette: Palette;
  selected?: boolean;
  aiPick?: boolean;
  /** Committed pick (plays the flood upstream). Receives the click point. */
  onSelect?: (id: string, point: { x: number; y: number }) => void;
  /** Hover/focus preview (instant swap, no flood — CHR-09 AC2). null = preview ended. */
  onPreview?: (id: string | null) => void;
  className?: string;
}

/** Skewed palette card (CHR-09). Use inside a role="radiogroup". */
export function Swatch({ palette: p, selected, aiPick, onSelect, onPreview, className }: SwatchProps) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={!!selected}
      aria-label={`${p.name}${aiPick ? " (AI pick)" : ""}${p.fit ? `: ${p.fit}` : ""}`}
      className={cx(s.swatch, className)}
      style={{ "--sw-stage": p.stage } as CSSProperties}
      onClick={(e) => onSelect?.(p.id, { x: e.clientX, y: e.clientY })}
      onMouseEnter={() => onPreview?.(p.id)}
      onMouseLeave={() => onPreview?.(null)}
      onFocus={() => onPreview?.(p.id)}
      onBlur={() => onPreview?.(null)}
    >
      {aiPick && (
        <Tape tone="paper" size="sm" className={s.swatchTag}>
          AI pick
        </Tape>
      )}
      <span className={s.swatchFace} aria-hidden="true">
        <i style={{ background: p.primary }} />
        <i style={{ background: p.secondary }} />
        <i style={{ background: p.accent }} />
      </span>
      <span className={s.swatchName}>{p.name}</span>
    </button>
  );
}

// <EnergyBar> (spec §3.5, doc 04 §6.1, VMD §2.2). Owner: VMD.
// characterId → live energy via the EE's useEnergy(); energy → a plain value.
// stage 6 px / chat 10 px. Drain = fighting-game damage ghost (hold 200 ms, collapse 400 ms) + "−N ⚡" float;
// regen = sheen every 2.8 s; top-up = 600 ms fill + 6 sparks; exhausted = .55↔1 pulse.
// All change effects are imperative (WAAPI on refs), so a ticking value never re-renders anything else.
import { useLayoutEffect, useRef, type CSSProperties } from "react";
import type { EnergyState } from "../contract/types";
import { useEnergy } from "@/client/hooks";
import { formatDrain } from "../domain/format";
import { getMotionPrefs } from "../motion/prefs";
import { DUR, EASE } from "../motion/tokens";
import { paletteClass } from "../theme/palettes";
import { BoltIcon } from "../ui/icons";
import { cx } from "../ui/cx";
import s from "./EnergyBar.module.css";

export interface EnergyValue {
  current: number;
  max: number;
  state?: EnergyState;
  fullAt?: string | null;
}

export interface EnergyBarProps {
  characterId?: string;
  energy?: EnergyValue | null;
  size?: "stage" | "chat";
  /** `⚡ 640 / 1000` in mono. Default: on for chat, off for stage. */
  showLabel?: boolean;
  /** Shows a small "+" top-up button (opens O27 upstream). */
  onTopUp?: () => void;
  /** Additive: scope the fill colour to a palette (otherwise inherits the nearest PaletteScope). */
  paletteId?: string | null;
  /** Additive: accessible name prefix, e.g. the character's name. */
  label?: string;
  className?: string;
  style?: CSSProperties;
}

/** With `characterId` the bar is live (useEnergy); `energy`, if also given, is the fallback until the store knows the id. */
export function EnergyBar(props: EnergyBarProps) {
  if (props.characterId) return <LiveEnergyBar {...props} characterId={props.characterId} />;
  return <EnergyBarView {...props} value={props.energy ?? null} />;
}

function LiveEnergyBar(props: EnergyBarProps & { characterId: string }) {
  const live = useEnergy(props.characterId);
  return <EnergyBarView {...props} value={live ?? props.energy ?? null} />;
}

const TOPUP_MIN_FRAC = 0.04;

function EnergyBarView({
  value, size = "chat", showLabel, onTopUp, paletteId, label, className, style,
}: EnergyBarProps & { value: EnergyValue | null }) {
  const fill = useRef<HTMLSpanElement>(null);
  const ghost = useRef<HTMLSpanElement>(null);
  const fx = useRef<HTMLSpanElement>(null);
  const prev = useRef<number | null>(null);

  const max = Math.max(1, value?.max ?? 1);
  const cur = Math.max(0, Math.min(max, value?.current ?? 0));
  const pct = cur / max;
  const state: EnergyState = value?.state ?? (cur <= 0 ? "exhausted" : pct < 0.2 ? "tired" : "active");
  const tone = pct < 0.2 ? "red" : pct < 0.4 ? "amber" : "ok";
  const regen = !!value && cur < max && state !== "exhausted";
  const labelOn = showLabel ?? size === "chat";

  useLayoutEffect(() => {
    const was = prev.current;
    prev.current = cur;
    const f = fill.current;
    if (!f) return;
    const reduced = getMotionPrefs().reduced;
    if (was === null || was === cur || reduced) {
      f.style.transition = reduced && was !== null ? `transform ${DUR.reduced}ms linear` : "none";
      f.style.transform = `scaleX(${pct})`;
      return;
    }
    const wasPct = was / max;
    const delta = cur - was;
    if (delta < 0) {
      // Drain: fill snaps down, the paper ghost holds 200 ms then collapses over 400 ms.
      f.style.transition = `transform ${DUR.base}ms ${EASE.out}`;
      f.style.transform = `scaleX(${pct})`;
      ghost.current?.animate(
        [
          { transform: `scaleX(${wasPct})`, opacity: 0.6 },
          { transform: `scaleX(${wasPct})`, opacity: 0.6, offset: 1 / 3 },
          { transform: `scaleX(${pct})`, opacity: 0.6 },
        ],
        { duration: 600, easing: EASE.in, fill: "none" },
      );
      floatText(fx.current, formatDrain(Math.round(-delta)), pct);
    } else if (delta >= max * TOPUP_MIN_FRAC) {
      // Top-up: 600 ms fill + 6 sparks along the new length.
      f.style.transition = `transform 600ms ${EASE.out}`;
      f.style.transform = `scaleX(${pct})`;
      sparks(fx.current, wasPct, pct);
    } else {
      // Regen tick: glide.
      f.style.transition = `transform ${DUR.slow}ms ${EASE.out}`;
      f.style.transform = `scaleX(${pct})`;
    }
  }, [cur, max, pct]);

  const aria = `${label ? `${label} energy` : "Energy"} ${Math.floor(cur)} of ${max}${state !== "active" ? `, ${state}` : ""}`;
  return (
    <div
      className={cx(
        s.root, s[size], s[`tone_${tone}`], state === "exhausted" && s.exhausted,
        paletteId !== undefined && paletteClass(paletteId), className,
      )}
      style={style}
      data-energy-state={state}
    >
      <span className={s.track} role="meter" aria-label={aria} aria-valuemin={0} aria-valuemax={max} aria-valuenow={Math.floor(cur)}>
        <span ref={ghost} className={s.ghost} />
        <span ref={fill} className={s.fill} style={{ transform: `scaleX(${pct})` }}>
          {regen && <span className={s.sheen} />}
        </span>
        <span className={s.notches} />
      </span>
      {(labelOn || onTopUp) && (
        <span className={s.meta}>
          {labelOn && (
            <span className={s.label}>
              <BoltIcon width={11} height={11} />
              {Math.floor(cur)} / {max}
            </span>
          )}
          {onTopUp && (
            <button type="button" className={s.topup} onClick={onTopUp} aria-label="Top up energy">
              +
            </button>
          )}
        </span>
      )}
      <span ref={fx} className={s.fx} aria-hidden="true" />
    </div>
  );
}

function floatText(host: HTMLElement | null, text: string, atPct: number): void {
  if (!host) return;
  const el = document.createElement("span");
  el.className = s.float;
  el.textContent = text;
  el.style.left = `${Math.max(4, Math.min(92, atPct * 100))}%`;
  host.appendChild(el);
  const a = el.animate(
    [
      { opacity: 0, transform: "translate(-50%, 4px)" },
      { opacity: 1, transform: "translate(-50%, -2px)", offset: 0.12 },
      { opacity: 1, transform: "translate(-50%, -10px)", offset: 0.6 },
      { opacity: 0, transform: "translate(-50%, -18px)" },
    ],
    { duration: 1000, easing: "linear", fill: "both" },
  );
  a.onfinish = () => el.remove();
}

function sparks(host: HTMLElement | null, fromPct: number, toPct: number): void {
  if (!host) return;
  for (let i = 0; i < 6; i++) {
    const el = document.createElement("span");
    el.className = s.spark;
    const at = fromPct + ((toPct - fromPct) * (i + 0.5)) / 6;
    el.style.left = `${at * 100}%`;
    host.appendChild(el);
    const dx = (i % 2 ? 1 : -1) * (4 + i * 2);
    const a = el.animate(
      [
        { opacity: 0, transform: "translate(-50%, 0) scale(0.4) rotate(45deg)" },
        { opacity: 1, transform: `translate(calc(-50% + ${dx * 0.4}px), -6px) scale(1) rotate(45deg)`, offset: 0.3 },
        { opacity: 0, transform: `translate(calc(-50% + ${dx}px), -16px) scale(0.6) rotate(45deg)` },
      ],
      { duration: 600, delay: i * 60, easing: EASE.out, fill: "both" },
    );
    a.onfinish = () => el.remove();
  }
}

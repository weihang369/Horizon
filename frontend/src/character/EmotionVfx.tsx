// <EmotionVfx> (spec §3.5, VMD paper §2.5). Owner: VMD.
// An overlay box the size of the portrait card. DOM/SVG layers do shaped effects (vignette, ring, vein,
// "!" burst, thought bubble, blush hatch, edge glow); a bleeding canvas does particles on the global ticker.
// intensity: full · subtle (half the particles, no shake) · off (static badges only, R19).
// Reduced motion behaves as "off". `mini` = half-scale one-shot only (listener reactions).
import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import type { Emotion, EnergyState } from "../contract/types";
import { effectiveVfx, useMotionPrefs, type VfxIntensity } from "../motion/prefs";
import { playOneShot, startLoop, type CardBox, type VfxRun } from "../vfx/emotionPresets";
import { ParticleCanvas } from "../vfx/particles/ParticleCanvas";
import type { ParticleField } from "../vfx/particles/engine";
import { cx } from "../ui/cx";
import { emotionMeta } from "./emotionMeta";
import s from "./EmotionVfx.module.css";

export interface EmotionVfxProps {
  emotion: Emotion;
  /** Previous emotion: when it differs from `emotion` on mount, the one-shot plays immediately. */
  prev?: Emotion | null;
  /** Defaults to the user's display prefs. */
  intensity?: VfxIntensity;
  /** Half-scale, one-shot only (listener reactions). */
  mini?: boolean;
  /** Additive: energy-state loops (tired yawn, exhausted Zzz) and static badges. */
  energyState?: EnergyState;
  /** Additive: change to replay the one-shot without an emotion change. */
  playKey?: string | number;
  /** Additive: disable loops (one-shots only). Default: loops on unless mini. */
  loops?: boolean;
  className?: string;
  style?: CSSProperties;
}

const BLEED_X = 0.35;
const BLEED_Y = 0.25;
const SHOT_MS = 1200;

export function EmotionVfx({
  emotion, prev, intensity, mini = false, energyState = "active", playKey, loops, className, style,
}: EmotionVfxProps) {
  const prefs = useMotionPrefs();
  const level: VfxIntensity = prefs.reduced ? "off" : intensity ?? effectiveVfx(prefs);
  const animated = level !== "off";
  const withLoops = (loops ?? !mini) && animated;
  const field = useRef<ParticleField | null>(null);
  const [fieldReady, setFieldReady] = useState(0);
  const [shot, setShot] = useState<{ emotion: Emotion; key: number } | null>(null);
  const last = useRef<{ emotion: Emotion; playKey: typeof playKey }>({ emotion: prev ?? emotion, playKey });
  const shotSeq = useRef(0);
  const pending = useRef<Emotion | null>(null);

  const onField = useCallback((f: ParticleField | null) => {
    field.current = f;
    if (f) setFieldReady((n) => n + 1);
  }, []);

  const run = (): VfxRun | null => {
    const f = field.current;
    if (!f) return null;
    if (f.width < 2) f.resize();
    const box: CardBox = {
      x: (f.width * BLEED_X) / (1 + 2 * BLEED_X),
      y: (f.height * BLEED_Y) / (1 + 2 * BLEED_Y),
      w: f.width / (1 + 2 * BLEED_X),
      h: f.height / (1 + 2 * BLEED_Y),
    };
    return { field: f, box, scale: mini ? 0.5 : 1, density: level === "subtle" ? 0.5 : 1 };
  };

  // One-shot on emotion change (or playKey change).
  useEffect(() => {
    const changed = last.current.emotion !== emotion || last.current.playKey !== playKey;
    last.current = { emotion, playKey };
    if (!changed || !animated || emotion === "neutral") return;
    pending.current = emotion; // the canvas may mount for this shot; it fires once the field exists
    const key = ++shotSeq.current;
    setShot({ emotion, key });
    const t = window.setTimeout(() => setShot((cur) => (cur?.key === key ? null : cur)), SHOT_MS);
    return () => window.clearTimeout(t);
  }, [emotion, playKey, animated]);

  useEffect(() => {
    const e = pending.current;
    if (!e) return;
    const r = run();
    if (!r) return;
    pending.current = null;
    playOneShot(emotionMeta[e].vfx, r);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shot?.key, fieldReady]);

  // Loops (canvas half).
  useEffect(() => {
    if (!withLoops) return;
    const r = run();
    if (!r) return;
    const stops: (() => void)[] = [];
    if (energyState === "exhausted") stops.push(startLoop("sleep", r));
    else {
      if (energyState === "tired") stops.push(startLoop("yawn", r));
      const v = emotionMeta[emotion].vfx;
      if (v === "sparkle" || v === "rain") stops.push(startLoop(v, r));
    }
    return () => stops.forEach((x) => x());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [emotion, energyState, withLoops, level, mini, fieldReady]);

  const asleep = energyState === "exhausted";
  const loopEmotion = withLoops && !asleep ? emotion : null;
  const blush = !mini && !asleep && emotion === "embarrassed"; // held blush stays even when VFX are off (R19)
  const shotE = animated ? shot?.emotion : undefined;
  // Mount the canvas only while something needs it (idle cards hold no backing store).
  const loopNeedsCanvas =
    withLoops && (asleep || energyState === "tired" || emotionMeta[emotion].vfx === "sparkle" || emotionMeta[emotion].vfx === "rain");
  const canvasOn = animated && (loopNeedsCanvas || !!shot);

  return (
    <div
      className={cx(s.root, mini && s.mini, level === "subtle" && s.subtle, className)}
      style={style}
      aria-hidden="true"
      data-emotion={emotion}
      data-vfx={level}
    >
      {loopEmotion === "sad" && <div className={s.vignette} />}
      {loopEmotion === "angry" && <div className={s.edge} />}
      {blush && (
        <div className={cx(s.blush, !animated && s.static)}>
          <Hatch className={s.hatchL} />
          <Hatch className={s.hatchR} />
        </div>
      )}
      {shotE === "angry" && <Vein key={`v${shot?.key}`} />}
      {shotE === "surprised" && <Burst key={`b${shot?.key}`} />}
      {shotE === "sad" && mini && <div key={`s${shot?.key}`} className={cx(s.vignette, s.vignetteShot)} />}
      {(loopEmotion === "thinking" || (mini && shotE === "thinking")) && <Bubble key={mini ? `t${shot?.key}` : "t"} />}
      {!mini && asleep && <span className={s.badge}>Zzz</span>}
      {!mini && !asleep && energyState === "tired" && !animated && <span className={cx(s.badge, s.badgeTired)}>~</span>}
      {canvasOn && <ParticleCanvas onField={onField} className={s.canvas} />}
    </div>
  );
}

function Hatch({ className }: { className: string }) {
  return (
    <svg viewBox="0 0 40 20" className={cx(s.hatch, className)}>
      <path d="M6,17L14,5M16,17L24,5M26,17L34,5" />
    </svg>
  );
}

function Vein() {
  return (
    <svg viewBox="0 0 40 40" className={s.vein}>
      <path d="M15,4Q17,14 5,16M25,4Q23,14 35,16M5,24Q17,26 15,36M35,24Q23,26 25,36" />
    </svg>
  );
}

function Burst() {
  const pts: string[] = [];
  for (let i = 0; i < 24; i++) {
    const r = i % 2 ? 26 : 48;
    const a = (i / 24) * Math.PI * 2 - Math.PI / 2;
    pts.push(`${(50 + Math.cos(a) * r).toFixed(1)},${(50 + Math.sin(a) * r).toFixed(1)}`);
  }
  return (
    <svg viewBox="0 0 100 100" className={s.burst}>
      <polygon points={pts.join(" ")} />
      <text x="50" y="52">!</text>
    </svg>
  );
}

function Bubble() {
  return (
    <div className={s.bubble}>
      <span className={s.trail1} />
      <span className={s.trail2} />
      <span className={s.cloud}>
        <i />
        <i />
        <i />
      </span>
    </div>
  );
}

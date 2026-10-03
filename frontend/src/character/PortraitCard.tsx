// <PortraitCard> (spec §3.5, doc 04 §4, VMD paper §2.2/§2.5). Owner: VMD.
// 3:4 card, clip-path cut corner, 6 px palette frame, misregistered ink block behind, halftone stage.
// Preloads + decode()s every emotion image on mount; crossfades ≤ 300 ms with a 1.02→1 settle.
// Missing emotion art → neutral + VFX + tint (EMO-06). Exhausted → neutral (or blink) + a STATIC greyscale
// duplicate whose opacity fades in (R19). `/placeholder/` art gets the DOM "PLACEHOLDER · EMOTION" tape on the hero size only (R8, D-60).
// Idle life: breathing (4 s), blink (neutral, if the asset exists), cursor parallax on the global ticker.
import {
  useEffect, useLayoutEffect, useMemo, useRef, useState,
  type CSSProperties, type HTMLAttributes, type KeyboardEvent, type MouseEvent,
} from "react";
import type { Character, Emotion, EnergyState } from "../contract/types";
import { EMOTIONS } from "../contract/types";
import { effectiveVfx, useMotionPrefs } from "../motion/prefs";
import { DUR, EASE } from "../motion/tokens";
import { PaletteScope } from "../theme/PaletteScope";
import { cx } from "../ui/cx";
import { registerParallax } from "../vfx/parallax";
import { isPlaceholderUrl, shadowDataUrl, specFromAppearance } from "../vfx/shadow";
import { EmotionVfx } from "./EmotionVfx";
import { EnergyBar, type EnergyValue } from "./EnergyBar";
import { emotionMeta } from "./emotionMeta";
import { NamePlate } from "./NamePlate";
import s from "./PortraitCard.module.css";

export type PortraitSize = "hero" | "stage" | "card" | "thumb" | "head";

/** What the card needs from a Character (a full Character satisfies it; wizard drafts can pass partials). */
export type PortraitCharacter = Pick<Character, "id" | "paletteId" | "emotions"> & {
  profile: Pick<Character["profile"], "name" | "role"> & { title?: string };
  blink?: Character["blink"];
  appearance?: Character["appearance"] | null;
  energy?: EnergyValue;
};

export type PortraitReaction = Emotion | { emotion: Emotion; key: string | number };

export interface PortraitCardProps extends Omit<HTMLAttributes<HTMLDivElement>, "onClick" | "onContextMenu" | "children"> {
  character: PortraitCharacter;
  emotion: Emotion;
  size?: PortraitSize;
  /** Step-forward: scale 1.04 + lit frame (layouts add the 40 px translate toward centre). */
  speaking?: boolean;
  /** Listener: scale .96 under .25 ink. */
  listening?: boolean;
  /** Muted / loser: heavier ink veil. */
  dimmed?: boolean;
  energyState?: EnergyState;
  /** Cursor parallax (6–10 px). Default: on for hero/stage, off for small sizes. Respects prefs. */
  parallax?: boolean;
  /** Mini VFX burst for listener reactions. Use the object form to replay the same emotion. */
  reaction?: PortraitReaction | null;
  showPlate?: boolean;
  showEnergy?: boolean;
  onClick?: (e: MouseEvent<HTMLDivElement>) => void;
  onContextMenu?: (e: MouseEvent<HTMLDivElement>) => void;
  /** Additive: override the card width (px or CSS length). Defaults per size. */
  width?: number | string;
  /** Additive: subtitle for the plate (defaults to role). */
  plateSubtitle?: string | null;
  /** Additive: top-up handler forwarded to the energy bar. */
  onTopUp?: () => void;
}

const DEFAULT_W: Record<PortraitSize, number> = { hero: 520, stage: 280, card: 236, thumb: 96, head: 72 };
const PLATE: Record<PortraitSize, "lg" | "md" | "sm" | null> = { hero: "lg", stage: "md", card: "md", thumb: null, head: null };

// Images already decoded this session (shared across cards).
const decoded = new Set<string>();
function preload(urls: string[]): void {
  for (const u of urls) {
    if (decoded.has(u) || typeof Image === "undefined") continue;
    decoded.add(u);
    const img = new Image();
    img.decoding = "async";
    img.src = u;
    void img.decode?.().catch(() => decoded.delete(u));
  }
}

function hashId(id: string): number {
  let h = 2166136261;
  for (let i = 0; i < id.length; i++) h = Math.imul(h ^ id.charCodeAt(i), 16777619);
  return (h >>> 0) / 4294967295;
}

export function PortraitCard({
  character: c, emotion, size = "card", speaking, listening, dimmed, energyState, parallax, reaction,
  showPlate, showEnergy, onClick, onContextMenu, width, plateSubtitle, onTopUp,
  className, style, onKeyDown, ...rest
}: PortraitCardProps) {
  const prefs = useMotionPrefs();
  const vfx = effectiveVfx(prefs);
  const state: EnergyState = energyState ?? c.energy?.state ?? "active";
  const asleep = state === "exhausted";

  // ── Resolve art ────────────────────────────────────────────────────────────
  const fallback = useMemo(
    () => shadowDataUrl(specFromAppearance(c.appearance ?? null, c.paletteId, "neutral", "unknown", { characterId: c.id })),
    [c.appearance, c.paletteId, c.id],
  );
  const neutralUrl = c.emotions.neutral?.url ?? fallback;
  const blinkUrl = c.blink?.url ?? null;
  const missing = !asleep && emotion !== "neutral" && !c.emotions[emotion];
  const shownEmotion: Emotion = asleep ? "neutral" : emotion;
  const url = asleep ? blinkUrl ?? neutralUrl : c.emotions[emotion]?.url ?? neutralUrl;

  const urls = useMemo(() => {
    const list = EMOTIONS.map((e) => c.emotions[e]?.url).filter((u): u is string => !!u);
    if (!list.includes(neutralUrl)) list.unshift(neutralUrl);
    if (blinkUrl && !list.includes(blinkUrl)) list.push(blinkUrl);
    return list;
  }, [c.emotions, neutralUrl, blinkUrl]);

  useEffect(() => preload(urls), [urls]);

  // ── Crossfade bookkeeping: current on top fading in, previous held underneath ──
  const [layers, setLayers] = useState<{ cur: string; prev: string | null; seq: number }>({ cur: url, prev: null, seq: 0 });
  if (layers.cur !== url) setLayers({ cur: url, prev: layers.cur, seq: layers.seq + 1 });
  useEffect(() => {
    if (!layers.prev) return;
    const t = window.setTimeout(() => setLayers((l) => (l.seq === layers.seq ? { ...l, prev: null } : l)), DUR.swap + 40);
    return () => window.clearTimeout(t);
  }, [layers.seq, layers.prev]);

  // ── Card-level one-shots: settle on every change, shake (angry), jump (surprised) ──
  const settleRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const lastEmotion = useRef(emotion);
  useLayoutEffect(() => {
    if (lastEmotion.current === emotion) return;
    lastEmotion.current = emotion;
    settleRef.current?.animate([{ transform: "scale(1.02)" }, { transform: "scale(1)" }], { duration: DUR.swap, easing: EASE.out });
    if (vfx === "off" || asleep) return;
    const b = bodyRef.current;
    if (!b) return;
    if (emotion === "angry" && vfx === "full") {
      b.animate(
        [{ transform: "translate(6px,-3px)" }, { transform: "translate(-4px,2px)" }, { transform: "translate(0,0)" }],
        { duration: 99, easing: "steps(1, end)", delay: 40 },
      );
    } else if (emotion === "surprised") {
      b.animate(
        [{ transform: "translateY(0)", easing: EASE.out }, { transform: "translateY(-10px)", offset: 0.5, easing: EASE.in }, { transform: "translateY(0)" }],
        { duration: 120 * 2 },
      );
    }
  }, [emotion, vfx, asleep]);

  // ── Parallax (refs + global ticker) ───────────────────────────────────────
  const artRef = useRef<HTMLDivElement>(null);
  const wantParallax = (parallax ?? (size === "hero" || size === "stage")) && prefs.parallax && size !== "head";
  useEffect(() => {
    const el = artRef.current;
    if (!wantParallax || !el) return;
    return registerParallax(el, size === "hero" ? 10 : size === "stage" ? 8 : 6);
  }, [wantParallax, size]);

  // ── Reaction (mini burst) ─────────────────────────────────────────────────
  const react = reaction == null ? null : typeof reaction === "string" ? { emotion: reaction, key: reaction } : reaction;

  const w = width ?? DEFAULT_W[size];
  const plateSize = PLATE[size];
  const name = c.profile.name;
  // D-60: one "placeholder art" note per screen, on the profile hero; stages and cards stay clean for demos.
  const placeholder = isPlaceholderUrl(url) && size === "hero";
  const blinkOn = !!blinkUrl && shownEmotion === "neutral" && !asleep && !prefs.reduced && size !== "head" && size !== "thumb";
  const interactive = !!onClick;
  const delay = useMemo(() => `${(-hashId(c.id) * 5.2).toFixed(2)}s`, [c.id]);

  const handleKey = (e: KeyboardEvent<HTMLDivElement>) => {
    onKeyDown?.(e);
    if (e.defaultPrevented || !interactive) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onClick?.(e as unknown as MouseEvent<HTMLDivElement>);
    }
  };

  const showVfx = size !== "head";
  const label = `${name}, ${asleep ? "asleep" : emotionMeta[shownEmotion].label.toLowerCase()}`;

  return (
    <PaletteScope
      paletteId={c.paletteId}
      className={cx(
        s.root, s[size], speaking && s.speaking, listening && !speaking && s.listening, dimmed && s.dimmed,
        asleep && s.asleep, interactive && s.interactive, className,
      )}
      style={{ ...style, "--pc-w": typeof w === "number" ? `${w}px` : w } as CSSProperties}
    >
      <div
        className={s.pose}
        role={interactive ? "button" : "img"}
        aria-label={label}
        tabIndex={interactive ? 0 : rest.tabIndex}
        onClick={onClick}
        onContextMenu={onContextMenu}
        onKeyDown={handleKey}
        {...rest}
      >
        <div ref={bodyRef} className={s.body}>
          <div className={s.ring} aria-hidden="true" />
          <div className={s.misreg} aria-hidden="true" />
          <div className={s.frame} aria-hidden="true">
            <div className={s.inner}>
              <div className={s.backdrop} />
              <div ref={artRef} className={s.art}>
                <div ref={settleRef} className={s.settle}>
                  <div className={cx(s.breathe, prefs.reduced && s.still)} style={{ animationDelay: delay }}>
                    {urls.map((u) => {
                      const role = u === layers.cur ? "cur" : u === layers.prev ? "prev" : "off";
                      return (
                        <img
                          key={u}
                          src={u}
                          alt=""
                          draggable={false}
                          decoding="async"
                          className={cx(s.layer, s[role])}
                          data-seq={role === "cur" ? layers.seq : undefined}
                        />
                      );
                    })}
                    {blinkOn && <img src={blinkUrl!} alt="" draggable={false} className={cx(s.layer, s.blink)} style={{ animationDelay: delay }} />}
                    <img src={url} alt="" draggable={false} className={cx(s.layer, s.grey, asleep && s.greyOn)} />
                  </div>
                </div>
              </div>
              {missing && <div className={s.tint} style={{ "--tint": emotionMeta[emotion].tint } as CSSProperties} />}
              <div className={s.veil} />
              <div className={s.sheen} />
            </div>
          </div>
          {showVfx && (
            <EmotionVfx
              emotion={shownEmotion}
              energyState={state}
              mini={size === "thumb"}
              loops={size !== "thumb"}
            />
          )}
          {showVfx && react && size !== "thumb" && (
            <EmotionVfx emotion={react.emotion} prev="neutral" playKey={react.key} mini loops={false} />
          )}
          {placeholder && (
            <span className={s.phTape} aria-hidden="true">
              Placeholder · {asleep ? "asleep" : emotionMeta[emotion].label}
            </span>
          )}
        </div>
      </div>
      {(showPlate || showEnergy) && plateSize && (
        <div className={s.footer}>
          {showPlate && (
            <NamePlate
              character={c}
              size={plateSize}
              subtitle={plateSubtitle === undefined ? (asleep ? "Asleep · recharging" : undefined) : plateSubtitle}
            />
          )}
          {showEnergy && (
            <EnergyBar
              characterId={c.id}
              energy={c.energy}
              size={size === "hero" ? "chat" : "stage"}
              showLabel={size === "hero"}
              onTopUp={onTopUp}
              label={name}
              className={s.energy}
            />
          )}
        </div>
      )}
    </PaletteScope>
  );
}

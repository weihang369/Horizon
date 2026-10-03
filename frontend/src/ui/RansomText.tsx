import type { CSSProperties, ElementType } from "react";
import s from "./RansomText.module.css";
import { cx } from "./cx";

export type RansomTone = "mixed" | "ink" | "paper" | "brand";

export interface RansomTextProps {
  text: string;
  /** Font size (px number or any CSS length). Default 48. */
  size?: number | string;
  /** Element to render: h1/h2/span… Default span. */
  as?: ElementType;
  tone?: RansomTone;
  /** Play the tile slam on mount (Banner Slam / title). Reduced motion → fade. */
  slam?: boolean;
  /** Delay before the first tile lands (ms). */
  delayMs?: number;
  /** Per-tile stagger (ms). Default 30 (--stagger-tile). */
  staggerMs?: number;
  className?: string;
  style?: CSSProperties;
}

const FONTS = ["a", "b", "c"] as const;
const ROT = [-6, -3, 2, 5, -4, 3];

function hash(str: string, i: number): number {
  let h = 2166136261 ^ i;
  for (let k = 0; k < str.length; k++) h = Math.imul(h ^ str.charCodeAt(k), 16777619);
  h = Math.imul(h ^ (i * 374761393), 668265263);
  return (h >>> 0) / 4294967295;
}

/**
 * Ransom-note tiles (doc 04 §2): each letter gets a deterministic font, rotation, scale and
 * background from (text, index), so it never jitters on re-render. Titles and banners only.
 */
export function RansomText({
  text, size = 48, as: Tag = "span", tone = "mixed", slam, delayMs = 0, staggerMs = 30, className, style,
}: RansomTextProps) {
  const letters = [...text];
  // Group tiles into words so wrapping only happens between words, never mid-word.
  const words: { ch: string; i: number }[][] = [[]];
  letters.forEach((ch, i) => {
    if (ch === " ") words.push([]);
    else words[words.length - 1].push({ ch, i });
  });
  let tileIndex = 0;
  return (
    <Tag
      className={cx(s.root, slam && s.slam, className)}
      style={{ ...style, fontSize: typeof size === "number" ? `${size}px` : size }}
      aria-label={text}
      role={Tag === "span" ? "text" : undefined}
    >
      {words.filter((w) => w.length).map((w) => (
        <span key={w[0].i} className={s.word} aria-hidden="true">
          {w.map(({ ch, i }) => {
            const r = hash(text, i);
            const font = FONTS[Math.floor(hash(text, i + 101) * 3)];
            const bg =
              tone === "mixed" ? (["ink", "paper", "accent", "ink", "paper"] as const)[Math.floor(r * 5)]
              : tone === "brand" ? (i % 3 === 1 ? "ink" : "brand")
              : tone;
            const rot = ROT[(Math.floor(r * 97) + i) % ROT.length];
            const sc = 0.92 + hash(text, i + 7) * 0.16;
            const idx = tileIndex++;
            return (
              <span
                key={i}
                className={cx(s.tile, s[`f_${font}`], s[`bg_${bg}`])}
                style={{
                  "--r": `${rot}deg`,
                  "--sc": sc.toFixed(3),
                  "--r-from": `${rot * -2.5}deg`,
                  animationDelay: slam ? `${delayMs + idx * staggerMs}ms` : undefined,
                } as CSSProperties}
              >
                {ch}
              </span>
            );
          })}
        </span>
      ))}
    </Tag>
  );
}

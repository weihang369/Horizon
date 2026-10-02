// Canvas parts of the emotion VFX table (VMD paper §2.5, doc 04 §6). Owner: VMD.
// DOM/SVG parts (vignette, ring, vein, "!" burst, bubble, blush hatch, edge glow) live in
// character/EmotionVfx. Positions are card percentages. One-shots ≤ 1.2 s, at most 3 at once.
import type { VfxPreset } from "../contract/types";
import type { Emitter, ParticleField } from "./particles/engine";

/** Card rectangle inside the canvas (the canvas bleeds past the card so effects sit around it). */
export interface CardBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface VfxRun {
  field: ParticleField;
  box: CardBox;
  /** 1 = full size, 0.5 = "mini" listener reaction. */
  scale: number;
  /** 1 = full, 0.5 = "subtle" (half the particles). */
  density: number;
}

/** Extra loop-only presets for energy states. */
export type LoopPreset = VfxPreset | "yawn";

const TAU = Math.PI * 2;
const rand = (a: number, b: number) => a + Math.random() * (b - a);
const pt = (b: CardBox, px: number, py: number): [number, number] => [b.x + (px / 100) * b.w, b.y + (py / 100) * b.h];
const count = (n: number, d: number) => Math.max(1, Math.round(n * d));

function colors(f: ParticleField) {
  return {
    paper: f.cssVar("--paper-50", "#F5F2EA"),
    paper2: f.cssVar("--paper-300", "#BDB8AC"),
    glow: f.cssVar("--c-glow", "#FFB199"),
    accent: f.cssVar("--c-accent", "#FFC53D"),
    primary: f.cssVar("--c-primary", "#FF4D2E"),
    err: f.cssVar("--signal-err", "#FF3355"),
    blue: f.cssVar("--sad-blue", "#2B4C7E"),
  };
}

// ── One-shot budget: at most 3 concurrent one-shots app-wide ────────────────
const live: number[] = [];
function claimShot(ms: number): boolean {
  const now = performance.now();
  for (let i = live.length - 1; i >= 0; i--) if (live[i] < now) live.splice(i, 1);
  if (live.length >= 3) return false;
  live.push(now + ms);
  return true;
}

/** Fire the canvas half of a one-shot. Returns false if the 3-at-once budget is full. */
export function playOneShot(preset: VfxPreset, run: VfxRun): boolean {
  if (preset === "none" || preset === "ponder" || preset === "rain") return true; // DOM-only one-shots
  const { field: f, box, scale: s, density: d } = run;
  const c = colors(f);
  switch (preset) {
    case "sparkle": {
      if (!claimShot(700)) return false;
      const n = count(8, d);
      for (let i = 0; i < n; i++) {
        const [ox, oy] = pt(box, i % 2 ? 75 : 25, 62);
        const side = i % 2 ? 1 : -1;
        const ang = -Math.PI / 2 + side * rand(0.25, 1.35);
        const dist = rand(60, 140) * s;
        const v = dist * 4.3; // drag 4 → travels ≈ dist in ~0.7 s
        f.add({
          kind: "sparkle", x: ox, y: oy, life: 760, delay: i * 18,
          vx: Math.cos(ang) * v, vy: Math.sin(ang) * v, drag: 4,
          size: rand(13, 21) * s, grow: 0.55, vr: rand(-3, 3),
          color: i % 3 === 1 ? c.glow : c.paper, fadeIn: 0.04,
        });
        // trailing glints
        f.add({
          kind: "dot", x: ox, y: oy, life: 520, delay: i * 18 + 40,
          vx: Math.cos(ang) * v * 0.7, vy: Math.sin(ang) * v * 0.7, drag: 4.5,
          size: 2.2 * s, grow: 0.3, color: c.glow, fadeIn: 0.05,
        });
      }
      return true;
    }
    case "anger": {
      if (!claimShot(500)) return false;
      const [x, y] = pt(box, 50, 38);
      f.add({ kind: "ring", x, y, life: 520, size: box.w * 0.22, grow: 2.67, color: c.err, alpha: 1, fadeIn: 0.04 });
      if (d >= 1) f.add({ kind: "ring", x, y, life: 600, delay: 90, size: box.w * 0.18, grow: 2.4, color: c.err, alpha: 0.5, fadeIn: 0.05 });
      return true;
    }
    case "shock": {
      if (!claimShot(600)) return false;
      const [x, y] = pt(box, 70, 12);
      const n = count(8, d);
      for (let i = 0; i < n; i++) {
        const ang = (i / n) * TAU + rand(-0.15, 0.15);
        const v = rand(240, 380) * s;
        f.add({
          kind: "streak", x, y, life: 380, vx: Math.cos(ang) * v, vy: Math.sin(ang) * v, drag: 5,
          size: rand(10, 18) * s, rot: ang + Math.PI / 2, color: c.paper, fadeIn: 0.05,
        });
      }
      return true;
    }
    case "blush": {
      if (!claimShot(900)) return false;
      for (const px of [36, 64]) {
        const [x, y] = pt(box, px, 8);
        f.add({
          kind: "puff", x, y, life: 900, delay: px === 64 ? 120 : 0, vx: (px < 50 ? -1 : 1) * 14 * s, vy: -60 * s, drag: 1.2,
          size: 9 * s, grow: 2, color: c.paper, alpha: 0.55, fadeIn: 0.15,
        });
      }
      return true;
    }
    case "sleep": {
      zzz(run, c.paper);
      return true;
    }
  }
}

function zzz(run: VfxRun, color: string): void {
  const { field: f, box, scale: s } = run;
  const [x, y] = pt(box, 68, 20);
  [18, 24, 32].forEach((px, i) =>
    f.add({
      kind: "glyph", text: "Z", x: x + i * 10 * s, y: y - i * 6 * s, delay: i * 380, life: 2200,
      vx: 16 * s, vy: -30 * s, size: px * s, rot: -0.18, color, fadeIn: 0.2,
    }),
  );
}

/** Start the canvas half of a loop. Returns a stop function. */
export function startLoop(preset: LoopPreset, run: VfxRun): () => void {
  const { field: f, box, scale: s, density: d } = run;
  const c = colors(f);
  let e: Emitter | null = null;
  switch (preset) {
    case "sparkle":
      // 3 twinkles alive at a time
      e = {
        eager: true,
        next: () => rand(380, 620) / d,
        spawn: () => {
          const edge = Math.random() < 0.5;
          const px = edge ? (Math.random() < 0.5 ? rand(-8, 10) : rand(90, 108)) : rand(10, 90);
          const py = edge ? rand(15, 75) : rand(-6, 8);
          const [x, y] = pt(box, px, py);
          f.add({ kind: "sparkle", x, y, life: 1300, size: rand(6, 11) * s, bump: true, color: Math.random() < 0.5 ? c.paper : c.glow, vr: 0.6 });
        },
      };
      break;
    case "rain": {
      // 14 streaks (1×28 px, 14°) falling in the gutters either side of the card
      const life = 900;
      const ang = (14 * Math.PI) / 180;
      const fall = (f.height + 40) / (life / 1000);
      e = {
        eager: true,
        next: () => life / (14 * d),
        spawn: () => {
          const gutter = Math.max(18, box.x * 0.9);
          const left = Math.random() < 0.5;
          const x = left ? rand(box.x - gutter, box.x + 6) : rand(box.x + box.w - 6, box.x + box.w + gutter);
          f.add({
            kind: "streak", x: x + fall * Math.tan(ang) * 0.4, y: rand(-30, f.height * 0.3), life,
            vx: -fall * Math.tan(ang), vy: fall, size: 28 * s, rot: ang, color: c.paper2, alpha: 0.75, fadeIn: 0.1,
          });
        },
      };
      break;
    }
    case "sleep":
      e = { eager: true, next: () => 1700, spawn: () => zzz(run, c.paper) };
      break;
    case "yawn": {
      // "~" puff every 20 ± 4 s (first one soon so the state is discoverable)
      let first = true;
      e = {
        next: () => (first ? ((first = false), 2500) : rand(16000, 24000)),
        spawn: () => {
          const [x, y] = pt(box, 58, 46);
          f.add({ kind: "puff", x, y, life: 1400, vx: 18 * s, vy: -34 * s, drag: 0.8, size: 8 * s, grow: 2.2, color: c.paper, alpha: 0.4, fadeIn: 0.2 });
          f.add({ kind: "glyph", text: "~", x: x + 4, y: y - 6, life: 1400, vx: 22 * s, vy: -40 * s, size: 22 * s, color: c.paper, alpha: 0.9, fadeIn: 0.2, font: '"Inter Variable", sans-serif' });
        },
      };
      break;
    }
    default:
      return () => undefined;
  }
  return f.emit(e);
}

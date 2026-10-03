// Motion tokens as TS constants (mirror of styles/tokens.css). Owner: VMD.
export const DUR = {
  tap: 80,
  fast: 140,
  base: 220,
  swap: 300,
  slow: 400,
  scene: 550,
  reduced: 160,
  skip: 120,
} as const;

export const EASE = {
  wipe: "cubic-bezier(0.7, 0, 0.2, 1)",
  slam: "cubic-bezier(0.2, 0.9, 0.3, 1.3)",
  out: "cubic-bezier(0.16, 1, 0.3, 1)",
  in: "cubic-bezier(0.5, 0, 0.75, 0)",
  breathe: "cubic-bezier(0.45, 0, 0.55, 1)",
  linear: "linear",
} as const;

export const STAGGER = { tile: 30, list: 40, listMax: 8, shard: 25 } as const;

/** Flood peak opacity per flash-intensity setting (R10). */
export const FLASH_PEAK = { full: 0.85, low: 0.35, off: 0 } as const;

/** Minimum gap between two Palette Floods (NFR-16: ≤ 3 flashes/s; we allow 1/s). */
export const FLOOD_MIN_GAP_MS = 1000;

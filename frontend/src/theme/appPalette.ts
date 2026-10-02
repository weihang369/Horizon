// setAppPalette — themes the app root (R9: single-character screens) with flood + snap (R10). Owner: VMD.
// The palette class flips at the flood's cover point; CSS variables are never interpolated.
// At most one flood per second; extra commits inside that window snap without a flood.
import { useSyncExternalStore } from "react";
import { runTransition } from "../motion/transitions";
import { FLOOD_MIN_GAP_MS } from "../motion/tokens";
import { getPalette, paletteClass, PALETTE_CLASSES } from "./palettes";

let current: string | null = null;
let lastFloodAt = -Infinity;
const listeners = new Set<() => void>();

function applyClass(id: string | null): void {
  current = id;
  if (typeof document !== "undefined") {
    const root = document.documentElement;
    root.classList.remove(...PALETTE_CLASSES);
    root.classList.add(paletteClass(id));
    root.dataset.palette = id ?? "pal_house";
  }
  listeners.forEach((l) => l());
}

/**
 * Set the app-root palette. `null` = house palette.
 * With `flood`, plays a Palette Flood from that point (committed change only — never on hover).
 * Without `flood`, the swap is instant (hover previews, route entry).
 */
export function setAppPalette(paletteId: string | null, opts?: { flood?: { x: number; y: number } }): void {
  const next = paletteId && getPalette(paletteId).id === paletteId ? paletteId : null;
  if (next === current) return;
  const now = typeof performance !== "undefined" ? performance.now() : Date.now();
  if (!opts?.flood || now - lastFloodAt < FLOOD_MIN_GAP_MS || typeof document === "undefined") {
    applyClass(next);
    return;
  }
  lastFloodAt = now;
  runTransition("flood", {
    origin: opts.flood,
    color: getPalette(next).primary,
    onCover: () => applyClass(next),
  });
}

export function getAppPalette(): string | null {
  return current;
}

export function useAppPalette(): string | null {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    getAppPalette,
    getAppPalette,
  );
}

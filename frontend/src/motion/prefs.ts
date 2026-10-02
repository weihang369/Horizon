// Display / motion preference plumbing via root data attributes. Owner: VMD.
// The EE's prefs store calls applyDisplayPrefs(settings.display) whenever prefs change.
// Visual-kit components read prefs from here (no dependency on the stores).
import { useSyncExternalStore } from "react";
import type { AppSettings } from "../contract/types";

export type DisplayPrefs = AppSettings["display"];
export type VfxIntensity = DisplayPrefs["vfxIntensity"];
export type FlashIntensity = DisplayPrefs["flashIntensity"];

export interface MotionPrefs {
  /** Effective reduced motion (setting "system" resolved against the OS). */
  reduced: boolean;
  vfx: VfxIntensity;
  flash: FlashIntensity;
  parallax: boolean;
  textSize: DisplayPrefs["textSize"];
}

const DEFAULT_DISPLAY: DisplayPrefs = {
  reducedMotion: "system",
  vfxIntensity: "full",
  flashIntensity: "full",
  parallax: true,
  textSize: "m",
  speakerCutIns: true,
};

let display: DisplayPrefs = DEFAULT_DISPLAY;
let snapshot: MotionPrefs = compute();
const listeners = new Set<() => void>();

function osReduced(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : false;
}

function compute(): MotionPrefs {
  const reduced = display.reducedMotion === "on" || (display.reducedMotion === "system" && osReduced());
  return {
    reduced,
    // Reduced motion disables particles too (APP-05), but static badges still render.
    vfx: display.vfxIntensity,
    flash: reduced && display.flashIntensity === "full" ? "low" : display.flashIntensity,
    parallax: display.parallax && !reduced,
    textSize: display.textSize,
  };
}

function writeRoot(p: MotionPrefs): void {
  if (typeof document === "undefined") return;
  const d = document.documentElement.dataset;
  d.motion = p.reduced ? "reduced" : "full";
  d.vfx = p.reduced ? "off" : p.vfx;
  d.flash = p.flash;
  d.textSize = p.textSize;
  d.parallax = p.parallax ? "on" : "off";
}

function refresh(): void {
  snapshot = compute();
  writeRoot(snapshot);
  listeners.forEach((l) => l());
}

/** Apply the user's display settings (SET-04). Safe to call often. */
export function applyDisplayPrefs(next: Partial<DisplayPrefs>): void {
  display = { ...display, ...next };
  refresh();
}

export function getMotionPrefs(): MotionPrefs {
  return snapshot;
}

/** Effective VFX intensity for components (reduced motion → "off"). */
export function effectiveVfx(p: MotionPrefs = snapshot): VfxIntensity {
  return p.reduced ? "off" : p.vfx;
}

export function subscribeMotionPrefs(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

export function useMotionPrefs(): MotionPrefs {
  return useSyncExternalStore(subscribeMotionPrefs, getMotionPrefs, getMotionPrefs);
}

// Initialise the root attributes and follow OS changes.
if (typeof window !== "undefined") {
  writeRoot(snapshot);
  if (typeof window.matchMedia === "function") {
    window.matchMedia("(prefers-reduced-motion: reduce)").addEventListener?.("change", refresh);
  }
}

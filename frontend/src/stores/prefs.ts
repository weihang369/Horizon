// Prefs: per-browser display/audio/presenter settings, persisted separately from the mock DB (Lead gap ruling).
// Every change re-applies the VMD's root data attributes (applyDisplayPrefs) and the audio engine volumes. Owner: EE.
import { createStore } from "zustand/vanilla";
import { useStore } from "zustand";
import type { AppSettings } from "../contract/types";
import { applyDisplayPrefs } from "../motion/prefs";

export interface Prefs {
  display: AppSettings["display"];
  audio: AppSettings["audio"];
  presenterMode: boolean;
  /** First run → Onboarding (APP-04). */
  seenOnboarding: boolean;
  /** Replay gap trim (Lead ruling: on by default, can be switched off). */
  replayTrimGaps: boolean;
}

export const PREFS_KEY = "horizon.prefs.v1";

export const DEFAULT_PREFS: Prefs = {
  display: { reducedMotion: "system", vfxIntensity: "full", flashIntensity: "full", parallax: true, textSize: "m", speakerCutIns: true },
  audio: { masterMuted: false, musicMuted: false, sfxMuted: false, master: 0.8, music: 0.6, sfx: 0.8, duckMusic: true },
  presenterMode: false,
  seenOnboarding: false,
  replayTrimGaps: true,
};

function read(): Prefs {
  try {
    const raw = typeof localStorage !== "undefined" ? localStorage.getItem(PREFS_KEY) : null;
    if (!raw) return DEFAULT_PREFS;
    const p = JSON.parse(raw) as Partial<Prefs>;
    return {
      ...DEFAULT_PREFS, ...p,
      display: { ...DEFAULT_PREFS.display, ...p.display },
      audio: { ...DEFAULT_PREFS.audio, ...p.audio },
    };
  } catch {
    return DEFAULT_PREFS;
  }
}

export const prefs = createStore<Prefs>(() => read());

type Listener = (p: Prefs) => void;
const audioListeners = new Set<Listener>();
/** The audio engine registers here (keeps stores free of a WebAudio import). */
export function onPrefsAudio(cb: Listener): () => void {
  audioListeners.add(cb);
  cb(prefs.getState());
  return () => audioListeners.delete(cb);
}

function apply(p: Prefs): void {
  applyDisplayPrefs({ ...p.display, ...(p.presenterMode ? { textSize: "l" as const } : {}) });
  if (typeof document !== "undefined") document.documentElement.dataset.presenter = p.presenterMode ? "on" : "off";
  audioListeners.forEach((cb) => cb(p));
}

prefs.subscribe((p) => {
  apply(p);
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(p));
  } catch { /* private mode */ }
});
apply(prefs.getState());

export function setPrefs(patch: Partial<Omit<Prefs, "display" | "audio">> & { display?: Partial<Prefs["display"]>; audio?: Partial<Prefs["audio"]> }): void {
  const cur = prefs.getState();
  prefs.setState({
    ...cur, ...patch,
    display: { ...cur.display, ...patch.display },
    audio: { ...cur.audio, ...patch.audio },
  });
}

export function usePrefs<T>(sel: (p: Prefs) => T): T {
  return useStore(prefs, sel);
}

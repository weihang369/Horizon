// Waveform peaks for the theme player and track page (decoded buffer, or a seeded fake). Owner: Builder B.
import { useEffect, useState } from "react";

export const BARS = 72;
const peaksCache = new Map<string, number[]>();

export function fakePeaks(seed: string): number[] {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) h = Math.imul(h ^ seed.charCodeAt(i), 16777619);
  return Array.from({ length: BARS }, (_, i) => {
    h = Math.imul(h ^ (h >>> 13), 0x5bd1e995);
    const r = ((h >>> 0) % 1000) / 1000;
    return 0.25 + 0.55 * Math.abs(Math.sin(i * 0.33)) * (0.6 + 0.4 * r);
  });
}

export function usePeaks(url: string | undefined): number[] {
  const [peaks, setPeaks] = useState<number[]>(() => (url ? peaksCache.get(url) ?? fakePeaks(url) : fakePeaks("none")));
  useEffect(() => {
    if (!url) return;
    const hit = peaksCache.get(url);
    if (hit) return setPeaks(hit);
    let live = true;
    void import("@/audio/resolve").then((m) => m.resolveAudio(url)).then((buf) => {
      const ch = buf.getChannelData(0);
      const step = Math.floor(ch.length / BARS);
      const out: number[] = [];
      let max = 0;
      for (let b = 0; b < BARS; b++) {
        let peak = 0;
        for (let i = b * step; i < (b + 1) * step; i += 64) peak = Math.max(peak, Math.abs(ch[i]));
        out.push(peak);
        max = Math.max(max, peak);
      }
      const norm = out.map((p) => 0.12 + 0.88 * (max ? p / max : 0));
      peaksCache.set(url, norm);
      if (live) setPeaks(norm);
    }).catch(() => {});
    return () => void (live = false);
  }, [url]);
  return peaks;
}


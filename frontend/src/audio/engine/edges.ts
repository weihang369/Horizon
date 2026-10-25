// Edge fades for generated themes (the user's v1 review, 2026-10-21). A Lyria clip is one take with its own start and
// end, and has no loop points yet (docs/v2/README.md §9), so a plain loop restarts with a jump. Each pass instead
// starts from silence and ends in silence: near-silent edges are trimmed, then the start fades in and the end fades
// out. Procedural tracks are built to loop and never come through here. Pure (channels in, channels out) for tests.

export const FADE_IN_SEC = 1.5;
export const FADE_OUT_SEC = 3;
/** Below this (≈ −60 dBFS) an edge sample counts as silence. */
const SILENCE = 0.001;

export function edgeFade(channels: Float32Array<ArrayBuffer>[], sampleRate: number): Float32Array<ArrayBuffer>[] {
  const len = channels[0]?.length ?? 0;
  const loud = (i: number) => channels.some((c) => Math.abs(c[i]) > SILENCE);
  let start = 0;
  let end = len;
  while (start < len && !loud(start)) start++;
  while (end > start && !loud(end - 1)) end--;
  if (end - start < 4) return channels;
  const n = end - start;
  // A short clip keeps its middle: neither fade takes more than a quarter of it.
  const nIn = Math.min(Math.round(FADE_IN_SEC * sampleRate), n >> 2);
  const nOut = Math.min(Math.round(FADE_OUT_SEC * sampleRate), n >> 2);
  return channels.map((c) => {
    const d = c.slice(start, end);
    for (let i = 0; i < nIn; i++) d[i] *= Math.sin(((i / nIn) * Math.PI) / 2);
    for (let i = 0; i < nOut; i++) d[n - 1 - i] *= Math.sin(((i / nOut) * Math.PI) / 2);
    return d;
  });
}

// One global requestAnimationFrame ticker (R12). Owner: VMD (shared with EE).
// Subscribers get (dtMs, nowMs). The loop runs only while something is subscribed,
// and dt is clamped so a backgrounded tab doesn't produce a giant step.
export type TickFn = (dtMs: number, nowMs: number) => void;

const subs = new Set<TickFn>();
let raf = 0;
let last = 0;

function frame(now: number): void {
  const dt = last ? Math.min(64, now - last) : 16.7;
  last = now;
  subs.forEach((fn) => {
    try {
      fn(dt, now);
    } catch (err) {
      console.error("[ticker]", err);
    }
  });
  raf = subs.size ? requestAnimationFrame(frame) : 0;
  if (!raf) last = 0;
}

export function onTick(fn: TickFn): () => void {
  subs.add(fn);
  if (!raf && typeof requestAnimationFrame !== "undefined") raf = requestAnimationFrame(frame);
  return () => {
    subs.delete(fn);
  };
}

export const ticker = { onTick, get size() { return subs.size; } };

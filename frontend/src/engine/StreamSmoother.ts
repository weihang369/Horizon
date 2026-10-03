// R12: reveals streamed text at an adaptive rate so coarse fixture chunks and bursty SSE both look smooth.
// Target lag ≈ 150 ms: each frame reveals backlog / (150 ms / dt) characters (at least a minimum rate).
// Pure stepping logic here; stores/streamText.ts drives it from the global ticker.

export interface SmootherEntry {
  /** Everything received so far. */
  target: string;
  /** Characters revealed so far. */
  shown: number;
  /** The stream ended: finish revealing, then the entry can be dropped. */
  done: boolean;
}

export const SMOOTHER_LAG_MS = 150;
/** Minimum reveal speed (chars per second) so a trickle still moves. */
export const SMOOTHER_MIN_CPS = 30;

/** Advance one entry by dt ms. Returns the new shown count. */
export function stepSmoother(e: SmootherEntry, dtMs: number, lagMs = SMOOTHER_LAG_MS): number {
  const backlog = e.target.length - e.shown;
  if (backlog <= 0) return e.target.length;
  const lag = e.done ? lagMs / 2 : lagMs;
  const adaptive = backlog * Math.min(1, dtMs / lag);
  const floor = (SMOOTHER_MIN_CPS * dtMs) / 1000;
  let next = e.shown + Math.max(adaptive, floor, 1);
  next = Math.min(e.target.length, Math.ceil(next));
  // Don't cut a surrogate pair in half.
  const code = e.target.charCodeAt(next - 1);
  if (code >= 0xd800 && code <= 0xdbff && next < e.target.length) next += 1;
  return next;
}

export class StreamSmoother {
  private entries = new Map<string, SmootherEntry>();

  /** Set the full received text for a message (call on every coalesced store write). */
  setTarget(id: string, target: string, done = false): void {
    const prev = this.entries.get(id);
    if (prev && target.startsWith(prev.target.slice(0, Math.min(prev.shown, target.length)))) {
      prev.target = target;
      prev.done = done;
      if (prev.shown > target.length) prev.shown = target.length;
    } else {
      this.entries.set(id, { target, shown: prev ? Math.min(prev.shown, target.length) : 0, done });
    }
  }

  /** Reveal everything immediately (reduced motion, seek, replay jumps). */
  flush(id: string): void {
    const e = this.entries.get(id);
    if (e) e.shown = e.target.length;
  }

  /** Step every entry; returns ids whose visible text changed. Finished entries are removed after reporting. */
  step(dtMs: number): { changed: [string, string][]; finished: string[] } {
    const changed: [string, string][] = [];
    const finished: string[] = [];
    for (const [id, e] of this.entries) {
      const next = stepSmoother(e, dtMs);
      if (next !== e.shown) {
        e.shown = next;
        changed.push([id, e.target.slice(0, next)]);
      }
      if (e.done && e.shown >= e.target.length) finished.push(id);
    }
    for (const id of finished) this.entries.delete(id);
    return { changed, finished };
  }

  visible(id: string): string | undefined {
    const e = this.entries.get(id);
    return e ? e.target.slice(0, e.shown) : undefined;
  }

  has(id: string): boolean { return this.entries.has(id); }
  get size(): number { return this.entries.size; }
  clear(): void { this.entries.clear(); }
}

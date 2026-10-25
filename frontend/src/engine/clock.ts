// Clocks for the virtual-time engine. Real in the app; Manual in tests (advance(ms) fires due timers in order).

export type TimerHandle = number;

export interface Clock {
  /** Monotonic milliseconds. */
  now(): number;
  /** Wall-clock epoch milliseconds (for ISO timestamps). */
  wallNow(): number;
  setTimeout(fn: () => void, ms: number): TimerHandle;
  clearTimeout(h: TimerHandle): void;
}

export const realClock: Clock = {
  now: () => (typeof performance !== "undefined" ? performance.now() : Date.now()),
  wallNow: () => Date.now(),
  setTimeout: (fn, ms) => globalThis.setTimeout(fn, Math.max(0, ms)) as unknown as TimerHandle,
  clearTimeout: (h) => globalThis.clearTimeout(h),
};

interface ManualTimer { id: number; at: number; fn: () => void; order: number }

export class ManualClock implements Clock {
  private t = 0;
  private wallBase: number;
  private timers: ManualTimer[] = [];
  private nextId = 1;
  private order = 0;

  constructor(wallStartMs = Date.parse("2026-10-01T09:00:00Z")) {
    this.wallBase = wallStartMs;
  }

  now(): number { return this.t; }
  wallNow(): number { return this.wallBase + this.t; }

  setTimeout(fn: () => void, ms: number): TimerHandle {
    const id = this.nextId++;
    this.timers.push({ id, at: this.t + Math.max(0, ms), fn, order: this.order++ });
    return id;
  }

  clearTimeout(h: TimerHandle): void {
    this.timers = this.timers.filter((x) => x.id !== h);
  }

  /** Advance virtual time, firing timers (including ones scheduled by timers) in time order. */
  advance(ms: number): void {
    const target = this.t + ms;
    for (;;) {
      this.timers.sort((a, b) => a.at - b.at || a.order - b.order);
      const next = this.timers[0];
      if (!next || next.at > target) break;
      this.timers.shift();
      this.t = next.at;
      next.fn();
    }
    this.t = target;
  }

  /** Run everything pending (bounded). */
  runAll(maxMs = 3600_000): void {
    this.advance(maxMs);
  }

  get pending(): number { return this.timers.length; }
}

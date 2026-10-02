// Scheduler: tagged timers on the virtual clock (jobs, engines). Owner: EE.
// Tags let a whole session or job be cancelled at once (Stop, cancel, mock reset).
import type { Clock } from "./Clock";
import { VirtualClock } from "./Clock";

export class Scheduler {
  readonly clock: VirtualClock;
  private byTag = new Map<string, Set<number>>();

  constructor(base?: Clock, speed = 1) {
    this.clock = new VirtualClock(base, speed);
  }

  get speed(): number { return this.clock.speed; }
  setSpeed(speed: number): void { this.clock.setSpeed(speed); }
  /** Wall-clock epoch ms (timestamps). */
  wallNow(): number { return this.clock.wallNow(); }

  /** Run `fn` after `ms` of virtual time. Returns a cancel function. */
  after(ms: number, fn: () => void, tag?: string): () => void {
    let id = 0;
    id = this.clock.setTimeout(() => {
      if (tag) this.byTag.get(tag)?.delete(id);
      fn();
    }, ms);
    if (tag) {
      if (!this.byTag.has(tag)) this.byTag.set(tag, new Set());
      this.byTag.get(tag)!.add(id);
    }
    return () => {
      this.clock.clearTimeout(id);
      if (tag) this.byTag.get(tag)?.delete(id);
    };
  }

  /** Repeat every `ms` until the returned function is called or `fn` returns false. */
  every(ms: number, fn: () => boolean | void, tag?: string): () => void {
    let stop = false;
    let cancel = () => {};
    const tick = () => {
      if (stop) return;
      if (fn() === false) return;
      cancel = this.after(ms, tick, tag);
    };
    cancel = this.after(ms, tick, tag);
    return () => {
      stop = true;
      cancel();
    };
  }

  cancelTag(tag: string): void {
    const ids = this.byTag.get(tag);
    if (!ids) return;
    for (const id of ids) this.clock.clearTimeout(id);
    this.byTag.delete(tag);
  }

  cancelAll(): void {
    this.clock.clearAll();
    this.byTag.clear();
  }
}

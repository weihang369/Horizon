// Mock time (EE paper §2.3). Owner: EE.
// VirtualClock: virtual ms = base ms × demo speed (×1/×2/×4). A speed change rebases time and reschedules every
// pending timer by its remaining *virtual* delay, so a 20 s portrait job at ×4 still reads as 20 s of mock time.
// Wall time (ISO stamps, energy regen) is never sped up.
import type { Clock, TimerHandle } from "../../engine/clock";
import { ManualClock, realClock } from "../../engine/clock";

export type { Clock, TimerHandle };
export { ManualClock, realClock };

interface VTimer { id: number; due: number; fn: () => void; handle: TimerHandle | null }

export class VirtualClock implements Clock {
  private vBase = 0;
  private bBase: number;
  private _speed: number;
  private timers = new Map<number, VTimer>();
  private nextId = 1;
  readonly base: Clock;

  constructor(base: Clock = realClock, speed = 1) {
    this.base = base;
    this.bBase = base.now();
    this._speed = speed;
  }

  get speed(): number { return this._speed; }

  now(): number { return this.vBase + (this.base.now() - this.bBase) * this._speed; }
  wallNow(): number { return this.base.wallNow(); }

  setSpeed(speed: number): void {
    if (speed <= 0 || speed === this._speed) return;
    this.vBase = this.now();
    this.bBase = this.base.now();
    this._speed = speed;
    for (const t of this.timers.values()) this.arm(t);
  }

  setTimeout(fn: () => void, ms: number): TimerHandle {
    const t: VTimer = { id: this.nextId++, due: this.now() + Math.max(0, ms), fn, handle: null };
    this.timers.set(t.id, t);
    this.arm(t);
    return t.id;
  }

  clearTimeout(h: TimerHandle): void {
    const t = this.timers.get(h);
    if (!t) return;
    if (t.handle !== null) this.base.clearTimeout(t.handle);
    this.timers.delete(h);
  }

  /** Cancel everything (mock reset). */
  clearAll(): void {
    for (const t of this.timers.values()) if (t.handle !== null) this.base.clearTimeout(t.handle);
    this.timers.clear();
  }

  get pending(): number { return this.timers.size; }

  private arm(t: VTimer): void {
    if (t.handle !== null) this.base.clearTimeout(t.handle);
    const delay = Math.max(0, (t.due - this.now()) / this._speed);
    t.handle = this.base.setTimeout(() => {
      this.timers.delete(t.id);
      t.fn();
    }, delay);
  }
}

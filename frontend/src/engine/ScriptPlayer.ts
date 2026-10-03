// R1: plays a timeline of entries on a virtual clock. Replay feeds it recorded SessionEvents (timeline from the
// `at` deltas, gaps over 2.5 s trimmed); the MockClient appends generated turn scripts to a live player.
// One timer at a time, rescheduled on rate change, so pause/seek/rate are exact.
import type { SessionEvent } from "../contract/types";
import type { Clock, TimerHandle } from "./clock";
import { realClock } from "./clock";

export interface TimelineEntry<T> {
  /** Virtual milliseconds from the start of the timeline. */
  t: number;
  /** Payload delivered to onEntry (an event), or… */
  item?: T;
  /** …a callback run at that time (live engines use it to chain the next turn). */
  run?: () => void;
  /** Tag for cancellation (e.g. a turn id). */
  tag?: string;
}

export interface ScriptPlayerOptions<T> {
  clock?: Clock;
  rate?: number;
  onEntry: (item: T) => void;
  /** Called when playback reaches the end of the (current) timeline. */
  onEnd?: () => void;
  /** Called on every state change (play/pause/seek/rate/position jumps). */
  onState?: (s: PlayerState) => void;
}

export interface PlayerState { playing: boolean; position: number; duration: number; rate: number }

export class ScriptPlayer<T> {
  private entries: TimelineEntry<T>[] = [];
  private cursor = 0;
  private clock: Clock;
  private rate: number;
  private playing = false;
  private basePos = 0;
  private baseReal = 0;
  private timer: TimerHandle | null = null;
  private opts: ScriptPlayerOptions<T>;

  constructor(entries: TimelineEntry<T>[], opts: ScriptPlayerOptions<T>) {
    this.entries = [...entries].sort((a, b) => a.t - b.t);
    this.clock = opts.clock ?? realClock;
    this.rate = opts.rate ?? 1;
    this.opts = opts;
  }

  get position(): number {
    return this.playing ? this.basePos + (this.clock.now() - this.baseReal) * this.rate : this.basePos;
  }
  get duration(): number {
    return this.entries.length ? this.entries[this.entries.length - 1].t : 0;
  }
  get isPlaying(): boolean { return this.playing; }
  get currentRate(): number { return this.rate; }
  get remaining(): number { return this.entries.length - this.cursor; }

  state(): PlayerState {
    return { playing: this.playing, position: this.position, duration: this.duration, rate: this.rate };
  }

  play(): void {
    if (this.playing) return;
    this.playing = true;
    this.baseReal = this.clock.now();
    this.schedule();
    this.emitState();
  }

  pause(): void {
    if (!this.playing) return;
    this.basePos = this.position;
    this.playing = false;
    this.clearTimer();
    this.emitState();
  }

  setRate(rate: number): void {
    if (rate <= 0 || rate === this.rate) return;
    this.basePos = this.position;
    this.baseReal = this.clock.now();
    this.rate = rate;
    this.schedule();
    this.emitState();
  }

  /**
   * Jump to a position. Entries between the old and new position are delivered synchronously when seeking
   * forward; seeking backward only moves the cursor (callers reset their state and use `entriesUpTo`).
   */
  seek(pos: number, opts?: { deliver?: boolean }): void {
    const target = Math.max(0, pos);
    if (target >= this.position && opts?.deliver !== false) {
      this.basePos = target;
      this.baseReal = this.clock.now();
      this.flushDue(target);
    } else {
      this.cursor = this.entries.findIndex((e) => e.t > target);
      if (this.cursor < 0) this.cursor = this.entries.length;
      this.basePos = target;
      this.baseReal = this.clock.now();
    }
    if (this.playing) this.schedule();
    this.emitState();
  }

  /** Items with t ≤ pos (for rebuilding state after a backward seek). */
  itemsUpTo(pos: number): T[] {
    const out: T[] = [];
    for (const e of this.entries) {
      if (e.t > pos) break;
      if (e.item !== undefined) out.push(e.item);
    }
    return out;
  }

  /** Append entries at offsets relative to the current position (live mode). */
  appendRelative(entries: TimelineEntry<T>[]): void {
    const base = this.position;
    const add = entries.map((e) => ({ ...e, t: base + e.t }));
    this.insert(add);
  }

  /** Insert entries at absolute timeline positions. */
  insert(add: TimelineEntry<T>[]): void {
    const pending = this.entries.slice(this.cursor).concat(add).sort((a, b) => a.t - b.t);
    this.entries = this.entries.slice(0, this.cursor).concat(pending);
    if (this.playing) this.schedule();
  }

  /** Drop pending entries matching the predicate (Stop, skip, cancel). Returns the dropped entries. */
  cancel(pred: (e: TimelineEntry<T>) => boolean): TimelineEntry<T>[] {
    const done = this.entries.slice(0, this.cursor);
    const pending = this.entries.slice(this.cursor);
    const dropped = pending.filter(pred);
    this.entries = done.concat(pending.filter((e) => !pred(e)));
    if (this.playing) this.schedule();
    return dropped;
  }

  dispose(): void {
    this.clearTimer();
    this.playing = false;
    this.entries = [];
    this.cursor = 0;
  }

  private flushDue(pos: number): void {
    while (this.cursor < this.entries.length && this.entries[this.cursor].t <= pos) {
      const e = this.entries[this.cursor++];
      if (e.item !== undefined) this.opts.onEntry(e.item);
      e.run?.();
    }
  }

  private schedule(): void {
    this.clearTimer();
    if (!this.playing) return;
    if (this.cursor >= this.entries.length) {
      this.opts.onEnd?.();
      return;
    }
    const next = this.entries[this.cursor];
    const delay = Math.max(0, (next.t - this.position) / this.rate);
    this.timer = this.clock.setTimeout(() => {
      this.timer = null;
      this.flushDue(this.position + 0.0001);
      const wasEmpty = this.cursor >= this.entries.length;
      if (wasEmpty) {
        this.opts.onEnd?.();
        this.emitState();
      } else {
        this.schedule();
      }
    }, delay);
  }

  private clearTimer(): void {
    if (this.timer !== null) {
      this.clock.clearTimeout(this.timer);
      this.timer = null;
    }
  }

  private emitState(): void {
    this.opts.onState?.(this.state());
  }
}

/** Default gap trim for Replay (Lead ruling: gaps over 2.5 s are clamped; the trim can be switched off). */
export const REPLAY_GAP_TRIM_MS = 2500;

/** Build a replay timeline from recorded events: t from `at` deltas, long gaps clamped. */
export function timelineFromEvents(events: SessionEvent[], opts?: { trimGapsMs?: number | null }): TimelineEntry<SessionEvent>[] {
  const trim = opts?.trimGapsMs === undefined ? REPLAY_GAP_TRIM_MS : opts.trimGapsMs;
  const sorted = [...events].sort((a, b) => a.seq - b.seq);
  let t = 0;
  let prev: number | null = null;
  return sorted.map((e) => {
    const at = Date.parse(e.at);
    if (prev !== null) {
      let gap = Math.max(0, at - prev);
      if (trim !== null && gap > trim) gap = trim;
      t += gap;
    }
    prev = at;
    return { t, item: e };
  });
}

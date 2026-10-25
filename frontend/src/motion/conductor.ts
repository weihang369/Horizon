// Ceremony conductor (R6, D-55): one queue, one punctuation at a time, never blocks input.
// Any key or click while a ceremony runs skips it to its end state within ≤ 120 ms; the event is NOT
// swallowed, so the key/click still does its normal job ("replayed").
// Reduced motion caps every ceremony at 200 ms (the component renders a fade).
import { useSyncExternalStore } from "react";
import { DUR } from "./tokens";
import { getMotionPrefs } from "./prefs";

export type CeremonyResult = "done" | "skipped";

export interface CeremonyHandle {
  skip(): void;
  done: Promise<CeremonyResult>;
}

export interface CeremonyOpts {
  durationMs: number;
  onSkip?: () => void;
  /** Ignore key/click skipping (still skippable via handle / skipAllCeremonies). Default false. */
  noInputSkip?: boolean;
}

interface Entry {
  id: string;
  opts: CeremonyOpts;
  status: "queued" | "active" | "skipped";
  startedAt: number;
  timer: number;
  resolve: (r: CeremonyResult) => void;
}

export interface CeremonyState {
  active: boolean;
  skipped: boolean;
  queued: boolean;
}

const IDLE: CeremonyState = { active: false, skipped: false, queued: false };
const queue: Entry[] = [];
let states = new Map<string, CeremonyState>();
const listeners = new Set<() => void>();

function publish(): void {
  const next = new Map<string, CeremonyState>();
  for (const e of queue) {
    next.set(e.id, {
      active: e.status !== "queued",
      skipped: e.status === "skipped",
      queued: e.status === "queued",
    });
  }
  states = next;
  listeners.forEach((l) => l());
}

function now(): number {
  return typeof performance !== "undefined" ? performance.now() : Date.now();
}

function startNext(): void {
  const e = queue[0];
  if (!e || e.status !== "queued") return;
  e.status = "active";
  e.startedAt = now();
  const dur = getMotionPrefs().reduced ? Math.min(200, e.opts.durationMs) : e.opts.durationMs;
  e.timer = window.setTimeout(() => finish(e, "done"), dur);
  publish();
}

function finish(e: Entry, result: CeremonyResult): void {
  const i = queue.indexOf(e);
  if (i < 0) return;
  clearTimeout(e.timer);
  queue.splice(i, 1);
  e.resolve(result);
  publish();
  startNext();
}

function skipEntry(e: Entry): void {
  if (e.status === "skipped") return;
  if (e.status === "queued") {
    // Never started: drop it.
    e.opts.onSkip?.();
    finish(e, "skipped");
    return;
  }
  clearTimeout(e.timer);
  e.status = "skipped";
  e.opts.onSkip?.();
  publish();
  e.timer = window.setTimeout(() => finish(e, "skipped"), DUR.skip);
}

/** Queue a ceremony. It starts when every earlier ceremony has finished. */
export function playCeremony(id: string, opts: CeremonyOpts): CeremonyHandle {
  let resolve!: (r: CeremonyResult) => void;
  const done = new Promise<CeremonyResult>((r) => (resolve = r));
  if (typeof window === "undefined") {
    resolve("done");
    return { skip() {}, done };
  }
  const e: Entry = { id, opts, status: "queued", startedAt: 0, timer: 0, resolve };
  queue.push(e);
  publish();
  if (queue.length === 1) startNext();
  return { skip: () => skipEntry(e), done };
}

/** Skip the active ceremony and drop all queued ones (e.g. Replay seek). */
export function skipAllCeremonies(): void {
  [...queue].reverse().forEach(skipEntry);
}

export function isCeremonyActive(): boolean {
  return queue.length > 0 && queue[0].status !== "queued";
}

export function getCeremonyState(id: string): CeremonyState {
  return states.get(id) ?? IDLE;
}

export function subscribeCeremonies(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

/** Components render their END state when `skipped` (or when not active after playing). */
export function useCeremony(id: string): CeremonyState {
  return useSyncExternalStore(
    subscribeCeremonies,
    () => getCeremonyState(id),
    () => IDLE,
  );
}

// ── Input skipping ────────────────────────────────────────────────────────────
const MODIFIERS = new Set(["Shift", "Control", "Alt", "Meta", "CapsLock", "Tab"]);
const GRACE_MS = 80; // the gesture that started a ceremony must not skip it

function onInput(ev: Event): void {
  const e = queue[0];
  if (!e || e.status !== "active" || e.opts.noInputSkip) return;
  if (now() - e.startedAt < GRACE_MS) return;
  if (ev instanceof KeyboardEvent && (ev.repeat || MODIFIERS.has(ev.key))) return;
  skipEntry(e);
}

if (typeof window !== "undefined") {
  window.addEventListener("keydown", onInput, { capture: true });
  window.addEventListener("pointerdown", onInput, { capture: true });
}

// Mock DB persistence (Lead gap ruling): snapshot to localStorage keyed by the fixture hash.
// A new seed build (new hash) discards old snapshots. Recorded events identical to seed/ are not stored. Owner: EE.
import type { Dataset, SessionRecord } from "./dataset";

export const SNAPSHOT_KEY = "horizon.mock.db.v1";

interface Snapshot { hash: string; savedAt: number; data: Omit<Dataset, "sessions"> & { sessions: Record<string, Partial<SessionRecord>> } }

export type KV = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export function defaultStorage(): KV | null {
  try {
    return typeof localStorage !== "undefined" ? localStorage : null;
  } catch {
    return null;
  }
}

export function saveSnapshot(storage: KV | null, ds: Dataset, seed: Dataset): void {
  if (!storage) return;
  const sessions: Record<string, Partial<SessionRecord>> = {};
  for (const [id, rec] of Object.entries(ds.sessions)) {
    const orig = seed.sessions[id];
    sessions[id] = orig && orig.events.length === rec.events.length
      ? { session: rec.session, messages: rec.messages }
      : rec;
  }
  const snap: Snapshot = { hash: seed.hash, savedAt: Date.now(), data: { ...ds, sessions } };
  try {
    storage.setItem(SNAPSHOT_KEY, JSON.stringify(snap));
  } catch (err) {
    console.warn("[mock] snapshot not saved", err);
  }
}

/** The saved dataset merged over a fresh seed copy, or null if none / stale. */
export function loadSnapshot(storage: KV | null, seed: Dataset): Dataset | null {
  if (!storage) return null;
  let snap: Snapshot;
  try {
    const raw = storage.getItem(SNAPSHOT_KEY);
    if (!raw) return null;
    snap = JSON.parse(raw) as Snapshot;
  } catch {
    return null;
  }
  if (snap.hash !== seed.hash) {
    storage.removeItem(SNAPSHOT_KEY);
    return null;
  }
  const sessions: Dataset["sessions"] = {};
  for (const [id, part] of Object.entries(snap.data.sessions)) {
    const orig = seed.sessions[id];
    if (!part.session) continue;
    sessions[id] = { session: part.session, messages: part.messages ?? orig?.messages ?? [], events: part.events ?? orig?.events ?? [] };
  }
  return { ...snap.data, sessions };
}

export function clearSnapshot(storage: KV | null): void {
  storage?.removeItem(SNAPSHOT_KEY);
}

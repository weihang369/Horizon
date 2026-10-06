// Entities store: normalised client query results (EE paper §2.6). Owner: EE.
// Resources are keyed strings ("worlds", "characters:<wid>:all", …). `entity.changed` / `mock.reset` from the client
// invalidate matching keys; mounted hooks refetch them in place (no skeleton flash on refetch).
import { createStore } from "zustand/vanilla";
import type { AppSettings, Character } from "../contract/types";
import type { HorizonErrorShape } from "../contract/errors";
import { toHorizonError } from "../contract/errors";

export type ResStatus = "idle" | "loading" | "ready" | "error";
export interface Res<T = unknown> {
  data?: T;
  status: ResStatus;
  error?: HorizonErrorShape;
  /** Bumped by invalidate(); a mounted hook refetches when it changes. */
  stale: number;
}

export interface EntitiesState {
  res: Record<string, Res>;
  /** Every character seen in any response, by id (EnergyBar, name lookups). */
  chars: Record<string, Character>;
  settings?: AppSettings;
}

export const IDLE: Res = { status: "idle", stale: 0 };

export const entities = createStore<EntitiesState>(() => ({ res: {}, chars: {} }));

/** In-flight fetches, tagged with the key's version when they started. */
const inflight = new Map<string, { v: number; p: Promise<unknown> }>();
/** Bumped by invalidate() and putResource(): a fetch that started before a bump is stale and never written. */
const versions = new Map<string, number>();
const bump = (key: string) => versions.set(key, (versions.get(key) ?? 0) + 1);

function absorb(data: unknown): void {
  const put = (c: Character) => entities.setState((s) => ({ chars: { ...s.chars, [c.id]: c } }));
  if (Array.isArray(data)) {
    const cs = data.filter((x): x is Character => !!x && typeof x === "object" && "profile" in x && "energy" in x);
    if (cs.length) entities.setState((s) => ({ chars: { ...s.chars, ...Object.fromEntries(cs.map((c) => [c.id, c])) } }));
  } else if (data && typeof data === "object") {
    if ("profile" in data && "energy" in data) put(data as Character);
    if ("openRouterKeyStatus" in data) entities.setState({ settings: data as AppSettings });
    if ("character" in data && (data as { character: Character }).character?.profile) put((data as { character: Character }).character);
  }
}

/**
 * Fetch a resource (deduped). Keeps old data visible while refetching. A fetch that started before the key was
 * invalidated or written is not reused, and its late answer never overwrites newer data (an event can land while a
 * request is on the wire).
 */
export function loadResource<T>(key: string, fetcher: () => Promise<T>, opts?: { force?: boolean }): Promise<T> {
  const cur = entities.getState().res[key];
  if (!opts?.force && cur?.status === "ready") return Promise.resolve(cur.data as T);
  const v = versions.get(key) ?? 0;
  const running = inflight.get(key);
  if (running && running.v === v) return running.p as Promise<T>;
  entities.setState((s) => ({ res: { ...s.res, [key]: { ...(s.res[key] ?? IDLE), status: s.res[key]?.data !== undefined ? "ready" : "loading" } } }));
  const entry: { v: number; p: Promise<unknown> } = { v, p: Promise.resolve() };
  const settle = (): boolean => {
    if (inflight.get(key) === entry) inflight.delete(key);
    return (versions.get(key) ?? 0) === v;
  };
  // Superseded: answer with the newer data, or (a first load invalidated mid-flight, which no hook refetches while it
  // is "loading") with a fresh fetch, joining one already under way.
  const again = (): T | Promise<T> => {
    const now = entities.getState().res[key];
    return now?.status === "loading" ? loadResource(key, fetcher, { force: true }) : (now?.data as T);
  };
  const p = fetcher().then(
    (data) => {
      if (!settle()) return again();
      absorb(data);
      entities.setState((s) => ({ res: { ...s.res, [key]: { data, status: "ready", stale: s.res[key]?.stale ?? 0 } } }));
      return data;
    },
    (err) => {
      if (!settle()) return again();
      const e = toHorizonError(err).toJSON();
      entities.setState((s) => ({ res: { ...s.res, [key]: { ...(s.res[key] ?? IDLE), status: "error", error: e } } }));
      throw err;
    },
  );
  entry.p = p;
  inflight.set(key, entry);
  return p;
}

/** Mark keys stale (prefix match). Mounted hooks refetch. */
export function invalidate(pred: (key: string) => boolean): void {
  const keys = Object.keys(entities.getState().res).filter(pred);
  keys.forEach(bump);
  entities.setState((s) => {
    const res = { ...s.res };
    for (const k of keys) if (res[k]) res[k] = { ...res[k], stale: res[k].stale + 1 };
    return { res };
  });
}

export function invalidateAll(): void {
  invalidate(() => true);
}

/** Optimistic local write (after a command resolves with the new entity). */
export function putResource<T>(key: string, data: T): void {
  bump(key);
  absorb(data);
  entities.setState((s) => ({ res: { ...s.res, [key]: { data, status: "ready", stale: s.res[key]?.stale ?? 0 } } }));
}

export function putCharacter(c: Character): void {
  absorb(c);
}

export const resKeys = {
  settings: "settings",
  worlds: "worlds",
  world: (id: string) => `world:${id}`,
  characters: (worldId: string, archived = false) => `characters:${worldId}:${archived ? "all" : "live"}`,
  character: (id: string) => `character:${id}`,
  sessions: (worldId: string) => `sessions:${worldId}`,
  job: (id: string) => `job:${id}`,
  usage: "usage",
  usageSummary: "usage:summary",
  memory: (cid: string) => `memory:${cid}`,
  knowledge: (cid: string) => `knowledge:${cid}`,
  song: (cid: string) => `song:${cid}`,
  activeJobs: "jobs:active",
};

// Data hooks (README §3.4). Owner: EE.
// Queries go through the entities store (deduped, refetched in place on entity.changed / mock.reset).
// Session runtimes come from client/sessionRuntime.ts; streamed text from stores/streamText.ts.
import { useEffect, useMemo, useReducer, useState } from "react";
import { useStore } from "zustand";
import type {
  AppSettings, Character, EnergyState, GenerationJob, KnowledgeSource, MemoryItem, Message, Participant, Session,
  ThemeSong, UsageRecord, World,
} from "../contract/types";
import type { HorizonErrorShape } from "../contract/errors";
import { EST_REPLY_POINTS, liveEnergy, regenAt } from "../domain/energy";
import { rushHourInfo } from "../domain/rushHour";
import type { PricePeriod } from "../domain/rushHour";
import { emotionHold, holdInputFor } from "../engine/emotionHold";
import type { SessionRuntimeState } from "../engine/sessionReducer";
import { entities, IDLE, invalidate, invalidateAll, loadResource, putResource, resKeys } from "../stores/entities";
import type { Res } from "../stores/entities";
import { sessionStore, slotKey } from "../stores/session";
import type { ReplayInfo } from "../stores/session";
import { streamText } from "../stores/streamText";
import { client } from "./index";
import type { UsageSummary } from "./HorizonClient";
import { acquireRuntime, controlsFor } from "./sessionRuntime";
import type { RuntimeControls } from "./sessionRuntime";

// ── Invalidation wiring (once) ────────────────────────────────────────────────
client.onGlobal((e) => {
  if (e.type === "mock.reset") return invalidateAll();
  if (e.type === "job.done") return invalidate((k) => k === resKeys.activeJobs || k === resKeys.job(e.job.id) || k === resKeys.character(e.job.characterId) || k.startsWith("characters:") || k === resKeys.song(e.job.characterId));
  if (e.type !== "entity.changed") return;
  const { kind, id, worldId } = e;
  switch (kind) {
    case "settings": return invalidate((k) => k === resKeys.settings);
    case "world": return invalidate((k) => k === resKeys.worlds || (!!id && k === resKeys.world(id)));
    case "character": return invalidate((k) => (!!id && (k === resKeys.character(id) || k === resKeys.song(id))) || (worldId ? k.startsWith(`characters:${worldId}:`) : k.startsWith("characters:")) || k === resKeys.worlds || (!!worldId && k === resKeys.world(worldId)));
    case "session": return invalidate((k) => (worldId ? k === resKeys.sessions(worldId) : k.startsWith("sessions:")));
    case "usage": return invalidate((k) => k === resKeys.usage || k === resKeys.usageSummary || k === resKeys.settings);
    case "memory": return invalidate((k) => k.startsWith("memory:"));
    case "knowledge": return invalidate((k) => k.startsWith("knowledge:"));
    case "job": return invalidate((k) => k === resKeys.activeJobs || (!!id && k === resKeys.job(id)));
  }
});

// ── Generic query hook ───────────────────────────────────────────────────────
export interface QueryResult<T> {
  data: T | undefined;
  status: Res["status"];
  error?: HorizonErrorShape;
  /** First load (no data yet): render skeletons (STATE-02). */
  loading: boolean;
  reload(): void;
}

const loadedStale = new Map<string, number>();

function useQuery<T>(key: string | null, fetcher: () => Promise<T>): QueryResult<T> {
  const res = useStore(entities, (s) => (key ? s.res[key] ?? IDLE : IDLE)) as Res<T>;
  useEffect(() => {
    if (!key) return;
    const seen = loadedStale.get(key);
    if (res.status === "ready" && seen === res.stale) return;
    if (res.status === "loading") return;
    if (res.status === "error" && seen === res.stale) return;
    loadedStale.set(key, res.stale);
    loadResource(key, fetcher, { force: res.status !== "idle" }).catch(() => {});
    // fetcher is derived from key
  }, [key, res.stale, res.status]); // eslint-disable-line react-hooks/exhaustive-deps
  return {
    data: res.data,
    status: key ? res.status : "idle",
    error: res.error,
    loading: !!key && res.data === undefined && res.status !== "error",
    reload: () => {
      if (key) loadResource(key, fetcher, { force: true }).catch(() => {});
    },
  };
}

export const useSettings = (): QueryResult<AppSettings> => useQuery(resKeys.settings, () => client.settings.get());
export const useWorlds = (): QueryResult<World[]> => useQuery(resKeys.worlds, () => client.worlds.list());
export const useWorld = (id: string | null | undefined): QueryResult<World> => useQuery(id ? resKeys.world(id) : null, () => client.worlds.get(id!));
export const useCharacters = (worldId: string | null | undefined, opts?: { includeArchived?: boolean }): QueryResult<Character[]> =>
  useQuery(worldId ? resKeys.characters(worldId, opts?.includeArchived) : null, () => client.characters.list(worldId!, opts));
export const useCharacter = (id: string | null | undefined): QueryResult<Character> => useQuery(id ? resKeys.character(id) : null, () => client.characters.get(id!));
export const useSessions = (worldId: string | null | undefined): QueryResult<Session[]> => useQuery(worldId ? resKeys.sessions(worldId) : null, () => client.sessions.list(worldId!));
export const useMemory = (characterId: string | null | undefined): QueryResult<MemoryItem[]> => useQuery(characterId ? resKeys.memory(characterId) : null, () => client.characters.memory(characterId!));
export const useKnowledge = (characterId: string | null | undefined): QueryResult<KnowledgeSource[]> => useQuery(characterId ? resKeys.knowledge(characterId) : null, () => client.characters.knowledge(characterId!));
/** Additive: a character's theme song (null = none yet). */
export const useSong = (characterId: string | null | undefined): QueryResult<ThemeSong | null> => useQuery(characterId ? resKeys.song(characterId) : null, () => client.characters.song(characterId!));
/** Additive: running jobs (the background job pill). */
export const useActiveJobs = (): QueryResult<GenerationJob[]> => useQuery(resKeys.activeJobs, () => client.jobs.listActive());

export function useUsage(): QueryResult<{ records: UsageRecord[]; summary: UsageSummary }> {
  return useQuery(resKeys.usage, async () => {
    const [records, summary] = await Promise.all([client.usage.list(), client.usage.summary()]);
    return { records, summary };
  });
}

/** A generation job with live progress (job.progress / task.update / job.done). */
export function useJob(jobId: string | null | undefined): QueryResult<GenerationJob> {
  const q = useQuery(jobId ? resKeys.job(jobId) : null, () => client.jobs.get(jobId!));
  useEffect(() => {
    if (!jobId) return;
    return client.jobs.subscribe(jobId, (e) => {
      if (e.type === "task.update") {
        const cur = entities.getState().res[resKeys.job(jobId)]?.data as GenerationJob | undefined;
        if (cur) putResource(resKeys.job(jobId), { ...cur, tasks: cur.tasks.map((t) => (t.id === e.task.id ? e.task : t)) });
      } else putResource(resKeys.job(jobId), e.job);
    });
  }, [jobId]);
  return q;
}

// ── Clock ────────────────────────────────────────────────────────────────────
/** Re-render every `ms` (energy regen, countdowns). */
export function useNow(ms = 15_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(t);
  }, [ms]);
  return now;
}

// ── Rush hour (ENG-06) ───────────────────────────────────────────────────────
export interface RushHourView { peak: boolean; period: PricePeriod; nextChangeAt: string }

export function useRushHour(): RushHourView {
  const now = useNow(30_000);
  const pricing = useStore(entities, (s) => s.settings?.pricing);
  useSettings();
  return useMemo(() => {
    if (pricing && Date.parse(pricing.nextChangeAt) > now) return { peak: pricing.period === "peak", period: pricing.period, nextChangeAt: pricing.nextChangeAt };
    const r = rushHourInfo(now);
    return { peak: r.peak, period: r.period, nextChangeAt: r.nextChangeAt };
  }, [pricing, now]);
}

// ── Energy (ENG-01..07) ──────────────────────────────────────────────────────
export interface EnergyView { current: number; max: number; state: EnergyState; fullAt?: string; pct: number }

/**
 * Live energy for a character: an open session runtime's value wins (Replay drains are a sandboxed overlay);
 * otherwise the stored Energy with lazy regen. Demo mode and Replay are frozen (ENG-07). Null until known.
 */
export function useEnergy(characterId: string | null | undefined): EnergyView | null {
  const now = useNow(15_000);
  const { peak } = useRushHour();
  // D-78: the threshold comes from settings (config-owned), so the UI and the speak/skip gate agree.
  const estPoints = useStore(entities, (s) => s.settings?.energy.estReplyPoints);
  const char = useStore(entities, (s) => (characterId ? s.chars[characterId] : undefined));
  const demo = useStore(entities, (s) => s.settings?.demoMode ?? true);
  const rtEnergy = useStore(sessionStore, (s) => {
    if (!characterId) return undefined;
    const slots = Object.values(s.slots);
    for (let i = slots.length - 1; i >= 0; i--) if (slots[i].runtime?.energyById[characterId]) return slots[i].runtime!.energyById[characterId];
    return undefined;
  });
  const rtReplay = useStore(sessionStore, (s) => (characterId ? Object.values(s.slots).some((x) => x.replay && x.runtime?.energyById[characterId]) : false));
  useEffect(() => {
    if (characterId && !entities.getState().chars[characterId]) loadResource(resKeys.character(characterId), () => client.characters.get(characterId)).catch(() => {});
  }, [characterId]);
  return useMemo(() => {
    const est = (estPoints ?? EST_REPLY_POINTS)[peak ? "peak" : "off_peak"];
    if (rtEnergy) {
      const frozen = rtReplay || demo || !rtEnergy.at;
      const regen = rtEnergy.max / 24;
      const current = frozen ? rtEnergy.current : Math.floor(regenAt({ current: rtEnergy.current, max: rtEnergy.max, asOf: rtEnergy.at!, regenPerHour: regen }, now));
      const e = liveEnergy({ max: rtEnergy.max, current, asOf: new Date(now).toISOString(), regenPerHour: regen, state: rtEnergy.state, spentToday: 0, fullAt: rtEnergy.fullAt }, now, { frozen, estReplyPoints: est });
      return { current: e.current, max: e.max, state: frozen ? rtEnergy.state : e.state, fullAt: e.fullAt, pct: e.pct };
    }
    if (!char) return null;
    const e = liveEnergy(char.energy, now, { frozen: demo, estReplyPoints: est });
    return { current: e.current, max: e.max, state: demo ? char.energy.state : e.state, fullAt: e.fullAt, pct: e.pct };
  }, [char, rtEnergy, rtReplay, demo, now, peak, estPoints]);
}

// ── Session runtime (R1) ─────────────────────────────────────────────────────
export type RuntimeParticipant = Participant & { displayEmotion: Participant["currentEmotion"]; leanIn: boolean };

export interface SessionRuntimeView {
  status: "loading" | "ready" | "error";
  error?: HorizonErrorShape;
  session?: Session;
  messages: Record<string, Message>;
  order: string[];
  /** Additive: messages in order. */
  list: Message[];
  participants: RuntimeParticipant[];
  energyById: SessionRuntimeState["energyById"];
  phase: SessionRuntimeState["phase"];
  watch: SessionRuntimeState["watch"];
  nextSpeakerId?: string;
  thinkingId?: string;
  streamingId?: string;
  paused: boolean;
  pausedReason?: SessionRuntimeState["pausedReason"];
  errors: SessionRuntimeState["errors"];
  /** Additive: the raw reducer state (budget warning, turn timing, lastSeq…). */
  runtime?: SessionRuntimeState;
  /** Replay transport state (replay only). */
  player?: ReplayInfo;
  controls: RuntimeControls;
}

const EMPTY: Record<string, Message> = {};
const EMPTY_ORDER: string[] = [];

export function useSessionRuntime(sessionId: string | null | undefined, opts: { replay?: boolean } = {}): SessionRuntimeView {
  const replay = !!opts.replay;
  const key = sessionId ? slotKey(sessionId, replay) : "";
  useEffect(() => {
    if (!sessionId) return;
    const c = acquireRuntime(sessionId, replay);
    return () => c.release();
  }, [sessionId, replay]);
  const slot = useStore(sessionStore, (s) => (key ? s.slots[key] : undefined));
  const rt = slot?.runtime;
  const [tick, bump] = useReducer((x: number) => x + 1, 0);
  const holds = useMemo(() => {
    const out: Record<string, { leanIn: boolean; recheck: number | null }> = {};
    if (!rt) return out;
    const now = Date.now();
    for (const p of rt.session.participants) {
      const h = emotionHold(holdInputFor(rt, p.characterId), replay && rt.lastAt ? Date.parse(rt.lastAt) : now);
      out[p.characterId] = { leanIn: h.leanIn, recheck: h.recheckInMs };
    }
    return out;
  }, [rt, replay, tick]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const next = Object.values(holds).map((h) => h.recheck).filter((x): x is number => x !== null);
    if (!next.length) return;
    const t = setTimeout(bump, Math.min(...next) + 5);
    return () => clearTimeout(t);
  }, [holds]);
  const controls = useMemo(() => controlsFor(key), [key]);
  return useMemo<SessionRuntimeView>(() => {
    const participants: RuntimeParticipant[] = rt
      ? rt.session.participants.map((p) => ({ ...p, displayEmotion: rt.displayEmotion[p.characterId] ?? p.currentEmotion, leanIn: holds[p.characterId]?.leanIn ?? false }))
      : [];
    return {
      status: slot?.status ?? "loading",
      error: slot?.error,
      session: rt?.session,
      messages: rt?.messages ?? EMPTY,
      order: rt?.order ?? EMPTY_ORDER,
      list: rt ? rt.order.map((id) => rt.messages[id]).filter((m): m is Message => !!m) : [],
      participants,
      energyById: rt?.energyById ?? {},
      phase: rt?.phase ?? null,
      watch: rt?.watch ?? null,
      nextSpeakerId: rt?.nextSpeakerId,
      thinkingId: rt?.thinkingId,
      streamingId: rt?.streamingId,
      paused: rt?.paused ?? false,
      pausedReason: rt?.pausedReason,
      errors: rt?.errors ?? [],
      runtime: rt,
      player: slot?.player,
      controls,
    };
  }, [rt, slot?.status, slot?.error, slot?.player, holds, controls]);
}

/** The smoothed live text of a streaming message (undefined when not streaming in this tab). */
export function useStreamText(messageId: string | null | undefined): string | undefined {
  return useStore(streamText, (s) => (messageId ? s.text[messageId] : undefined));
}

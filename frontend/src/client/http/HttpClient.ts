// The HttpClient: HorizonClient over the local backend (doc backend/03 §5, http-client spec). Owner: SWE.
// Each milestone adds the methods for its own routes. A method whose backend hasn't shipped yet rejects at once,
// without a request, with a non-retryable `validation` error whose `details.availableIn` names the milestone.
import { HorizonError } from "../../contract/errors";
import type {
  AppSettings, Character, EmotionAsset, GenerationJob, KnowledgeChunk, KnowledgeSource, MemoryItem, Message, Session,
  SessionEvent, ThemeSong, TurnTrace, UsageRecord, World,
} from "../../contract/types";
import type {
  GlobalEvent, HorizonClient, JobEvent, SessionSnapshot, Unsubscribe, UsageSummary,
} from "../HorizonClient";
import { collect } from "./paging";
import { GlobalStream, SessionStreams } from "./sse";
import type { EventSourceCtor } from "./sse";
import { Transport } from "./transport";
import type { FetchLike } from "./transport";

export type Milestone = "M2" | "M3" | "M4" | "M5" | "M6";

export interface HttpClientOptions {
  /** "/api/v1" in the browser (Vite proxies it); an absolute URL in Node tests. */
  baseUrl: string;
  fetch?: FetchLike;
  /** The browser's EventSource by default; Node tests inject one. */
  EventSource?: EventSourceCtor;
  newKey?: () => string;
}

const notYet = (m: Milestone): HorizonError =>
  new HorizonError("validation", "Not available on the local backend yet.", { retryable: false, details: { availableIn: m } });

/** A Promise-returning stub for a method whose milestone hasn't shipped. */
const later = (m: Milestone) => (): Promise<never> => Promise.reject(notYet(m));

const enc = encodeURIComponent;

class NoEventSource {
  onmessage: ((e: MessageEvent) => void) | null = null;
  addEventListener(): void {}
  close(): void {}
}

export class HttpClient implements HorizonClient {
  readonly kind = "http" as const;
  private readonly t: Transport;
  private readonly global: GlobalStream;
  private readonly streams: SessionStreams;

  constructor(opts: HttpClientOptions) {
    this.t = new Transport({ baseUrl: opts.baseUrl, fetch: opts.fetch, newKey: opts.newKey });
    const ES: EventSourceCtor = opts.EventSource ?? (globalThis as { EventSource?: EventSourceCtor }).EventSource ?? NoEventSource;
    this.global = new GlobalStream(this.t.url("/events"), ES);
    this.streams = new SessionStreams(
      (sid, since) => this.t.url(`/sessions/${enc(sid)}/stream`, { sinceSeq: since }),
      ES,
      (sid) => this.sessions.events(sid),
    );
  }

  settings: HorizonClient["settings"] = {
    get: () => this.t.get<AppSettings>("/settings"),
    update: later("M2"),
    setKey: later("M2"),
    testConnection: later("M2"),
    testModel: later("M2"),
  };

  worlds: HorizonClient["worlds"] = {
    list: () => this.t.get<World[]>("/worlds"),
    get: (id) => this.t.get<World>(`/worlds/${enc(id)}`),
    create: (input) => this.t.post<World>("/worlds", input),
    update: (id, patch) => this.t.patch<World>(`/worlds/${enc(id)}`, patch),
    delete: (id) => this.t.delete(`/worlds/${enc(id)}`),
    uploadCover: later("M4"),
  };

  characters: HorizonClient["characters"] = {
    list: (worldId, opts) => this.t.get<Character[]>(`/worlds/${enc(worldId)}/characters`, { includeArchived: opts?.includeArchived ? true : undefined }),
    get: (id) => this.t.get<Character>(`/characters/${enc(id)}`),
    assets: (id) => this.t.get<EmotionAsset[]>(`/characters/${enc(id)}/assets`),
    song: (id) => this.t.get<ThemeSong | null>(`/characters/${enc(id)}/song`),
    memory: (id) => this.t.get<MemoryItem[]>(`/characters/${enc(id)}/memory`),
    knowledge: (id) => this.t.get<KnowledgeSource[]>(`/characters/${enc(id)}/knowledge`),
    knowledgeSource: (sourceId) => this.t.get<{ source: KnowledgeSource; chunks: KnowledgeChunk[] }>(`/knowledge/${enc(sourceId)}`),
    createDraft: later("M4"),
    update: later("M4"),
    lockPortrait: later("M4"),
    approve: later("M4"),
    archive: later("M4"),
    restore: later("M4"),
    delete: later("M4"),
    acceptAssetVersion: later("M4"),
    topUpEnergy: later("M2"),
    setEnergyMax: later("M2"),
    forgetMemory: later("M5"),
    addKnowledge: later("M5"),
    deleteKnowledge: later("M5"),
    reindexKnowledge: later("M5"),
  };

  jobs: HorizonClient["jobs"] = {
    get: (jobId) => this.t.get<GenerationJob>(`/jobs/${enc(jobId)}`),
    listActive: () => this.t.get<GenerationJob[]>("/jobs", { active: true }),
    // No per-job stream (doc 03 §3): a snapshot, then the global stream filtered by jobId.
    subscribe: (jobId, cb) => {
      let open = true;
      const unsub = this.onGlobal((e) => {
        if (!open) return;
        if ((e.type === "job.progress" || e.type === "job.done") && e.job.id === jobId) cb({ type: e.type, job: e.job } as JobEvent);
        else if (e.type === "task.update" && e.jobId === jobId) cb({ type: "task.update", jobId, task: e.task });
      });
      void this.jobs.get(jobId).then((job) => open && cb({ type: "job.progress", job }), () => undefined);
      return () => {
        open = false;
        unsub();
      };
    },
    estimate: later("M4"),
    start: later("M4"),
    cancel: later("M4"),
    retryTask: later("M4"),
  };

  sessions: HorizonClient["sessions"] = {
    list: (worldId) => this.t.get<Session[]>(`/worlds/${enc(worldId)}/sessions`),
    get: (id) => this.t.get<SessionSnapshot>(`/sessions/${enc(id)}`),
    messages: (id) => collect<Message>(this.t, `/sessions/${enc(id)}/messages`),
    trace: (messageId) => this.t.get<TurnTrace | null>(`/messages/${enc(messageId)}/trace`),
    events: (id) => collect<SessionEvent>(this.t, `/sessions/${enc(id)}/events`),
    subscribe: (id, opts, cb): Unsubscribe => this.streams.subscribe(id, opts.sinceSeq, cb),
    create: later("M3"),
    rename: later("M3"),
    delete: later("M3"),
    forkSeedSession: later("M3"),
    export: later("M3"),
    leave: later("M3"),
    end: later("M3"),
  };

  chat: HorizonClient["chat"] = {
    send: later("M3"), stop: later("M3"), regenerate: later("M3"), setEmotion: later("M3"), setEmotionMode: later("M3"),
    setResponderPolicy: later("M3"), setMusicPolicy: later("M3"), setReadableMode: later("M3"), everyoneAnswer: later("M3"),
    nextSpeaker: later("M3"), muteParticipant: later("M3"),
  };

  debate: HorizonClient["debate"] = {
    pause: later("M3"), resume: later("M3"), next: later("M3"), setAutoAdvance: later("M3"), askCharacter: later("M3"),
    interject: later("M3"), extendRound: later("M3"), skipToClosing: later("M3"), endDebate: later("M3"), pickStrongerCase: later("M3"),
  };

  watch: HorizonClient["watch"] = {
    play: later("M3"), pause: later("M3"), step: later("M3"), setPace: later("M3"), direct: later("M3"), stepIn: later("M3"),
    extendWatch: later("M3"), summarise: later("M3"),
  };

  usage: HorizonClient["usage"] = {
    list: (opts) => collect<UsageRecord>(this.t, "/usage", { sinceDays: opts?.sinceDays }),
    summary: () => this.t.get<UsageSummary>("/usage/summary"),
  };

  admin: HorizonClient["admin"] = {
    resetDemo: () => this.t.post<void>("/admin/reset-demo", { confirm: true }),
  };

  onGlobal(cb: (e: GlobalEvent) => void): Unsubscribe {
    return this.global.subscribe(cb);
  }

  /** Close every stream (tests; the app keeps one client for its lifetime). */
  dispose(): void {
    this.global.close();
    this.streams.close();
  }

  /** Open EventSources (tests: the browser must never hold more than two). */
  get openStreams(): number {
    return (this.global.size ? 1 : 0) + this.streams.open;
  }
}

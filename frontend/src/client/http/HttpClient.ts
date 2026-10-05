// The HttpClient: HorizonClient over the local backend (doc backend/03 §5, http-client spec). Owner: SWE.
// Each milestone adds the methods for its own routes. A method whose backend hasn't shipped yet rejects at once,
// without a request, with a non-retryable `validation` error whose `details.availableIn` names the milestone.
import { HorizonError } from "../../contract/errors";
import type {
  AppSettings, Character, EmotionAsset, Energy, GenerationJob, KnowledgeChunk, KnowledgeSource, MemoryItem, Message, Session,
  SessionEvent, ThemeSong, TurnTrace, UsageRecord, World,
} from "../../contract/types";
import type {
  ConnectionResult, GlobalEvent, HorizonClient, JobEvent, ModelTestResult, SessionSnapshot, Unsubscribe, UsageSummary,
} from "../HorizonClient";
import { collect } from "./paging";
import { GlobalStream, SessionStreams } from "./sse";
import type { EventSourceCtor } from "./sse";
import { Transport } from "./transport";
import type { FetchLike } from "./transport";

export type Milestone = "M4" | "M5" | "M6";

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
    update: (patch) => this.t.patch<AppSettings>("/settings", patch),
    setKey: (key) => this.t.put<AppSettings>("/settings/key", { key }),
    testConnection: () => this.t.post<ConnectionResult>("/settings/test-connection"),
    testModel: (role) => this.t.post<ModelTestResult>("/settings/test-model", { role }),
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
    topUpEnergy: (id, points) => this.t.post<Energy>(`/characters/${enc(id)}/energy/top-up`, { points }),
    setEnergyMax: (id, points) => this.t.put<Energy>(`/characters/${enc(id)}/energy/max`, { points }),
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
    // M3 (session-runtime): the session lifecycle routes.
    create: (input) => this.t.post<SessionSnapshot>("/sessions", input),
    rename: (id, title) => this.t.patch<Session>(`/sessions/${enc(id)}`, { title }),
    delete: (id) => this.t.delete(`/sessions/${enc(id)}`),
    forkSeedSession: (id, atSeq) => this.t.post<SessionSnapshot>(`/sessions/${enc(id)}/fork`, atSeq === undefined ? {} : { atSeq }),
    export: (id) => this.t.getText(`/sessions/${enc(id)}/export`),
    leave: (id) => this.t.post<void>(`/sessions/${enc(id)}/leave`),
    end: (id) => this.t.post<void>(`/sessions/${enc(id)}/end`),
  };

  /** A session command: resolves once the backend accepts it (202); its effects arrive on the session stream. */
  private cmd(sid: string, name: string, body: object = {}): Promise<void> {
    return this.t.post<unknown>(`/sessions/${enc(sid)}/${name}`, body).then(() => undefined);
  }

  chat: HorizonClient["chat"] = {
    send: (sid, text, opts) => this.cmd(sid, "send", opts?.mentions?.length ? { text, mentions: opts.mentions } : { text }),
    stop: (sid) => this.cmd(sid, "stop"),
    regenerate: (sid, messageId) => this.cmd(sid, "regenerate", { messageId }),
    setEmotion: (sid, characterId, emotion) => this.cmd(sid, "set-emotion", { characterId, emotion }),
    setEmotionMode: (sid, mode) => this.cmd(sid, "set-emotion-mode", { mode }),
    setResponderPolicy: (sid, policy) => this.cmd(sid, "set-responder-policy", { policy }),
    setMusicPolicy: (sid, policy) => this.cmd(sid, "set-music-policy", { policy }),
    setReadableMode: (sid, on) => this.cmd(sid, "set-readable-mode", { on }),
    everyoneAnswer: (sid) => this.cmd(sid, "everyone-answer"),
    nextSpeaker: (sid, characterId) => this.cmd(sid, "next-speaker", characterId ? { characterId } : {}),
    muteParticipant: (sid, characterId, muted) => this.cmd(sid, "mute", { characterId, muted }),
  };

  debate: HorizonClient["debate"] = {
    pause: (sid) => this.cmd(sid, "debate/pause"),
    resume: (sid) => this.cmd(sid, "debate/resume"),
    next: (sid) => this.cmd(sid, "debate/next"),
    setAutoAdvance: (sid, on) => this.cmd(sid, "debate/auto-advance", { on }),
    askCharacter: (sid, characterId, text) => this.cmd(sid, "debate/ask", { characterId, text }),
    interject: (sid, text) => this.cmd(sid, "debate/interject", { text }),
    extendRound: (sid) => this.cmd(sid, "debate/extend-round"),
    skipToClosing: (sid) => this.cmd(sid, "debate/skip-to-closing"),
    endDebate: (sid, withVerdict) => this.cmd(sid, "debate/end", { withVerdict }),
    pickStrongerCase: (sid, side) => this.cmd(sid, "debate/pick", { side }),
  };

  watch: HorizonClient["watch"] = {
    play: (sid) => this.cmd(sid, "watch/play"),
    pause: (sid) => this.cmd(sid, "watch/pause"),
    step: (sid) => this.cmd(sid, "watch/step"),
    setPace: (sid, paceMs) => this.cmd(sid, "watch/pace", { paceMs }),
    direct: (sid, text) => this.cmd(sid, "watch/direct", { text }),
    stepIn: (sid, text) => this.cmd(sid, "watch/step-in", { text }),
    extendWatch: (sid, turns) => this.cmd(sid, "watch/extend", turns === undefined ? {} : { turns }),
    summarise: (sid) => this.cmd(sid, "watch/summarise"),
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

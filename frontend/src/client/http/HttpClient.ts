// The HttpClient: HorizonClient over the local backend (doc backend/03 §5, http-client spec). Owner: SWE.
// Each milestone added the methods for its own routes. Until M5 a method whose backend hadn't shipped rejected at once,
// without a request, with a non-retryable `validation` error naming the milestone (`details.availableIn`); from M5
// every method has a route, so nothing is held back.
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

export interface HttpClientOptions {
  /** "/api/v1" in the browser (Vite proxies it); an absolute URL in Node tests. */
  baseUrl: string;
  fetch?: FetchLike;
  /** The browser's EventSource by default; Node tests inject one. */
  EventSource?: EventSourceCtor;
  newKey?: () => string;
}

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
    // M4: multipart, one `file` part; the backend checks the content (magic bytes) and re-encodes it.
    uploadCover: (id, file) => {
      const form = new FormData();
      form.append("file", file, file.name || "cover");
      return this.t.postForm<World>(`/worlds/${enc(id)}/cover`, form);
    },
  };

  characters: HorizonClient["characters"] = {
    list: (worldId, opts) => this.t.get<Character[]>(`/worlds/${enc(worldId)}/characters`, { includeArchived: opts?.includeArchived ? true : undefined }),
    get: (id) => this.t.get<Character>(`/characters/${enc(id)}`),
    assets: (id) => this.t.get<EmotionAsset[]>(`/characters/${enc(id)}/assets`),
    song: (id) => this.t.get<ThemeSong | null>(`/characters/${enc(id)}/song`),
    memory: (id) => this.t.get<MemoryItem[]>(`/characters/${enc(id)}/memory`),
    knowledge: (id) => this.t.get<KnowledgeSource[]>(`/characters/${enc(id)}/knowledge`),
    knowledgeSource: (sourceId) => this.t.get<{ source: KnowledgeSource; chunks: KnowledgeChunk[] }>(`/knowledge/${enc(sourceId)}`),
    // M4 (generation-jobs): the character lifecycle.
    createDraft: (worldId, input) => this.t.post<{ character: Character; job: GenerationJob }>(`/worlds/${enc(worldId)}/characters`, input),
    update: (id, patch) => this.t.patch<Character>(`/characters/${enc(id)}`, patch),
    lockPortrait: (id, candidateId) => this.t.post<Character>(`/characters/${enc(id)}/lock-portrait`, { candidateId }),
    approve: (id) => this.t.post<Character>(`/characters/${enc(id)}/approve`),
    archive: (id) => this.t.post<Character>(`/characters/${enc(id)}/archive`),
    restore: (id) => this.t.post<Character>(`/characters/${enc(id)}/restore`),
    delete: (id) => this.t.delete(`/characters/${enc(id)}`),
    acceptAssetVersion: (assetId) => this.t.post<Character>(`/assets/${enc(assetId)}/accept`),
    topUpEnergy: (id, points) => this.t.post<Energy>(`/characters/${enc(id)}/energy/top-up`, { points }),
    setEnergyMax: (id, points) => this.t.put<Energy>(`/characters/${enc(id)}/energy/max`, { points }),
    // M5 (knowledge-memory-storage): knowledge sources and Forget. A file goes as multipart with one `file` part
    // (the backend checks magic bytes and limits while streaming); pasted text goes as JSON. Every POST carries an
    // Idempotency-Key (the transport adds it).
    forgetMemory: (memoryItemId) => this.t.delete(`/memory/${enc(memoryItemId)}`),
    addKnowledge: (id, input) => {
      if ("file" in input) {
        const form = new FormData();
        form.append("file", input.file, input.file.name || "upload");
        return this.t.postForm<KnowledgeSource>(`/characters/${enc(id)}/knowledge`, form);
      }
      return this.t.post<KnowledgeSource>(`/characters/${enc(id)}/knowledge`, input);
    },
    deleteKnowledge: (sourceId) => this.t.delete(`/knowledge/${enc(sourceId)}`),
    reindexKnowledge: (sourceId) => this.t.post<KnowledgeSource>(`/knowledge/${enc(sourceId)}/reindex`),
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
    // M4 (generation-jobs): `start` is refused before anything is queued (key, one active job, caps).
    estimate: (input) => this.t.post<{ estimatedCostUsd: number }>("/jobs/estimate", input),
    start: (input) => this.t.post<GenerationJob>("/jobs", input),
    cancel: (jobId) => this.t.post<GenerationJob>(`/jobs/${enc(jobId)}/cancel`).then(() => undefined),
    retryTask: (jobId, taskId) => this.t.post<GenerationJob>(`/jobs/${enc(jobId)}/tasks/${enc(taskId)}/retry`).then(() => undefined),
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

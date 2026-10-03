// Session runtime controllers (R1, R12): one per open session (live or replay), ref-counted by useSessionRuntime.
// Live: snapshot → subscribe(sinceSeq). Replay: recorded events → ScriptPlayer on the real clock (gaps trimmed).
// Both feed the same reducer; events are coalesced into one store write per frame, and streamed text goes to the
// streamText store through the StreamSmoother. Owner: EE.
import type { Message, Session, SessionEvent } from "../contract/types";
import { toHorizonError } from "../contract/errors";
import { realClock } from "../engine/clock";
import { replayInitial } from "../engine/replay";
import { ScriptPlayer, timelineFromEvents } from "../engine/ScriptPlayer";
import type { SessionRuntimeState } from "../engine/sessionReducer";
import { applyEvent, initialRuntime, reduceAll } from "../engine/sessionReducer";
import { prefs } from "../stores/prefs";
import { dropSlot, patchSlot, sessionStore, slotKey } from "../stores/session";
import type { ReplayInfo } from "../stores/session";
import { clearStream, flushStream, setStreamTarget } from "../stores/streamText";
import { client } from "./index";
import type { Unsubscribe } from "./HorizonClient";

export interface RuntimeControls {
  play(): void;
  pause(): void;
  /** Seek to a timeline position in ms (replay). */
  seek(ms: number): void;
  /** Seek to the state right after event `seq` (replay; route `t`). */
  seekSeq(seq: number): void;
  rate(r: number): void;
  /** Live timeline position (for a rAF scrubber). */
  position(): number;
}

const NOOP_CONTROLS: RuntimeControls = { play() {}, pause() {}, seek() {}, seekSeq() {}, rate() {}, position: () => 0 };
const PATCHABLE: (keyof Session)[] = ["title", "titleIsCustom", "config", "emotionMode", "musicPolicy", "readableMode"];

const raf: (cb: () => void) => unknown = typeof requestAnimationFrame !== "undefined" ? requestAnimationFrame : (cb) => setTimeout(cb, 16);

class Controller {
  readonly key: string;
  refs = 0;
  private queue: SessionEvent[] = [];
  private scheduled = false;
  private disposed = false;
  private unsub: Unsubscribe | null = null;
  private unglobal: Unsubscribe | null = null;
  private player: ScriptPlayer<SessionEvent> | null = null;
  private recorded: SessionEvent[] = [];
  private session: Session | null = null;
  private releaseTimer: ReturnType<typeof setTimeout> | null = null;
  readonly id: string;
  readonly replay: boolean;
  readonly controls: RuntimeControls;

  constructor(id: string, replay: boolean) {
    this.id = id;
    this.replay = replay;
    this.key = slotKey(id, replay);
    this.controls = replay ? this.replayControls() : NOOP_CONTROLS;
    patchSlot(this.key, { id, replay, status: "loading" });
    this.unglobal = client.onGlobal((e) => {
      if (e.type === "mock.reset") void this.start();
      else if (!replay && e.type === "entity.changed" && e.kind === "session" && e.id === id) void this.refreshFields();
    });
    void this.start();
  }

  private get runtime(): SessionRuntimeState | undefined {
    return sessionStore.getState().slots[this.key]?.runtime;
  }

  private async start(): Promise<void> {
    this.unsub?.();
    this.unsub = null;
    this.player?.dispose();
    this.player = null;
    this.queue = [];
    try {
      if (this.replay) await this.startReplay();
      else await this.startLive();
    } catch (err) {
      if (!this.disposed) patchSlot(this.key, { status: "error", error: toHorizonError(err).toJSON() });
    }
  }

  private async startLive(): Promise<void> {
    const snap = await client.sessions.get(this.id);
    if (this.disposed) return;
    this.session = snap.session;
    const runtime = { ...initialRuntime(snap.session, snap.messages), lastSeq: snap.lastSeq };
    patchSlot(this.key, { status: "ready", runtime, error: undefined });
    const streaming = snap.messages.find((m) => m.status === "streaming");
    if (streaming) setStreamTarget(streaming.id, streaming.content);
    this.unsub = client.sessions.subscribe(this.id, { sinceSeq: snap.lastSeq }, (e) => this.enqueue(e));
  }

  private async startReplay(): Promise<void> {
    const [snap, events] = await Promise.all([client.sessions.get(this.id), client.sessions.events(this.id)]);
    if (this.disposed) return;
    this.session = snap.session;
    this.recorded = events;
    const trim = prefs.getState().replayTrimGaps ? undefined : null;
    this.player = new ScriptPlayer(timelineFromEvents(events, { trimGapsMs: trim }), {
      clock: realClock,
      onEntry: (e) => this.enqueue(e),
      onEnd: () => {
        this.player?.pause();
        this.publishPlayer({ ended: true });
      },
      onState: () => this.publishPlayer(),
    });
    clearStream();
    patchSlot(this.key, { status: "ready", runtime: replayInitial(snap.session), error: undefined, player: this.playerInfo() });
    // Apply the opening snapshot (session.state + energy, first ~50 ms) so the stage shows the start, not the end.
    this.player.seek(50);
  }

  private async refreshFields(): Promise<void> {
    const rt = this.runtime;
    if (!rt) return;
    try {
      const { session } = await client.sessions.get(this.id);
      const cur = this.runtime;
      if (!cur || this.disposed) return;
      const patch: Partial<Session> = {};
      for (const k of PATCHABLE) {
        if (JSON.stringify(cur.session[k]) !== JSON.stringify(session[k])) (patch as Record<string, unknown>)[k] = session[k];
      }
      if (Object.keys(patch).length) patchSlot(this.key, { runtime: { ...cur, session: { ...cur.session, ...patch } } });
    } catch { /* keep the old fields */ }
  }

  private enqueue(e: SessionEvent): void {
    this.queue.push(e);
    if (this.scheduled) return;
    this.scheduled = true;
    raf(() => this.flush());
  }

  private flush(): void {
    this.scheduled = false;
    if (this.disposed || !this.queue.length) return;
    const events = this.queue;
    this.queue = [];
    let rt = this.runtime;
    if (!rt) return;
    const touched = new Set<string>();
    for (const e of events) {
      rt = applyEvent(rt, e);
      if (e.type === "token" || e.type === "turn.end" || e.type === "turn.start") touched.add((e.payload as { messageId: string }).messageId);
    }
    for (const id of touched) {
      const m: Message | undefined = rt.messages[id];
      if (m) setStreamTarget(id, m.content, m.status !== "streaming");
    }
    patchSlot(this.key, { runtime: rt, ...(this.player ? { player: this.playerInfo(rt.lastSeq) } : {}) });
  }

  // ── Replay transport ──
  private playerInfo(seq?: number): ReplayInfo {
    const p = this.player;
    return {
      playing: p?.isPlaying ?? false, position: p?.position ?? 0, duration: p?.duration ?? 0, rate: p?.currentRate ?? 1,
      ended: (p?.remaining ?? 1) === 0, seq: seq ?? this.runtime?.lastSeq ?? 0,
    };
  }

  private publishPlayer(extra?: Partial<ReplayInfo>): void {
    if (this.disposed) return;
    patchSlot(this.key, { player: { ...this.playerInfo(), ...extra } });
  }

  private rebuildTo(pos: number): void {
    const p = this.player;
    if (!p || !this.session) return;
    this.queue = [];
    const rt = reduceAll(replayInitial(this.session), p.itemsUpTo(pos));
    p.seek(pos, { deliver: false });
    clearStream();
    for (const m of Object.values(rt.messages)) if (m.status === "streaming") setStreamTarget(m.id, m.content);
    flushStream();
    patchSlot(this.key, { runtime: rt, player: this.playerInfo(rt.lastSeq) });
  }

  private replayControls(): RuntimeControls {
    return {
      play: () => {
        const p = this.player;
        if (!p) return;
        if (p.remaining === 0) this.rebuildTo(0);
        p.play();
      },
      pause: () => this.player?.pause(),
      seek: (ms) => {
        const p = this.player;
        if (!p) return;
        const target = Math.max(0, Math.min(ms, p.duration));
        if (target < p.position) this.rebuildTo(target);
        else {
          p.seek(target);
          raf(() => flushStream());
        }
      },
      seekSeq: (seq) => {
        const p = this.player;
        if (!p) return;
        const timeline = timelineFromEvents(this.recorded, { trimGapsMs: prefs.getState().replayTrimGaps ? undefined : null });
        const hit = timeline.find((x) => x.item!.seq >= seq);
        this.rebuildTo(hit ? hit.t : p.duration);
      },
      rate: (r) => this.player?.setRate(r),
      position: () => this.player?.position ?? 0,
    };
  }

  // ── Lifetime ──
  acquire(): void {
    this.refs++;
    if (this.releaseTimer) {
      clearTimeout(this.releaseTimer);
      this.releaseTimer = null;
    }
  }

  release(): void {
    this.refs = Math.max(0, this.refs - 1);
    if (this.refs > 0 || this.releaseTimer) return;
    // Deferred so StrictMode's mount → unmount → mount doesn't pause the session.
    this.releaseTimer = setTimeout(() => {
      this.releaseTimer = null;
      if (this.refs === 0) this.dispose();
    }, 300);
  }

  private dispose(): void {
    this.disposed = true;
    this.unsub?.();
    this.unglobal?.();
    this.player?.dispose();
    controllers.delete(this.key);
    const rt = this.runtime;
    if (!this.replay && rt && !rt.session.isSeed && rt.session.status === "active") void client.sessions.leave(this.id).catch(() => {});
    if (rt) clearStream(Object.keys(rt.messages));
    dropSlot(this.key);
  }
}

const controllers = new Map<string, Controller>();

export function acquireRuntime(id: string, replay: boolean): Controller {
  const key = slotKey(id, replay);
  let c = controllers.get(key);
  if (!c) {
    c = new Controller(id, replay);
    controllers.set(key, c);
  }
  c.acquire();
  return c;
}

export type { Controller as RuntimeController };

/** Stable controls object for a slot key (delegates to the live controller, no-ops before it exists). */
export function controlsFor(key: string): RuntimeControls {
  const get = () => controllers.get(key)?.controls ?? NOOP_CONTROLS;
  return {
    play: () => get().play(),
    pause: () => get().pause(),
    seek: (ms) => get().seek(ms),
    seekSeq: (seq) => get().seekSeq(seq),
    rate: (r) => get().rate(r),
    position: () => get().position(),
  };
}

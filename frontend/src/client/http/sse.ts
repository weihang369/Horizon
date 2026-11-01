// SSE for the HttpClient (doc backend/03 §4–§5): at most two EventSources (global + the open session).
// - Global: one shared EventSource, opened by the first `onGlobal` subscriber and closed after the last leaves.
// - Session: one stream at a time. Subscribers of the same session share it; a later subscriber that asks for older
//   events gets that backlog over HTTP while live events are held back, then everything is de-duplicated by `seq`.
//   Subscribing to another session closes the previous stream. Reconnects are the browser's (Last-Event-ID).
import type { SessionEvent, StreamEventType } from "../../contract/types";
import type { GlobalEvent, Unsubscribe } from "../HorizonClient";

export interface EventSourceLike {
  addEventListener(type: string, listener: (e: Event) => void): void;
  close(): void;
  onmessage: ((e: MessageEvent) => void) | null;
  readyState?: number;
}
export type EventSourceCtor = new (url: string) => EventSourceLike;

/** U-92: the browser reconnects after a network drop by itself, but an HTTP error answer (the dev proxy's 502 while
 * the backend starts or restarts) closes an EventSource for good: no more events until a reload. A closed stream is
 * reopened every RETRY_MS while anyone listens. */
export const RETRY_MS = 2000;
const CLOSED = 2;

export const SESSION_EVENT_TYPES: StreamEventType[] = [
  "turn.next", "turn.thinking", "turn.start", "token", "emotion", "turn.end", "energy", "reaction", "insight", "phase",
  "watch.state", "session.paused", "session.resumed", "budget.warning", "error", "message", "session.state",
];

const isMessage = (e: Event): e is MessageEvent => typeof (e as MessageEvent).data === "string";

export class GlobalStream {
  private es: EventSourceLike | null = null;
  private readonly subs = new Set<(e: GlobalEvent) => void>();

  private readonly url: string;
  private readonly ES: EventSourceCtor;

  constructor(url: string, ES: EventSourceCtor) {
    this.url = url;
    this.ES = ES;
  }

  private retry: ReturnType<typeof setTimeout> | null = null;
  private missed = false;

  subscribe(cb: (e: GlobalEvent) => void): Unsubscribe {
    this.subs.add(cb);
    if (!this.es && !this.retry) this.open();
    return () => {
      this.subs.delete(cb);
      if (!this.subs.size) this.stop();
    };
  }

  private open(): void {
    const es = new this.ES(this.url);
    this.es = es;
    es.onmessage = (m) => {
      let e: GlobalEvent;
      try {
        e = JSON.parse(m.data as string) as GlobalEvent;
      } catch {
        return;
      }
      for (const s of [...this.subs]) s(e);
    };
    // Reopened after a closed stream: whatever changed meanwhile was never announced, so every screen re-queries in
    // place (`mock.reset`'s meaning, as after Reset demo data).
    es.addEventListener("open", () => {
      if (!this.missed) return;
      this.missed = false;
      for (const s of [...this.subs]) s({ type: "mock.reset" });
    });
    es.addEventListener("error", () => {
      // The browser reconnects by itself (CONNECTING) after a backend restart: that open is a resync too (J6-04)
      if (this.es === es) this.missed = true;
      if (es.readyState !== CLOSED || this.es !== es) return;
      this.es = null;
      this.missed = true;
      this.retry = setTimeout(() => {
        this.retry = null;
        if (this.subs.size && !this.es) this.open();
      }, RETRY_MS);
    });
  }

  private stop(): void {
    if (this.retry) clearTimeout(this.retry);
    this.retry = null;
    this.es?.close();
    this.es = null;
  }

  get size(): number { return this.subs.size; }

  close(): void {
    this.subs.clear();
    this.stop();
  }
}

interface Sub { cb: (e: SessionEvent) => void; last: number; ready: boolean; held: SessionEvent[] }

export class SessionStreams {
  private current: { sessionId: string; es: EventSourceLike; subs: Set<Sub>; seq: number } | null = null;

  private readonly urlFor: (sessionId: string, sinceSeq: number) => string;
  private readonly ES: EventSourceCtor;
  private readonly backlog: (sessionId: string) => Promise<SessionEvent[]>;

  constructor(
    urlFor: (sessionId: string, sinceSeq: number) => string,
    ES: EventSourceCtor,
    backlog: (sessionId: string) => Promise<SessionEvent[]>,
  ) {
    this.urlFor = urlFor;
    this.ES = ES;
    this.backlog = backlog;
  }

  /** Open session streams (0 or 1): the browser keeps at most two EventSources with the global one. */
  get open(): number { return this.current ? 1 : 0; }

  subscribe(sessionId: string, sinceSeq: number, cb: (e: SessionEvent) => void): Unsubscribe {
    if (this.current && this.current.sessionId !== sessionId) this.closeCurrent();
    const sub: Sub = { cb, last: sinceSeq, ready: true, held: [] };
    if (!this.current) {
      const subs = new Set<Sub>();
      const onFrame = (m: Event) => {
        if (!isMessage(m)) return; // a connection error (EventSource reconnects by itself)
        let e: SessionEvent;
        try {
          e = JSON.parse(m.data) as SessionEvent;
        } catch {
          return;
        }
        if (this.current?.subs === subs && typeof e.seq === "number") this.current.seq = Math.max(this.current.seq, e.seq);
        for (const s of [...subs]) push(s, e);
      };
      // U-92: closed for good (see RETRY_MS): reopen from the last event seen; `emit` drops anything already delivered
      const open = (since: number): EventSourceLike => {
        const es = new this.ES(this.urlFor(sessionId, since));
        for (const t of SESSION_EVENT_TYPES) es.addEventListener(t, onFrame);
        es.addEventListener("error", () => {
          if (es.readyState !== CLOSED || this.current?.es !== es) return;
          setTimeout(() => {
            const cur = this.current;
            if (cur && cur.es === es && cur.subs.size) cur.es = open(cur.seq);
          }, RETRY_MS);
        });
        return es;
      };
      this.current = { sessionId, es: open(sinceSeq), subs, seq: sinceSeq };
    } else {
      // Joining an open stream: fetch what this subscriber is missing, holding live events until it's delivered.
      sub.ready = false;
      const release = (events: SessionEvent[]) => {
        for (const e of events) emit(sub, e);
        sub.ready = true;
        for (const e of sub.held.splice(0).sort((a, b) => a.seq - b.seq)) emit(sub, e);
      };
      void this.backlog(sessionId).then(release, () => release([]));
    }
    const cur = this.current;
    cur.subs.add(sub);
    return () => {
      cur.subs.delete(sub);
      if (this.current === cur && !cur.subs.size) this.closeCurrent();
    };
  }

  close(): void {
    this.closeCurrent();
  }

  private closeCurrent(): void {
    this.current?.es.close();
    this.current?.subs.clear();
    this.current = null;
  }
}

/** A live event: held while the subscriber's backlog is still loading. */
function push(s: Sub, e: SessionEvent): void {
  if (s.ready) emit(s, e);
  else s.held.push(e);
}

/** Deliver once, in order: anything at or below what this subscriber already has is dropped. */
function emit(s: Sub, e: SessionEvent): void {
  if (e.seq <= s.last) return;
  s.last = e.seq;
  s.cb(e);
}

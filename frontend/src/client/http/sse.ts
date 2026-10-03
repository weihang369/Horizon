// SSE for the HttpClient (doc backend/03 §4–§5): at most two EventSources (global + the open session). Owner: SWE.
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
}
export type EventSourceCtor = new (url: string) => EventSourceLike;

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

  subscribe(cb: (e: GlobalEvent) => void): Unsubscribe {
    this.subs.add(cb);
    if (!this.es) {
      this.es = new this.ES(this.url);
      this.es.onmessage = (m) => {
        let e: GlobalEvent;
        try {
          e = JSON.parse(m.data as string) as GlobalEvent;
        } catch {
          return;
        }
        for (const s of [...this.subs]) s(e);
      };
    }
    return () => {
      this.subs.delete(cb);
      if (!this.subs.size && this.es) {
        this.es.close();
        this.es = null;
      }
    };
  }

  get size(): number { return this.subs.size; }

  close(): void {
    this.subs.clear();
    this.es?.close();
    this.es = null;
  }
}

interface Sub { cb: (e: SessionEvent) => void; last: number; ready: boolean; held: SessionEvent[] }

export class SessionStreams {
  private current: { sessionId: string; es: EventSourceLike; subs: Set<Sub> } | null = null;

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
      const es = new this.ES(this.urlFor(sessionId, sinceSeq));
      const subs = new Set<Sub>();
      const onFrame = (m: Event) => {
        if (!isMessage(m)) return; // a connection error (EventSource reconnects by itself)
        let e: SessionEvent;
        try {
          e = JSON.parse(m.data) as SessionEvent;
        } catch {
          return;
        }
        for (const s of [...subs]) push(s, e);
      };
      for (const t of SESSION_EVENT_TYPES) es.addEventListener(t, onFrame);
      this.current = { sessionId, es, subs };
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

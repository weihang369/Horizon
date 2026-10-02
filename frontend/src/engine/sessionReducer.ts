// R1: the one pure reducer. Live mock, Replay, demo mode and the future HttpClient all feed doc 05 §6
// SessionEvents through `applyEvent`. No clocks, no randomness, no I/O: the same events always give the same state.
import type {
  DebatePhase, DebateState, Emotion, EnergyState, ErrorCode, Message, MessageUsage, Participant, PausedReason,
  Session, SessionEvent, StreamEvent, WatchState,
} from "../contract/types";

export interface RuntimeEnergy {
  current: number; max: number; state: EnergyState; fullAt?: string;
  /** ⚡ drained by the last event (drives the "−5 ⚡" float). */
  lastSpent?: number;
  /** ISO time of the last change. */
  at?: string;
}

export interface RuntimeError {
  code: ErrorCode; message: string; retryable: boolean; messageId?: string; at: string; seq: number;
}

export interface TurnTiming {
  messageId: string; characterId?: string;
  thinkingAt?: string; startAt: string; firstTokenAt?: string; emotionAt?: string; endAt?: string;
}

export interface PhaseInfo { phase: DebatePhase; round: number; iteration: number }
export interface WatchInfo { status: WatchState["status"]; paceMs: number; turnsTaken: number; turnLimit: number }

export interface SessionRuntimeState {
  session: Session;
  messages: Record<string, Message>;
  order: string[];
  /** What each portrait shows now (MANUAL ignores AI emotions; reactions apply in AUTO only). */
  displayEmotion: Record<string, Emotion>;
  /** A speaker emotion that arrived before the first token waits here (CHAT-03 AC4). */
  pendingEmotion: Record<string, Emotion>;
  energyById: Record<string, RuntimeEnergy>;
  phase: PhaseInfo | null;
  watch: WatchInfo | null;
  nextSpeakerId?: string;
  lastSkipped?: { characterId: string; reason: "exhausted" | "muted" | "archived" }[];
  /** Character currently "thinking" (typing … + lean-in). */
  thinkingId?: string;
  /** Message currently streaming. */
  streamingId?: string;
  /** Timing of the most recent character turn (feeds emotionHold). */
  turn?: TurnTiming;
  paused: boolean;
  pausedReason?: PausedReason;
  errors: RuntimeError[];
  budgetWarning?: { scope: "daily" | "creation"; spentUsd: number; capUsd: number; at: string };
  lastSeq: number;
  lastAt?: string;
}

export function initialRuntime(session: Session, messages: Message[] = []): SessionRuntimeState {
  const order = [...messages].sort((a, b) => a.seq - b.seq).map((m) => m.id);
  const displayEmotion: Record<string, Emotion> = {};
  for (const p of session.participants) displayEmotion[p.characterId] = p.currentEmotion;
  const st = session.state;
  return {
    session,
    messages: Object.fromEntries(messages.map((m) => [m.id, m])),
    order,
    displayEmotion,
    pendingEmotion: {},
    energyById: {},
    phase: st && "phase" in st ? { phase: st.phase, round: st.round, iteration: st.iteration } : null,
    watch: null,
    nextSpeakerId: st?.nextSpeakerId,
    paused: session.status === "paused",
    pausedReason: session.pausedReason,
    errors: [],
    lastSeq: 0,
  };
}

const isManual = (s: SessionRuntimeState) => s.session.emotionMode === "user";

function setDisplay(s: SessionRuntimeState, characterId: string, emotion: Emotion): SessionRuntimeState {
  if (s.displayEmotion[characterId] === emotion) return s;
  const participants = s.session.participants.map((p) =>
    p.characterId === characterId ? { ...p, currentEmotion: emotion } : p,
  );
  return {
    ...s,
    displayEmotion: { ...s.displayEmotion, [characterId]: emotion },
    session: { ...s.session, participants },
  };
}

function clearPending(s: SessionRuntimeState, characterId: string): SessionRuntimeState {
  if (!(characterId in s.pendingEmotion)) return s;
  const pendingEmotion = { ...s.pendingEmotion };
  delete pendingEmotion[characterId];
  return { ...s, pendingEmotion };
}

function putMessage(s: SessionRuntimeState, m: Message): SessionRuntimeState {
  const isNew = !s.messages[m.id];
  const order = isNew ? [...s.order, m.id] : s.order;
  return {
    ...s,
    messages: { ...s.messages, [m.id]: m },
    order,
    session: {
      ...s.session,
      messageCount: order.length,
      lastMessageAt: isNew ? m.createdAt : s.session.lastMessageAt,
    },
  };
}

function patchMessage(s: SessionRuntimeState, id: string, fn: (m: Message) => Message): SessionRuntimeState {
  const m = s.messages[id];
  if (!m) return s;
  return { ...s, messages: { ...s.messages, [id]: fn(m) } };
}

function nextMessageSeq(s: SessionRuntimeState): number {
  let max = 0;
  for (const id of s.order) max = Math.max(max, s.messages[id]?.seq ?? 0);
  return max + 1;
}

function patchState(s: SessionRuntimeState, patch: Partial<DebateState> | Partial<WatchState>): SessionRuntimeState {
  const st = s.session.state;
  if (!st) return s;
  return { ...s, session: { ...s.session, state: { ...st, ...patch } as DebateState | WatchState } };
}

/** Apply one event. Pure. Unknown or stale events are ignored. */
export function applyEvent(state: SessionRuntimeState, evt: SessionEvent): SessionRuntimeState {
  if (evt.seq <= state.lastSeq) return state;
  const e = { type: evt.type, payload: evt.payload } as StreamEvent;
  let s: SessionRuntimeState = {
    ...state,
    lastSeq: evt.seq,
    lastAt: evt.at,
    session: { ...state.session, updatedAt: evt.at },
  };

  switch (e.type) {
    case "turn.next": {
      s = { ...s, nextSpeakerId: e.payload.nextSpeakerId, lastSkipped: e.payload.skipped };
      s = patchState(s, { nextSpeakerId: e.payload.nextSpeakerId });
      return s;
    }
    case "turn.thinking":
      return { ...s, thinkingId: e.payload.characterId };

    case "turn.start": {
      const { messageId, author, emotion, variantId } = e.payload;
      const existing = s.messages[messageId];
      if (existing && variantId) {
        // Regenerate: the original becomes variant 1, the new one streams as the active variant.
        const variants = existing.variants?.length
          ? existing.variants
          : [{ id: existing.activeVariantId ?? `${messageId}_v1`, content: existing.content, emotion: existing.emotion, createdAt: existing.createdAt }];
        s = patchMessage(s, messageId, (m) => ({
          ...m,
          variants: [...variants, { id: variantId, content: "", createdAt: evt.at }],
          activeVariantId: variantId,
          content: "",
          status: "streaming",
          interruptedBy: undefined,
          usage: undefined,
          trace: undefined,
          error: undefined,
        }));
      } else if (!existing) {
        const extra = e.payload.message ?? {};
        const m: Message = {
          kind: "chat",
          ...extra,
          id: messageId,
          sessionId: s.session.id,
          seq: extra.seq ?? nextMessageSeq(s),
          author,
          content: "",
          status: "streaming",
          createdAt: evt.at,
        };
        s = putMessage(s, m);
      }
      s = {
        ...s,
        streamingId: messageId,
        thinkingId: undefined,
        turn: { messageId, characterId: author.characterId, startAt: evt.at, thinkingAt: state.thinkingId ? state.lastAt : undefined },
      };
      if (emotion && author.characterId) {
        s = applyEmotion(s, messageId, author.characterId, emotion, "llm", evt.at);
      }
      return s;
    }

    case "token": {
      const { messageId, delta, variantId } = e.payload;
      const m = s.messages[messageId];
      if (!m) return s;
      const first = !s.turn?.firstTokenAt && s.turn?.messageId === messageId;
      s = patchMessage(s, messageId, (msg) => ({
        ...msg,
        content: msg.content + delta,
        variants: variantId && msg.variants
          ? msg.variants.map((v) => (v.id === variantId ? { ...v, content: v.content + delta } : v))
          : msg.variants,
      }));
      if (first && s.turn) {
        s = { ...s, turn: { ...s.turn, firstTokenAt: evt.at } };
        const cid = m.author.characterId;
        if (cid && s.pendingEmotion[cid]) {
          const pe = s.pendingEmotion[cid];
          s = clearPending(s, cid);
          if (!isManual(s)) s = setDisplay(s, cid, pe);
        }
      }
      return s;
    }

    case "emotion": {
      const { messageId, characterId, emotion, source } = e.payload;
      return applyEmotion(s, messageId, characterId, emotion, source, evt.at);
    }

    case "turn.end": {
      const { messageId, status, interruptedBy, usage, variantId } = e.payload;
      s = patchMessage(s, messageId, (m) => ({
        ...m,
        status,
        interruptedBy,
        usage: usage ?? m.usage,
        variants: variantId && m.variants ? m.variants : m.variants,
      }));
      const m = s.messages[messageId];
      if (m?.author.characterId && s.pendingEmotion[m.author.characterId]) {
        const cid = m.author.characterId;
        const pe = s.pendingEmotion[cid];
        s = clearPending(s, cid);
        if (!isManual(s)) s = setDisplay(s, cid, pe);
      }
      s = {
        ...s,
        streamingId: s.streamingId === messageId ? undefined : s.streamingId,
        turn: s.turn?.messageId === messageId ? { ...s.turn, endAt: evt.at } : s.turn,
        session: { ...s.session, costUsd: round6(s.session.costUsd + (usage?.costUsd ?? 0)) },
      };
      return s;
    }

    case "energy": {
      const { characterId, current, max, state: es, fullAt, spent } = e.payload;
      return {
        ...s,
        energyById: { ...s.energyById, [characterId]: { current, max, state: es, fullAt, lastSpent: spent, at: evt.at } },
      };
    }

    case "reaction": {
      const { messageId, characterId, emotion, p } = e.payload;
      s = patchMessage(s, messageId, (m) => ({
        ...m,
        reactions: [...(m.reactions ?? []), p === undefined ? { characterId, emotion, at: evt.at } : { characterId, emotion, p, at: evt.at }],
      }));
      if (!isManual(s)) s = setDisplay(s, characterId, emotion);
      return s;
    }

    case "insight":
      return patchMessage(s, e.payload.messageId, (m) => ({ ...m, trace: e.payload.trace }));

    case "phase": {
      const { phase, round, iteration } = e.payload;
      s = { ...s, phase: { phase, round, iteration } };
      return patchState(s, { phase, round, iteration });
    }

    case "watch.state": {
      const { status, paceMs, turnsTaken, turnLimit } = e.payload;
      s = { ...s, watch: { status, paceMs, turnsTaken, turnLimit } };
      return patchState(s, { status, turnsTaken, turnLimit });
    }

    case "session.paused":
      return {
        ...s,
        paused: true,
        pausedReason: e.payload.reason,
        session: { ...s.session, status: "paused", pausedReason: e.payload.reason },
      };

    case "session.resumed":
      return {
        ...s,
        paused: false,
        pausedReason: undefined,
        session: { ...s.session, status: "active", pausedReason: undefined },
      };

    case "budget.warning":
      return { ...s, budgetWarning: { ...e.payload, at: evt.at } };

    case "error": {
      const { code, message, retryable, messageId } = e.payload;
      s = { ...s, errors: [...s.errors, { code, message, retryable, messageId, at: evt.at, seq: evt.seq }] };
      if (messageId) s = patchMessage(s, messageId, (m) => ({ ...m, error: { code, message, retryable } }));
      return s;
    }

    case "message": {
      const m = e.payload.message;
      s = putMessage(s, m);
      const cid = m.author.characterId;
      if (cid && m.emotion && m.author.type === "character" && !isManual(s)) s = setDisplay(s, cid, m.emotion);
      if (m.usage?.costUsd) s = { ...s, session: { ...s.session, costUsd: round6(s.session.costUsd + m.usage.costUsd) } };
      return s;
    }

    case "session.state": {
      const { status, pausedReason, state: st, participants } = e.payload;
      let session: Session = { ...s.session };
      if (status) {
        session = { ...session, status, pausedReason: status === "paused" ? pausedReason ?? session.pausedReason : undefined };
      } else if (pausedReason) {
        session = { ...session, pausedReason };
      }
      if (st) session = { ...session, state: st };
      if (participants) session = { ...session, participants };
      s = {
        ...s,
        session,
        paused: session.status === "paused",
        pausedReason: session.pausedReason,
      };
      if (st && "phase" in st) s = { ...s, phase: { phase: st.phase, round: st.round, iteration: st.iteration }, nextSpeakerId: st.nextSpeakerId ?? s.nextSpeakerId };
      if (st && "turnsTaken" in st) {
        s = { ...s, watch: { status: st.status, paceMs: s.watch?.paceMs ?? 0, turnsTaken: st.turnsTaken, turnLimit: st.turnLimit } };
      }
      if (participants) {
        const displayEmotion = { ...s.displayEmotion };
        for (const p of participants) displayEmotion[p.characterId] = p.currentEmotion;
        s = { ...s, displayEmotion };
      }
      return s;
    }
  }
  return s;
}

function applyEmotion(
  s: SessionRuntimeState, messageId: string | undefined, characterId: string, emotion: Emotion,
  source: "user" | "llm" | "classifier" | "default", at: string,
): SessionRuntimeState {
  if (!messageId) {
    // MANUAL face change (D-51): no message, source "user".
    return setDisplay(clearPending(s, characterId), characterId, emotion);
  }
  s = patchMessage(s, messageId, (m) => ({
    ...m,
    emotion,
    emotionSource: source,
    variants: m.activeVariantId && m.variants
      ? m.variants.map((v) => (v.id === m.activeVariantId ? { ...v, emotion } : v))
      : m.variants,
  }));
  if (s.turn?.messageId === messageId) s = { ...s, turn: { ...s.turn, emotionAt: s.turn.emotionAt ?? at } };
  if (isManual(s)) return s; // recorded for Insight, not displayed (CHAT-04 AC5)
  const m = s.messages[messageId];
  const streamingBeforeFirstToken = m && m.status === "streaming" && m.content === "" && s.turn?.messageId === messageId && !s.turn.firstTokenAt;
  if (streamingBeforeFirstToken) {
    // Shown at stream start (first token), not before.
    return { ...s, pendingEmotion: { ...s.pendingEmotion, [characterId]: emotion } };
  }
  return setDisplay(s, characterId, emotion);
}

const round6 = (n: number) => Math.round(n * 1e6) / 1e6;

/** Reduce a whole script. */
export function reduceAll(initial: SessionRuntimeState, events: SessionEvent[]): SessionRuntimeState {
  let s = initial;
  for (const e of events) s = applyEvent(s, e);
  return s;
}

/** Ordered message list. */
export const orderedMessages = (s: SessionRuntimeState): Message[] =>
  s.order.map((id) => s.messages[id]).filter((m): m is Message => Boolean(m));

/** Was this batch only `token` events? (Used to avoid republishing the whole runtime per frame, R12.) */
export const isTokenOnly = (events: SessionEvent[]): boolean => events.every((e) => e.type === "token");

export type { MessageUsage, Participant };

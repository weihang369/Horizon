// Screenplay format: doc 06 transcripts as typed beats. The compiler turns them into SessionEvents (R2).
import type {
  DebatePhase, DebateState, Emotion, MessageUsage, PausedReason, Session, Side, TurnTrace, Verdict, WatchState,
} from "../../src/contract/types";
import type { EmotionTiming } from "../../src/mock/script/turnScript";

export type Beat =
  /** The user speaks (chat), steers a debate (steer/interject) or directs a scene (direction). */
  | { k: "user"; text: string; kind?: "chat" | "steer" | "interject" | "direction"; target?: string; gapMs?: number }
  /** A character turn. */
  | {
      k: "line"; who: string; emotion: Emotion; text: string;
      reactions?: Partial<Record<string, Emotion>>;
      /** Explicit reaction delays (ms after turn.end) and probabilities, by character. */
      reactionTiming?: Partial<Record<string, { delayMs?: number; p?: number }>>;
      forcedBy?: "user_ask" | "mention" | "nudge" | "round_order";
      side?: Side;
      emotionTiming?: EmotionTiming;
      /** Absolute ISO time for turn.start (anchors the whole session timeline). */
      at?: string;
      usage?: MessageUsage;
      trace?: TurnTrace;
      contextInSession?: TurnTrace["contextInSession"];
      memory?: NonNullable<TurnTrace["memory"]>["recalled"];
      /** Group routing candidates (Auto responders). */
      candidates?: { characterId: string; p: number }[];
      gapMs?: number;
    }
  /** MANUAL face change by the user (D-51). */
  | { k: "face"; who: string; emotion: Emotion }
  /** Debate phase boundary: `phase` event + a system_note divider in the log. */
  | { k: "phase"; phase: DebatePhase; round: number; iteration?: number; label?: string }
  /** AI host narration (moderator: auto_host). */
  | { k: "host"; text: string }
  | { k: "system"; text: string }
  | { k: "verdict"; verdict: Verdict; text: string }
  /** End: ended (debate) or paused (watch turn cap, user leaving). */
  | { k: "end"; status: "ended" | "paused"; reason?: PausedReason }
  | { k: "wait"; ms: number };

export interface Screenplay {
  /** Short code used in ids: msg_<msgKey>01, evt_<evtKey>0001. */
  msgKey: string;
  evtKey: string;
  /** Session start (ISO). Ignored when a beat has `at` (the anchor wins). */
  startAt: string;
  session: Omit<Session, "costUsd" | "messageCount" | "createdAt" | "updatedAt" | "lastMessageAt" | "status" | "pausedReason" | "state"> & {
    initialState: DebateState | WatchState | null;
  };
  beats: Beat[];
  /** seed/ (shipped) or seed/_mock (UI-phase only). */
  mock: boolean;
  /** Price period for every reply (rush hour fixtures use "peak"). */
  period?: "peak" | "off_peak";
}

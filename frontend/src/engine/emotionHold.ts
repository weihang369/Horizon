// CHAT-03 AC4 / NFR-29: the portrait holds a subtle "lean-in" while waiting for the speaker's emotion,
// for at most 800 ms after the first token; if the emotion arrives later it switches late. Never blank.
import type { Emotion } from "../contract/types";
import type { SessionRuntimeState } from "./sessionReducer";

export const EMOTION_HOLD_MS = 800;

export interface EmotionHoldInput {
  /** What the reducer says the portrait shows (already respects MANUAL and pending-until-first-token). */
  display: Emotion;
  thinking: boolean;
  streaming: boolean;
  /** Epoch ms of the first token of the current turn, if any. */
  firstTokenAt?: number;
  /** Epoch ms the emotion for the current turn arrived, if any. */
  emotionAt?: number;
  manual: boolean;
}

export interface EmotionHoldResult {
  emotion: Emotion;
  /** Show the lean-in pose. */
  leanIn: boolean;
  /** ms until the result may change on its own (for scheduling a re-render), or null. */
  recheckInMs: number | null;
}

export function emotionHold(i: EmotionHoldInput, nowMs: number): EmotionHoldResult {
  if (i.manual) return { emotion: i.display, leanIn: i.thinking, recheckInMs: null };
  if (i.thinking) return { emotion: i.display, leanIn: true, recheckInMs: null };
  if (i.streaming && i.emotionAt === undefined) {
    if (i.firstTokenAt === undefined) return { emotion: i.display, leanIn: true, recheckInMs: null };
    const waited = nowMs - i.firstTokenAt;
    if (waited < EMOTION_HOLD_MS) return { emotion: i.display, leanIn: true, recheckInMs: EMOTION_HOLD_MS - waited };
    return { emotion: i.display, leanIn: false, recheckInMs: null };
  }
  return { emotion: i.display, leanIn: false, recheckInMs: null };
}

/** Build the hold input for one character from the runtime state. */
export function holdInputFor(s: SessionRuntimeState, characterId: string): EmotionHoldInput {
  const turn = s.turn?.characterId === characterId ? s.turn : undefined;
  const streaming = Boolean(turn && s.streamingId === turn.messageId);
  return {
    display: s.displayEmotion[characterId] ?? "neutral",
    thinking: s.thinkingId === characterId,
    streaming,
    firstTokenAt: turn?.firstTokenAt ? Date.parse(turn.firstTokenAt) : undefined,
    emotionAt: turn?.emotionAt ? Date.parse(turn.emotionAt) : undefined,
    manual: s.session.emotionMode === "user",
  };
}

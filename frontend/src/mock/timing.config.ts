// APP-07: every simulated-AI timing lives in this one file. Demo speed (×1/×2/×4) divides all of them.
export interface TimingConfig {
  /** Delay from send to the typing indicator (≤ 100 ms, CHAT-02). */
  thinkingMs: number;
  /** Send → first token. */
  firstTokenMs: number;
  /** Streaming speed. */
  tokensPerSec: number;
  /** Characters per token when chunking text. */
  charsPerToken: number;
  /** Tokens per emitted `token` event (deltas are coalesced in the UI anyway). */
  tokensPerEvent: number;
  /** Gap between turn.end and the next turn.next (≤ 500 ms, NFR-02). */
  turnGapMs: number;
  /** Listener reactions arrive this long after turn.end. */
  reactionDelayMs: [number, number];
  /** Probability that a listener reacts at all. */
  reactionChance: number;
  /** Emotion arrival relative to the first token: [before, early (≤ 800 ms), late] probabilities. */
  emotionTiming: { before: number; early: number; late: number };
  lateEmotionMs: number;
  profileDraftMs: number;
  fieldRegenerateMs: number;
  portraitMs: number;
  portraitParallel: number;
  emotionMs: number;
  emotionParallel: number;
  sheetMs: number;
  songMs: number;
  /** Job progress tick. */
  jobTickMs: number;
  /** Debate: VS splash length before the first turn. Watch: curtain. */
  debateStartMs: number;
  watchStartMs: number;
  /** Greeting delay on a new 1:1 session. */
  greetingMs: number;
}

export const DEFAULT_TIMING: TimingConfig = {
  thinkingMs: 60,
  firstTokenMs: 1500,
  tokensPerSec: 40,
  charsPerToken: 4,
  tokensPerEvent: 3,
  turnGapMs: 400,
  reactionDelayMs: [300, 800],
  reactionChance: 0.7,
  emotionTiming: { before: 0.7, early: 0.25, late: 0.05 },
  lateEmotionMs: 1200,
  profileDraftMs: 4000,
  fieldRegenerateMs: 2000,
  portraitMs: 20000,
  portraitParallel: 2,
  emotionMs: 15000,
  emotionParallel: 2,
  sheetMs: 30000,
  songMs: 40000,
  jobTickMs: 250,
  debateStartMs: 1600,
  watchStartMs: 800,
  greetingMs: 300,
};

export type DemoSpeed = 1 | 2 | 4;
export const DEMO_SPEEDS: DemoSpeed[] = [1, 2, 4];

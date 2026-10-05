// Backend runtime knobs (session-runtime design D9), emitted with the mock's timing table into seed/runtime.json, so
// the backend paces live sessions from the same committed numbers the MockClient uses. The mock never reads this file.
// Owner: SWE.
export interface RuntimeConfig {
  /** Per-mode reply caps (`max_tokens`) for the naive turn engine; debate by turn length. */
  replyMaxTokens: { one_on_one: number; group: number; watch: number; debate: { short: number; medium: number; long: number } };
  /** History window in tokens; when full, the oldest half is dropped in one step (cache-friendly). */
  windowTokens: number;
  /** Token coalescing: flush at this many characters or this much clock time since the first buffered delta. */
  coalesce: { maxChars: number; maxMs: number };
  /** A live session with no subscribers and no work releases its runtime after this much clock time. */
  idleReleaseMs: number;
  /** Opening turns generated ahead of their slot (debate opening round, group everyone-answer). */
  prefetchMax: number;
  /** Concurrent LLM calls (shared with M4's job scheduler). */
  llmConcurrency: number;
}

export const RUNTIME: RuntimeConfig = {
  replyMaxTokens: { one_on_one: 350, group: 250, watch: 220, debate: { short: 200, medium: 320, long: 480 } },
  windowTokens: 6000,
  coalesce: { maxChars: 48, maxMs: 50 },
  idleReleaseMs: 600_000,
  prefetchMax: 2,
  llmConcurrency: 4,
};

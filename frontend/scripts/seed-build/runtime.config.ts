// Backend runtime knobs (session-runtime design D9), emitted with the mock's timing table into seed/runtime.json, so
// the backend paces live sessions from the same committed numbers the MockClient uses. The mock never reads this file.
// Owner: SWE.
/** One settings row per DeepSeek call type (docs/ai/03 C1, C2): code never hard-codes these. Owner: AI. */
export interface LlmCallRow {
  /** off = `reasoning: {enabled: false}` (every call today); low / high only after the latency suite passes again. */
  thinking: "off" | "low" | "high";
  /** null = send no temperature (the provider default). */
  temperature: number | null;
  output: "stream" | "text" | "json";
  /** A fixed safety net, for calls whose cap isn't per mode (replies use `replyMaxTokens`). */
  maxTokens?: number;
}

export interface RuntimeConfig {
  /** Per-mode reply caps (`max_tokens`), a safety net about 1.5–2× the prompt's length target (docs/ai/03 C4);
   *  `one_on_one_deep` is used once a turn plan says the turn is deep (M9); debate by turn length. */
  replyMaxTokens: {
    one_on_one: number; one_on_one_deep: number; group: number; watch: number;
    debate: { short: number; medium: number; long: number };
  };
  /** docs/ai/03 C1: the DeepSeek call settings, by call key. */
  llm: { calls: Record<string, LlmCallRow> };
  /** History window in tokens per mode (docs/ai/05 X2): past it, the newest half is kept and the rest folds into the
   *  rolling summary, after the reply (cache-friendly). */
  windowTokens: { one_on_one: number; group: number; watch: number; debate: number };
  /** Token coalescing: flush at this many characters or this much clock time since the first buffered delta. */
  coalesce: { maxChars: number; maxMs: number };
  /** A live session with no subscribers and no work releases its runtime after this much clock time. */
  idleReleaseMs: number;
  /** Opening turns generated ahead of their slot (debate opening round, group everyone-answer). */
  prefetchMax: number;
  /** Concurrent LLM calls (shared with M4's job scheduler). */
  llmConcurrency: number;
  /** M5 retrieval (knowledge-memory-storage design D12, D13): hits per reply, and how long a reply waits for the
   *  user message's query embedding before using keyword retrieval alone. AI-stage tunables. */
  retrieval: { knowledgeK: number; memoryK: number; queryEmbedWaitMs: number };
  /** docs/ai/04 P8: the dynamic-tail repeat hint, off until the repetition metric misses its target (doc 13 W12). */
  persona: { repeatHint: boolean };
  /** docs/ai/05 X5: the dynamic-tail voice reminder, off until the long suite shows drift (doc 13 W12). */
  context: { voiceReminder: boolean };
}

export const RUNTIME: RuntimeConfig = {
  replyMaxTokens: {
    one_on_one: 200, one_on_one_deep: 300, group: 150, watch: 150, debate: { short: 200, medium: 320, long: 480 },
  },
  llm: {
    calls: {
      "reply.chat": { thinking: "off", temperature: 1.0, output: "stream" },   // M8 (persona-context D34, the user): 1.3 collapsed long chats
      "reply.debate": { thinking: "off", temperature: 1.0, output: "stream" },
      host: { thinking: "off", temperature: 1.0, output: "text", maxTokens: 120 },
      verdict: { thinking: "off", temperature: 0.7, output: "json", maxTokens: 1200 },
      summary: { thinking: "off", temperature: 0.7, output: "text", maxTokens: 600 },
      episode: { thinking: "off", temperature: 0.7, output: "text", maxTokens: 400 },
      memory: { thinking: "off", temperature: 0.7, output: "json" },
      query_rewrite: { thinking: "off", temperature: 0.0, output: "text", maxTokens: 60 },
      profile: { thinking: "off", temperature: 1.0, output: "json", maxTokens: 2400 },
      probe: { thinking: "off", temperature: null, output: "text", maxTokens: 1 },
    },
  },
  windowTokens: { one_on_one: 6000, group: 9000, watch: 9000, debate: 9000 },
  coalesce: { maxChars: 48, maxMs: 50 },
  idleReleaseMs: 600_000,
  prefetchMax: 2,
  llmConcurrency: 4,
  retrieval: { knowledgeK: 5, memoryK: 3, queryEmbedWaitMs: 400 },
  persona: { repeatHint: false },
  context: { voiceReminder: false },
};

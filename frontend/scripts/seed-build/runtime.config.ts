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

/** M12 (docs/ai/10 K5–K7, K15; doc 13 W12; rag D26): the `agent` deep path's knobs. `naive` and `scripted` keep
 *  `knowledgeK`, `memoryK` and `queryEmbedWaitMs`. AI-stage tunables; the thresholds live in the question bank. */
export interface AgentRetrieval {
  /** BM25 and dense lists, each this long (K5). */
  pool: number;
  /** Candidates picked by MMR from the top `pool` and checked by Jev call 2 (K5, K6). */
  candidates: number;
  /** The documents block's ceiling (K8). */
  blockTokens: number;
  /** MMR's relevance weight; 1.0 turns it off (K5). */
  mmrLambda: number;
  /** Passages kept per reply, by mode (K7). */
  k: { oneOnOne: number; group: number; watch: number; debate: number };
  /** `pack@2`'s piece target and ceiling (K1), recorded here for the evaluation's arms. */
  pieceTarget: number;
  pieceMax: number;
  /** The query rewrite's deadline from its start (K4). */
  rewriteMs: number;
  /** Each `deep_check` request's deadline from when it was sent (K6). */
  deepCheckMs: number;
  /** The deep path's wait for a query embedding from when the search needs it (rag 11.5: 800, the embedding starting
   *  with Jev call 1; the top-level `queryEmbedWaitMs` stays naive's). */
  queryEmbedWaitMs: number;
  /** M13 (docs/ai/09 M9; memory design D31–D35, D42): recall's search, Jev call 2 and tail; `t_recall` is in the bank. */
  recall: RecallKnobs;
}

export interface RecallKnobs {
  /** BM25 and dense lists per corpus. */
  pool: number;
  /** At most this many from each corpus (the session's lines, the overflow memories) into the merge. */
  perCorpus: number;
  /** MMR's picks over the merge, each checked by Jev call 2. */
  candidates: number;
  mmrLambda: number;
  /** Kept at or above `t_recall`, by p. */
  keep: number;
  /** Every answer missing: this many from the top of the merged order, unscored. */
  fallbackKeep: number;
  /** Each recall check's deadline from when it was sent. */
  checkMs: number;
  /** Both recall headings in the tail together. */
  tailTokens: number;
  /** A line hit and the message before it, each at most this many words. */
  lineWords: number;
}

/** M13 (docs/ai/09 M1, M2, M4–M8; doc 13 W12; memory design D42): pause runs and the memory list. AI-stage
 *  tunables; the guard's `t_keep` lives in the question bank. The mock never writes memories. */
export interface MemoryKnobs {
  /** Doc 09 M1 trigger 1: the session stream left with nobody back this long starts a pause run. */
  leaveGraceMs: number;
  /** Pause runs at once (never the reply slots). */
  maxConcurrent: number;
  /** Doc 09 M2: a longer stretch runs in pieces of this many tokens. */
  pieceTokens: number;
  /** Doc 09 M6: failed tries on one checkpoint before the piece is skipped. */
  maxTries: number;
  /** Doc 09 M8: the memory list in system message 1, filled to this many tokens. */
  blockTokens: number;
  /** Recency = max(recencyFloor, 0.5 ^ (days / halfLifeDays)). */
  halfLifeDays: number;
  recencyFloor: number;
  /** D-71's down-weighting by the memory's source mode. */
  modeWeight: { oneOnOne: number; group: number; debate: number; watch: number };
  /** Doc 09 M4: an added line scored under this is dropped. */
  minImportance: number;
  /** Doc 09 M5: an added line this close (cosine) to a current memory reinforces it instead. */
  dupCosine: number;
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
  retrieval: { knowledgeK: number; memoryK: number; queryEmbedWaitMs: number; agent: AgentRetrieval };
  /** docs/ai/04 P8: the dynamic-tail repeat hint, off until the repetition metric misses its target (doc 13 W12).
   *  docs/ai/06 E4: the mood line, off since M9's on/off run found no gain (turn-plan-emotion D40). */
  persona: { repeatHint: boolean; moodLine: boolean };
  /** docs/ai/05 X5: the dynamic-tail voice reminder, off until the long suite shows drift (doc 13 W12). */
  context: { voiceReminder: boolean };
  /** docs/ai/06 E3 (doc 13 W12): a kept face in this set becomes neutral, for the speaker and for listeners. */
  emotion: { fade: string[] };
  /** M11 (doc 08 V6; debate D11): how long the Auto host's written line may hold the debate: the welcome until Start +
   *  this, every other line until its banner + this; then the fixed sentence shows. The mock's host is instant. */
  debate: { hostWelcomeWaitMs: number; hostBannerWaitMs: number };
  /** M13: pause runs and the memory list. */
  memory: MemoryKnobs;
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
  retrieval: {
    knowledgeK: 5, memoryK: 3, queryEmbedWaitMs: 400,
    agent: {
      pool: 20, candidates: 8, blockTokens: 1400, mmrLambda: 1.0, k: { oneOnOne: 3, group: 2, watch: 2, debate: 2 },
      pieceTarget: 300, pieceMax: 400, rewriteMs: 1200, deepCheckMs: 1500, queryEmbedWaitMs: 200,
      // M13 (memory D42): recall's numbers, tuned in phase 10
      recall: { pool: 10, perCorpus: 5, candidates: 6, mmrLambda: 0.7, keep: 3, fallbackKeep: 2, checkMs: 1500,
        tailTokens: 400, lineWords: 60 },
    },
  },
  persona: { repeatHint: false, moodLine: false },
  context: { voiceReminder: false },
  emotion: { fade: ["surprised", "embarrassed"] },   // M9 (turn-plan-emotion D13): moments, not moods
  debate: { hostWelcomeWaitMs: 3000, hostBannerWaitMs: 1500 },
  memory: {
    leaveGraceMs: 30_000, maxConcurrent: 2, pieceTokens: 8000, maxTries: 3, blockTokens: 1000, halfLifeDays: 30,
    recencyFloor: 0.5, modeWeight: { oneOnOne: 1.0, group: 1.0, debate: 0.85, watch: 0.7 }, minImportance: 0.25,
    dupCosine: 0.92,
  },
};

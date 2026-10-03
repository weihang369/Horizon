// Reducer unit tests (R1). Owner: EE.
import { describe, expect, it } from "vitest";
import type { Session, SessionEvent, StreamEvent } from "../contract/types";
import { applyEvent, initialRuntime, orderedMessages, reduceAll } from "./sessionReducer";

const T0 = Date.parse("2026-10-01T10:00:00Z");
const session = (over: Partial<Session> = {}): Session => ({
  id: "ses_t", worldId: "wld_t", title: "t", titleIsCustom: false, mode: "one_on_one", status: "active",
  participants: [{ characterId: "chr_a", role: "speaker", currentEmotion: "neutral", mutedByUser: false }, { characterId: "chr_b", role: "speaker", currentEmotion: "neutral", mutedByUser: false }],
  emotionMode: "llm", musicPolicy: "character_theme", readableMode: false, config: null, state: null,
  isSeed: false, costUsd: 0, messageCount: 0, createdAt: "2026-10-01T10:00:00Z", updatedAt: "2026-10-01T10:00:00Z", ...over,
});
function evs(...list: StreamEvent[]): SessionEvent[] {
  return list.map((e, i) => ({ id: `evt_t${i + 1}`, sessionId: "ses_t", seq: i + 1, at: new Date(T0 + i * 100).toISOString(), type: e.type, payload: e.payload }));
}
const turn = (emotion: "happy" | "sad" = "happy"): StreamEvent[] => [
  { type: "turn.next", payload: { nextSpeakerId: "chr_a" } },
  { type: "turn.thinking", payload: { characterId: "chr_a" } },
  { type: "turn.start", payload: { messageId: "msg_1", author: { type: "character", characterId: "chr_a" } } },
  { type: "emotion", payload: { messageId: "msg_1", characterId: "chr_a", emotion, source: "llm" } },
  { type: "token", payload: { messageId: "msg_1", delta: "Hello " } },
  { type: "token", payload: { messageId: "msg_1", delta: "there." } },
  { type: "turn.end", payload: { messageId: "msg_1", status: "complete", usage: { tokensIn: 10, tokensOut: 2, costUsd: 0.0002, firstTokenMs: 900, totalMs: 1500 } } },
];

describe("sessionReducer", () => {
  it("a later insight for the same message replaces the earlier trace (doc 05 §6, rev 1.3)", () => {
    const first = { messageId: "msg_1", routing: { selected: "chr_a", reason: "first" } };
    const second = { messageId: "msg_1", routing: { selected: "chr_a", reason: "second" }, calls: [{ purpose: "reply", model: "m", costUsd: 0.0002, latencyMs: 1500 }] };
    const s = reduceAll(initialRuntime(session()), evs(
      ...turn(),
      { type: "insight", payload: { messageId: "msg_1", trace: first } },
      { type: "insight", payload: { messageId: "msg_1", trace: second } },
    ));
    expect(orderedMessages(s)[0].trace).toEqual(second);
  });

  it("streams a turn into one complete message and adds its cost", () => {
    const s = reduceAll(initialRuntime(session()), evs(...turn()));
    const [m] = orderedMessages(s);
    expect(m.content).toBe("Hello there.");
    expect(m.status).toBe("complete");
    expect(m.emotion).toBe("happy");
    expect(s.streamingId).toBeUndefined();
    expect(s.thinkingId).toBeUndefined();
    expect(s.session.costUsd).toBeCloseTo(0.0002);
    expect(s.session.messageCount).toBe(1);
  });

  it("holds an early emotion until the first token (CHAT-03 AC4)", () => {
    const e = evs(...turn());
    const beforeToken = reduceAll(initialRuntime(session()), e.slice(0, 4));
    expect(beforeToken.displayEmotion.chr_a).toBe("neutral");
    expect(beforeToken.pendingEmotion.chr_a).toBe("happy");
    const afterToken = reduceAll(initialRuntime(session()), e.slice(0, 5));
    expect(afterToken.displayEmotion.chr_a).toBe("happy");
  });

  it("MANUAL mode records AI emotions but never displays them; user face changes do", () => {
    const manual = session({ emotionMode: "user" });
    const s = reduceAll(initialRuntime(manual), evs(...turn(), { type: "emotion", payload: { characterId: "chr_a", emotion: "sad", source: "user" } }));
    expect(orderedMessages(s)[0].emotion).toBe("happy");
    expect(s.displayEmotion.chr_a).toBe("sad");
  });

  it("listener reactions change the listener's face (AUTO only)", () => {
    const s = reduceAll(initialRuntime(session()), evs(...turn(), { type: "reaction", payload: { messageId: "msg_1", characterId: "chr_b", emotion: "surprised", p: 0.7, source: "classifier" } }));
    expect(s.displayEmotion.chr_b).toBe("surprised");
    expect(orderedMessages(s)[0].reactions?.[0]).toMatchObject({ characterId: "chr_b", emotion: "surprised", p: 0.7 });
  });

  it("ignores stale or duplicate seqs", () => {
    const e = evs(...turn());
    const s = reduceAll(initialRuntime(session()), [...e, e[4]]);
    expect(orderedMessages(s)[0].content).toBe("Hello there.");
  });

  it("regenerate streams a new variant and keeps the original (CHAT-06)", () => {
    const base = reduceAll(initialRuntime(session()), evs(...turn()));
    const more: SessionEvent[] = [
      { type: "turn.start", payload: { messageId: "msg_1", author: { type: "character", characterId: "chr_a" }, variantId: "msg_1_v2" } },
      { type: "token", payload: { messageId: "msg_1", delta: "Hi!", variantId: "msg_1_v2" } },
      { type: "turn.end", payload: { messageId: "msg_1", status: "complete", variantId: "msg_1_v2" } },
    ].map((e, i) => ({ id: `evt_v${i}`, sessionId: "ses_t", seq: 100 + i, at: new Date(T0 + 5000 + i).toISOString(), type: e.type as StreamEvent["type"], payload: e.payload as StreamEvent["payload"] }));
    const s = reduceAll(base, more);
    const m = orderedMessages(s)[0];
    expect(m.content).toBe("Hi!");
    expect(m.variants?.map((v) => v.content)).toEqual(["Hello there.", "Hi!"]);
    expect(m.activeVariantId).toBe("msg_1_v2");
  });

  it("message, session.state, pause/resume, energy and errors", () => {
    let s = initialRuntime(session({ mode: "debate", state: { phase: "setup", round: 0, iteration: 1 } }));
    const user = { id: "msg_u", sessionId: "ses_t", seq: 1, author: { type: "user" as const }, kind: "steer" as const, content: "Mei?", status: "complete" as const, createdAt: "2026-10-01T10:00:00Z" };
    s = reduceAll(s, evs(
      { type: "message", payload: { message: user } },
      { type: "phase", payload: { phase: "rebuttal", round: 2, iteration: 1 } },
      { type: "session.state", payload: { participants: [{ characterId: "chr_a", role: "debater", side: "prop", currentEmotion: "angry", mutedByUser: true }] } },
      { type: "energy", payload: { characterId: "chr_a", current: 742, max: 1000, state: "active", spent: 5 } },
      { type: "session.paused", payload: { reason: "daily_budget" } },
      { type: "error", payload: { code: "rate_limited", message: "slow down", retryable: true } },
    ));
    expect(orderedMessages(s)[0].kind).toBe("steer");
    expect(s.phase).toEqual({ phase: "rebuttal", round: 2, iteration: 1 });
    expect((s.session.state as { phase: string }).phase).toBe("rebuttal");
    expect(s.displayEmotion.chr_a).toBe("angry");
    expect(s.session.participants[0].mutedByUser).toBe(true);
    expect(s.energyById.chr_a).toMatchObject({ current: 742, lastSpent: 5 });
    expect(s.paused).toBe(true);
    expect(s.session.pausedReason).toBe("daily_budget");
    expect(s.errors[0].code).toBe("rate_limited");
    const resumed = applyEvent(s, { id: "evt_r", sessionId: "ses_t", seq: 99, at: "2026-10-01T10:01:00Z", type: "session.resumed", payload: {} });
    expect(resumed.paused).toBe(false);
    expect(resumed.session.status).toBe("active");
  });

  it("session.state settings patch updates mid-session settings (D-57)", () => {
    const s = reduceAll(initialRuntime(session()), evs(
      { type: "session.state", payload: { settings: { emotionMode: "user", readableMode: true, title: "Renamed", titleIsCustom: true } } },
    ));
    expect(s.session).toMatchObject({ emotionMode: "user", readableMode: true, title: "Renamed", titleIsCustom: true });
  });

  it("a turn stopped before turn.start still clears the typing indicator", () => {
    const s = reduceAll(initialRuntime(session()), evs(
      { type: "turn.thinking", payload: { characterId: "chr_a" } },
      { type: "turn.end", payload: { messageId: "msg_never", status: "interrupted", interruptedBy: "user" } },
    ));
    expect(s.thinkingId).toBeUndefined();
    expect(s.order).toHaveLength(0);
  });
});

// Turns one character line into a timed SessionEvent script (R1). Shared by the seed build (fixtures) and the
// live MockClient engines, so recorded and live turns look identical: turn.next → thinking → start → tokens
// (+ emotion before/early/late) → turn.end → energy → insight → listener reactions.
import type {
  Emotion, EmotionSource, Message, MessageUsage, StreamEvent, TurnTrace,
} from "../../contract/types";
import { EMOTIONS } from "../../contract/types";
import type { PricingTable } from "../../domain/cost";
import { chatCostUsd, estimateTokens } from "../../domain/cost";
import { energyState, EST_REPLY_POINTS, pointsForCost } from "../../domain/energy";
import type { PricePeriod } from "../../domain/rushHour";
import type { TimelineEntry } from "../../engine/ScriptPlayer";
import type { Rng } from "../rng";
import type { TimingConfig } from "../timing.config";
import { chunkTokens, tokenize } from "./tokenize";

export type EmotionTiming = "before" | "early" | "late" | "none";

export interface ReactionSpec { characterId: string; emotion: Emotion; p?: number; delayMs?: number }

export interface LineSpec {
  sessionId: string;
  messageId: string;
  characterId: string;
  text: string;
  emotion: Emotion;
  emotionSource?: EmotionSource;
  /** Extra message fields carried on turn.start (seq, kind, debate, forcedSpeaker, targetCharacterId). */
  message?: Partial<Message>;
  variantId?: string;
  forcedBy?: "user_ask" | "mention" | "nudge" | "round_order";
  skipped?: { characterId: string; reason: "exhausted" | "muted" | "archived" }[];
  routing?: TurnTrace["routing"];
  /** Listeners who may react. Explicit `reactions` win over generated ones. */
  listeners?: string[];
  reactions?: ReactionSpec[] | null;
  /** Energy before this reply. */
  energyBefore: { current: number; max: number };
  period: PricePeriod;
  /** Prior conversation size in tokens (drives tokensIn / caching). */
  historyTokens: number;
  emotionTiming?: EmotionTiming;
  contextInSession?: TurnTrace["contextInSession"];
  memoryRecalled?: NonNullable<TurnTrace["memory"]>["recalled"];
  /** Overrides for fixtures that must match the docs exactly (doc 05 §8). */
  usageOverride?: MessageUsage;
  traceOverride?: TurnTrace;
  /** Fault injection (Mock State Switcher). */
  fault?: { kind: "cut"; afterTokens: number } | { kind: "refuse" } | null;
  /** Omit turn.next/thinking (the caller already emitted them, e.g. a greeting). */
  skipPreamble?: boolean;
}

export interface LineScript {
  entries: TimelineEntry<StreamEvent>[];
  /** ms from the start of the script to turn.end (the next turn may start ≤ 500 ms after it). */
  endMs: number;
  usage: MessageUsage;
  energyAfter: number;
  spent: number;
  trace: TurnTrace;
  status: Message["status"];
}

const r3 = (n: number) => Math.round(n * 1000) / 1000;

function emotionCandidates(chosen: Emotion, rng: Rng): { label: Emotion; p: number }[] {
  const top = r3(rng.range(0.55, 0.88));
  const others = rng.shuffle(EMOTIONS.filter((e) => e !== chosen)).slice(0, 2);
  const rest = 1 - top;
  const second = r3(rest * rng.range(0.55, 0.8));
  const third = r3(Math.max(0.01, rest - second - rng.range(0, rest - second) * 0.5));
  return [{ label: chosen, p: top }, { label: others[0], p: second }, { label: others[1], p: third }];
}

export function buildLineScript(spec: LineSpec, timing: TimingConfig, pricing: PricingTable, rng: Rng): LineScript {
  const entries: TimelineEntry<StreamEvent>[] = [];
  const add = (t: number, evt: StreamEvent) => entries.push({ t: Math.round(t), item: evt });
  const { messageId, characterId } = spec;

  // ── Usage & cost ──
  const tokens = tokenize(spec.text, timing.charsPerToken);
  const persona = 700 + rng.int(0, 120);
  const system = 900;
  const mode = spec.message?.debate ? 580 : 220;
  const user = 40 + rng.int(0, 40);
  const tokensIn = system + persona + mode + user + spec.historyTokens;
  const tokensCached = Math.floor((system + persona + spec.historyTokens * 0.9) * (spec.historyTokens > 0 ? 1 : 0.8));
  const firstTokenMs = spec.usageOverride?.firstTokenMs ?? Math.round(timing.firstTokenMs * rng.range(0.85, 1.15));
  const streamMs = Math.round((tokens.length / timing.tokensPerSec) * 1000);
  const totalMs = spec.usageOverride?.totalMs ?? firstTokenMs + streamMs + 80;
  const baseUsage = { tokensIn, tokensCached, tokensOut: Math.max(1, estimateTokens(spec.text)) };
  const costUsd = chatCostUsd(baseUsage, pricing.chat, spec.period);
  let usage: MessageUsage = spec.usageOverride ?? {
    ...baseUsage, costUsd, energySpent: pointsForCost(costUsd), firstTokenMs, totalMs,
  };

  // ── Timeline ──
  const T_START = spec.skipPreamble ? 0 : 100;
  if (!spec.skipPreamble) {
    add(0, { type: "turn.next", payload: { nextSpeakerId: characterId, ...(spec.forcedBy ? { forcedBy: spec.forcedBy } : {}), ...(spec.skipped?.length ? { skipped: spec.skipped } : {}) } });
    add(timing.thinkingMs, { type: "turn.thinking", payload: { characterId } });
  }
  add(T_START, {
    type: "turn.start",
    payload: {
      messageId,
      author: { type: "character", characterId },
      ...(spec.variantId ? { variantId: spec.variantId } : {}),
      ...(spec.message ? { message: spec.message } : {}),
    },
  });

  const firstTokenAt = Math.max(T_START + 1, firstTokenMs);
  const chunks = chunkTokens(tokens, timing.tokensPerEvent);
  const endAtPlanned = Math.max(firstTokenAt + 1, totalMs);
  const stepMs = chunks.length > 1 ? (endAtPlanned - 50 - firstTokenAt) / (chunks.length - 1) : 0;

  let status: Message["status"] = "complete";
  let cutAt = chunks.length;
  if (spec.fault?.kind === "cut") cutAt = Math.min(chunks.length, Math.max(1, Math.ceil(spec.fault.afterTokens / timing.tokensPerEvent)));
  if (spec.fault?.kind === "refuse") cutAt = 0;

  let sentText = "";
  for (let i = 0; i < cutAt; i++) {
    add(firstTokenAt + i * stepMs, { type: "token", payload: { messageId, delta: chunks[i], ...(spec.variantId ? { variantId: spec.variantId } : {}) } });
    sentText += chunks[i];
  }

  // Emotion timing (doc 05 §6: may arrive before, during or after tokens).
  const et = spec.emotionTiming ?? "before";
  const source = spec.emotionSource ?? "llm";
  const emoEvt: StreamEvent = { type: "emotion", payload: { messageId, characterId, emotion: spec.emotion, source } };
  if (et === "before") add(T_START + 40, emoEvt);
  else if (et === "early") add(firstTokenAt + rng.range(80, 700), emoEvt);
  else if (et === "late") add(firstTokenAt + timing.lateEmotionMs + rng.range(0, 400), emoEvt);

  let endAt = endAtPlanned;
  if (spec.fault?.kind === "cut" && cutAt < chunks.length) {
    endAt = firstTokenAt + Math.max(0, cutAt - 1) * stepMs + 120;
    status = "interrupted";
    add(endAt - 10, { type: "error", payload: { code: "network", message: "Can't reach the Horizon server.", retryable: true, messageId } });
  } else if (spec.fault?.kind === "refuse") {
    endAt = firstTokenAt + 200;
    status = "error";
    add(endAt - 10, { type: "error", payload: { code: "content_refused", message: "The model declined this request. Try different wording.", retryable: true, messageId } });
  }

  // Partial output costs proportionally.
  if (status !== "complete" && !spec.usageOverride) {
    const frac = chunks.length ? cutAt / chunks.length : 0;
    const partial = { tokensIn, tokensCached, tokensOut: Math.max(0, Math.round(baseUsage.tokensOut * frac)) };
    const c = status === "error" ? 0 : chatCostUsd(partial, pricing.chat, spec.period);
    usage = { ...partial, costUsd: c, energySpent: pointsForCost(c), firstTokenMs, totalMs: Math.round(endAt) };
  }

  add(endAt, {
    type: "turn.end",
    payload: {
      messageId, status, ...(status === "interrupted" ? { interruptedBy: "error" as const } : {}), usage,
      ...(spec.variantId ? { variantId: spec.variantId } : {}),
    },
  });

  const spent = usage.energySpent ?? pointsForCost(usage.costUsd);
  const energyAfter = Math.max(0, spec.energyBefore.current - spent);
  const est = EST_REPLY_POINTS[spec.period];
  if (spent > 0) {
    add(endAt + 10, {
      type: "energy",
      payload: { characterId, current: energyAfter, max: spec.energyBefore.max, state: energyState(energyAfter, spec.energyBefore.max, est), spent },
    });
  }

  const trace: TurnTrace = spec.traceOverride ?? {
    messageId,
    model: {
      id: pricing.chat.model, provider: pricing.chat.provider, pricePeriod: spec.period,
      latencyMs: { firstToken: usage.firstTokenMs, total: usage.totalMs },
      tokensIn: usage.tokensIn, ...(usage.tokensCached !== undefined ? { tokensCached: usage.tokensCached } : {}),
      tokensOut: usage.tokensOut, costUsd: usage.costUsd,
    },
    energy: { characterId, spent, remaining: energyAfter, max: spec.energyBefore.max },
    emotion: { chosen: spec.emotion, source, candidates: emotionCandidates(spec.emotion, rng) },
    routing: spec.routing ?? {
      selected: characterId,
      ...(spec.forcedBy ? { forcedBy: spec.forcedBy } : {}),
      ...(spec.skipped?.length ? { skipped: spec.skipped } : {}),
    },
    ...(spec.memoryRecalled?.length ? { memory: { recalled: spec.memoryRecalled } } : {}),
    ...(spec.contextInSession?.length ? { contextInSession: spec.contextInSession } : {}),
    context: {
      budget: 12000,
      cacheHitPct: Math.round((100 * (usage.tokensCached ?? 0)) / Math.max(1, usage.tokensIn)),
      used: {
        system, persona, memory: spec.memoryRecalled?.length ? 120 * spec.memoryRecalled.length : 0, knowledge: 0,
        history: spec.historyTokens, user, mode,
      },
    },
    guardrail: { checks: [{ name: "sfw", verdict: "pass", p: r3(rng.range(0.95, 0.995)) }, { name: "advice_scope", verdict: "pass" }] },
  };
  if (status !== "error") add(endAt + 60, { type: "insight", payload: { messageId, trace } });

  // Listener reactions: 300–800 ms after turn.end; never delay the next speaker.
  if (status === "complete" && spec.reactions !== null) {
    const reactions: ReactionSpec[] = spec.reactions ?? (spec.listeners ?? [])
      .filter(() => rng.chance(timing.reactionChance))
      .map((cid) => ({
        characterId: cid,
        emotion: rng.pick<Emotion>(["thinking", "happy", "surprised", "neutral", "embarrassed", "sad", "angry"]),
        p: r3(rng.range(0.42, 0.9)),
      }));
    for (const r of reactions) {
      const delay = r.delayMs ?? rng.range(timing.reactionDelayMs[0], timing.reactionDelayMs[1]);
      add(endAt + delay, { type: "reaction", payload: { messageId, characterId: r.characterId, emotion: r.emotion, ...(r.p !== undefined ? { p: r.p } : {}), source: "classifier" } });
    }
  }

  entries.sort((a, b) => a.t - b.t);
  void sentText;
  return { entries, endMs: Math.round(endAt), usage, energyAfter, spent, trace, status };
}

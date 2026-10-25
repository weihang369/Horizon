// Ensemble helpers (Builder D): pure stage maths + small runtime hooks shared by S09/S10/S12, the docks and overlays.
// Pure functions are unit-tested in shared.test.ts.
import { useEffect, useRef } from "react";
import { useStore } from "zustand";
import type { Character, DebateConfig, DebatePhase, Emotion, Message, Side, Verdict } from "../../contract/types";
import type { RuntimeParticipant, SessionRuntimeView } from "../../client/hooks";
import { entities } from "../../stores/entities";
import { sessionStore } from "../../stores/session";
import type { SessionSlot } from "../../stores/session";

// ── Characters ───────────────────────────────────────────────────────────────
/** Every character the client has seen (SessionScreen loads the world's cast, archived included). */
export function useCharMap(): Record<string, Character> {
  return useStore(entities, (s) => s.chars);
}

export const firstName = (c: Pick<Character, "profile"> | undefined, fallback = "—"): string =>
  c ? c.profile.name.split(" ")[0] : fallback;

// ── Session slots (overlays only get a sessionId) ────────────────────────────
/** The open runtime slot for a session (prefers replay when both are open, since that's what's on screen). */
export function findSlot(sessionId: string, state = sessionStore.getState()): SessionSlot | undefined {
  const slots = Object.values(state.slots).filter((s) => s.id === sessionId && s.runtime);
  return slots.find((s) => s.replay) ?? slots[0];
}

export function useSlot(sessionId: string): SessionSlot | undefined {
  return useStore(sessionStore, (s) => findSlot(sessionId, s));
}

// ── Speaker focus ────────────────────────────────────────────────────────────
/** Who is "on" right now: streaming speaker, else the one thinking. */
export function activeSpeakerId(rt: Pick<SessionRuntimeView, "streamingId" | "thinkingId" | "messages">): string | undefined {
  if (rt.streamingId) {
    const m = rt.messages[rt.streamingId];
    if (m?.author.characterId) return m.author.characterId;
  }
  return rt.thinkingId;
}

/** The last character who spoke (complete or not), newest first. */
export function lastSpeakerId(list: Message[]): string | undefined {
  for (let i = list.length - 1; i >= 0; i--) {
    const m = list[i];
    if (m.author.type === "character" && m.author.characterId) return m.author.characterId;
  }
  return undefined;
}

/**
 * Order a column / wing so its focus character is in front (index 0), keeping the others in cast order.
 * Focus = the active speaker if they're in this group, else the group's most recent speaker, else cast order.
 */
export function frontFirst(ids: string[], focus: string | undefined): string[] {
  if (!focus || !ids.includes(focus)) return ids;
  return [focus, ...ids.filter((x) => x !== focus)];
}

export function recentSpeakerIn(ids: string[], list: Message[]): string | undefined {
  for (let i = list.length - 1; i >= 0; i--) {
    const cid = list[i].author.characterId;
    if (list[i].author.type === "character" && cid && ids.includes(cid)) return cid;
  }
  return undefined;
}

/** Split a group cast into wings (R14/D-53): left gets the extra seat; a 5th seat stacks behind on the left. */
export function splitWings(ids: string[]): { left: string[]; right: string[] } {
  if (ids.length <= 1) return { left: ids, right: [] };
  if (ids.length === 2) return { left: [ids[0]], right: [ids[1]] };
  if (ids.length === 3) return { left: [ids[0], ids[2]], right: [ids[1]] };
  // 4 → 2/2 · 5 → 3/2 (third left seat stacks behind at 0.8)
  const left = ids.filter((_, i) => i % 2 === 0);
  const right = ids.filter((_, i) => i % 2 === 1);
  return { left, right };
}

/** Debate columns: two-sided by side; panel splits the cast alternately (an "arc" collapsed to two columns). */
export function debateColumns(participants: Pick<RuntimeParticipant, "characterId" | "side">[], cfg: DebateConfig | null): { prop: string[]; opp: string[] } {
  if (cfg?.format === "panel" || participants.every((p) => !p.side)) {
    const ids = participants.map((p) => p.characterId);
    return { prop: ids.filter((_, i) => i % 2 === 0), opp: ids.filter((_, i) => i % 2 === 1) };
  }
  return {
    prop: participants.filter((p) => p.side === "prop").map((p) => p.characterId),
    opp: participants.filter((p) => p.side === "opp").map((p) => p.characterId),
  };
}

// ── Debate phases ────────────────────────────────────────────────────────────
export const PHASE_LABEL: Record<DebatePhase, string> = {
  setup: "Setup", opening: "Opening", rebuttal: "Rebuttal", closing: "Closing", verdict: "Verdict", ended: "Ended",
};

/** "ROUND 2: REBUTTAL" (+ " · EXTENDED" when the round repeats). */
export function roundBannerLabel(p: { phase: DebatePhase; round: number; iteration: number }): string {
  if (p.phase === "verdict") return "VERDICT";
  const base = `ROUND ${p.round}: ${PHASE_LABEL[p.phase].toUpperCase()}`;
  return p.iteration > 1 ? `${base} ×${p.iteration}` : base;
}

export type RailStep = { phase: DebatePhase; label: string; state: "done" | "current" | "todo" };

/** The timeline rail: configured phases + Verdict. */
export function railSteps(phases: DebateConfig["phases"], current: DebatePhase | undefined): RailStep[] {
  const all: DebatePhase[] = [...phases, "verdict"];
  const idx = current === "ended" ? all.length : current === "setup" || !current ? -1 : all.indexOf(current);
  return all.map((ph, i) => ({ phase: ph, label: PHASE_LABEL[ph], state: i < idx ? "done" : i === idx ? "current" : "todo" }));
}

// ── Verdict ──────────────────────────────────────────────────────────────────
export type VerdictHeadline =
  | { kind: "side"; side: Side; text: string; sub: string }
  | { kind: "tie"; text: string; sub: string }
  | { kind: "summary"; text: string; sub: string };

export const SIDE_NAME: Record<Side, string> = { prop: "Proposition", opp: "Opposition" };

export function verdictHeadline(v: Verdict, format: DebateConfig["format"]): VerdictHeadline {
  if (format === "panel" || v.decidedBy === "none") {
    return { kind: "summary", text: "SUMMARY", sub: format === "panel" ? "Panel debate · each debater argued their own position" : "No verdict · summary only" };
  }
  if (v.strongerCase === "prop" || v.strongerCase === "opp") {
    const side = v.strongerCase;
    return v.decidedBy === "user"
      ? { kind: "side", side, text: `STRONGER CASE: ${SIDE_NAME[side].toUpperCase()}`, sub: `Your call · stronger case: ${SIDE_NAME[side]}` }
      : { kind: "side", side, text: `STRONGER CASE: ${SIDE_NAME[side].toUpperCase()}`, sub: "Arbiter's assessment of argument quality, not of which side is factually right." };
  }
  return { kind: "tie", text: "TOO CLOSE TO CALL", sub: "Arbiter's assessment of argument quality, not of which side is factually right." };
}

export interface RubricRow { id: string; label: string; values: { subjectId: string; value: number }[] }

/** Long-format scores → one row per criterion (rubric order), subjects in the given order. */
export function rubricRows(v: Verdict, rubric: DebateConfig["rubric"], subjects: string[]): RubricRow[] {
  if (!v.scores?.length) return [];
  return rubric
    .map((r) => ({
      id: r.id,
      label: r.label,
      values: subjects
        .map((sid) => ({ subjectId: sid, value: v.scores!.find((x) => x.criterionId === r.id && x.subjectId === sid)?.value }))
        .filter((x): x is { subjectId: string; value: number } => typeof x.value === "number"),
    }))
    .filter((r) => r.values.length > 0);
}

export function totalScore(v: Verdict, subjectId: string): number {
  return (v.scores ?? []).filter((s) => s.subjectId === subjectId).reduce((a, s) => a + s.value, 0);
}

// ── Seek-aware ceremony triggers ─────────────────────────────────────────────
/** More events than this in one store write = a seek / snapshot, not playback: ceremonies are suppressed (UXA §2.3). */
export const SEEK_JUMP = 24;

/**
 * Calls `fire(next, prev)` when `key` changes during normal playback / live flow. Skips the first value
 * (mount / snapshot) and any change that arrived with a large seq jump (Replay seek).
 */
export function useBoundary<K>(key: K | null, seq: number, fire: (next: K, prev: K | null) => void): void {
  const prev = useRef<{ key: K | null; seq: number } | null>(null);
  const cb = useRef(fire);
  cb.current = fire;
  useEffect(() => {
    const p = prev.current;
    prev.current = { key, seq };
    if (!p || key === null) return;
    if (Object.is(p.key, key)) return;
    if (seq - p.seq > SEEK_JUMP || seq < p.seq) return;
    cb.current(key, p.key);
  }, [key, seq]);
}

// ── Dock expansion drafts (O12 keeps its draft, R5) ──────────────────────────
const drafts = new Map<string, string>();
export const draftKey = (sessionId: string, kind: string) => `${sessionId}:${kind}`;
export const getDraft = (k: string): string => drafts.get(k) ?? "";
export const setDraft = (k: string, v: string): void => {
  if (v) drafts.set(k, v);
  else drafts.delete(k);
};

// ── Misc ─────────────────────────────────────────────────────────────────────
/** Last reaction per character on the most recent message that has reactions (drives the mini burst). */
export function latestReactions(list: Message[]): Record<string, { emotion: Emotion; key: string }> {
  for (let i = list.length - 1; i >= Math.max(0, list.length - 3); i--) {
    const m = list[i];
    if (m.reactions?.length) {
      const out: Record<string, { emotion: Emotion; key: string }> = {};
      for (const r of m.reactions) out[r.characterId] = { emotion: r.emotion, key: `${m.id}:${r.at}:${r.emotion}` };
      return out;
    }
  }
  return {};
}

export const PACE_OPTIONS = [
  { value: "3000", ms: 3000 as const, label: "Slow" },
  { value: "1500", ms: 1500 as const, label: "Normal" },
  { value: "500", ms: 500 as const, label: "Fast" },
];

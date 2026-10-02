// Replay scrubber markers (UXA §2.3 O23): rounds, emotion changes, steering, director's notes, turns.
import type { Message, SessionEvent, StreamEvent } from "../../contract/types";
import { timelineFromEvents } from "../../engine/ScriptPlayer";

export type MarkerKind = "round" | "emotion" | "steer" | "turn" | "verdict";
export interface ReplayMarker { t: number; seq: number; kind: MarkerKind; label: string }

const PHASE_LABEL: Record<string, string> = { opening: "Opening", rebuttal: "Rebuttal", closing: "Closing", verdict: "Verdict", ended: "End" };

export function replayMarkers(events: SessionEvent[], trim: boolean, nameOf: (id: string) => string = (id) => id): ReplayMarker[] {
  const tl = timelineFromEvents(events, { trimGapsMs: trim ? undefined : null });
  const out: ReplayMarker[] = [];
  const lastEmotion: Record<string, string> = {};
  for (const { t, item } of tl) {
    if (!item) continue;
    const e = { type: item.type, payload: item.payload } as StreamEvent;
    switch (e.type) {
      case "phase":
        out.push({ t, seq: item.seq, kind: e.payload.phase === "verdict" ? "verdict" : "round", label: `R${e.payload.round} · ${PHASE_LABEL[e.payload.phase] ?? e.payload.phase}` });
        break;
      case "turn.start":
        if (e.payload.author.type === "character") out.push({ t, seq: item.seq, kind: "turn", label: nameOf(e.payload.author.characterId ?? "") });
        break;
      case "emotion": {
        const { characterId, emotion, messageId } = e.payload;
        if (lastEmotion[characterId] && lastEmotion[characterId] !== emotion && (messageId || e.payload.source === "user")) {
          out.push({ t, seq: item.seq, kind: "emotion", label: `${nameOf(characterId)} → ${emotion}` });
        }
        lastEmotion[characterId] = emotion;
        break;
      }
      case "message": {
        const m: Message = e.payload.message;
        if (m.kind === "steer" || m.kind === "interject" || m.kind === "direction") out.push({ t, seq: item.seq, kind: "steer", label: m.kind === "direction" ? "Director's note" : "Moderator" });
        else if (m.kind === "verdict") out.push({ t, seq: item.seq, kind: "verdict", label: "Verdict" });
        else if (m.kind === "system_note" && /round/i.test(m.content) && !out.some((x) => x.kind === "round" && Math.abs(x.t - t) < 400)) {
          out.push({ t, seq: item.seq, kind: "round", label: m.content });
        }
        break;
      }
    }
  }
  return out;
}

/** Next / previous turn start from a position (→ / ← in replay). */
export function stepTurn(markers: ReplayMarker[], pos: number, dir: 1 | -1): number | null {
  const turns = markers.filter((m) => m.kind === "turn").map((m) => m.t);
  if (dir === 1) return turns.find((t) => t > pos + 50) ?? null;
  const prev = turns.filter((t) => t < pos - 600);
  return prev.length ? prev[prev.length - 1] : 0;
}

export function formatClock(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

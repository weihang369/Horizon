// Insight's Emotion section rules (turn-plan-emotion D15; speaker-emotion "Kept face in Insight"). When the face shown
// is not Jev's top candidate (`none`, unsure or a fallback kept the previous face), the chip says "kept" instead of the
// source and the band is dropped: the band would describe a face that wasn't shown. Owner: AI.
import type { TurnTrace } from "../../contract/types";

export type TraceEmotion = NonNullable<TurnTrace["emotion"]>;

/** The top 3 candidates by p, and whether the face shown was kept against the top one. */
export function emotionView(e: TraceEmotion): { cands: NonNullable<TraceEmotion["candidates"]>; kept: boolean } {
  const cands = [...(e.candidates ?? [])].sort((a, b) => b.p - a.p).slice(0, 3);
  return { cands, kept: cands.length > 0 && cands[0].label !== e.chosen };
}

/** The section's aside: "kept", or the source as before ("AI" for `llm`). */
export function emotionChip(e: TraceEmotion): string {
  return emotionView(e).kept ? "kept" : e.source === "llm" ? "AI" : e.source;
}

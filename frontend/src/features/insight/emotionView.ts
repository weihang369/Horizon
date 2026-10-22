// Insight's Emotion section rules (turn-plan-emotion D15; speaker-emotion "Kept face in Insight"). When the face shown
// is not Jev's top candidate (`none`, unsure or a fallback kept the previous face), the chip says "kept" instead of the
// source and the band is dropped: the band would describe a face that wasn't shown. U-57: so does any face Jev didn't
// pick (source `default` with Jev's candidates), even when it happens to be the top one; a face Jev picked is never
// "kept", even when another candidate has a higher p. Owner: AI.
import type { TurnTrace } from "../../contract/types";

export type TraceEmotion = NonNullable<TurnTrace["emotion"]>;

/** The top 3 candidates by p, and whether the face shown was kept: Jev answered (candidates) but didn't pick it
 * (source `default`: "none", unsure or late). U-57: Jev's pick can differ from its top probability (Takeshi's happy at
 * 0.45 under neutral's 0.55, picked with confidence 0.37), so the pick decides, not the order of the bars. */
export function emotionView(e: TraceEmotion): { cands: NonNullable<TraceEmotion["candidates"]>; kept: boolean } {
  const cands = [...(e.candidates ?? [])].sort((a, b) => b.p - a.p).slice(0, 3);
  return { cands, kept: cands.length > 0 && e.source === "default" };
}

/** The section's aside: "kept", or the source as before ("AI" for `llm`). */
export function emotionChip(e: TraceEmotion): string {
  return emotionView(e).kept ? "kept" : e.source === "llm" ? "AI" : e.source;
}

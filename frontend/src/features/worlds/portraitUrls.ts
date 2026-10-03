// Head-crop sources for world cards, session rows and the pause menu. Real art swaps by URL only. Owner: Builder A.
import type { Character } from "../../contract/types";
import { shadowDataUrl } from "../../vfx/shadow/renderShadowSvg";
import { specFromAppearance } from "../../vfx/shadow/specFromAppearance";

const cache = new Map<string, string>();

export function headUrl(c: Pick<Character, "id" | "emotions" | "appearance" | "paletteId">): string {
  const url = c.emotions.neutral?.url;
  if (url) return url;
  const key = `${c.id}:${c.paletteId}`;
  let d = cache.get(key);
  if (!d) {
    d = shadowDataUrl(specFromAppearance(c.appearance, c.paletteId, "neutral", "unknown", { characterId: c.id }));
    cache.set(key, d);
  }
  return d;
}

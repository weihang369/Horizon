// Asset URL policy. Flip ASSET_SOURCE to "real" when the Seed Asset Sprint delivers: every fixture URL is rewritten
// to the real WebP/opus paths and nothing else changes (R8/R11: swap by URL only).
import type { Emotion } from "../../src/contract/types";

export type AssetSource = "placeholder" | "real";
export const ASSET_SOURCE: AssetSource = (process.env.HORIZON_ASSETS as AssetSource | undefined) === "real" ? "real" : "placeholder";

export type PortraitVariant = Emotion | "blink" | "cand-2";

export function portraitUrl(characterId: string, variant: PortraitVariant): string {
  return ASSET_SOURCE === "real"
    ? `/assets/portraits/${characterId}/${variant}.webp`
    : `/assets/placeholder/portraits/${characterId}/${variant}.svg`;
}

export function themeUrl(characterId: string): string {
  return ASSET_SOURCE === "real" ? `/assets/themes/${characterId}.opus` : `/assets/placeholder/themes/${characterId}.proc.json`;
}

/** File path (relative to seed/assets) for a URL, or null if not a placeholder we generate. */
export function placeholderFile(url: string): string | null {
  return url.startsWith("/assets/placeholder/") ? url.slice("/assets/".length) : null;
}

// Asset URL policy (R8/R11: swap by URL only). A variant uses its real file when `horizon demo export --assets` has
// put one in seed/assets/ (portraits/<id>/<variant>.webp, themes/<id>.mp3); otherwise the build draws its labelled
// placeholder. So a character can be part-real (e.g. one emotion regenerated) and the build still holds together.
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { Emotion } from "../../src/contract/types";

export type AssetSource = "placeholder" | "mixed" | "real";

const SEED_ASSETS = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../seed/assets");
const hasFile = (rel: string) => existsSync(path.join(SEED_ASSETS, rel));

export type PortraitVariant = Emotion | "blink" | "cand-2";

export function portraitUrl(characterId: string, variant: PortraitVariant): string {
  const real = `portraits/${characterId}/${variant}.webp`;
  return hasFile(real) ? `/assets/${real}` : `/assets/placeholder/portraits/${characterId}/${variant}.svg`;
}

export function themeUrl(characterId: string): string {
  const real = `themes/${characterId}.mp3`;
  return hasFile(real) ? `/assets/${real}` : `/assets/placeholder/themes/${characterId}.proc.json`;
}

/** File path (relative to seed/assets) for a URL, or null if not a placeholder we generate. */
export function placeholderFile(url: string): string | null {
  return url.startsWith("/assets/placeholder/") ? url.slice("/assets/".length) : null;
}

/** The manifest's summary of every asset URL the build emitted. */
export function assetSource(urls: string[]): AssetSource {
  const placeholders = urls.filter((u) => placeholderFile(u) !== null).length;
  return placeholders === 0 ? "real" : placeholders === urls.length ? "placeholder" : "mixed";
}

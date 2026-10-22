// The theme song's small print on screen (U-73): the stored credit without its decision-log reference, and the model
// named once. Stored notes read "Composed by <model> through OpenRouter (D-87)." (services/theme.py).
import type { ThemeSong } from "@/contract/types";

export const DEFAULT_SONG_MODEL = "google/lyria-3-clip-preview";

export function songCredit(song: Pick<ThemeSong, "licenseNote" | "generation"> | null | undefined, sketch = false): string {
  const note = (song?.licenseNote ?? "").replace(/\s*\(D-\d+\)\.?\s*$/, "").trim();
  if (note) return note;
  if (sketch) return "Placeholder: procedural WebAudio sketch";
  return `Composed by ${song?.generation?.model ?? DEFAULT_SONG_MODEL} through OpenRouter`;
}

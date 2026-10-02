// Self-hosted OFL fonts, LATIN SUBSETS ONLY (R18, NFR-13). Owner: VMD.
// - Static families: the @fontsource `latin-400.css` entry points (Dela Gothic One would otherwise pull in
//   several MB of Japanese glyphs).
// - Variable families: @fontsource-variable has no per-subset CSS, so we register the latin woff2 directly
//   with the FontFace API (Vite fingerprints the file via `?url`).
import "@fontsource/anton/latin-400.css";
import "@fontsource/dela-gothic-one/latin-400.css";
import "@fontsource/bowlby-one-sc/latin-400.css";
import interLatin from "@fontsource-variable/inter/files/inter-latin-wght-normal.woff2?url";
import monoLatin from "@fontsource-variable/jetbrains-mono/files/jetbrains-mono-latin-wght-normal.woff2?url";

const LATIN_RANGE =
  "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD";

function registerVariable(family: string, url: string): void {
  if (typeof document === "undefined" || typeof FontFace === "undefined") return;
  const face = new FontFace(family, `url(${url}) format("woff2-variations"), url(${url}) format("woff2")`, {
    weight: "100 900",
    style: "normal",
    display: "swap",
    unicodeRange: LATIN_RANGE,
  });
  document.fonts.add(face);
  void face.load().catch(() => undefined);
}

registerVariable("Inter Variable", interLatin);
registerVariable("JetBrains Mono Variable", monoLatin);

/** Families the title waits on before its kinetic intro. */
export const DISPLAY_FONTS = ['400 1em "Anton"', '400 1em "Dela Gothic One"', '400 1em "Bowlby One SC"'];

/**
 * Resolves when the display fonts are ready, or after `capMs` (R18: the title waits ≤ 800 ms).
 * Never rejects.
 */
export function waitForFonts(capMs = 800): Promise<void> {
  if (typeof document === "undefined" || !document.fonts) return Promise.resolve();
  const loads = Promise.all(DISPLAY_FONTS.map((f) => document.fonts.load(f))).then(() => undefined);
  const cap = new Promise<void>((r) => setTimeout(r, capMs));
  return Promise.race([loads.catch(() => undefined), cap]);
}

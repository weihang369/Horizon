import type { Palette } from "../contract/types";

// Fixed palette catalogue (doc 04 §3). An AI may choose from this list but never invent one.
const TEXT = "#F5F2EA";
const p = (
  id: string, name: string, primary: string, secondary: string, accent: string,
  stage: string, surface: string, onPrimary: string, glow: string, fit: string,
): Palette => ({ id, name, primary, secondary, accent, stage, surface, onPrimary, glow, text: TEXT, fit });

export const PALETTES: Palette[] = [
  p("pal_crimson_rebel", "Crimson Rebel", "#E63946", "#FFD6D9", "#FFD23F", "#1A0B0E", "#2A1418", "#1A0B0E", "#FF6B76", "Bold leaders"),
  p("pal_sakura_pop", "Sakura Pop", "#FF6FAE", "#FFE0EE", "#7A2E5A", "#1C0F17", "#2D1825", "#1C0F17", "#FF9CC8", "Sweet, romantic"),
  p("pal_ocean_clinic", "Ocean Clinic", "#2EC4B6", "#CBF3F0", "#FF9F80", "#071A1F", "#0F2A31", "#071A1F", "#6FE3D8", "Calm, medical"),
  p("pal_royal_verdict", "Royal Verdict", "#6E5FE6", "#D9D4FF", "#F2C14E", "#100C26", "#1C1740", "#FFFFFF", "#9488F0", "Authority, law"),
  p("pal_golden_ledger", "Golden Ledger", "#D4A017", "#FFF3C4", "#2F5D8A", "#17130A", "#262014", "#17130A", "#F0C64A", "Analytical, academic"),
  p("pal_citrus_spark", "Citrus Spark", "#FF9F1C", "#FFE8C2", "#2EC4B6", "#1A1308", "#2A2010", "#1A1308", "#FFC066", "Energetic builders"),
  p("pal_forest_sage", "Forest Sage", "#3A9D5D", "#D4EDC2", "#F4A259", "#0B1A10", "#14291B", "#0B1A10", "#6CCB8C", "Grounded elders"),
  p("pal_midnight_ink", "Midnight Ink", "#6286BA", "#BFD7EA", "#EE6C4D", "#0A111C", "#142033", "#0A111C", "#8FAEDB", "Serious, strategic"),
  p("pal_lavender_dream", "Lavender Dream", "#B388EB", "#F1E3FF", "#FF8FAB", "#150F1F", "#241A33", "#150F1F", "#D2B5FF", "Dreamy, artistic"),
  p("pal_neon_arcade", "Neon Arcade", "#00E5C7", "#C9FFF6", "#F15BB5", "#0B0B1A", "#16162E", "#0B0B1A", "#5CFFE6", "Gamer, techy"),
  p("pal_ember_ash", "Ember Ash", "#FF5E3A", "#FFD0C2", "#8A8A99", "#170D0A", "#281814", "#170D0A", "#FF8A6B", "Intense, rebellious"),
  p("pal_frost_byte", "Frost Byte", "#7FD1FF", "#E6F6FF", "#A06CD5", "#0A1520", "#132536", "#0A1520", "#B5E6FF", "Cool, precise"),
];

export const PALETTE_BY_ID: Record<string, Palette> = Object.fromEntries(PALETTES.map((x) => [x.id, x]));

/** House "palette" used in the hub, system UI and moderator/host lines (doc 04 §2). */
export const HOUSE_PALETTE: Palette = {
  id: "pal_house", name: "Horizon", primary: "#FF4D2E", secondary: "#FFB199", accent: "#FFC53D",
  stage: "#0B0B0F", surface: "#1A1A22", onPrimary: "#0B0B0F", glow: "#FFB199", text: TEXT,
};

export function getPalette(id?: string | null): Palette {
  return (id && PALETTE_BY_ID[id]) || HOUSE_PALETTE;
}

/** CSS class for a palette (palettes.css): `pal_ocean_clinic` → `pal-ocean_clinic`; null → `pal-house`. */
export function paletteClass(id?: string | null): string {
  const p = getPalette(id);
  return p.id === HOUSE_PALETTE.id ? "pal-house" : `pal-${p.id.replace(/^pal_/, "")}`;
}

/** All palette classes, for removal when swapping. */
export const PALETTE_CLASSES: string[] = ["pal-house", ...PALETTES.map((x) => paletteClass(x.id))];

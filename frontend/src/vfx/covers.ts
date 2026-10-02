// The 8 world-cover presets (doc 06 §8, VMD paper §2.7). Pure CSS backgrounds + inline SVG silhouettes.
// Node-safe (strings only).

const svg = (path: string, fill: string) =>
  `url("data:image/svg+xml,${encodeURIComponent(
    `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 160 100' preserveAspectRatio='none'><path d='${path}' fill='${fill}'/></svg>`,
  )}")`;

const SKYLINE = svg(
  "M0 100V62h8V48h10v20h6V30h12v38h8V52h10V20h4v-8h4v8h4v50h10V44h12v24h8V36h14v32h6V56h10v44Z",
  "#0B0B0F",
);
const ROOFS = svg(
  "M0 100V70l15-12 15 12V60h22l11-9 11 9v12h18V52l14-10 14 10v48h12V66l13-9 13 9v34Z",
  "#1A0B0E",
);

export type CoverPresetId =
  | "cover_night_skyline" | "cover_sunset_rooftops" | "cover_ocean_horizon" | "cover_sakura_street"
  | "cover_neon_city" | "cover_forest_mist" | "cover_desert_dusk" | "cover_starfield";

export interface CoverPreset {
  id: CoverPresetId;
  name: string;
  background: string;
  /** Neon City: a perspective grid layer (static transform). */
  grid?: boolean;
  /** Dominant tone for text over the cover. */
  ink: "light" | "dark";
}

export const COVER_PRESETS: CoverPreset[] = [
  {
    id: "cover_night_skyline", name: "Night Skyline", ink: "light",
    background: `${SKYLINE} bottom/100% 45% no-repeat, radial-gradient(circle at 78% 22%, #F5F2EA 0 2.2%, #F5F2EA2E 2.6% 7%, transparent 7.5%), linear-gradient(180deg, #0A1030, #1C1F5A 55%, #4B2A6B 82%, #FF4D2E)`,
  },
  {
    id: "cover_sunset_rooftops", name: "Sunset Rooftops", ink: "light",
    background: `${ROOFS} bottom/100% 38% no-repeat, repeating-linear-gradient(180deg, transparent 0 9px, #C2416B 9px 12px) 0 66%/100% 14% no-repeat, radial-gradient(circle at 32% 70%, #FFE9B0 0 13%, transparent 13.5%), linear-gradient(180deg, #2A1A4A, #C2416B 38%, #FF8A4C 62%, #FFD27A 74%)`,
  },
  {
    id: "cover_ocean_horizon", name: "Ocean Horizon", ink: "light",
    background: `repeating-linear-gradient(176deg, transparent 0 9px, #CBF3F014 9px 10px) bottom/100% 48% no-repeat, radial-gradient(ellipse 30% 3% at 50% 52%, #FFB199, transparent), linear-gradient(180deg, #0E2A47, #2E6F95 52%, #071A2B 52%, #03101C)`,
  },
  {
    id: "cover_sakura_street", name: "Sakura Street", ink: "dark",
    background: `radial-gradient(ellipse 5px 3px, #FFFFFFD9 60%, transparent 65%) 0 0/97px 83px, radial-gradient(ellipse 4px 3px, #FFE0EE 60%, transparent 65%) 41px 29px/131px 113px, linear-gradient(104deg, transparent 46%, #FF6FAE33 46% 58%, transparent 58%), linear-gradient(160deg, #FFE0EE, #FF9CC8 40%, #7A2E5A)`,
  },
  {
    id: "cover_neon_city", name: "Neon City", ink: "light", grid: true,
    background: `linear-gradient(180deg, #0B0B1A, #1B0F3A 60%, #3A0F4A)`,
  },
  {
    id: "cover_forest_mist", name: "Forest Mist", ink: "light",
    background: `linear-gradient(180deg, transparent 40%, #F5F2EA59 55%, transparent 70%), repeating-linear-gradient(90deg, transparent 0 38px, #0B1A108C 38px 46px, transparent 46px 91px), linear-gradient(180deg, #CFE3D2, #6C9C7E 35%, #1E3A2A 70%, #0B1A10)`,
  },
  {
    id: "cover_desert_dusk", name: "Desert Dusk", ink: "light",
    background: `radial-gradient(ellipse 80% 30% at 20% 100%, #8A3F2A 60%, transparent 61%), radial-gradient(ellipse 70% 25% at 85% 100%, #6B2F22 60%, transparent 61%), linear-gradient(180deg, #3B1E54, #B8456B 40%, #F28C4E 62%, #F6C177 63%, #C9733E 80%, #5C2A1E)`,
  },
  {
    id: "cover_starfield", name: "Starfield", ink: "light",
    background: `radial-gradient(1px 1px at 13px 17px, #F5F2EA 99%, transparent) 0 0/97px 89px, radial-gradient(1.5px 1.5px at 71px 43px, #BFD7EA 99%, transparent) 0 0/163px 151px, radial-gradient(ellipse 40% 25% at 70% 35%, #B388EB59, transparent 70%), radial-gradient(ellipse at 50% 120%, #3B2A80, #120B2E 45%, #05040C)`,
  },
];

export const COVER_BY_ID: Record<string, CoverPreset> = Object.fromEntries(COVER_PRESETS.map((c) => [c.id, c]));

export function getCoverPreset(id?: string | null): CoverPreset {
  return (id && COVER_BY_ID[id]) || COVER_PRESETS[0];
}

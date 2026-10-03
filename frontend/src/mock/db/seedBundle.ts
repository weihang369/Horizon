// Every seed/ JSON fixture in one lazily-loaded chunk (≈ 75 KB gz). Owner: EE.
// Imported dynamically by loadSeed so the entry bundle stays inside its budget (EE paper §2.9).
export const SEED_FILES: Record<string, unknown> = import.meta.glob(
  ["../../../../seed/**/*.json", "!../../../../seed/assets/**"],
  { eager: true, import: "default" },
);

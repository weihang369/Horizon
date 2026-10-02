// Loads the seed dataset (one lazy chunk, cached). Owner: EE.
import type { Dataset } from "./dataset";
import { cloneDataset, datasetFromFiles } from "./dataset";

let cached: Promise<Dataset> | null = null;

/** A fresh, mutable copy of the shipped seed dataset (seed + _mock overlays). */
export async function loadSeedDataset(): Promise<Dataset> {
  cached ??= import("./seedBundle").then((m) => datasetFromFiles(m.SEED_FILES));
  return cloneDataset(await cached);
}

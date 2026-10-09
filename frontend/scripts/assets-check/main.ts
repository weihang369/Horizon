// `npm run assets:check`: builds the shipped-asset inventory from the repo and checks ASSETS.md against it
// (asset-credits spec). Run directly by Node (erasable TypeScript). Exit 1 with one line per problem. Owner: SWE.
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { checkAssets } from "./check.ts";
import type { Inventory } from "./check.ts";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");

function walk(dir: string): string[] {
  const abs = path.join(REPO, dir);
  if (!statSync(abs, { throwIfNoEntry: false })?.isDirectory()) return [];
  const out: string[] = [];
  for (const name of readdirSync(abs).sort()) {
    const rel = `${dir}/${name}`;
    if (statSync(path.join(REPO, rel)).isDirectory()) out.push(...walk(rel));
    else out.push(rel);
  }
  return out;
}

export function repoInventory(): Inventory {
  const pkg = JSON.parse(readFileSync(path.join(REPO, "frontend/package.json"), "utf8")) as { dependencies?: Record<string, string> };
  const tracks = JSON.parse(readFileSync(path.join(REPO, "seed/system-tracks.json"), "utf8")) as { data: { id: string; licence: string }[] };
  return {
    files: [...walk("seed/assets"), ...walk("frontend/public")],
    fonts: Object.keys(pkg.dependencies ?? {}).filter((d) => d.startsWith("@fontsource")).sort(),
    tracks: Object.fromEntries(tracks.data.map((t) => [t.id, t.licence])),
  };
}

const md = readFileSync(path.join(REPO, "ASSETS.md"), "utf8");
const { problems, assets, rows } = checkAssets(repoInventory(), md);
if (problems.length) {
  for (const p of problems) console.error(`✗ ${p}`);
  console.error(`assets:check failed: ${problems.length} problem(s), ${assets} shipped assets, ${rows} rows.`);
  process.exit(1);
}
console.log(`assets:check passed: ${assets} shipped assets covered by ${rows} rows in ASSETS.md.`);

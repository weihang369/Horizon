// Bundle budgets (EE paper §2.9, R20). Run after `npm run build`. Owner: EE.
//   Entry JS (index.html script + its modulepreloads) ≤ 150 KB gz · each lazy JS chunk ≤ 60 KB gz
//   Fonts ≤ 450 KB woff2 (Latin subsets, R18). Exempt from the chunk cap: the seed data chunk and the dev Kit Gallery.
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

const here = path.dirname(fileURLToPath(import.meta.url));
const dist = path.resolve(here, "../dist");
const KB = 1024;
const LIMITS = { entry: 150 * KB, chunk: 60 * KB, fonts: 450 * KB };
const EXEMPT = [/^seedBundle-/, /^KitGallery-/];

if (!existsSync(path.join(dist, "index.html"))) {
  console.error("[budget] dist/ not found. Run `npm run build` first.");
  process.exit(1);
}

const gz = (file) => gzipSync(readFileSync(file), { level: 9 }).length;
const fmt = (n) => `${(n / KB).toFixed(1)} KB`;
const html = readFileSync(path.join(dist, "index.html"), "utf8");
const entryFiles = new Set(
  [...html.matchAll(/<script[^>]+src="\/?([^"]+\.js)"/g), ...html.matchAll(/<link[^>]+rel="modulepreload"[^>]+href="\/?([^"]+\.js)"/g)].map((m) => m[1]),
);

const walk = (dir) => readdirSync(dir).flatMap((n) => {
  const p = path.join(dir, n);
  return statSync(p).isDirectory() ? walk(p) : [p];
});
const all = walk(dist);
const js = all.filter((f) => f.endsWith(".js"));
const rel = (f) => path.relative(dist, f).replace(/\\/g, "/");

let entry = 0;
const problems = [];
const rows = [];
for (const f of js) {
  const size = gz(f);
  const r = rel(f);
  if (entryFiles.has(r)) {
    entry += size;
    rows.push(["entry", r, size]);
    continue;
  }
  const name = path.basename(f);
  const exempt = EXEMPT.some((re) => re.test(name));
  rows.push([exempt ? "exempt" : "chunk", r, size]);
  if (!exempt && size > LIMITS.chunk) problems.push(`chunk ${r} is ${fmt(size)} gz (limit ${fmt(LIMITS.chunk)})`);
}
if (entry > LIMITS.entry) problems.push(`entry JS is ${fmt(entry)} gz (limit ${fmt(LIMITS.entry)})`);
const fonts = all.filter((f) => f.endsWith(".woff2")).reduce((a, f) => a + statSync(f).size, 0);
if (fonts > LIMITS.fonts) problems.push(`fonts are ${fmt(fonts)} (limit ${fmt(LIMITS.fonts)})`);

rows.sort((a, b) => b[2] - a[2]);
for (const [kind, r, size] of rows.slice(0, 12)) console.log(`  ${kind.padEnd(6)} ${fmt(size).padStart(9)}  ${r}`);
console.log(`[budget] entry JS ${fmt(entry)} gz / ${fmt(LIMITS.entry)} · largest lazy chunk ${fmt(Math.max(0, ...rows.filter((x) => x[0] === "chunk").map((x) => x[2])))} / ${fmt(LIMITS.chunk)} · fonts ${fmt(fonts)} / ${fmt(LIMITS.fonts)}`);
if (problems.length) {
  console.error(`[budget] FAIL\n  ${problems.join("\n  ")}`);
  process.exit(1);
}
console.log("[budget] OK");

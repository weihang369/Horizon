// Seed build (R2): screenplays + fixture data → repo-root seed/**.
//   npm run seed:build   regenerate and write
//   npm run seed:check   regenerate in memory and fail on any difference
// Deterministic: no wall-clock time, seeded randomness only.
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import type { Emotion } from "../../src/contract/types";
import { SCHEMA_VERSION } from "../../src/contract/types";
import { PRICING } from "../../src/mock/pricing.config";
import { hashString } from "../../src/mock/rng";
import { PALETTES } from "../../src/theme/palettes";
import { themeSpecFromBrief } from "../../src/audio/synth/spec";
import { compileScreenplay } from "./compile";
import type { CompiledSession } from "./compile";
import { ASSET_SOURCE, placeholderFile, portraitUrl } from "./assets";
import type { PortraitVariant } from "./assets";
import { CHARACTERS } from "./data/characters";
import {
  DEFAULT_SETTINGS, JOBS, KNOWLEDGE, MEMORY, MEMORY_OWNERS, STYLE_PRESETS, SYSTEM_TRACKS, VARIANTS, WORLDS, songsFor,
} from "./data/catalog";
import { ledgerFor } from "./ledger";
import { MOCK_SCREENPLAYS } from "./screenplays/mock";
import { SEED_SCREENPLAYS } from "./screenplays/seed";

type Outputs = Map<string, string>;

const json = (data: unknown) => `${JSON.stringify({ schemaVersion: SCHEMA_VERSION, data }, null, 2)}\n`;
/** Events: one event per line keeps diffs readable. */
const jsonLines = (items: unknown[]) =>
  `{"schemaVersion":${SCHEMA_VERSION},"data":[\n${items.map((x) => JSON.stringify(x)).join(",\n")}\n]}\n`;

type ShadowModule = typeof import("../../src/vfx/shadow");

async function loadShadow(): Promise<ShadowModule | null> {
  try {
    const mod = (await import("../../src/vfx/shadow")) as ShadowModule;
    return typeof mod.renderShadowSvg === "function" && typeof mod.specFromAppearance === "function" ? mod : null;
  } catch (err) {
    console.warn(`[seed-build] Shadow renderer unavailable (${(err as Error).message}); placeholder SVGs skipped.`);
    return null;
  }
}

export async function buildSeed(): Promise<{ outputs: Outputs; warnings: string[] }> {
  const out: Outputs = new Map();
  const warnings: string[] = [];
  const put = (rel: string, content: string) => out.set(rel.replace(/\\/g, "/"), content);

  // ── Catalogues & settings ──
  put("settings.json", json(DEFAULT_SETTINGS));
  put("palettes.json", json(PALETTES));
  put("style-presets.json", json(STYLE_PRESETS));
  put("system-tracks.json", json(SYSTEM_TRACKS));
  put("pricing.json", json(PRICING));

  // ── Characters & songs ──
  for (const d of CHARACTERS) put(`${d.mock ? "_mock/" : ""}characters/${d.character.id}.json`, json(d.character));
  for (const { song, mock } of songsFor(CHARACTERS)) put(`${mock ? "_mock/" : ""}songs/${song.id}.json`, json(song));

  // ── Worlds ──
  for (const w of WORLDS) put(`worlds/${w.id}.json`, json(w));

  // ── Sessions ──
  const endEnergy = Object.fromEntries(CHARACTERS.map((d) => [d.character.id, d.character.energy.current]));
  const compiled: { c: CompiledSession; mock: boolean }[] = [];
  for (const sp of [...SEED_SCREENPLAYS, ...MOCK_SCREENPLAYS]) {
    const c = compileScreenplay(sp, endEnergy);
    compiled.push({ c, mock: sp.mock });
    const dir = `${sp.mock ? "_mock/" : ""}sessions/${sp.session.id}`;
    put(`${dir}/session.json`, json(c.session));
    put(`${dir}/messages.json`, json(c.messages));
    put(`${dir}/events.json`, jsonLines(c.events));
  }

  // ── Memory, knowledge, ledger, jobs, variants ──
  for (const owner of MEMORY_OWNERS) put(`memory/${owner}.json`, json(MEMORY.filter((m) => m.characterId === owner)));
  const knowledgeOwners = [...new Set(KNOWLEDGE.map((k) => k.characterId))];
  for (const owner of knowledgeOwners) put(`knowledge/${owner}.json`, json(KNOWLEDGE.filter((k) => k.characterId === owner)));
  const ledger = ledgerFor(
    compiled.map(({ c, mock }) => ({ sessionId: c.session.id, mode: c.session.mode, messages: c.messages, mock })),
    CHARACTERS,
  );
  put("usage/ledger.json", json(ledger.seed));
  put("_mock/usage/ledger.json", json(ledger.mock));
  for (const j of JOBS) put(`_mock/jobs/${j.id}.json`, json(j));
  for (const v of VARIANTS) put(`_mock/variants/${v.id}.json`, json(v));

  // ── Placeholder assets ──
  if (ASSET_SOURCE === "placeholder") {
    const shadow = await loadShadow();
    for (const d of CHARACTERS) {
      const c = d.character;
      const variants: PortraitVariant[] = [...d.renderEmotions];
      if (d.renderBlink) variants.push("blink");
      if (d.renderCandidate2) variants.push("cand-2");
      for (const v of variants) {
        const file = placeholderFile(portraitUrl(c.id, v));
        if (!file) continue;
        if (!shadow) {
          warnings.push(`missing renderer: ${file}`);
          continue;
        }
        const emotion: Emotion = v === "blink" || v === "cand-2" ? "neutral" : v;
        const spec = shadow.specFromAppearance(c.appearance, c.paletteId, emotion, v === "blink" ? "blink" : "default", {
          characterId: c.id, candidate: v === "cand-2" ? 2 : 1,
        });
        put(`assets/${file}`, shadow.renderShadowSvg(spec));
      }
    }
    for (const d of CHARACTERS) {
      if (!d.song) continue;
      const spec = themeSpecFromBrief(d.character.id, d.song.brief, `${d.character.profile.name.split(" ")[0]}'s Theme`);
      put(`assets/placeholder/themes/${d.character.id}.proc.json`, `${JSON.stringify(spec, null, 2)}\n`);
    }
  }

  // ── Manifest (fixture hash keys the mock's localStorage snapshot) ──
  const keys = [...out.keys()].sort();
  let acc = "";
  for (const k of keys) acc += `${k}:${hashString(out.get(k)!)};`;
  put("manifest.json", json({ hash: hashString(acc).toString(36), files: keys.length, assetSource: ASSET_SOURCE }));

  return { outputs: out, warnings };
}

// ── CLI ──
const GENERATED_DIRS = ["characters", "worlds", "sessions", "memory", "knowledge", "usage", "songs", "jobs", "_mock", "assets/placeholder"];

function listFiles(root: string, rel = ""): string[] {
  const dir = path.join(root, rel);
  if (!existsSync(dir)) return [];
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const r = rel ? `${rel}/${name}` : name;
    if (statSync(path.join(root, r)).isDirectory()) out.push(...listFiles(root, r));
    else out.push(r);
  }
  return out;
}

export async function main(mode: "build" | "check", seedDir: string): Promise<number> {
  const { outputs, warnings } = await buildSeed();
  for (const w of new Set(warnings)) console.warn(`[seed-build] skipped ${w}`);
  const existing = GENERATED_DIRS.flatMap((d) => listFiles(seedDir, d));

  if (mode === "check") {
    const problems: string[] = [];
    for (const [rel, content] of outputs) {
      const file = path.join(seedDir, rel);
      if (!existsSync(file)) problems.push(`missing  ${rel}`);
      else if (readFileSync(file, "utf8").replace(/\r\n/g, "\n") !== content) problems.push(`changed  ${rel}`);
    }
    for (const rel of existing) if (!outputs.has(rel)) problems.push(`stale    ${rel}`);
    if (problems.length) {
      console.error(`[seed:check] seed/ is out of date (${problems.length}):\n  ${problems.slice(0, 40).join("\n  ")}\nRun: npm run seed:build`);
      return 1;
    }
    console.log(`[seed:check] OK: ${outputs.size} files match.`);
    return 0;
  }

  for (const rel of existing) if (!outputs.has(rel)) rmSync(path.join(seedDir, rel));
  let written = 0;
  for (const [rel, content] of outputs) {
    const file = path.join(seedDir, rel);
    mkdirSync(path.dirname(file), { recursive: true });
    if (existsSync(file) && readFileSync(file, "utf8") === content) continue;
    writeFileSync(file, content);
    written++;
  }
  console.log(`[seed:build] ${outputs.size} files (${written} written) → ${seedDir}`);
  return 0;
}

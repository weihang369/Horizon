// Seed build (R2): screenplays + fixture data → repo-root seed/**.
//   npm run seed:build   regenerate and write
//   npm run seed:check   regenerate in memory and fail on any difference
// Deterministic: no wall-clock time, seeded randomness only.
import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import type { Emotion, MemoryItem } from "../../src/contract/types";
import { SCHEMA_VERSION } from "../../src/contract/types";
import { PRICING } from "../../src/mock/pricing.config";
import { DEFAULT_TIMING } from "../../src/mock/timing.config";
import { hashString } from "../../src/mock/rng";
import { PALETTES } from "../../src/theme/palettes";
import { themeSpecFromBrief } from "../../src/audio/synth/spec";
import { compileScreenplay } from "./compile";
import type { CompiledSession } from "./compile";
import { assetSource, placeholderFile, portraitUrl, themeUrl } from "./assets";
import type { PortraitVariant } from "./assets";
import { CHARACTERS } from "./data/characters";
import { makeEnergy } from "../../src/domain/energy";
import {
  DEFAULT_SETTINGS, JOBS, KNOWLEDGE, MEMORY, MEMORY_OWNERS, STYLE_PRESETS, SYSTEM_TRACKS, VARIANTS, WORLDS, songsFor,
} from "./data/catalog";
import type { CharacterDef } from "./data/characters";
import { KNOWLEDGE_CHUNKS, KNOWLEDGE_IDS, KNOWLEDGE_KEYS } from "./data/knowledge";
import { ledgerFor } from "./ledger";
import { RUNTIME } from "./runtime.config";
import { RECORDED_MEMORY, RECORDED_ROWS, recordedSession } from "./recorded";
import { rowsOutput } from "./rows";
import { compileRecorded, rewrite } from "./recordedCompile";
import type { RecordingMap } from "./recordedCompile";
import { MOCK_SCREENPLAYS } from "./screenplays/mock";
import { SEED_SCREENPLAYS } from "./screenplays/seed";
import { system1Fixture } from "./system1";

type Outputs = Map<string, string>;
/** Binary files copied as they are (D-110: the documents' stored originals): seed-relative path → source file. */
type Copies = Map<string, string>;

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

/** D-110: a whole-demo recording carries each character's real energy at its end; older exports keep the fixture's. */
const CHARACTERS_BUILT: CharacterDef[] = CHARACTERS.map((d) => {
  const e = RECORDED_ROWS?.energy[d.character.id];
  if (!e) return d;
  // in wire form (whole points, doc backend/04 §4), with the derived fields computed from it, as the API reads it back
  const energy = makeEnergy(Math.floor(e.energy_current), d.character.energy.max, e.energy_as_of, Math.floor(e.energy_spent_today));
  return { ...d, character: { ...d.character, energy } };
});

export async function buildSeed(): Promise<{ outputs: Outputs; copies: Copies; warnings: string[] }> {
  const CHARACTERS = CHARACTERS_BUILT;
  const out: Outputs = new Map();
  const copies: Copies = new Map();
  const warnings: string[] = [];
  const put = (rel: string, content: string) => out.set(rel.replace(/\\/g, "/"), content);

  // ── Catalogues & settings ──
  put("settings.json", json(DEFAULT_SETTINGS));
  put("palettes.json", json(PALETTES));
  put("style-presets.json", json(STYLE_PRESETS));
  put("system-tracks.json", json(SYSTEM_TRACKS));
  put("pricing.json", json(PRICING));
  // session-runtime D9: one pacing table for the mock and the backend.
  put("runtime.json", json({ timing: DEFAULT_TIMING, runtime: RUNTIME }));
  // docs/ai/13 W1: the scripted backend's and the MockClient's System 1 rows, from the question bank's labels.
  put("system1.fixture.json", json(system1Fixture()));

  // ── Characters & songs ──
  for (const d of CHARACTERS) put(`${d.mock ? "_mock/" : ""}characters/${d.character.id}.json`, json(d.character));
  for (const { song, mock } of songsFor(CHARACTERS)) put(`${mock ? "_mock/" : ""}songs/${song.id}.json`, json(song));

  // ── Worlds ──
  for (const w of WORLDS) put(`worlds/${w.id}.json`, json(w));

  // ── Sessions ──
  const endEnergy = Object.fromEntries(CHARACTERS.map((d) => [d.character.id, d.character.energy.current]));
  const compiled: { c: CompiledSession; mock: boolean }[] = [];
  // D-104/U-40: every install ships the mock overlay, so the mock recordings are the seed characters' history too:
  // every recording's memories go into seed/memory
  const recordings: (RecordingMap & { mock: boolean })[] = [];
  for (const sp of [...SEED_SCREENPLAYS, ...MOCK_SCREENPLAYS]) {
    // The real demo: a session recorded in the app (horizon demo export --session) replaces its screenplay.
    const rec = recordedSession(sp.session.id);
    let c: CompiledSession;
    if (rec) {
      const r = compileRecorded(sp, rec, endEnergy, KNOWLEDGE_IDS, !RECORDED_ROWS);
      c = r.compiled;
      recordings.push({ ...r.map, mock: sp.mock });
    } else {
      c = compileScreenplay(sp, endEnergy);
    }
    compiled.push({ c, mock: sp.mock });
    const dir = `${sp.mock ? "_mock/" : ""}sessions/${sp.session.id}`;
    put(`${dir}/session.json`, json(c.session));
    put(`${dir}/messages.json`, json(c.messages));
    put(`${dir}/events.json`, jsonLines(c.events));
  }

  // ── Memory, knowledge, ledger, jobs, variants ──
  const memoryIds: Record<string, string> = {};
  const memory = RECORDED_MEMORY ? recordedMemory(RECORDED_MEMORY, recordings, memoryIds) : MEMORY;
  for (const owner of MEMORY_OWNERS) put(`memory/${owner}.json`, json(memory.filter((m) => m.characterId === owner)));
  // D-59: citedCount = citation markers across the shipped (non-mock) sessions; chunks per source.
  const citedCount: Record<string, number> = {};
  for (const { c, mock } of compiled) {
    if (mock) continue;
    for (const m of c.messages) for (const ct of m.citations ?? []) citedCount[ct.sourceId] = (citedCount[ct.sourceId] ?? 0) + 1;
  }
  const sources = KNOWLEDGE.map((k) => {
    const chunks = KNOWLEDGE_CHUNKS[k.id];
    if (k.status === "indexed" && !chunks?.length) warnings.push(`indexed source without chunks: ${k.id}`);
    return {
      ...k,
      ...(k.status === "indexed" ? { chunks: chunks?.length ?? 0, citedCount: citedCount[k.id] ?? 0 } : {}),
    };
  });
  const knowledgeOwners = [...new Set(sources.map((k) => k.characterId))];
  for (const owner of knowledgeOwners) put(`knowledge/${owner}.json`, json(sources.filter((k) => k.characterId === owner)));
  for (const [sourceId, chunks] of Object.entries(KNOWLEDGE_CHUNKS)) put(`knowledge/chunks/${sourceId}.json`, json(chunks));
  const rows = RECORDED_ROWS ? rowsOutput(RECORDED_ROWS, recordings, KNOWLEDGE_IDS, KNOWLEDGE_KEYS, memoryIds) : null;
  for (const [rel, data] of rows?.files ?? []) put(rel, json(data));
  for (const [rel, file] of rows?.copies ?? []) copies.set(rel, file);
  const ledger = ledgerFor(
    compiled.map(({ c, mock }) => ({ sessionId: c.session.id, mode: c.session.mode, messages: c.messages, mock })),
    CHARACTERS, rows?.ledger,
  );
  put("usage/ledger.json", json(ledger.seed));
  put("_mock/usage/ledger.json", json(ledger.mock));
  for (const j of JOBS) put(`_mock/jobs/${j.id}.json`, json(j));
  for (const v of VARIANTS) put(`_mock/variants/${v.id}.json`, json(v));

  // ── Placeholder assets: drawn only for the variants that have no real file yet ──
  const shadow = await loadShadow();
  const assetUrls: string[] = [];
  for (const d of CHARACTERS) {
    const c = d.character;
    const variants: PortraitVariant[] = [...d.renderEmotions];
    if (d.renderBlink) variants.push("blink");
    if (d.renderCandidate2) variants.push("cand-2");
    for (const v of variants) {
      const url = portraitUrl(c.id, v);
      assetUrls.push(url);
      const file = placeholderFile(url);
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
    const url = themeUrl(d.character.id);
    assetUrls.push(url);
    if (!placeholderFile(url)) continue;
    const spec = themeSpecFromBrief(d.character.id, d.song.brief, `${d.character.profile.name.split(" ")[0]}'s Theme`);
    put(`assets/placeholder/themes/${d.character.id}.proc.json`, `${JSON.stringify(spec, null, 2)}\n`);
  }

  // ── Manifest (fixture hash keys the mock's localStorage snapshot) ──
  const keys = [...out.keys(), ...copies.keys()].sort();
  let acc = "";
  for (const k of keys) acc += `${k}:${out.has(k) ? hashString(out.get(k)!) : hashString(readFileSync(copies.get(k)!).toString("base64"))};`;
  put("manifest.json", json({ hash: hashString(acc).toString(36), files: keys.length, assetSource: assetSource(assetUrls) }));

  return { outputs: out, copies, warnings };
}

/** Memories the recorded sessions produced: seed ids (`mem_<character key><n>`), their session and message ids mapped.
 * `ids` collects recorded id → seed id (the rows' vectors follow it). */
function recordedMemory(items: MemoryItem[], recordings: RecordingMap[], ids: Record<string, string>): MemoryItem[] {
  const count: Record<string, number> = {};
  const out: MemoryItem[] = [];
  for (const m of items) {
    const rec = recordings.find((r) => r.sourceSessionId === m.sourceSessionId);
    if (!rec) continue;
    const key = m.characterId.replace(/^chr_/, "");
    count[key] = (count[key] ?? 0) + 1;
    ids[m.id] = `mem_${key}${count[key]}`;
    out.push({ ...rewrite(m, { ...rec.messageIds, [rec.sourceSessionId]: rec.seedSessionId }, rec.shiftMs), id: ids[m.id] });
  }
  return out;
}

// ── CLI ──
const GENERATED_DIRS = ["characters", "worlds", "sessions", "memory", "knowledge", "usage", "songs", "jobs", "_mock", "rows",
  "assets/placeholder"];

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
  const { outputs, copies, warnings } = await buildSeed();
  const same = (file: string, src: string) => existsSync(file) && readFileSync(file).equals(readFileSync(src));
  for (const w of new Set(warnings)) console.warn(`[seed-build] skipped ${w}`);
  const existing = GENERATED_DIRS.flatMap((d) => listFiles(seedDir, d));

  if (mode === "check") {
    const problems: string[] = [];
    for (const [rel, content] of outputs) {
      const file = path.join(seedDir, rel);
      if (!existsSync(file)) problems.push(`missing  ${rel}`);
      else if (readFileSync(file, "utf8").replace(/\r\n/g, "\n") !== content) problems.push(`changed  ${rel}`);
    }
    for (const [rel, src] of copies) if (!same(path.join(seedDir, rel), src)) problems.push(`changed  ${rel}`);
    for (const rel of existing) if (!outputs.has(rel) && !copies.has(rel)) problems.push(`stale    ${rel}`);
    if (problems.length) {
      console.error(`[seed:check] seed/ is out of date (${problems.length}):\n  ${problems.slice(0, 40).join("\n  ")}\nRun: npm run seed:build`);
      return 1;
    }
    console.log(`[seed:check] OK: ${outputs.size} files match.`);
    return 0;
  }

  for (const rel of existing) if (!outputs.has(rel) && !copies.has(rel)) rmSync(path.join(seedDir, rel));
  let written = 0;
  for (const [rel, content] of outputs) {
    const file = path.join(seedDir, rel);
    mkdirSync(path.dirname(file), { recursive: true });
    if (existsSync(file) && readFileSync(file, "utf8") === content) continue;
    writeFileSync(file, content);
    written++;
  }
  for (const [rel, src] of copies) {
    const file = path.join(seedDir, rel);
    if (same(file, src)) continue;
    mkdirSync(path.dirname(file), { recursive: true });
    copyFileSync(src, file);
    written++;
  }
  console.log(`[seed:build] ${outputs.size + copies.size} files (${written} written) → ${seedDir}`);
  return 0;
}

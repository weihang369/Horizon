// Dataset: the mock's in-memory copy of repo-root seed/ (doc 05 shapes). Owner: EE.
// Built from the raw fixture files (path → parsed JSON). `_mock/` overlays (UI-phase-only fixtures) are merged in.
import type {
  AppSettings, Character, EmotionAsset, Emotion, GenerationJob, KnowledgeChunk, KnowledgeSource, MemoryItem, Message, Palette, Session, SessionEvent,
  StylePreset, SystemTrack, ThemeSong, UsageRecord, World,
} from "../../contract/types";
import type { PricingTable } from "../../domain/cost";

export interface SessionRecord { session: Session; messages: Message[]; events: SessionEvent[] }
export interface FixtureVariant {
  id: string; label: string;
  characterPatches: { characterId: string; energy?: { current: number; state: "active" | "tired" | "exhausted" } }[];
}

export interface Dataset {
  hash: string;
  settings: AppSettings;
  palettes: Palette[];
  stylePresets: StylePreset[];
  systemTracks: SystemTrack[];
  pricing: PricingTable;
  worlds: Record<string, World>;
  characters: Record<string, Character>;
  /** Emotion asset history (derived from character refs at load; jobs add versions). */
  assets: Record<string, EmotionAsset>;
  songs: Record<string, ThemeSong>;
  sessions: Record<string, SessionRecord>;
  memory: Record<string, MemoryItem>;
  knowledge: Record<string, KnowledgeSource>;
  /** D-59 indexed passages by chunk id (seed/knowledge/chunks/<sourceId>.json). */
  knowledgeChunks: Record<string, KnowledgeChunk>;
  /** rev 1.3: content hash per user-added source (duplicate detection). Absent in seed and old snapshots. */
  knowledgeHashes?: Record<string, string>;
  ledger: UsageRecord[];
  jobs: Record<string, GenerationJob>;
  variants: Record<string, FixtureVariant>;
}

type Files = Record<string, unknown>;

/** Normalise any glob/fs key to a path relative to seed/ ("characters/chr_x.json"). */
export function seedRel(key: string): string {
  const k = key.replace(/\\/g, "/");
  const i = k.lastIndexOf("/seed/");
  return i >= 0 ? k.slice(i + 6) : k.replace(/^\.?\/?seed\//, "");
}

const dataOf = <T>(v: unknown): T => (v && typeof v === "object" && "data" in (v as object) ? (v as { data: T }).data : (v as T));

/** Build a Dataset from seed files. `includeMock` merges seed/_mock (default true: the UI phase needs it). */
export function datasetFromFiles(raw: Files, opts: { includeMock?: boolean } = {}): Dataset {
  const includeMock = opts.includeMock ?? true;
  const files: Files = {};
  for (const [k, v] of Object.entries(raw)) files[seedRel(k)] = v;
  const get = <T>(rel: string): T => {
    if (!(rel in files)) throw new Error(`seed file missing: ${rel}`);
    return dataOf<T>(files[rel]);
  };
  const ds: Dataset = {
    hash: dataOf<{ hash: string }>(files["manifest.json"] ?? { data: { hash: "dev" } }).hash,
    settings: get<AppSettings>("settings.json"),
    palettes: get<Palette[]>("palettes.json"),
    stylePresets: get<StylePreset[]>("style-presets.json"),
    systemTracks: get<SystemTrack[]>("system-tracks.json"),
    pricing: get<PricingTable>("pricing.json"),
    worlds: {}, characters: {}, assets: {}, songs: {}, sessions: {}, memory: {}, knowledge: {}, knowledgeChunks: {}, ledger: [], jobs: {}, variants: {},
  };
  const sessionParts: Record<string, Partial<SessionRecord>> = {};
  for (const rel of Object.keys(files).sort()) {
    const mock = rel.startsWith("_mock/");
    if (mock && !includeMock) continue;
    const r = mock ? rel.slice(6) : rel;
    const [dir] = r.split("/");
    const v = files[rel];
    switch (dir) {
      case "worlds": { const w = dataOf<World>(v); ds.worlds[w.id] = w; break; }
      case "characters": { const c = dataOf<Character>(v); ds.characters[c.id] = c; break; }
      case "songs": { const s = dataOf<ThemeSong>(v); ds.songs[s.id] = s; break; }
      case "memory": for (const m of dataOf<MemoryItem[]>(v)) ds.memory[m.id] = m; break;
      case "knowledge":
        if (r.startsWith("knowledge/chunks/")) for (const c of dataOf<KnowledgeChunk[]>(v)) ds.knowledgeChunks[c.id] = c;
        else for (const k of dataOf<KnowledgeSource[]>(v)) ds.knowledge[k.id] = k;
        break;
      case "usage": ds.ledger.push(...dataOf<UsageRecord[]>(v)); break;
      case "jobs": { const j = dataOf<GenerationJob>(v); ds.jobs[j.id] = j; break; }
      case "variants": { const x = dataOf<FixtureVariant>(v); ds.variants[x.id] = x; break; }
      case "sessions": {
        const [, sid, file] = r.split("/");
        const part = (sessionParts[sid] ??= {});
        if (file === "session.json") part.session = dataOf<Session>(v);
        else if (file === "messages.json") part.messages = dataOf<Message[]>(v);
        else if (file === "events.json") part.events = dataOf<SessionEvent[]>(v);
        break;
      }
    }
  }
  for (const [sid, p] of Object.entries(sessionParts)) {
    if (p.session) ds.sessions[sid] = { session: p.session, messages: p.messages ?? [], events: p.events ?? [] };
  }
  ds.ledger.sort((a, b) => a.at.localeCompare(b.at));
  for (const c of Object.values(ds.characters)) {
    for (const [emotion, ref] of Object.entries(c.emotions) as [Emotion, Character["emotions"][Emotion]][]) {
      if (!ref) continue;
      ds.assets[ref.assetId] = {
        id: ref.assetId, characterId: c.id, emotion, variant: "default", status: "ready", url: ref.url,
        vfxPreset: ref.vfxPreset, version: 1, isActive: true,
      };
    }
  }
  return ds;
}

export const cloneDataset = (ds: Dataset): Dataset => structuredClone(ds);

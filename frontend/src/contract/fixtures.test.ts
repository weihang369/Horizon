// Fixture validation (EE paper §2.10): zod over every seed/ file + integrity (NFR-23 world isolation, monotonic
// seq/at, a trace on every character message) + msg_seedD08 = doc 05 §8. Owner: EE.
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { z } from "zod";
import type { AppSettings, Character, KnowledgeChunk, KnowledgeSource, Message, Session, SessionEvent, World } from "./types";
import {
  AppSettingsSchema, CharacterSchema, GenerationJobSchema, KnowledgeChunkSchema, KnowledgeSourceSchema, MemoryItemSchema, MessageSchema,
  PaletteSchema, SessionEventSchema, SessionSchema, StylePresetSchema, SystemTrackSchema, ThemeSongSchema,
  UsageRecordSchema, WorldSchema, fixtureFile,
} from "./schemas";

const SEED = path.resolve(__dirname, "../../../seed");
const DOC05 = path.resolve(__dirname, "../../../docs/requirements/05-data-contract.md");

function walk(dir: string, rel = ""): string[] {
  return readdirSync(path.join(dir, rel)).flatMap((n) => {
    const r = rel ? `${rel}/${n}` : n;
    return statSync(path.join(dir, r)).isDirectory() ? walk(dir, r) : [r];
  });
}
const files = walk(SEED).filter((f) => f.endsWith(".json") && !f.startsWith("assets/"));
const read = (rel: string) => JSON.parse(readFileSync(path.join(SEED, rel), "utf8")) as { schemaVersion: number; data: unknown };

function schemaFor(rel: string): z.ZodType | null {
  const r = rel.replace(/^_mock\//, "");
  if (r === "settings.json") return AppSettingsSchema;
  if (r === "palettes.json") return z.array(PaletteSchema);
  if (r === "style-presets.json") return z.array(StylePresetSchema);
  if (r === "system-tracks.json") return z.array(SystemTrackSchema);
  if (r.startsWith("worlds/")) return WorldSchema;
  if (r.startsWith("characters/")) return CharacterSchema;
  if (r.startsWith("songs/")) return ThemeSongSchema;
  if (r.startsWith("memory/")) return z.array(MemoryItemSchema);
  if (r.startsWith("knowledge/chunks/")) return z.array(KnowledgeChunkSchema);
  if (r.startsWith("knowledge/")) return z.array(KnowledgeSourceSchema);
  if (r.startsWith("usage/")) return z.array(UsageRecordSchema);
  if (r.startsWith("jobs/")) return GenerationJobSchema;
  if (r.endsWith("/session.json")) return SessionSchema;
  if (r.endsWith("/messages.json")) return z.array(MessageSchema);
  if (r.endsWith("/events.json")) return z.array(SessionEventSchema);
  return null; // manifest, pricing, variants: build artefacts, checked by seed:check
}

// Contract rev 1.3 is additive: entities frozen from the rev 1.2 seed (before the rev 1.3 seed fixes) still validate.
describe("rev 1.2 entities validate under rev 1.3", () => {
  const REV12 = path.resolve(__dirname, "__fixtures__/rev12");
  const cases: [string, z.ZodType][] = [
    ["character.json", CharacterSchema],
    ["session.json", SessionSchema],
    ["messages.json", z.array(MessageSchema)],
    ["knowledge.json", z.array(KnowledgeSourceSchema)],
  ];
  for (const [file, schema] of cases) {
    it(file, () => {
      const res = fixtureFile(schema).safeParse(JSON.parse(readFileSync(path.join(REV12, file), "utf8")));
      if (!res.success) throw new Error(`${file}: ${z.prettifyError(res.error)}`);
    });
  }
  it("still includes a legacy url source", () => {
    const { data } = JSON.parse(readFileSync(path.join(REV12, "knowledge.json"), "utf8")) as { data: KnowledgeSource[] };
    expect(data.some((k) => k.type === "url")).toBe(true);
  });
});

describe("seed fixtures", () => {
  it("found the seed folder", () => {
    expect(files.length).toBeGreaterThan(50);
  });

  for (const rel of files) {
    const schema = schemaFor(rel);
    if (!schema) continue;
    it(`validates ${rel}`, () => {
      const res = fixtureFile(schema).safeParse(read(rel));
      if (!res.success) throw new Error(`${rel}: ${z.prettifyError(res.error)}`);
    });
  }

  const worlds = new Map(files.filter((f) => /(^|\/)worlds\//.test(f)).map((f) => [(read(f).data as World).id, read(f).data as World]));
  const chars = new Map(files.filter((f) => /(^|\/)characters\//.test(f)).map((f) => [(read(f).data as Character).id, read(f).data as Character]));
  const sessionDirs = [...new Set(files.filter((f) => f.endsWith("/session.json")).map((f) => path.posix.dirname(f)))];

  it("world isolation: every character and session participant resolves to its own world (NFR-23)", () => {
    for (const c of chars.values()) expect(worlds.has(c.worldId), c.id).toBe(true);
    for (const dir of sessionDirs) {
      const s = read(`${dir}/session.json`).data as Session;
      for (const p of s.participants) expect(chars.get(p.characterId)?.worldId, `${s.id} → ${p.characterId}`).toBe(s.worldId);
    }
  });

  it("events have monotonic seq and at; every character message has a trace", () => {
    for (const dir of sessionDirs) {
      const events = read(`${dir}/events.json`).data as SessionEvent[];
      events.forEach((e, i) => {
        expect(e.seq, `${dir} #${i}`).toBe(i + 1);
        if (i) expect(Date.parse(e.at), `${dir} at #${i}`).toBeGreaterThanOrEqual(Date.parse(events[i - 1].at));
      });
      const messages = read(`${dir}/messages.json`).data as Message[];
      for (const m of messages) if (m.author.type === "character" && m.status === "complete") expect(m.trace, m.id).toBeTruthy();
    }
  });

  it("five shipped seed sessions, all replay-only", () => {
    const seed = sessionDirs.filter((d) => !d.startsWith("_mock/"));
    expect(seed).toHaveLength(5);
    for (const d of seed) expect((read(`${d}/session.json`).data as Session).isSeed).toBe(true);
  });

  it("msg_seedD08 matches doc 05 §8 (content abbreviated with … in the doc; trace.messageId required by the type)", () => {
    const md = readFileSync(DOC05, "utf8");
    const doc = JSON.parse(md.split("## 8.")[1].split("```json")[1].split("```")[0]) as Message;
    const m = (read("sessions/ses_seedDebate4Day/messages.json").data as Message[]).find((x) => x.id === "msg_seedD08")!;
    expect(m.content.startsWith(doc.content.replace(/…$/, ""))).toBe(true);
    const { content: _a, trace: t1, ...restDoc } = doc;
    const { content: _b, trace: t2, ...restSeed } = m;
    expect(restSeed).toEqual(restDoc);
    expect({ ...t2, messageId: undefined }).toEqual({ ...t1, messageId: undefined });
    expect(t2?.messageId).toBe("msg_seedD08");
  });

  it("knowledge citations (D-59): markers in text, chunks resolve, quotes match, citedCount matches", () => {
    const sources = new Map<string, KnowledgeSource>();
    for (const f of files.filter((x) => /^knowledge\/[^/]+\.json$/.test(x))) for (const k of read(f).data as KnowledgeSource[]) sources.set(k.id, k);
    const chunks = new Map<string, KnowledgeChunk>();
    for (const f of files.filter((x) => x.startsWith("knowledge/chunks/"))) for (const k of read(f).data as KnowledgeChunk[]) chunks.set(k.id, k);
    for (const k of chunks.values()) expect(sources.has(k.sourceId), k.id).toBe(true);
    for (const s of sources.values()) {
      if (s.status === "indexed") expect([...chunks.values()].filter((k) => k.sourceId === s.id).length, s.id).toBe(s.chunks);
      if (s.status === "failed") expect(s.error, s.id).toBeTruthy();
    }
    const counted: Record<string, number> = {};
    for (const dir of sessionDirs.filter((d) => !d.startsWith("_mock/"))) {
      for (const m of read(`${dir}/messages.json`).data as Message[]) {
        for (const c of m.citations ?? []) {
          expect(m.content, `${m.id} [${c.n}]`).toContain(`[${c.n}]`);
          expect(chunks.get(c.chunkId)?.text, c.chunkId).toBe(c.quote);
          expect(chunks.get(c.chunkId)?.sourceId).toBe(c.sourceId);
          expect(m.trace?.knowledge?.retrieved.some((r) => r.chunkId === c.chunkId && r.cited && r.n === c.n), m.id).toBe(true);
          counted[c.sourceId] = (counted[c.sourceId] ?? 0) + 1;
        }
      }
    }
    expect(Object.keys(counted).length).toBeGreaterThanOrEqual(4);
    for (const s of sources.values()) if (s.status === "indexed") expect(s.citedCount ?? 0, s.id).toBe(counted[s.id] ?? 0);
  });

  // ── demo-data spec (rev 1.3) ──────────────────────────────────────────────
  it("prices and models match the decision log (D-61 Seedream, D-66 Jev, D-64 embedding)", () => {
    const pricing = read("pricing.json").data as {
      decision: { model: string; inputPerM: number; outputPerM: number };
      embedding: { model: string; inputPerM: number };
      generation: Record<string, number>;
    };
    expect(pricing.decision).toMatchObject({ model: "typesafe/jev-1.13", inputPerM: 0.042, outputPerM: 0 });
    expect(pricing.embedding).toMatchObject({ model: "qwen/qwen3-embedding-8b", inputPerM: 0.01 });
    for (const k of ["portrait", "emotionEdit", "tweak", "expressionSheet", "blinkFrame"]) expect(pricing.generation[k], k).toBe(0.018);
    const settings = read("settings.json").data as AppSettings;
    expect(settings.models.image).toBe("bytedance-seed/seedream-5-0-flash");
    expect(settings.models.embedding).toBe("qwen/qwen3-embedding-8b");
    expect(settings.energy.estReplyPoints).toEqual({ off_peak: 4, peak: 8 });
  });

  it("seed knowledge is file or text only: no url sources, no CSV (D-65)", () => {
    const all = files.filter((x) => /(^|\/)knowledge\/[^/]+\.json$/.test(x) && !x.includes("chunks/")).flatMap((f) => read(f).data as KnowledgeSource[]);
    expect(all.length).toBeGreaterThanOrEqual(5);
    for (const k of all) {
      expect(k.type, k.id).not.toBe("url");
      expect(k.title.toLowerCase().endsWith(".csv"), k.id).toBe(false);
    }
    expect(all.some((k) => k.status === "failed"), "the demo keeps one failed source").toBe(true);
  });

  it("every id in the seed is globally unique, portrait candidates included", () => {
    const seen = new Map<string, string>();
    const visit = (v: unknown, where: string): void => {
      if (Array.isArray(v)) return v.forEach((x) => visit(x, where));
      if (!v || typeof v !== "object") return;
      const o = v as Record<string, unknown>;
      if (typeof o.id === "string" && /^cand_/.test(o.id)) {
        expect(seen.get(o.id), `${o.id} in ${where} and ${seen.get(o.id)}`).toBeUndefined();
        seen.set(o.id, where);
        expect(o.id, where).toMatch(/^[a-z]+_[0-9A-Za-z]{1,40}$/);
      }
      for (const x of Object.values(o)) visit(x, where);
    };
    for (const f of files.filter((x) => /(^|\/)characters\//.test(x))) visit(read(f).data, f);
    expect(seen.size).toBeGreaterThanOrEqual(6);
  });
});

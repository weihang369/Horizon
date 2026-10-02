// Fixture validation (EE paper §2.10): zod over every seed/ file + integrity (NFR-23 world isolation, monotonic
// seq/at, a trace on every character message) + msg_seedD08 = doc 05 §8. Owner: EE.
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { z } from "zod";
import type { Character, Message, Session, SessionEvent, World } from "./types";
import {
  AppSettingsSchema, CharacterSchema, GenerationJobSchema, KnowledgeSourceSchema, MemoryItemSchema, MessageSchema,
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
  if (r.startsWith("knowledge/")) return z.array(KnowledgeSourceSchema);
  if (r.startsWith("usage/")) return z.array(UsageRecordSchema);
  if (r.startsWith("jobs/")) return GenerationJobSchema;
  if (r.endsWith("/session.json")) return SessionSchema;
  if (r.endsWith("/messages.json")) return z.array(MessageSchema);
  if (r.endsWith("/events.json")) return z.array(SessionEventSchema);
  return null; // manifest, pricing, variants: build artefacts, checked by seed:check
}

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
});

// export-schema (rev 1.3): the JSON Schema the backend validates against covers the whole contract and is deterministic.
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { buildSchemaDocument, buildSchemaJson } from "../../scripts/export-schema/schema";

const COMMITTED = path.resolve(__dirname, "../../../backend/horizon/contract/schema.json");

describe("contract JSON Schema export", () => {
  const doc = buildSchemaDocument() as { $defs: Record<string, { pattern?: string; properties?: Record<string, { pattern?: string }> }> };

  it("defines every entity, event and the error envelope", () => {
    for (const name of [
      "AppSettings", "World", "Character", "Energy", "EmotionAsset", "ThemeSong", "Session", "Message", "TurnTrace", "TurnCall",
      "Citation", "SessionEvent", "GlobalEvent", "JobEvent", "GenerationJob", "GenerationTask", "UsageRecord", "MemoryItem",
      "KnowledgeSource", "KnowledgeChunk", "HorizonErrorShape", "ErrorCode",
    ]) expect(doc.$defs, name).toHaveProperty(name);
  });

  it("keeps ID prefixes and timestamp formats that the refinements expressed", () => {
    expect(doc.$defs.KnowledgeSource.properties?.id.pattern).toBe("^kno_[0-9A-Za-z]{1,40}$");
    expect(doc.$defs.KnowledgeChunk.properties?.id.pattern).toBe("^kch_[0-9A-Za-z]{1,40}$");
    expect(JSON.stringify(doc.$defs.World)).toContain('"format":"date-time"');
  });

  it("is deterministic and matches the committed file", () => {
    const a = buildSchemaJson();
    expect(buildSchemaJson()).toBe(a);
    expect(a.endsWith("\n")).toBe(true);
    expect(a.includes("\r")).toBe(false);
    expect(readFileSync(COMMITTED, "utf8").replace(/\r\n/g, "\n"), "run `npm run export-schema`").toBe(a);
  });
});

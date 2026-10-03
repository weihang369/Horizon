import { describe, expect, it } from "vitest";
import type { KnowledgeSource } from "@/contract/types";
import { formatAdded, formatBytes, sortSources, sourceFacts } from "./knowledge";

const src = (id: string, extra: Partial<KnowledgeSource> = {}): KnowledgeSource =>
  ({ id, characterId: "c", worldId: "w", title: id, type: "file", status: "indexed", ...extra });

describe("knowledge helpers", () => {
  it("sorts cited sources first, then failed last, then newest", () => {
    const out = sortSources([
      src("a", { addedAt: "2026-01-01" }),
      src("b", { citedCount: 1 }),
      src("c", { status: "failed", addedAt: "2026-09-01" }),
      src("d", { citedCount: 4 }),
      src("e", { addedAt: "2026-03-01", status: "indexing" }),
    ]).map((s) => s.id);
    expect(out).toEqual(["d", "b", "e", "a", "c"]);
  });
  it("formats bytes, dates and facts", () => {
    expect(formatBytes(482_000)).toBe("482 KB");
    expect(formatBytes(2_310_442)).toBe("2.3 MB");
    expect(formatBytes()).toBe("");
    expect(formatAdded("2026-09-24T14:05:00Z")).toMatch(/^24 Sept? 2026$/);
    expect(formatAdded("nope")).toBe("");
    expect(sourceFacts(src("x", { pages: 18, chunks: 10, bytes: 482_000 }))).toEqual(["18 pages", "10 passages", "482 KB"]);
    expect(sourceFacts(src("x", { chunks: 1 }), { bytes: false })).toEqual(["1 passage"]);
  });
});

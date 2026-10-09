import { describe, expect, it } from "vitest";
import type { GlobalEvent, IngestProgress } from "@/client/HorizonClient";
import type { KnowledgeSource } from "@/contract/types";
import {
  ACCEPT, formatAdded, formatBytes, isReadable, PASTE_MAX_BYTES, pasteCounter, pasteProblem, reduceProgress, sortSources,
  sourceFacts, STATUS_LABEL, type ProgressMap,
} from "./knowledge";

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
  it("keyword_only sources sort with readable ones, open in the viewer and get their own badge (rev 1.3)", () => {
    const out = sortSources([
      src("a", { status: "failed", addedAt: "2026-09-01" }),
      src("k", { status: "keyword_only", addedAt: "2026-02-01" }),
      src("i", { addedAt: "2026-01-01" }),
    ]).map((s) => s.id);
    expect(out).toEqual(["k", "i", "a"]);
    expect(isReadable(src("k", { status: "keyword_only" }))).toBe(true);
    expect(isReadable(src("f", { status: "failed" }))).toBe(false);
    expect(STATUS_LABEL.keyword_only).toBe("keyword only");
    expect(new Set(Object.values(STATUS_LABEL)).size).toBe(4);
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

  it("the progress fold keeps the latest stage per source and clears a source when its run ends", () => {
    const ev = (id: string, progress?: IngestProgress): GlobalEvent => ({ type: "entity.changed", kind: "knowledge", id, worldId: "w", ...(progress ? { progress } : {}) });
    let st: ProgressMap = {};
    st = reduceProgress(st, ev("a", { stage: "extracting", pct: 0.15 }));
    st = reduceProgress(st, ev("b", { stage: "extracting", pct: 0.05 }));
    st = reduceProgress(st, ev("a", { stage: "chunking", pct: 0.65 }));
    st = reduceProgress(st, ev("a", { stage: "embedding", pct: 0.85 }));
    expect(st).toEqual({ a: { stage: "embedding", pct: 0.85 }, b: { stage: "extracting", pct: 0.05 } });
    const same = reduceProgress(st, { type: "entity.changed", kind: "memory", id: "a" });
    expect(same).toBe(st);
    st = reduceProgress(st, ev("a"));
    expect(st).toEqual({ b: { stage: "extracting", pct: 0.05 } });
    expect(reduceProgress(st, ev("zzz"))).toBe(st);
    expect(reduceProgress(st, { type: "mock.reset" })).toEqual({});
  });

  it("the Paste text dialog refuses an empty title, empty text and text over 200 KB", () => {
    expect(pasteProblem("  ", "Rice first.")).toBe("Give the pasted text a title.");
    expect(pasteProblem("Rice", " \n ")).toBe("Paste some text first.");
    expect(pasteProblem("Rice", "a".repeat(PASTE_MAX_BYTES))).toBeNull();
    expect(pasteProblem("Rice", "a".repeat(PASTE_MAX_BYTES + 1))).toBe("Pasted text can be at most 200 KB.");
    // The limit is in UTF-8 bytes: 70 000 three-byte characters are 210 000 bytes.
    expect(pasteProblem("Kanji", "漢".repeat(70_000))).toBe("Pasted text can be at most 200 KB.");
    expect(pasteCounter(0)).toBe("0.0 KB / 200 KB");
    expect(pasteCounter(PASTE_MAX_BYTES)).toBe("200 KB / 200 KB");
    expect(ACCEPT.split(",")).toEqual([".pdf", ".docx", ".md", ".markdown", ".txt"]);
  });
});

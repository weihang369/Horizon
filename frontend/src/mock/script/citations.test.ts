import { describe, expect, it } from "vitest";
import { createRng } from "../rng";
import { citeKnowledge, footnoteCitations, insertMarkers, liveCitations } from "./citations";
import type { ChunkRef } from "./citations";

const ref = (i: number): ChunkRef => ({
  chunk: { id: `kch_t${i}`, sourceId: "kno_t", index: i, locator: `p. ${i}`, text: `Passage ${i}.` },
  source: { id: "kno_t", title: "Test.pdf", type: "file" },
});

describe("citations (D-59)", () => {
  it("insertMarkers places [n] after sentence ends, or at the end", () => {
    expect(insertMarkers("One. Two two two. Three three.", 2)).toBe("One. Two two two.[1] Three three.[2]");
    expect(insertMarkers("no stop", 1)).toBe("no stop[1]");
  });

  it("citeKnowledge numbers cited passages and keeps uncited ones in the trace", () => {
    const { citations, knowledge } = citeKnowledge("k", [ref(1), ref(2)], [ref(3)], { query: "q" });
    expect(citations.map((c) => c.n)).toEqual([1, 2]);
    expect(knowledge.retrieved).toHaveLength(3);
    expect(knowledge.retrieved.filter((r) => r.cited).map((r) => r.n).sort()).toEqual([1, 2]);
    const uncited = knowledge.retrieved.find((r) => !r.cited)!;
    expect(uncited.score).toBeLessThan(Math.min(...citations.map((c) => c.score!)));
  });

  it("liveCitations is deterministic per rng seed", () => {
    const pool = [ref(1), ref(2), ref(3)];
    const a = liveCitations("s", "Hello there. Fine.", "p", pool, createRng("x"));
    const b = liveCitations("s", "Hello there. Fine.", "p", pool, createRng("x"));
    expect(a).toEqual(b);
  });
});

describe("footnoteCitations (Markdown export)", () => {
  it("numbers footnotes across messages and leaves code spans alone", () => {
    const notes: string[] = [];
    const cites = [citeKnowledge("k", [ref(1)]).citations[0]];
    expect(footnoteCitations("A.[1] `[1]` [2]", cites, notes)).toBe("A.[^1] `[1]` [2]");
    expect(footnoteCitations("B.[1]", cites, notes)).toBe("B.[^2]");
    expect(notes).toEqual(['[^1]: Test.pdf, p. 1. "Passage 1."', '[^2]: Test.pdf, p. 1. "Passage 1."']);
  });
});

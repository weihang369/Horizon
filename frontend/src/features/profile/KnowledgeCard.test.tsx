// Knowledge tab cards (knowledge-sources "Supported formats in the UI", design D20), rendered to static markup in the
// node test environment: Index needs a key, Retry is on failed sources, indexing cards show the stage and a bar.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { KnowledgeSource } from "@/contract/types";
import { KnowledgeCard, type KnowledgeCardProps } from "./KnowledgeCard";

const src = (extra: Partial<KnowledgeSource> = {}): KnowledgeSource =>
  ({ id: "kno_a", characterId: "c", worldId: "w", title: "Bees.md", type: "file", status: "keyword_only", chunks: 3, ...extra });
const noop = () => {};
const html = (p: Partial<KnowledgeCardProps>) =>
  renderToStaticMarkup(createElement(KnowledgeCard, { d: src(), i: 0, keySet: false, onOpen: noop, onDelete: noop, onReindex: noop, ...p }));

describe("KnowledgeCard", () => {
  it("offers ↻ Index on a keyword-only source while a key is set", () => {
    const out = html({ keySet: true });
    expect(out).toContain("↻ Index");
    expect(out).toContain("keyword only");
    expect(out).not.toContain("A key enables search by meaning");
  });

  it("has no Index button without a key, and says what a key adds", () => {
    const out = html({ keySet: false });
    expect(out).not.toContain("↻ Index");
    expect(out).toContain("A key enables search by meaning");
  });

  it("offers ↻ Retry on a failed source with its reason, and delete on every card", () => {
    const out = html({ d: src({ status: "failed", error: "This document is password-protected." }), keySet: true });
    expect(out).toContain("↻ Retry");
    expect(out).toContain("This document is password-protected.");
    expect(out).not.toContain("↻ Index");
    for (const status of ["indexed", "indexing", "keyword_only", "failed"] as const) {
      expect(html({ d: src({ status }) }), status).toContain('aria-label="Delete Bees.md"');
    }
  });

  it("shows an indexing source's stage and progress", () => {
    const out = html({ d: src({ status: "indexing" }), progress: { stage: "embedding", pct: 0.85 } });
    expect(out).toContain("Indexing for search by meaning…");
    expect(out).toContain('aria-valuenow="85"');
    expect(out).toContain("width:85%");
    expect(html({ d: src({ status: "indexing" }) })).toContain("Reading and indexing…");
  });

  it("opens readable sources (indexed and keyword-only) as a button", () => {
    expect(html({ d: src({ status: "indexed" }) })).toContain('aria-label="Open Bees.md"');
    expect(html({ d: src({ status: "failed" }) })).not.toContain('aria-label="Open Bees.md"');
  });
});

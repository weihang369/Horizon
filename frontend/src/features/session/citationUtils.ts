// D-59 citation helpers (C): opening O28, type glyph text, grouping by source. Components live in Citations.tsx.
import type { Citation, KnowledgeSource } from "../../contract/types";
import { openOverlay } from "../../app/layers";

/** Opens the Source viewer on the cited passage, carrying the snapshot for a deleted source (AC5). */
export function openCitation(c: Pick<Citation, "n" | "sourceId" | "chunkId" | "title" | "locator" | "quote">, characterId?: string): void {
  openOverlay("O28", {
    sourceId: c.sourceId,
    chunkId: c.chunkId,
    ...(characterId ? { characterId } : {}),
    // n = 0: a retrieved-but-uncited passage (Insight) has no marker, so no snapshot.
    ...(c.n ? { cited: { n: c.n, title: c.title, ...(c.locator ? { locator: c.locator } : {}), quote: c.quote } } : {}),
  });
}

/** PDF · CSV · FILE · LINK · TEXT. */
export function typeGlyph(type: KnowledgeSource["type"], title: string): string {
  if (type === "url") return "LINK";
  if (type === "text") return "TEXT";
  const ext = /\.([a-z0-9]{2,4})$/i.exec(title)?.[1]?.toUpperCase();
  return ext && ext.length <= 4 ? ext : "FILE";
}

export interface SourceGroup { sourceId: string; title: string; type: KnowledgeSource["type"]; items: Citation[] }

export function groupBySource(cites: Citation[]): SourceGroup[] {
  const out = new Map<string, SourceGroup>();
  for (const c of [...cites].sort((a, b) => a.n - b.n)) {
    const g = out.get(c.sourceId) ?? { sourceId: c.sourceId, title: c.title, type: c.type, items: [] };
    g.items.push(c);
    out.set(c.sourceId, g);
  }
  return [...out.values()];
}

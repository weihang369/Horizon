// D-59 knowledge citations: turns chosen passages into `Citation[]` + `TurnTrace.knowledge`. Shared by the seed build
// (screenplay beats) and the live mock engines, so recorded and live cited turns have the same shape.
import type { Citation, KnowledgeChunk, KnowledgeSource, TurnTrace } from "../../contract/types";
import { hashString } from "../rng";
import type { Rng } from "../rng";

export interface ChunkRef {
  chunk: KnowledgeChunk;
  source: Pick<KnowledgeSource, "id" | "title" | "type">;
}

export type KnowledgeTrace = NonNullable<TurnTrace["knowledge"]>;

const QUOTE_MAX = 400;
const r2 = (n: number) => Math.round(n * 100) / 100;

/** Deterministic similarity: cited passages score high, retrieved-only ones lower. */
export function passageScore(key: string, chunkId: string, cited: boolean): number {
  const u = (hashString(`${key}:${chunkId}`) % 1000) / 1000;
  return cited ? r2(0.74 + u * 0.19) : r2(0.46 + u * 0.22);
}

/** `cited[i]` backs marker `[i + 1]`; `uncited` are retrieved but not used. */
export function citeKnowledge(
  key: string, cited: ChunkRef[], uncited: ChunkRef[] = [],
  opts: { query?: string; trigger?: KnowledgeTrace["trigger"] } = {},
): { citations: Citation[]; knowledge: KnowledgeTrace } {
  const citations: Citation[] = cited.map(({ chunk, source }, i) => ({
    n: i + 1,
    sourceId: source.id,
    title: source.title,
    type: source.type,
    chunkId: chunk.id,
    ...(chunk.locator ? { locator: chunk.locator } : {}),
    quote: chunk.text.length > QUOTE_MAX ? `${chunk.text.slice(0, QUOTE_MAX - 1)}…` : chunk.text,
    score: passageScore(key, chunk.id, true),
  }));
  const retrieved: KnowledgeTrace["retrieved"] = [
    ...cited.map(({ chunk, source }, i) => ({
      chunkId: chunk.id, sourceId: source.id, title: source.title, ...(chunk.locator ? { locator: chunk.locator } : {}),
      text: chunk.text, score: citations[i].score!, cited: true, n: i + 1,
    })),
    ...uncited.map(({ chunk, source }) => ({
      chunkId: chunk.id, sourceId: source.id, title: source.title, ...(chunk.locator ? { locator: chunk.locator } : {}),
      text: chunk.text, score: passageScore(key, chunk.id, false), cited: false,
    })),
  ].sort((a, b) => b.score - a.score);
  return {
    citations,
    knowledge: { ...(opts.query ? { query: opts.query } : {}), trigger: opts.trigger ?? "always", retrieved },
  };
}

/** Places `[1]..[count]` after the `count` longest sentences (in reading order), or at the end of the text. */
export function insertMarkers(text: string, count: number): string {
  const ends: { at: number; len: number }[] = [];
  const re = /[.!?…](?=\s|$)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    const at = m.index + m[0].length;
    ends.push({ at, len: at - last });
    last = at;
  }
  const picked = [...ends].sort((a, b) => b.len - a.len).slice(0, count).sort((a, b) => a.at - b.at);
  let out = "";
  let from = 0;
  picked.forEach((e, i) => {
    out += `${text.slice(from, e.at)}[${i + 1}]`;
    from = e.at;
  });
  out += text.slice(from);
  for (let n = picked.length + 1; n <= count; n++) out = `${out.trimEnd()}[${n}]`;
  return out;
}

const words = (t: string) => new Set((t.toLowerCase().match(/[a-z]{4,}/g) ?? []).map((w) => w.replace(/s$/, "")));

/** Rank passages by word overlap with the prompt and reply (seeded shuffle breaks ties). */
function rankPool(pool: ChunkRef[], query: string, rng: Rng): ChunkRef[] {
  const q = words(query);
  const scored = rng.shuffle(pool).map((r) => {
    let hit = 0;
    for (const w of words(`${r.chunk.text} ${r.source.title}`)) if (q.has(w)) hit++;
    return { r, hit };
  });
  return scored.sort((a, b) => b.hit - a.hit).map((x) => x.r);
}

/**
 * Live mock: maybe cite the speaker's indexed knowledge (deterministic per rng). About half of the replies of a
 * character with indexed passages cite 1–2 of them (the best word overlap with the prompt first); one more passage
 * is retrieved but not used.
 */
export function liveCitations(
  key: string, text: string, prompt: string, pool: ChunkRef[], rng: Rng,
): { text: string; citations: Citation[]; knowledge: KnowledgeTrace } | null {
  if (!pool.length || !rng.chance(0.55)) return null;
  const picked = rankPool(pool, `${prompt} ${text}`, rng);
  const count = Math.min(picked.length, rng.chance(0.4) ? 2 : 1);
  const sentences = (text.match(/[.!?…](\s|$)/g) ?? []).length;
  const n = Math.max(1, Math.min(count, sentences || 1));
  const { citations, knowledge } = citeKnowledge(key, picked.slice(0, n), picked.slice(n, n + 1), {
    query: prompt.trim() ? prompt.trim().slice(0, 120) : undefined,
    trigger: "always",
  });
  return { text: insertMarkers(text, n), citations, knowledge };
}

/** Replace `[n]` markers that have a citation, skipping inline code and fenced code blocks. */
export function mapMarkers(text: string, ns: ReadonlySet<number>, fn: (n: number) => string): string {
  return text
    .split(/(```[\s\S]*?(?:```|$)|`[^`\n]*`)/)
    .map((part, i) => (i % 2 ? part : part.replace(/\[(\d{1,2})\](?!\()/g, (all, d: string) => (ns.has(Number(d)) ? fn(Number(d)) : all))))
    .join("");
}

/**
 * Markdown export (D-59): `[n]` → `[^k]` footnotes, numbered across the whole transcript. `notes` collects the
 * footnote definitions (title, locator, quote) for the end of the file.
 */
export function footnoteCitations(content: string, citations: Citation[] | undefined, notes: string[]): string {
  if (!citations?.length) return content;
  const byN = new Map(citations.map((c) => [c.n, c]));
  const assigned = new Map<number, number>();
  return mapMarkers(content, new Set(byN.keys()), (n) => {
    let k = assigned.get(n);
    if (k === undefined) {
      const c = byN.get(n)!;
      k = notes.length + 1;
      assigned.set(n, k);
      const quote = c.quote.replace(/\s+/g, " ").trim();
      notes.push(`[^${k}]: ${c.title}${c.locator ? `, ${c.locator}` : ""}. "${quote}"`);
    }
    return `[^${k}]`;
  });
}

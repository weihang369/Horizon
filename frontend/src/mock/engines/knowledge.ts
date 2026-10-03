// Knowledge ingestion in the mock (rev 1.3, D-65, doc backend/02 §3.8): validate → `indexing` → staged progress on the
// global stream → `indexed` (key set: an `embedding` ledger row) | `keyword_only` (no key or no budget) | `failed`.
// MD / TXT / pasted text are chunked from their real text; PDF / DOCX get synthetic passages (the backend's Docling
// does the real extraction). Time runs on the mock Scheduler, so tests stay deterministic. Owner: EE.
import type { KnowledgeChunk, KnowledgeSource, UsageRecord } from "../../contract/types";
import { HorizonError } from "../../contract/errors";
import type { AddKnowledgeInput, IngestProgress } from "../../client/HorizonClient";
import type { PricingTable } from "../../domain/cost";
import { embeddingCostUsd, estimateTokens } from "../../domain/cost";
import type { Dataset } from "../db/dataset";
import type { Scheduler } from "../time/Scheduler";

export const KNOWLEDGE_LIMITS = { maxBytes: 10 * 1024 * 1024, maxSourcesPerCharacter: 20, maxPages: 300 } as const;

const FILE_KINDS = {
  pdf: { mimes: ["application/pdf"], magic: "%PDF", locator: "p." },
  docx: { mimes: ["application/vnd.openxmlformats-officedocument.wordprocessingml.document"], magic: "PK\u0003\u0004", locator: "§" },
  md: { mimes: ["text/markdown", "text/x-markdown", "text/plain"], magic: null, locator: "¶" },
  markdown: { mimes: ["text/markdown", "text/x-markdown", "text/plain"], magic: null, locator: "¶" },
  txt: { mimes: ["text/plain"], magic: null, locator: "¶" },
} as const;
type FileKind = keyof typeof FILE_KINDS;
const isFileKind = (x: string): x is FileKind => x in FILE_KINDS;

/** Stage plan: [delay ms after the previous step, stage, pct]. ~2.4 s end to end at demo speed ×1. */
const STAGES: [number, IngestProgress["stage"], number][] = [
  [300, "extracting", 0.15], [500, "extracting", 0.45], [400, "chunking", 0.65], [400, "embedding", 0.85],
];
const FINISH_MS = 800;

export interface KnowledgeHost {
  readonly db: Dataset;
  readonly sched: Scheduler;
  readonly pricing: PricingTable;
  newId(prefix: string): string;
  iso(): string;
  /** Embedding is possible: a valid key is set and today's cap isn't reached. */
  canEmbed(): boolean;
  ledger(row: Omit<UsageRecord, "id" | "at">): void;
  progress(source: KnowledgeSource, progress?: IngestProgress): void;
  /** Passages waiting for a running pipeline (per client; not persisted: a reload restarts from stored chunks). */
  readonly pending: Map<string, Prepared>;
}

/** What the pipeline needs to finish a source: its passages (and their ids when re-indexing), or why it can't be read. */
export interface Prepared { chunks: string[]; ids?: string[]; locators?: string[]; locator: string; pages?: number; error?: string }

const invalid = (message: string, details?: Record<string, unknown>) => new HorizonError("validation", message, { retryable: false, details });

/** FNV-1a over the content: duplicate detection per character (doc backend/02: unique (character, sha256)). */
export function contentHash(bytes: Uint8Array): string {
  let h = 0x811c9dc5;
  for (const b of bytes) {
    h ^= b;
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return `${h.toString(16).padStart(8, "0")}:${bytes.length}`;
}

function paragraphs(text: string): string[] {
  const out: string[] = [];
  for (const para of text.replace(/\r\n/g, "\n").split(/\n\s*\n/)) {
    const p = para.replace(/\s+/g, " ").trim();
    if (!p) continue;
    // Keep passages readable in the viewer: split long paragraphs on sentence ends near 900 chars.
    let rest = p;
    while (rest.length > 1200) {
      const cut = rest.lastIndexOf(". ", 900);
      const at = cut > 300 ? cut + 1 : 900;
      out.push(rest.slice(0, at).trim());
      rest = rest.slice(at).trim();
    }
    out.push(rest);
  }
  return out;
}

function syntheticPassages(title: string, kind: "pdf" | "docx", bytes: number): Prepared {
  const pages = kind === "pdf" ? Math.min(KNOWLEDGE_LIMITS.maxPages, Math.max(1, Math.round(bytes / 40_000))) : undefined;
  const n = Math.max(1, Math.min(6, pages ?? Math.ceil(bytes / 60_000)));
  const chunks = Array.from({ length: n }, (_, i) =>
    `Passage ${i + 1} of “${title}”. In the live app, Docling extracts the real text of this ${kind.toUpperCase()} and these passages show it; the demo shows placeholders.`);
  return { chunks, locator: FILE_KINDS[kind].locator, pages };
}

/** Validated input, ready to create a source (throws `validation` / `conflict`). */
export interface Accepted { title: string; type: "file" | "text"; bytes: number; hash: string; prepared: Prepared }

export async function acceptInput(h: KnowledgeHost, characterId: string, input: AddKnowledgeInput): Promise<Accepted> {
  const existing = Object.values(h.db.knowledge).filter((k) => k.characterId === characterId);
  if (existing.length >= KNOWLEDGE_LIMITS.maxSourcesPerCharacter) {
    throw invalid(`A character can have at most ${KNOWLEDGE_LIMITS.maxSourcesPerCharacter} sources. Delete one first.`, { field: "sources", limit: KNOWLEDGE_LIMITS.maxSourcesPerCharacter });
  }
  let accepted: Accepted;
  if ("file" in input) {
    const f = input.file;
    const ext = f.name.split(".").pop()?.toLowerCase() ?? "";
    if (!isFileKind(ext)) {
      throw invalid("Add a PDF, DOCX, Markdown or text file. CSV, spreadsheets and links aren't supported.", { field: "file", accepted: ["pdf", "docx", "md", "txt"] });
    }
    const kind = FILE_KINDS[ext];
    if (f.type && f.type !== "application/octet-stream" && !(kind.mimes as readonly string[]).includes(f.type)) {
      throw invalid(`That file's type (${f.type}) doesn't match .${ext}.`, { field: "file", mime: f.type });
    }
    if (f.size > KNOWLEDGE_LIMITS.maxBytes) throw invalid("Files can be at most 10 MB.", { field: "file", limit: KNOWLEDGE_LIMITS.maxBytes, bytes: f.size });
    const bytes = new Uint8Array(await f.arrayBuffer());
    if (kind.magic && String.fromCharCode(...bytes.slice(0, kind.magic.length)) !== kind.magic) {
      throw invalid(`This doesn't look like a real .${ext} file.`, { field: "file" });
    }
    let prepared: Prepared;
    if (ext === "pdf" || ext === "docx") prepared = syntheticPassages(f.name, ext, f.size);
    else {
      const chunks = paragraphs(new TextDecoder().decode(bytes));
      prepared = chunks.length ? { chunks, locator: "¶" } : { chunks: [], locator: "¶", error: "This file has no readable text." };
    }
    accepted = { title: f.name, type: "file", bytes: f.size, hash: contentHash(bytes), prepared };
  } else {
    const title = input.title.trim();
    if (!title) throw invalid("Give the pasted text a title.", { field: "title" });
    const bytes = new TextEncoder().encode(input.text);
    if (!input.text.trim()) throw invalid("Paste some text first.", { field: "text" });
    if (bytes.length > KNOWLEDGE_LIMITS.maxBytes) throw invalid("Pasted text can be at most 10 MB.", { field: "text", limit: KNOWLEDGE_LIMITS.maxBytes });
    accepted = { title: title.slice(0, 200), type: "text", bytes: bytes.length, hash: contentHash(bytes), prepared: { chunks: paragraphs(input.text), locator: "¶" } };
  }
  const hashes = h.db.knowledgeHashes ?? {};
  const dup = existing.find((k) => hashes[k.id] === accepted.hash);
  if (dup) throw new HorizonError("conflict", `“${dup.title}” already has this content.`, { retryable: false, details: { existingSourceId: dup.id } });
  return accepted;
}

/** Create the `indexing` source and schedule its pipeline. */
export function startSource(h: KnowledgeHost, characterId: string, worldId: string, a: Accepted): KnowledgeSource {
  const src: KnowledgeSource = {
    id: h.newId("kno"), characterId, worldId, title: a.title, type: a.type, status: "indexing", bytes: a.bytes, addedAt: h.iso(),
  };
  h.db.knowledge[src.id] = src;
  (h.db.knowledgeHashes ??= {})[src.id] = a.hash;
  h.pending.set(src.id, a.prepared);
  runPipeline(h, src.id);
  return src;
}

export function runPipeline(h: KnowledgeHost, sourceId: string): void {
  const tag = `kno:${sourceId}`;
  h.sched.cancelTag(tag);
  let t = 0;
  for (const [delay, stage, pct] of STAGES) {
    t += delay;
    h.sched.after(t, () => {
      const s = h.db.knowledge[sourceId];
      if (s?.status === "indexing") h.progress(s, { stage, pct });
    }, tag);
  }
  h.sched.after(t + FINISH_MS, () => finish(h, sourceId), tag);
}

function finish(h: KnowledgeHost, sourceId: string): void {
  const s = h.db.knowledge[sourceId];
  if (!s || s.status !== "indexing") return;
  const prepared = h.pending.get(sourceId) ?? fromStoredChunks(h.db, sourceId, s);
  h.pending.delete(sourceId);
  if (prepared.error) {
    Object.assign(s, { status: "failed", error: prepared.error, chunks: undefined });
    h.progress(s);
    return;
  }
  for (const c of Object.values(h.db.knowledgeChunks)) if (c.sourceId === sourceId) delete h.db.knowledgeChunks[c.id];
  const key = sourceId.replace(/^kno_/, "");
  prepared.chunks.forEach((text, i) => {
    const chunk: KnowledgeChunk = {
      // Re-indexing keeps chunk ids (and locators), so citations in old transcripts still resolve.
      id: prepared.ids?.[i] ?? `kch_${key}${String(i + 1).padStart(2, "0")}`, sourceId, index: i,
      locator: prepared.locators?.[i] ?? `${prepared.locator} ${i + 1}`, text,
    };
    h.db.knowledgeChunks[chunk.id] = chunk;
  });
  const embed = h.canEmbed();
  if (embed) {
    const tokens = prepared.chunks.reduce((n, c) => n + estimateTokens(c), 0);
    const p = h.pricing.embedding;
    h.ledger({ category: "embedding", model: p.model, provider: p.provider, characterId: s.characterId, tokensIn: tokens, costUsd: embeddingCostUsd(tokens, p) });
  }
  Object.assign(s, { status: embed ? "indexed" : "keyword_only", chunks: prepared.chunks.length, error: undefined, ...(prepared.pages ? { pages: prepared.pages } : {}) });
  h.progress(s);
}

/** Re-index without the original (seed, or after a reload): reuse the stored passages; a failed source fails again. */
function fromStoredChunks(db: Dataset, sourceId: string, s: KnowledgeSource): Prepared {
  const chunks = Object.values(db.knowledgeChunks).filter((c) => c.sourceId === sourceId).sort((a, b) => a.index - b.index);
  if (!chunks.length) return { chunks: [], locator: "¶", error: s.error ?? "Couldn't read this source." };
  const loc = chunks[0].locator?.split(" ")[0] ?? "¶";
  return {
    chunks: chunks.map((c) => c.text), ids: chunks.map((c) => c.id), locators: chunks.map((c) => c.locator ?? ""),
    locator: loc, pages: s.pages,
  };
}

/** Re-run indexing for an existing source. */
export function reindex(h: KnowledgeHost, s: KnowledgeSource): KnowledgeSource {
  if (s.type === "url") throw new HorizonError("conflict", "Web page sources are read-only and can't be re-indexed.", { retryable: false });
  if (s.status === "indexing") throw new HorizonError("conflict", "This source is already being indexed.", { retryable: false });
  h.pending.set(s.id, fromStoredChunks(h.db, s.id, s));
  Object.assign(s, { status: "indexing" });
  runPipeline(h, s.id);
  return s;
}

export function removeSource(h: KnowledgeHost, sourceId: string): void {
  h.sched.cancelTag(`kno:${sourceId}`);
  h.pending.delete(sourceId);
  delete h.db.knowledge[sourceId];
  if (h.db.knowledgeHashes) delete h.db.knowledgeHashes[sourceId];
  for (const c of Object.values(h.db.knowledgeChunks)) if (c.sourceId === sourceId) delete h.db.knowledgeChunks[c.id];
}

/** After load or reset: sources left in `indexing` (a reload mid-pipeline) restart from what is stored. */
export function resumeIndexing(h: KnowledgeHost): void {
  for (const s of Object.values(h.db.knowledge)) if (s.status === "indexing") runPipeline(h, s.id);
}

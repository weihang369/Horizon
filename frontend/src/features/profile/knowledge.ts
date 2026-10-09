// Knowledge helpers shared by the Knowledge tab (PRF-08) and O28 Source viewer (D-59). Owner: Builder B.
import type { GlobalEvent, IngestProgress } from "@/client/HorizonClient";
import type { KnowledgeSource } from "@/contract/types";

/** The file picker's filter: the supported inputs only (knowledge-sources "Supported formats in the UI"). */
export const ACCEPT = ".pdf,.docx,.md,.markdown,.txt";
/** D-65: pasted text is capped at 200 KB on both clients (files stay at 10 MB). */
export const PASTE_MAX_BYTES = 204_800;
export const pasteBytes = (text: string) => new TextEncoder().encode(text).length;
/** "12.3 KB / 200 KB": the Paste text dialog's counter (KB = 1 024 bytes, as the limit is). */
export const pasteCounter = (bytes: number) => `${(bytes / 1024).toFixed(bytes < 10_240 ? 1 : 0)} KB / 200 KB`;
/** Why the Paste text dialog can't be submitted yet, or null (the clients refuse the same inputs). */
export function pasteProblem(title: string, text: string): string | null {
  if (!title.trim()) return "Give the pasted text a title.";
  if (!text.trim()) return "Paste some text first.";
  if (pasteBytes(text) > PASTE_MAX_BYTES) return "Pasted text can be at most 200 KB.";
  return null;
}

export const STAGE_LABEL: Record<IngestProgress["stage"], string> = {
  extracting: "Reading", chunking: "Splitting into passages", embedding: "Indexing for search by meaning",
};
export type ProgressMap = Readonly<Record<string, IngestProgress>>;
/**
 * The latest ingestion stage per source, from `entity.changed { kind: "knowledge", id, progress }` on the global stream.
 * The final event of a run (no `progress`) clears the source; a demo reset clears everything.
 */
export function reduceProgress(state: ProgressMap, e: GlobalEvent): ProgressMap {
  if (e.type === "mock.reset") return Object.keys(state).length ? {} : state;
  if (e.type !== "entity.changed" || e.kind !== "knowledge" || !e.id) return state;
  if (!e.progress) {
    if (!(e.id in state)) return state;
    const { [e.id]: _done, ...rest } = state;
    return rest;
  }
  return { ...state, [e.id]: e.progress };
}

/** Cited sources first (most-cited on top), then newest; failed sources sink below indexing ones. */
export function sortSources(list: KnowledgeSource[]): KnowledgeSource[] {
  const rank = (s: KnowledgeSource) => (s.status === "failed" ? 1 : 0);
  return [...list].sort((a, b) =>
    (b.citedCount ?? 0) - (a.citedCount ?? 0)
    || rank(a) - rank(b)
    || (b.addedAt ?? "").localeCompare(a.addedAt ?? "")
    || a.title.localeCompare(b.title));
}

export function formatBytes(n?: number): string {
  if (!n) return "";
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)} MB`;
  if (n >= 1e3) return `${Math.round(n / 1e3)} KB`;
  return `${n} B`;
}

const DATE = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
export function formatAdded(iso?: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : DATE.format(d);
}

/** "18 pages · 10 passages · 482 KB" (whatever the source knows). */
export function sourceFacts(s: KnowledgeSource, opts: { bytes?: boolean } = {}): string[] {
  const out: string[] = [];
  if (s.pages) out.push(`${s.pages} ${s.pages === 1 ? "page" : "pages"}`);
  if (s.chunks) out.push(`${s.chunks} ${s.chunks === 1 ? "passage" : "passages"}`);
  if (opts.bytes !== false && s.bytes) out.push(formatBytes(s.bytes));
  return out;
}

export const TYPE_NAME: Record<KnowledgeSource["type"], string> = { file: "Document", url: "Web page", text: "Pasted text" };
/** Badge text per status (rev 1.3 adds `keyword_only`: searchable by keyword only until re-indexed). */
export const STATUS_LABEL: Record<KnowledgeSource["status"], string> = {
  indexed: "indexed", indexing: "indexing", keyword_only: "keyword only", failed: "failed",
};
/** Badge tone per status (Knowledge tab, O28 viewer, dev kit). */
export const STATUS_TONE = { indexed: "ok", indexing: "ink", keyword_only: "warn", failed: "error" } as const satisfies Record<KnowledgeSource["status"], string>;
/** Sources with readable passages open in the O28 viewer. */
export const isReadable = (s: KnowledgeSource) => s.status === "indexed" || s.status === "keyword_only";

// Knowledge helpers shared by the Knowledge tab (PRF-08) and O28 Source viewer (D-59). Owner: Builder B.
import type { KnowledgeSource } from "@/contract/types";

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

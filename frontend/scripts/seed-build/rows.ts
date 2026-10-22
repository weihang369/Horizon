// D-110: what the real run stored that the contract doesn't carry (`horizon demo export --rows`) → seed/rows/**, read by
// the backend's seed import only: the documents as the app indexed them (sections, pieces, their vectors, the stored
// originals), the memories' vectors and recall counts, recall's line index, the stored query rewrites and safety answers,
// and the full ledger rows. Ids are renamed and times moved exactly as for the recorded sessions.
import path from "node:path";
import type { UsageRecord } from "../../src/contract/types";
import type { RecordedRows, Row } from "./recorded";
import { RECORDED_FILES_DIR } from "./recorded";
import { rewrite } from "./recordedCompile";
import type { RecordingMap } from "./recordedCompile";

const pad2 = (n: number) => String(n).padStart(2, "0");

export interface RowsOutput {
  /** seed-relative path → JSON data (wrapped by the build). */
  files: [string, unknown][];
  /** seed-relative path → a file to copy as is. */
  copies: [string, string][];
  /** The real ledger in wire form: shipped sessions' rows (and rows of no session) vs the mock overlay's. */
  ledger: { seed: UsageRecord[]; mock: UsageRecord[] };
}

export function rowsOutput(
  rows: RecordedRows, recordings: (RecordingMap & { mock: boolean })[], knowledgeIds: Record<string, string>,
  knowledgeKeys: Record<string, string>, memoryIds: Record<string, string>,
): RowsOutput {
  const files: [string, unknown][] = [];
  const copies: [string, string][] = [];
  const ids: Record<string, string> = { ...knowledgeIds, ...memoryIds };
  const bySession: Record<string, RecordingMap & { mock: boolean }> = {};
  const byMessage: Record<string, RecordingMap & { mock: boolean }> = {};
  for (const r of recordings) {
    ids[r.sourceSessionId] = r.seedSessionId;
    Object.assign(ids, r.messageIds);
    bySession[r.sourceSessionId] = r;
    for (const m of Object.keys(r.messageIds)) byMessage[m] = r;
  }
  const recOf = (row: Row) => bySession[String(row.session_id ?? row.source_session_id ?? "")] ?? byMessage[String(row.message_id ?? "")];
  const move = <T>(row: T, rec: RecordingMap | undefined): T => rewrite(row, ids, rec?.shiftMs ?? 0);

  files.push(["rows/space.json", rows.space]);

  // Documents: no session, so no time shift (they were added on their story dates)
  for (const k of rows.knowledge) {
    const seedId = knowledgeIds[String(k.source.id)];
    const key = knowledgeKeys[seedId];
    if (!seedId || !key) throw new Error(`[seed-build] recorded source ${String(k.source.id)} matches no fixture`);
    const sections = [...k.sections].sort((a, b) => Number(a.idx) - Number(b.idx));
    sections.forEach((s, i) => { ids[String(s.id)] = `ksec_${key}${pad2(i + 1)}`; });
    for (const name of k.files) copies.push([`knowledge/files/${seedId}/${name}`, path.join(RECORDED_FILES_DIR, String(k.source.id), name)]);
    files.push([`rows/knowledge/${seedId}.json`, {
      space: rows.space.id,
      source: move(k.source, undefined),
      files: k.files,
      sections: sections.map((s) => move(s, undefined)),
      chunks: k.chunks.map((c) => move(c, undefined)),
    }]);
  }

  files.push(["rows/memory.json", rows.memory.filter((m) => memoryIds[String(m.id)]).map((m) => move(m, recOf(m)))]);
  files.push(["rows/message-index.json", rows.messageIndex.filter((m) => recOf(m)).map((m) => move(m, recOf(m)))]);
  files.push(["rows/ai-meta.json", rows.aiMeta.filter((m) => recOf(m)).map((m) => move(m, recOf(m)))]);

  const usage = rows.usage.map((u) => move(u, recOf(u)));
  files.push(["rows/usage.json", usage]);
  const ledger: RowsOutput["ledger"] = { seed: [], mock: [] };
  for (const [u, raw] of usage.map((u, i) => [u, rows.usage[i]] as const)) {
    (recOf(raw)?.mock ? ledger.mock : ledger.seed).push(usageWire(u));
  }
  return { files, copies, ledger };
}

function usageWire(u: Row): UsageRecord {
  const out: Record<string, unknown> = { id: u.id, at: u.at, category: u.category };
  const opt: [string, string][] = [["model", "model"], ["provider", "provider"], ["price_period", "pricePeriod"],
    ["session_id", "sessionId"], ["character_id", "characterId"], ["job_id", "jobId"], ["tokens_in", "tokensIn"],
    ["tokens_cached", "tokensCached"], ["tokens_out", "tokensOut"]];
  for (const [col, key] of opt) if (u[col] !== null && u[col] !== undefined) out[key] = u[col];
  out.costUsd = u.cost_usd;
  for (const [col, key] of [["estimated_cost_usd", "estimatedCostUsd"], ["energy_points", "energyPoints"], ["latency_ms", "latencyMs"]]) {
    if (u[col] !== null && u[col] !== undefined) out[key] = u[col];
  }
  return out as unknown as UsageRecord;
}

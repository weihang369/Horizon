// Real demo content exported by `horizon demo export` (backend/horizon/demo_export.py) into ./recorded/. Each file is
// optional: without it the build falls back to the hand-written fixtures, so a partial export still builds.
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { KnowledgeChunk, KnowledgeSource, MemoryItem, Message, Session, SessionEvent, ThemeSong } from "../../src/contract/types";

const DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "recorded");

function read<T>(rel: string): T | null {
  const file = path.join(DIR, rel);
  return existsSync(file) ? (JSON.parse(readFileSync(file, "utf8")) as T) : null;
}

export interface RecordedSession {
  /** The session id in the app it was recorded in. */
  source: string;
  exportedAt: string;
  session: Session;
  events: SessionEvent[];
  messages: Message[];
}

export type RecordedSong = Pick<ThemeSong, "durationSec" | "generation" | "licenseNote"> & { bytes?: number; format?: string; exportedAt: string };

export interface RecordedImages {
  variants: string[];
  model: string;
  summary: string;
  exportedAt: string;
}

export interface RecordedKnowledge {
  source: KnowledgeSource;
  chunks: KnowledgeChunk[];
}

/** A database row as stored (snake_case columns); `vector` is the float32 embedding, base64, in `space`. */
export type Row = Record<string, unknown> & { vector?: string };

/** D-110: what the real run wrote that the API doesn't show (`horizon demo export --rows`). */
export interface RecordedRows {
  space: { id: string; dims: number };
  knowledge: { source: Row; files: string[]; sections: Row[]; chunks: Row[] }[];
  memory: Row[];
  messageIndex: Row[];
  aiMeta: Row[];
  usage: Row[];
  energy: Record<string, { energy_current: number; energy_as_of: string; energy_spent_today: number }>;
}

export const recordedSession = (seedSessionId: string) => read<RecordedSession>(`sessions/${seedSessionId}.json`);
export const RECORDED_ROWS: RecordedRows | null = read("rows.json");
/** The recorded sources' stored files (original, extracted.md), by recorded source id. */
export const RECORDED_FILES_DIR = path.join(DIR, "knowledge-files");
export const RECORDED_SONGS: Record<string, RecordedSong> = read("songs.json") ?? {};
export const RECORDED_IMAGES: Record<string, RecordedImages> = read("images.json") ?? {};
export const RECORDED_KNOWLEDGE: RecordedKnowledge[] | null = read("knowledge.json");
export const RECORDED_MEMORY: MemoryItem[] | null = read("memory.json");

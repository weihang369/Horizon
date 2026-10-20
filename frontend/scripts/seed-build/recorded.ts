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

export const recordedSession = (seedSessionId: string) => read<RecordedSession>(`sessions/${seedSessionId}.json`);
export const RECORDED_SONGS: Record<string, RecordedSong> = read("songs.json") ?? {};
export const RECORDED_IMAGES: Record<string, RecordedImages> = read("images.json") ?? {};
export const RECORDED_KNOWLEDGE: RecordedKnowledge[] | null = read("knowledge.json");
export const RECORDED_MEMORY: MemoryItem[] | null = read("memory.json");

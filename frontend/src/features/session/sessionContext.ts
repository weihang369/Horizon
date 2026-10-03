// Session-screen context and small shared helpers (C). The frame provides it, so <SessionLog> and <Composer>
// work inside any layout (Builder D renders them with only `rt`) and still know replay / demo / readable state.
import { createContext, useContext } from "react";
import { useStore } from "zustand";
import type { Character, Message } from "../../contract/types";
import type { SessionRuntimeView } from "../../client/hooks";
import { entities } from "../../stores/entities";

export interface SessionCtx {
  replay: boolean;
  /** No key (demo mode): live actions open O05 (R15). */
  demo: boolean;
  /** A seed recording (replay-only, APP-09 AC6). */
  isSeed: boolean;
  /** Readable Mode forced for every message (CHAT-08 AC2). */
  readable: boolean;
  worldId: string;
  sessionId: string;
  /** O08 is open (log rows become selectable). */
  insightOpen: boolean;
}

export const SessionContext = createContext<SessionCtx | null>(null);

export function useSessionCtx(): SessionCtx | null {
  return useContext(SessionContext);
}

/** Every character known to the client, by id (absorbed from any query). */
export function useChars(): Record<string, Character> {
  return useStore(entities, (s) => s.chars);
}

export function useChar(id: string | undefined): Character | undefined {
  return useStore(entities, (s) => (id ? s.chars[id] : undefined));
}

/** "Dr. Amara Okafor" → "Amara". */
export function firstName(name: string | undefined): string {
  if (!name) return "";
  return name.split(" ").find((w) => !/^(dr|prof|mr|ms|mrs)\.?$/i.test(w)) ?? name;
}

/** The character currently talking (streaming), else the last character who spoke. */
export function currentSpeakerId(rt: Pick<SessionRuntimeView, "streamingId" | "messages" | "list" | "thinkingId">): string | undefined {
  const s = rt.streamingId ? rt.messages[rt.streamingId] : undefined;
  if (s?.author.characterId) return s.author.characterId;
  if (rt.thinkingId) return rt.thinkingId;
  for (let i = rt.list.length - 1; i >= 0; i--) {
    const m = rt.list[i];
    if (m.author.type === "character" && m.author.characterId) return m.author.characterId;
  }
  return undefined;
}

export const isCharacterMsg = (m: Message | undefined): m is Message =>
  !!m && m.author.type === "character" && !!m.author.characterId;

/** The latest finished character message id (Insight default selection, INS-01 AC5); a streaming one only if alone. */
export function latestCharacterMessageId(list: Message[]): string | undefined {
  let streaming: string | undefined;
  for (let i = list.length - 1; i >= 0; i--) {
    if (!isCharacterMsg(list[i])) continue;
    if (list[i].status !== "streaming") return list[i].id;
    streaming ??= list[i].id;
  }
  return streaming;
}

/** Long messages switch to the straight Readable panel (CHAT-08 AC1). */
export const READABLE_CHARS = 600;

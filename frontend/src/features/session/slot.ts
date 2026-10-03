// Read an open session runtime from the store (overlays O08/O10 ride on the screen's runtime, never their own).
import { useStore } from "zustand";
import type { SessionRuntimeState } from "../../engine/sessionReducer";
import { sessionStore, slotKey } from "../../stores/session";

/** The replay slot when one is open for this session, else the live slot. */
export function useSlotRuntime(sessionId: string | undefined): { runtime?: SessionRuntimeState; replay: boolean } {
  const replayRt = useStore(sessionStore, (s) => (sessionId ? s.slots[slotKey(sessionId, true)]?.runtime : undefined));
  const liveRt = useStore(sessionStore, (s) => (sessionId ? s.slots[slotKey(sessionId, false)]?.runtime : undefined));
  return replayRt ? { runtime: replayRt, replay: true } : { runtime: liveRt, replay: false };
}

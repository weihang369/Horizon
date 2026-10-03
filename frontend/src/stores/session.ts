// Session store: the reducer output for each open session runtime (live or replay). Owner: EE.
// Written at most once per animation frame by the runtime controller (client/sessionRuntime.ts).
import { createStore } from "zustand/vanilla";
import type { HorizonErrorShape } from "../contract/errors";
import type { SessionRuntimeState } from "../engine/sessionReducer";

export interface ReplayInfo {
  playing: boolean;
  /** Timeline ms (gaps trimmed). Updated on events and transport actions; poll `controls.position()` for a scrubber. */
  position: number;
  duration: number;
  rate: number;
  ended: boolean;
  /** seq of the last applied event (the "playhead" for Continue live, R16). */
  seq: number;
}

export interface SessionSlot {
  id: string;
  replay: boolean;
  status: "loading" | "ready" | "error";
  runtime?: SessionRuntimeState;
  error?: HorizonErrorShape;
  player?: ReplayInfo;
}

export interface SessionStoreState { slots: Record<string, SessionSlot> }

export const sessionStore = createStore<SessionStoreState>(() => ({ slots: {} }));

export const slotKey = (id: string, replay: boolean): string => `${id}:${replay ? "replay" : "live"}`;

export function patchSlot(key: string, patch: Partial<SessionSlot>): void {
  sessionStore.setState((s) => {
    const cur = s.slots[key];
    if (!cur && !patch.id) return s;
    return { slots: { ...s.slots, [key]: { ...(cur as SessionSlot), ...patch } } };
  });
}

export function dropSlot(key: string): void {
  sessionStore.setState((s) => {
    const slots = { ...s.slots };
    delete slots[key];
    return { slots };
  });
}

/** Energy overlay of any open runtime (replay drains are sandboxed here, never written to characters). */
export function runtimeEnergy(characterId: string, state: SessionStoreState = sessionStore.getState()): { energy: SessionRuntimeState["energyById"][string]; replay: boolean } | undefined {
  const slots = Object.values(state.slots);
  for (let i = slots.length - 1; i >= 0; i--) {
    const e = slots[i].runtime?.energyById[characterId];
    if (e) return { energy: e, replay: slots[i].replay };
  }
  return undefined;
}

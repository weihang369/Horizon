// Overlay ids, kinds and props (doc 03 §2, UXA D1, README §3.3). Owner: EE.
// Builders may add optional props (additive only).
import type { Emotion } from "../contract/types";

/** `dock` (additive) = an O12 DockExpansion: rendered by the Dock, collapsed by Esc step 2 (R4/R5). */
export type LayerKind = "modal" | "drawer" | "popover" | "ceremony" | "ambient" | "dock";

export interface AnchorRect { x: number; y: number; width: number; height: number }

export interface OverlayProps {
  O01: Record<string, never>;
  O02: { worldId?: string };
  O03: {
    title: string; body?: string; confirmLabel?: string;
    /** Typed confirmation: the user must type this exact text (delete world / character / all data). */
    typed?: string;
    onConfirm: () => void | Promise<void>;
  };
  O04: { label: string; estimateUsd: number; onConfirm: () => void };
  O05: { reason?: string };
  O06: { characterId: string; emotion: Emotion };
  O07: { sessionId: string; characterId: string; anchor?: AnchorRect };
  O08: { sessionId: string; messageId?: string };
  O09: { anchor?: AnchorRect };
  O10: { sessionId: string };
  O11: { sessionId: string; query: string; anchor?: AnchorRect; onPick: (characterId: string) => void };
  O12: { sessionId: string; kind: "ask" | "interject" | "direction" | "stepin"; characterId?: string };
  O13: { characterId: string; onSave: () => void; onDiscard: () => void };
  O14: Record<string, never>;
  O15: { characterId: string };
  O16: { sessionId: string; kind: "vs" | "round"; label?: string };
  O17: { sessionId: string };
  O18: Record<string, never>;
  O19: Record<string, never>;
  O20: Record<string, never>;
  O21: { scope: "daily" | "creation"; spentUsd: number; capUsd: number; sessionId?: string };
  O22: Record<string, never>;
  O23: { sessionId: string };
  O24: { sessionId: string; characterId: string; anchor?: AnchorRect };
  O25: { characterId: string; emotion: Emotion; newAssetId: string };
  O26: { sessionId: string };
  O27: { characterId: string; sessionId?: string };
  /** D-59 Source viewer: a knowledge source's passages, scrolled to and highlighting `chunkId`. */
  O28: { sourceId: string; chunkId?: string; characterId?: string };
}

export type OverlayId = keyof OverlayProps;

/** Props every overlay component receives besides its own. */
export interface OverlayBaseProps { close: () => void; layerKey: number }
export type OverlayComponentProps<Id extends OverlayId> = OverlayProps[Id] & OverlayBaseProps;

export const OVERLAY_NAMES: Record<OverlayId, string> = {
  O01: "Pause menu", O02: "Create / Edit World", O03: "Confirm", O04: "Cost confirmation", O05: "Key required",
  O06: "Emotion lightbox", O07: "Emotion picker", O08: "Insight drawer", O09: "Mini-player", O10: "Backlog",
  O11: "Mention picker", O12: "Dock expansion", O13: "Unsaved draft", O14: "Toast stack", O15: "Summon reveal",
  O16: "VS splash / Round banner", O17: "Episode end", O18: "Mock State Switcher", O19: "Desktop guard",
  O20: "Keyboard shortcuts", O21: "Budget reached", O22: "Demo-mode tape", O23: "Replay transport",
  O24: "Portrait menu", O25: "Old / New asset", O26: "End debate early", O27: "Energy top-up", O28: "Source viewer",
};

/** Layer kind per overlay (UXA D1 table; O12 is a dock expansion, O14/O19/O22/O23 are ambient). */
export const OVERLAY_KINDS: Record<OverlayId, LayerKind> = {
  O01: "modal", O02: "modal", O03: "modal", O04: "modal", O05: "modal", O06: "modal", O07: "popover", O08: "drawer",
  O09: "popover", O10: "drawer", O11: "popover", O12: "dock", O13: "modal", O14: "ambient", O15: "ceremony",
  O16: "ceremony", O17: "ceremony", O18: "drawer", O19: "ambient", O20: "modal", O21: "modal", O22: "ambient",
  O23: "ambient", O24: "popover", O25: "modal", O26: "modal", O27: "modal", O28: "modal",
};

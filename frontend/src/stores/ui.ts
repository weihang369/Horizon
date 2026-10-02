// UI store: the one LayerStack (R4), toasts (STATE-05), Insight selection, dock expansion, dev toggles. Owner: EE.
import { createStore } from "zustand/vanilla";
import { useStore } from "zustand";
import type { LayerKind, OverlayId, OverlayProps } from "../app/overlayTypes";

export interface Layer<Id extends OverlayId = OverlayId> {
  key: number;
  id: Id;
  kind: LayerKind;
  props: OverlayProps[Id];
  /** Focus returns here when the layer closes (modals). */
  returnFocusTo: HTMLElement | null;
}

export type ToastVariant = "success" | "info" | "warn" | "error";
export interface Toast { id: number; variant: ToastVariant; text: string; action?: { label: string; run(): void }; at: number }

export interface UiState {
  layers: Layer[];
  toasts: Toast[];
  /** Insight selection (O08): which message the drawer shows. */
  insight: { sessionId?: string; messageId?: string };
  /** O12 DockExpansion currently open (kind) per the active session dock. */
  dockExpansion: { sessionId: string; kind: OverlayProps["O12"]["kind"]; characterId?: string } | null;
  perfHud: boolean;
}

export const ui = createStore<UiState>(() => ({ layers: [], toasts: [], insight: {}, dockExpansion: null, perfHud: false }));

export function useUi<T>(sel: (s: UiState) => T): T {
  return useStore(ui, sel);
}

export const topLayer = (s: UiState = ui.getState()): Layer | undefined => s.layers[s.layers.length - 1];
export const hasBlockingLayer = (s: UiState = ui.getState()): boolean => s.layers.some((l) => l.kind === "modal" || l.kind === "ceremony");

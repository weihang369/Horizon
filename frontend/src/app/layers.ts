// Overlay + toast API (README §3.3). Owner: EE.
// One LayerStack in the ui store; LayerStack.tsx renders it with central Esc order and focus trap/restore.
import { audio } from "../audio/engine";
import type { SfxId } from "../audio/synth/sfx";
import { ui } from "../stores/ui";
import type { Layer, Toast, ToastVariant } from "../stores/ui";
import type { OverlayId, OverlayProps } from "./overlayTypes";
import { OVERLAY_KINDS } from "./overlayTypes";

let nextKey = 1;
let nextToast = 1;
const TOAST_MS = 4000;
const TOAST_MAX = 3;
const TOAST_SFX: Record<ToastVariant, SfxId> = { success: "toast_success", info: "toast_info", warn: "toast_warn", error: "toast_error" };

type PropsArg<Id extends OverlayId> = OverlayProps[Id] extends Record<string, never> ? [props?: OverlayProps[Id]] : [props: OverlayProps[Id]];

/** Open an overlay on the LayerStack. Re-opening an id that is already open replaces its props. Returns its layer key. */
export function openOverlay<Id extends OverlayId>(id: Id, ...[props]: PropsArg<Id>): number {
  const kind = OVERLAY_KINDS[id];
  if (kind === "dock") {
    const p = props as OverlayProps["O12"];
    ui.setState({ dockExpansion: { sessionId: p.sessionId, kind: p.kind, characterId: p.characterId } });
    return 0;
  }
  const s = ui.getState();
  const existing = s.layers.find((l) => l.id === id);
  if (existing) {
    ui.setState({ layers: s.layers.map((l) => (l === existing ? { ...l, props: (props ?? {}) as OverlayProps[Id] } : l)) });
    return existing.key;
  }
  const active = typeof document !== "undefined" ? (document.activeElement as HTMLElement | null) : null;
  const layer: Layer<Id> = { key: nextKey++, id, kind, props: (props ?? {}) as OverlayProps[Id], returnFocusTo: active };
  const patch: Partial<typeof s> = { layers: [...s.layers, layer as unknown as Layer] };
  if (id === "O08") patch.insight = { sessionId: (props as OverlayProps["O08"]).sessionId, messageId: (props as OverlayProps["O08"]).messageId };
  ui.setState(patch);
  return layer.key;
}

/** Close by overlay id or layer key. Focus returns to where it was when the layer opened. */
export function closeOverlay(idOrKey: OverlayId | number): void {
  if (idOrKey === "O12") {
    ui.setState({ dockExpansion: null });
    return;
  }
  const s = ui.getState();
  const layer = s.layers.find((l) => (typeof idOrKey === "number" ? l.key === idOrKey : l.id === idOrKey));
  if (!layer) return;
  ui.setState({ layers: s.layers.filter((l) => l !== layer) });
  const back = layer.returnFocusTo;
  if (back && back.isConnected && (layer.kind === "modal" || layer.kind === "popover")) queueMicrotask(() => back.focus({ preventScroll: true }));
}

export function isOverlayOpen(id: OverlayId): boolean {
  return id === "O12" ? ui.getState().dockExpansion !== null : ui.getState().layers.some((l) => l.id === id);
}

/** Insight selection without reopening the drawer (↑↓ in the log). */
export function selectInsight(messageId: string | undefined): void {
  ui.setState((s) => ({ insight: { ...s.insight, messageId } }));
}

// ── Toasts (STATE-05): top-right, max 3, 4 s, with SFX ───────────────────────
export function toast(t: { variant: ToastVariant; text: string; action?: { label: string; run(): void } }): number {
  const item: Toast = { id: nextToast++, at: Date.now(), ...t };
  ui.setState((s) => ({ toasts: [...s.toasts, item].slice(-TOAST_MAX) }));
  audio.playSfx(TOAST_SFX[t.variant]);
  setTimeout(() => dismissToast(item.id), TOAST_MS);
  return item.id;
}

export function dismissToast(id: number): void {
  ui.setState((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) }));
}

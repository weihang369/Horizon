// Overlay registry: every O01–O27 → { kind, component } (README §3.3, R4). Owner: EE.
// Builders replace only their own component imports. Components are lazy so heavy overlays (Insight) split out.
import { lazy } from "react";
import type { ComponentType, LazyExoticComponent } from "react";
import type { LayerKind, OverlayComponentProps, OverlayId } from "./overlayTypes";
import { OVERLAY_KINDS } from "./overlayTypes";
// Ambient overlays are always mounted by App (static imports; no chunk of their own).
import { DemoTape } from "../features/shell/DemoTape";
import { DesktopGuard } from "../features/shell/DesktopGuard";
import { ToastHost } from "./ToastHost";

type Loader<Id extends OverlayId> = () => Promise<{ default: ComponentType<OverlayComponentProps<Id>> }>;
const l = <Id extends OverlayId>(load: Loader<Id>) => lazy(load);
const now = <Id extends OverlayId>(c: ComponentType<OverlayComponentProps<Id>>) => lazy(() => Promise.resolve({ default: c }));

export const OVERLAY_COMPONENTS: { [Id in OverlayId]: LazyExoticComponent<ComponentType<OverlayComponentProps<Id>>> } = {
  O01: l(() => import("../features/shell/PauseMenu").then((m) => ({ default: m.PauseMenu }))),
  O02: l(() => import("../features/worlds/WorldEditor").then((m) => ({ default: m.WorldEditor }))),
  O03: l(() => import("../features/shell/ConfirmDialog").then((m) => ({ default: m.ConfirmDialog }))),
  O04: l(() => import("../features/wizard/CostConfirm").then((m) => ({ default: m.CostConfirm }))),
  O05: l(() => import("../features/shell/KeyRequired").then((m) => ({ default: m.KeyRequired }))),
  O06: l(() => import("../features/profile/EmotionLightbox").then((m) => ({ default: m.EmotionLightbox }))),
  O07: l(() => import("../features/session/EmotionPicker").then((m) => ({ default: m.EmotionPicker }))),
  O08: l(() => import("../features/insight/InsightDrawer").then((m) => ({ default: m.InsightDrawer }))),
  O09: l(() => import("../features/shell/MiniPlayerPopover").then((m) => ({ default: m.MiniPlayerPopover }))),
  O10: l(() => import("../features/session/Backlog").then((m) => ({ default: m.Backlog }))),
  O11: l(() => import("../features/session/MentionPicker").then((m) => ({ default: m.MentionPicker }))),
  O12: l(() => import("../features/ensemble/DockExpansion").then((m) => ({ default: m.DockExpansion }))),
  O13: l(() => import("../features/wizard/UnsavedDraft").then((m) => ({ default: m.UnsavedDraft }))),
  O14: now<"O14">(ToastHost as ComponentType<OverlayComponentProps<"O14">>),
  O15: l(() => import("../features/wizard/SummonReveal").then((m) => ({ default: m.SummonReveal }))),
  O16: l(() => import("../features/ensemble/VsSplash").then((m) => ({ default: m.VsSplash }))),
  O17: l(() => import("../features/ensemble/EpisodeEnd").then((m) => ({ default: m.EpisodeEnd }))),
  O18: l(() => import("../features/dev/MockSwitcher").then((m) => ({ default: m.MockSwitcher }))),
  O19: now<"O19">(DesktopGuard),
  O20: l(() => import("../features/shell/ShortcutsSheet").then((m) => ({ default: m.ShortcutsSheet }))),
  O21: l(() => import("../features/shell/BudgetReached").then((m) => ({ default: m.BudgetReached }))),
  O22: now<"O22">(DemoTape),
  O23: l(() => import("../features/session/ReplayTransport").then((m) => ({ default: m.ReplayTransport }))),
  O24: l(() => import("../features/ensemble/PortraitMenu").then((m) => ({ default: m.PortraitMenu }))),
  O25: l(() => import("../features/profile/AssetCompare").then((m) => ({ default: m.AssetCompare }))),
  O26: l(() => import("../features/ensemble/EndDebate").then((m) => ({ default: m.EndDebate }))),
  O27: l(() => import("../features/session/TopUpEnergy").then((m) => ({ default: m.TopUpEnergy }))),
  O28: l(() => import("../features/profile/SourceViewer").then((m) => ({ default: m.SourceViewer }))),
  O29: l(() => import("../features/profile/PasteText").then((m) => ({ default: m.PasteText }))),
};

export interface OverlayEntry<Id extends OverlayId> { kind: LayerKind; component: (typeof OVERLAY_COMPONENTS)[Id] }

export const OVERLAYS: { [Id in OverlayId]: OverlayEntry<Id> } = Object.fromEntries(
  (Object.keys(OVERLAY_COMPONENTS) as OverlayId[]).map((id) => [id, { kind: OVERLAY_KINDS[id], component: OVERLAY_COMPONENTS[id] }]),
) as { [Id in OverlayId]: OverlayEntry<Id> };

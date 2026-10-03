// SessionScreen seam (README §4, R5): layouts[mode] and docks[kind]. Owner: EE (pre-filled); C owns the 1:1 and
// replay/demo entries, D replaces the ensemble entries (stubs in features/ensemble/).
import type { ComponentType, ReactNode } from "react";
import type { SessionMode } from "../../contract/types";
import type { SessionRuntimeView } from "../../client/hooks";
import type { Route } from "../../router";
import { OneOnOneLayout } from "./OneOnOneLayout";
import { Composer } from "./Composer";
import { DemoDock } from "./DemoDock";
import { ReplayDock } from "./ReplayTransport";
import { DebateLayout } from "../ensemble/DebateLayout";
import { GroupLayout } from "../ensemble/GroupLayout";
import { SteeringBar } from "../ensemble/SteeringBar";
import { Transport } from "../ensemble/Transport";
import { WatchLayout } from "../ensemble/WatchLayout";

export type SessionRoute = Extract<Route, { name: "session" }>;

export interface LayoutProps {
  rt: SessionRuntimeView;
  route: SessionRoute;
  replay: boolean;
  /** Additive (C): the dock element, for layouts that place it themselves (S07 puts it in the log column). */
  dock?: ReactNode;
  /** Additive (C): O08 Insight is open (S07 compresses its stage; others are overlaid). */
  insightOpen?: boolean;
}

/** Additive (C): layouts that render `dock` themselves (the frame then skips its bottom dock row). */
export const layoutOwnsDock: Partial<Record<SessionMode, boolean>> = { one_on_one: true };

export type DockKind = "composer" | "steering" | "transport" | "replay" | "demo";

export interface DockProps {
  rt: SessionRuntimeView;
  sessionId: string;
  worldId: string;
  replay: boolean;
}

export const layouts: Record<SessionMode, ComponentType<LayoutProps>> = {
  one_on_one: OneOnOneLayout,
  group: GroupLayout,
  debate: DebateLayout,
  watch: WatchLayout,
};

export const docks: Record<DockKind, ComponentType<DockProps>> = {
  composer: Composer as ComponentType<DockProps>,
  steering: SteeringBar,
  transport: Transport,
  replay: ReplayDock,
  demo: DemoDock,
};

/** Which dock a session shows (R5, R15): replay → transport; a resumed seed or no key → DemoDock. */
export function dockFor(mode: SessionMode, opts: { replay: boolean; isSeed: boolean; demo: boolean }): DockKind {
  if (opts.replay) return "replay";
  if (opts.isSeed || opts.demo) return "demo";
  if (mode === "debate") return "steering";
  if (mode === "watch") return "transport";
  return "composer";
}

// Route registry: route name → lazy screen (one chunk per screen, prefetched on idle). Owner: EE.
// Builders replace only their own import lines.
import { lazy } from "react";
import type { ComponentType, LazyExoticComponent } from "react";
import type { Route, RouteName } from "../router";

type ScreenProps<N extends RouteName> = { route: Extract<Route, { name: N }> };
type Loader<N extends RouteName> = () => Promise<{ default: ComponentType<ScreenProps<N>> }>;

const loaders: { [N in RouteName]: Loader<N> } = {
  title: () => import("../features/shell/TitleScreen").then((m) => ({ default: m.TitleScreen })),
  onboarding: () => import("../features/shell/OnboardingScreen").then((m) => ({ default: m.OnboardingScreen })),
  worlds: () => import("../features/worlds/WorldSelectScreen").then((m) => ({ default: m.WorldSelectScreen })),
  hub: () => import("../features/worlds/WorldHubScreen").then((m) => ({ default: m.WorldHubScreen })),
  profile: () => import("../features/profile/ProfileScreen").then((m) => ({ default: m.ProfileScreen })),
  wizard: () => import("../features/wizard/WizardScreen").then((m) => ({ default: m.WizardScreen })),
  setup: () => import("../features/ensemble/SetupScreen").then((m) => ({ default: m.SetupScreen })),
  session: () => import("../features/session/SessionScreen").then((m) => ({ default: m.SessionScreen })),
  verdict: () => import("../features/ensemble/VerdictScreen").then((m) => ({ default: m.VerdictScreen })),
  settings: () => import("../features/settings/SettingsScreen").then((m) => ({ default: m.SettingsScreen })),
  dev: () => import("../features/dev/DevKitRoute").then((m) => ({ default: m.DevKitRoute })),
};

export const ROUTES = Object.fromEntries(
  (Object.keys(loaders) as RouteName[]).map((n) => [n, lazy(loaders[n] as Loader<RouteName>)]),
) as { [N in RouteName]: LazyExoticComponent<ComponentType<ScreenProps<N>>> };

/** Warm every route chunk after first paint (EE paper §2.5). */
export function prefetchRoutes(): void {
  const run = () => (Object.keys(loaders) as RouteName[]).filter((n) => n !== "dev").forEach((n) => void loaders[n]().catch(() => {}));
  if (typeof requestIdleCallback === "function") requestIdleCallback(run, { timeout: 3000 });
  else setTimeout(run, 1500);
}

/** Remount key: same screen with other query params keeps its state (tabs, filters). */
export function routeKey(r: Route): string {
  switch (r.name) {
    case "hub": case "setup": return `${r.name}:${r.worldId}`;
    case "profile": return `profile:${r.characterId}`;
    case "wizard": return `wizard:${r.worldId}:${r.characterId ?? "new"}`;
    case "session": return `session:${r.sessionId}:${r.replay ? "r" : "l"}`;
    case "verdict": return `verdict:${r.sessionId}`;
    default: return r.name;
  }
}

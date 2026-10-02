// Custom hash router (R3, README §3.1). Owner: EE.
// The URL updates at once; the screen swaps at the transition's cover point (VMD runTransition). The transition
// layer is pointer-events:none, so input is never blocked, and a second navigate() supersedes the first.
import { useSyncExternalStore } from "react";
import { createStore } from "zustand/vanilla";
import type { TransitionKind } from "../motion/transitions";
import { runTransition } from "../motion/transitions";
import type { Route } from "./routes";
import { formatRoute, parentOf, parseRoute, sameRoute } from "./routes";

export interface NavigateOpts {
  transition?: TransitionKind;
  origin?: { x: number; y: number };
  sourceEl?: HTMLElement;
  replace?: boolean;
  /** Skip the leave guard (the guard itself re-navigates with force after O13). Additive. */
  force?: boolean;
}

export interface RouterState {
  route: Route;
  /** The route being transitioned to (until its cover point). */
  pending: Route | null;
  /** Previous committed route (for "from" links and back animations). */
  prev: Route | null;
}

const initial = typeof location !== "undefined" ? parseRoute(location.hash) : ({ name: "title" } as Route);
export const routerStore = createStore<RouterState>(() => ({ route: initial, pending: null, prev: null }));

let depth = 0;
let navSeq = 0;
let leaveGuard: ((to: Route) => boolean) | null = null;
const COVER_FALLBACK_MS = 900;

/** Wizard/unsaved-draft guard (CHR-01 AC2): return false to cancel and open O13. One guard at a time. */
export function setLeaveGuard(fn: ((to: Route) => boolean) | null): () => void {
  leaveGuard = fn;
  return () => {
    if (leaveGuard === fn) leaveGuard = null;
  };
}

function commit(id: number, route: Route): void {
  if (id !== navSeq) return;
  const cur = routerStore.getState().route;
  routerStore.setState({ route, pending: null, prev: cur });
}

function go(route: Route, kind: TransitionKind, opts: NavigateOpts = {}): void {
  const id = ++navSeq;
  routerStore.setState({ pending: route });
  if (kind === "none" || typeof document === "undefined") {
    commit(id, route);
    return;
  }
  let covered = false;
  const fallback = setTimeout(() => {
    if (!covered) commit(id, route);
  }, COVER_FALLBACK_MS);
  try {
    runTransition(kind, {
      origin: opts.origin,
      sourceEl: opts.sourceEl,
      onCover: () => {
        covered = true;
        clearTimeout(fallback);
        commit(id, route);
      },
    });
  } catch (err) {
    console.warn("[router] transition failed", err);
    clearTimeout(fallback);
    commit(id, route);
  }
}

export function navigate(route: Route, opts: NavigateOpts = {}): void {
  const cur = routerStore.getState();
  if (!opts.force && leaveGuard && !leaveGuard(route)) return;
  if (sameRoute(route, cur.pending ?? cur.route)) return;
  const path = `#${formatRoute(route)}`;
  if (typeof history !== "undefined") {
    if (opts.replace) history.replaceState({ hz: depth }, "", path);
    else history.pushState({ hz: ++depth }, "", path);
  }
  go(route, opts.transition ?? "slash", opts);
}

/** In-app back: browser history when we have some, else the logical parent (UXA §2.1). */
export function back(): void {
  const { route } = routerStore.getState();
  if (leaveGuard && !leaveGuard(parentOf(route))) return;
  if (depth > 0 && typeof history !== "undefined") history.back();
  else navigate(parentOf(route), { transition: "slash-back", replace: true, force: true });
}

export function getRoute(): Route {
  return routerStore.getState().route;
}

export function useRoute(): Route {
  return useSyncExternalStore(routerStore.subscribe, () => routerStore.getState().route, () => routerStore.getState().route);
}

export function usePendingRoute(): Route | null {
  return useSyncExternalStore(routerStore.subscribe, () => routerStore.getState().pending, () => null);
}

let started = false;
/** Hash sync (browser back/forward, typed URLs). Called once by the app providers. */
export function startRouter(): () => void {
  if (started || typeof window === "undefined") return () => {};
  started = true;
  history.replaceState({ hz: 0 }, "", `#${formatRoute(routerStore.getState().route)}`);
  const onPop = (e: PopStateEvent) => {
    depth = typeof e.state?.hz === "number" ? e.state.hz : 0;
    const r = parseRoute(location.hash);
    if (leaveGuard && !leaveGuard(r)) {
      history.pushState({ hz: ++depth }, "", `#${formatRoute(routerStore.getState().route)}`);
      return;
    }
    if (!sameRoute(r, routerStore.getState().route)) go(r, "slash-back");
  };
  const onHash = () => {
    const r = parseRoute(location.hash);
    if (!sameRoute(r, routerStore.getState().pending ?? routerStore.getState().route)) go(r, "fade");
  };
  window.addEventListener("popstate", onPop);
  window.addEventListener("hashchange", onHash);
  return () => {
    started = false;
    window.removeEventListener("popstate", onPop);
    window.removeEventListener("hashchange", onHash);
  };
}

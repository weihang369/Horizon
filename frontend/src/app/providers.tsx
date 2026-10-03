// App boot: router hash sync, deep-linked mock scenarios, audio unlock, global client events → toasts/overlays,
// global shortcuts, route prefetch. Owner: EE.
import { useEffect, useState } from "react";
import { audio } from "../audio/engine";
import { client, mockDev } from "../client";
import { isScenarioId } from "../mock/scenarios";
import { startRouter } from "../router";
import { prefs } from "../stores/prefs";
import { ui } from "../stores/ui";
import { isOverlayOpen, closeOverlay, openOverlay, toast } from "./layers";
import { prefetchRoutes } from "./routes";
import { useShortcut } from "./shortcuts";

/** `#/…?scenario=rate_limited&speed=2` (EE paper §2.3) or `?scenario=…` before the hash. */
function applyDeepLink(): void {
  if (!mockDev || typeof location === "undefined") return;
  const q = new URLSearchParams(`${location.search.slice(1)}&${location.hash.split("?")[1] ?? ""}`);
  const sc = q.get("scenario");
  const sp = Number(q.get("speed"));
  if (isScenarioId(sc)) void mockDev.setScenario(sc);
  if (sp === 1 || sp === 2 || sp === 4) mockDev.setSpeed(sp);
}

export function useAppBoot(): void {
  useEffect(() => {
    const stopRouter = startRouter();
    applyDeepLink();
    prefetchRoutes();
    const unlock = () => void audio.unlock();
    window.addEventListener("pointerdown", unlock, { once: true, capture: true });
    window.addEventListener("keydown", unlock, { once: true, capture: true });
    const off = client.onGlobal((e) => {
      switch (e.type) {
        case "budget.warning":
          toast({ variant: "warn", text: `${e.scope === "daily" ? "Today's" : "Creation"} spend is at ${Math.round((e.spentUsd / e.capUsd) * 100)} % of the cap.` });
          break;
        case "budget.reached":
          openOverlay("O21", { scope: e.scope, spentUsd: e.spentUsd, capUsd: e.capUsd, sessionId: e.sessionId });
          break;
        case "job.done":
          if (e.job.status === "succeeded") toast({ variant: "success", text: `${e.characterName ? `${e.characterName}: ` : ""}${e.job.kind.replace(/_/g, " ")} ready.` });
          else if (e.job.status === "partial" || e.job.status === "failed") toast({ variant: e.job.status === "failed" ? "error" : "warn", text: `${e.characterName ? `${e.characterName}: ` : ""}${e.job.kind.replace(/_/g, " ")} ${e.job.status}.` });
          break;
        case "error":
          toast({ variant: "error", text: e.error.message });
          break;
      }
    });
    return () => {
      stopRouter();
      off();
      window.removeEventListener("pointerdown", unlock, true);
      window.removeEventListener("keydown", unlock, true);
    };
  }, []);

  // Global shortcuts (doc 03 §6).
  useShortcut("ctrl+shift+d", () => {
    if (prefs.getState().presenterMode) return;
    if (isOverlayOpen("O18")) closeOverlay("O18");
    else openOverlay("O18");
  }, { allowInInput: true, global: true });
  useShortcut("ctrl+shift+p", () => {
    if (import.meta.env.DEV) ui.setState((s) => ({ perfHud: !s.perfHud }));
  }, { allowInInput: true, global: true });
  useShortcut("?", () => openOverlay("O20"));
}

/** Viewport below 1280×720 → O19 (APP-06). */
export function useDesktopGuard(): boolean {
  const check = () => typeof window !== "undefined" && (window.innerWidth < 1280 || window.innerHeight < 720);
  const [small, setSmall] = useState(check);
  useEffect(() => {
    const on = () => setSmall(check());
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  return small;
}

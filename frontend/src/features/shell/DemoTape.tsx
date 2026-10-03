// O22 Demo-mode tape (APP-09 AC1). Ambient, never takes focus by itself, never blocks.
// Placement: a slim tape stuck to the TOP EDGE, right-aligned above the mini-player, inside the same top-right
// column every screen already keeps clear for the mini-player (the session TopBar reserves 296 px of it). While the
// tape is up it sets `data-demo-tape` on <html>, and the mini-player drops 10 px to sit under it (both stay inside
// the 56 px header band). So the tape never lands on a header, a portrait, a log or a dock, on any screen.
// Hover/focus drops the full AC1 copy beneath it. Click → Settings → Connection. Hidden on Onboarding (its key card
// already explains demo mode). Owner: Builder A. Statically imported by App (entry bundle): keep it light.
import { useEffect } from "react";
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { getRoute, navigate, useRoute } from "../../router";
import { formatRoute } from "../../router/routes";
import s from "./DemoTape.module.css";

export const DEMO_COPY = "DEMO MODE · Browsing seed data · Add your OpenRouter key to chat & create";

export function DemoTape(_: Partial<OverlayComponentProps<"O22">>) {
  const route = useRoute();
  const hidden = route.name === "onboarding";
  useEffect(() => {
    if (hidden) return;
    const root = document.documentElement;
    root.setAttribute("data-demo-tape", "");
    return () => root.removeAttribute("data-demo-tape");
  }, [hidden]);
  if (hidden) return null;
  return (
    <button
      type="button"
      className={s.tab}
      aria-label={`${DEMO_COPY}. Open Settings, Connection`}
      onClick={() => navigate({ name: "settings", tab: "connection", from: formatRoute(getRoute()) })}
    >
      <span className={s.strip} aria-hidden="true">
        <span className={s.demo}>DEMO MODE</span>
        <span className={s.cta}>
          <span className={s.ctaSeed}>SEED DATA ·</span> ⚿ ADD KEY <b>▸</b>
        </span>
      </span>
      <span className={s.fly} aria-hidden="true">
        <span className={s.flyTitle}>DEMO MODE</span>
        <span className={s.flyText}>Browsing seed data. Every recording plays; add your OpenRouter key to chat &amp; create.</span>
        <span className={s.flyCta}>Add key ▸</span>
      </span>
    </button>
  );
}

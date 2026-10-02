// O22 Demo-mode tape (APP-09 AC1). Ambient, never takes focus by itself, never blocks.
// Placement: a vertical tab on the LEFT EDGE, vertically centred in the 30–70 % band. Every screen's header lives in the
// top ~22 % (session TopBar 56 + debate banner 64 + rail 36 = 156 px of 720) and every dock + dock expansion in the
// bottom ~28 % (96 + 120 px), so this band can never collide with a header or a dock, whatever the screen's layout.
// The full copy flies out on hover/focus, and once for 4.5 s on first show. Click → Settings → Connection.
// Owner: Builder A. Statically imported by App (entry bundle): keep it light.
import { useEffect, useState } from "react";
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { getRoute, navigate } from "../../router";
import { formatRoute } from "../../router/routes";
import s from "./DemoTape.module.css";

let introShown = false;
const COPY = "DEMO MODE · Browsing seed data · Add your OpenRouter key to chat & create";

export function DemoTape(_: Partial<OverlayComponentProps<"O22">>) {
  const [intro, setIntro] = useState(!introShown);
  useEffect(() => {
    if (!intro) return;
    introShown = true;
    const t = window.setTimeout(() => setIntro(false), 4500);
    return () => window.clearTimeout(t);
  }, [intro]);
  return (
    <button
      type="button"
      className={s.tab}
      data-open={intro || undefined}
      aria-label={`${COPY}. Open Settings, Connection`}
      onClick={() => navigate({ name: "settings", tab: "connection", from: formatRoute(getRoute()) })}
    >
      <span className={s.spine} aria-hidden="true">
        <span className={s.spineDemo}>DEMO</span>
        <span className={s.spineKey}>⚿ ADD KEY</span>
      </span>
      <span className={s.fly} aria-hidden="true">
        <span className={s.flyTitle}>DEMO MODE</span>
        <span className={s.flyText}>Browsing seed data · Add your OpenRouter key to chat &amp; create</span>
        <span className={s.flyCta}>Add key ▸</span>
      </span>
    </button>
  );
}

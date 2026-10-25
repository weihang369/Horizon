// <TransitionLayer/> — mounted once by App (spec §3.2). pointer-events: none (R3).
import { useCallback } from "react";
import { registerTransitionHost } from "./transitions";

export function TransitionLayer() {
  const ref = useCallback((node: HTMLDivElement | null) => registerTransitionHost(node), []);
  return (
    <div
      ref={ref}
      aria-hidden="true"
      data-transition-layer=""
      style={{
        position: "fixed",
        inset: 0,
        pointerEvents: "none",
        zIndex: "var(--z-transition)",
        overflow: "hidden",
        contain: "strict",
      }}
    />
  );
}

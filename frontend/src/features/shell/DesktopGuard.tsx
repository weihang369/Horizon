// O19 Desktop guard (APP-06): foundation stub (Builder A replaces it). Owner: EE (stub). App mounts it below 1280×720.
import type { OverlayComponentProps } from "../../app/overlayTypes";

export function DesktopGuard(_: Partial<OverlayComponentProps<"O19">>) {
  return (
    <div
      role="alertdialog"
      aria-label="Desktop only"
      style={{ position: "fixed", inset: 0, zIndex: 200, display: "grid", placeItems: "center", background: "var(--ink-900)", color: "var(--paper-50)", padding: 24, textAlign: "center" }}
    >
      <p>O19 · Horizon is designed for desktop (≥ 1280×720).</p>
    </div>
  );
}

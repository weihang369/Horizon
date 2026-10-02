// Mini-player chip (MUS-04, top right): foundation stub (Builder A replaces it; O09 is its popover). Owner: EE (stub).
import { useSyncExternalStore } from "react";
import { audio } from "../../audio/engine";
import { openOverlay } from "../../app/layers";

export function MiniPlayer() {
  const st = useSyncExternalStore((cb) => audio.subscribe(cb), () => audio.getState());
  const label = st.blocked ? "▶ Enable audio" : st.track ? `♪ ${st.track.label || "Theme"}${st.track.procedural ? " · SKETCH" : ""}` : "♪ —";
  return (
    <button
      type="button"
      onClick={(e) => {
        if (st.blocked) void audio.unlock();
        else {
          const r = e.currentTarget.getBoundingClientRect();
          openOverlay("O09", { anchor: { x: r.x, y: r.y, width: r.width, height: r.height } });
        }
      }}
      style={{ position: "fixed", top: 12, right: 16, font: "600 12px/1 var(--font-mono)", padding: "6px 10px", background: "var(--ink-700)", color: "var(--paper-50)", border: 0 }}
    >
      {label}
    </button>
  );
}

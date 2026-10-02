// S12 Watch layout (proscenium + script, R14): foundation stub (Builder D replaces it). Owner: EE (stub).
import { SessionLog } from "../session/SessionLog";
import type { LayoutProps } from "../session/registry";

export function WatchLayout({ rt }: LayoutProps) {
  return (
    <div style={{ display: "grid", gridTemplateRows: "1fr auto", height: "100%" }}>
      <SessionLog rt={rt} variant="script" />
      <p style={{ textAlign: "center", margin: 8 }}>
        S12 · {rt.watch ? `${rt.watch.status} · ${rt.watch.turnsTaken}/${rt.watch.turnLimit}` : "—"} · {rt.participants.map((p) => `${p.characterId}:${p.displayEmotion}`).join(" · ")}
      </p>
    </div>
  );
}

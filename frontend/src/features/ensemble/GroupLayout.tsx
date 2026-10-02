// S09 Group layout (wings, R14): foundation stub (Builder D replaces it). Owner: EE (stub).
import { SessionLog } from "../session/SessionLog";
import type { LayoutProps } from "../session/registry";

export function GroupLayout({ rt }: LayoutProps) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 640px 1fr", height: "100%" }}>
      <aside style={{ padding: 16 }}>S09 · {rt.participants.map((p) => `${p.characterId}:${p.displayEmotion}`).join(" · ")}</aside>
      <SessionLog rt={rt} />
      <aside style={{ padding: 16 }}>NEXT ▸ {rt.nextSpeakerId ?? "—"}</aside>
    </div>
  );
}

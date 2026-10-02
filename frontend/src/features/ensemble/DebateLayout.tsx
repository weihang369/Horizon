// S10 Debate layout (side columns, R14): foundation stub (Builder D replaces it). Owner: EE (stub).
import type { DebateConfig } from "../../contract/types";
import { SessionLog } from "../session/SessionLog";
import type { LayoutProps } from "../session/registry";

export function DebateLayout({ rt }: LayoutProps) {
  const cfg = rt.session?.config as DebateConfig | null;
  const side = (s: "prop" | "opp") => rt.participants.filter((p) => p.side === s).map((p) => `${p.characterId}:${p.displayEmotion}`).join(" · ");
  return (
    <div style={{ display: "grid", gridTemplateRows: "auto 1fr", height: "100%" }}>
      <p style={{ textAlign: "center", margin: 8 }}>
        S10 · {cfg?.motion} · {rt.phase ? `ROUND ${rt.phase.round} · ${rt.phase.phase}` : "SETUP"} · NEXT ▸ {rt.nextSpeakerId ?? "—"}
      </p>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 760px 1fr", minHeight: 0 }}>
        <aside style={{ padding: 16 }}>PROP · {side("prop")}</aside>
        <SessionLog rt={rt} />
        <aside style={{ padding: 16 }}>OPP · {side("opp")}</aside>
      </div>
    </div>
  );
}

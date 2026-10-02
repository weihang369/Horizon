// S07 1:1 layout: foundation stub (Builder C replaces it). Owner: EE (stub).
import { SessionLog } from "./SessionLog";
import type { LayoutProps } from "./registry";

export function OneOnOneLayout({ rt }: LayoutProps) {
  const p = rt.participants[0];
  return (
    <div style={{ display: "grid", gridTemplateColumns: "42% 1fr", height: "100%" }}>
      <aside style={{ padding: 24 }}>
        <p>S07 · {p?.characterId}</p>
        <p>face: {p?.displayEmotion}{p?.leanIn ? " (lean-in)" : ""}</p>
        {p && rt.energyById[p.characterId] && <p>⚡ {rt.energyById[p.characterId].current} / {rt.energyById[p.characterId].max}</p>}
      </aside>
      <SessionLog rt={rt} />
    </div>
  );
}

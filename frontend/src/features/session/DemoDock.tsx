// DemoDock (R15, APP-09 AC5): foundation stub (Builder C replaces it). Owner: EE (stub).
import { client } from "../../client";
import { run } from "../../app/errors";
import { openOverlay } from "../../app/layers";
import { navigate } from "../../router";
import { Button } from "../../ui/Button";
import type { DockProps } from "./registry";

export function DemoDock({ rt, sessionId, worldId }: DockProps) {
  const seed = rt.session?.isSeed;
  return (
    <div style={{ display: "flex", gap: 12, alignItems: "center", padding: "12px 24px" }}>
      <span>{seed ? "This is a recording." : "Demo mode."} Live replies need your OpenRouter key.</span>
      <Button size="sm" variant="secondary" onClick={() => navigate({ name: "session", worldId, sessionId, replay: true })}>▶ Replay</Button>
      <Button size="sm" keyLocked={!seed} onClick={async () => {
        if (!seed) return void openOverlay("O05", {});
        const snap = await run(() => client.sessions.forkSeedSession(sessionId));
        if (snap) navigate({ name: "session", worldId, sessionId: snap.session.id });
      }}>{seed ? "Continue live" : "Add key"}</Button>
    </div>
  );
}

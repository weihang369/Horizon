// SessionScreen (S07/S09/S10/S12 frame, R5): foundation stub (Builder C replaces it). Owner: EE (stub).
// Picks layouts[mode] and docks[kind] from the registry; replay opens at route `t` (an event seq).
import { useEffect, useRef } from "react";
import { useCharacters, useSessionRuntime, useSettings } from "../../client/hooks";
import { back } from "../../router";
import { Button } from "../../ui/Button";
import { Tape } from "../../ui/Tape";
import { closeOverlay } from "../../app/layers";
import { useUi } from "../../stores/ui";
import { DockExpansion } from "../ensemble/DockExpansion";
import type { SessionRoute } from "./registry";
import { dockFor, docks, layouts } from "./registry";

export function SessionScreen({ route }: { route: SessionRoute }) {
  const replay = !!route.replay;
  const rt = useSessionRuntime(route.sessionId, { replay });
  const demo = useSettings().data?.demoMode ?? true;
  useCharacters(rt.session?.worldId, { includeArchived: true });
  const expansion = useUi((u) => u.dockExpansion);
  const seeked = useRef(false);
  useEffect(() => {
    if (replay && rt.status === "ready" && route.t !== undefined && !seeked.current) {
      seeked.current = true;
      rt.controls.seekSeq(route.t);
    }
  }, [replay, rt.status, route.t, rt.controls]);

  if (rt.status === "error") {
    return (
      <main style={{ padding: 48 }}>
        <p role="alert">{rt.error?.message ?? "This session can't be opened."}</p>
        <Button onClick={() => back()}>◂ Back</Button>
      </main>
    );
  }
  if (!rt.session) return <main style={{ padding: 48 }} aria-busy="true">Loading session…</main>;
  const s = rt.session;
  const Layout = layouts[s.mode];
  const Dock = docks[dockFor(s.mode, { replay, isSeed: s.isSeed, demo })];
  return (
    <main data-screen="session" data-mode={s.mode} style={{ display: "grid", gridTemplateRows: "56px 1fr auto", height: "100vh" }}>
      <header style={{ display: "flex", alignItems: "center", gap: 12, padding: "0 24px" }}>
        <Button variant="ghost" size="sm" onClick={() => back()}>◂</Button>
        <strong>{s.title}</strong>
        <Tape tone="ink" size="sm">{s.mode}</Tape>
        {replay && <Tape tone="brand" size="sm">REPLAY</Tape>}
        {rt.paused && <Tape tone="warn" size="sm">PAUSED{rt.pausedReason ? ` · ${rt.pausedReason}` : ""}</Tape>}
      </header>
      <div style={{ minHeight: 0, overflow: "hidden" }}>
        <Layout rt={rt} route={route} replay={replay} />
      </div>
      <div>
        {expansion?.sessionId === s.id && <DockExpansion {...expansion} layerKey={0} close={() => closeOverlay("O12")} />}
        <Dock rt={rt} sessionId={s.id} worldId={s.worldId} replay={replay} />
      </div>
    </main>
  );
}

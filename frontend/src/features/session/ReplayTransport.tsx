// O23 Replay transport + REPLAY badge: foundation stub (Builder C replaces it). Owner: EE (stub).
// "Continue live" forks from the playhead (R16, forkSeedSession(id, atSeq)).
import { client } from "../../client";
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { run } from "../../app/errors";
import { navigate } from "../../router";
import { Button } from "../../ui/Button";
import type { DockProps } from "./registry";

export function ReplayDock({ rt, sessionId, worldId }: DockProps) {
  const p = rt.player;
  const pct = p && p.duration ? Math.round((p.position / p.duration) * 100) : 0;
  const continueLive = async () => {
    const snap = await run(() => client.sessions.forkSeedSession(sessionId, p && p.seq > 0 && !p.ended ? p.seq : undefined));
    if (snap) navigate({ name: "session", worldId, sessionId: snap.session.id });
  };
  return (
    <div style={{ display: "flex", gap: 12, alignItems: "center", padding: "12px 24px" }}>
      {p?.playing
        ? <Button size="sm" onClick={() => rt.controls.pause()}>❚❚</Button>
        : <Button size="sm" onClick={() => rt.controls.play()}>▶</Button>}
      {[1, 2, 4].map((r) => (
        <Button key={r} size="sm" variant={p?.rate === r ? "primary" : "ghost"} onClick={() => rt.controls.rate(r)}>×{r}</Button>
      ))}
      <input
        type="range" min={0} max={p?.duration ?? 0} value={p?.position ?? 0} aria-label="Seek"
        onChange={(e) => rt.controls.seek(Number(e.target.value))} style={{ flex: 1 }}
      />
      <span>{pct}% · seq {p?.seq ?? 0}</span>
      <Button size="sm" variant="secondary" onClick={() => void continueLive()}>Continue live</Button>
    </div>
  );
}

/** O23 registry entry (ambient: it renders inside the session dock, not on the LayerStack). */
export function ReplayTransport(_: Partial<OverlayComponentProps<"O23">>) {
  return null;
}

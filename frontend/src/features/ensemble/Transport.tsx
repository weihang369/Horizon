// Watch Transport (MULTI-10): foundation stub (Builder D replaces it). Owner: EE (stub).
import { client } from "../../client";
import { run } from "../../app/errors";
import { openOverlay } from "../../app/layers";
import { Button } from "../../ui/Button";
import type { DockProps } from "../session/registry";

export function Transport({ rt, sessionId }: DockProps) {
  const playing = rt.watch?.status === "playing";
  return (
    <div style={{ display: "flex", gap: 8, padding: "12px 24px" }}>
      {playing
        ? <Button size="sm" onClick={() => void run(() => client.watch.pause(sessionId))}>❚❚</Button>
        : <Button size="sm" onClick={() => void run(() => client.watch.play(sessionId))}>▶</Button>}
      <Button size="sm" variant="secondary" onClick={() => void run(() => client.watch.step(sessionId))}>Step</Button>
      {([3000, 1500, 500] as const).map((ms) => (
        <Button key={ms} size="sm" variant="ghost" onClick={() => void run(() => client.watch.setPace(sessionId, ms))}>{ms === 3000 ? "Slow" : ms === 1500 ? "Normal" : "Fast"}</Button>
      ))}
      <Button size="sm" variant="secondary" onClick={() => openOverlay("O12", { sessionId, kind: "direction" })}>🎬 Director's note</Button>
      <Button size="sm" variant="secondary" onClick={() => openOverlay("O12", { sessionId, kind: "stepin" })}>Step in</Button>
      {rt.watch?.status === "ended" && <Button size="sm" onClick={() => void run(() => client.watch.extendWatch(sessionId, 10))}>Continue +10</Button>}
    </div>
  );
}

// SteeringBar (MULTI-07): foundation stub (Builder D replaces it). Owner: EE (stub).
import { client } from "../../client";
import { run } from "../../app/errors";
import { openOverlay } from "../../app/layers";
import { Button } from "../../ui/Button";
import type { DockProps } from "../session/registry";

export function SteeringBar({ rt, sessionId }: DockProps) {
  const ended = rt.session?.status === "ended";
  return (
    <div style={{ display: "flex", gap: 8, padding: "12px 24px", flexWrap: "wrap" }}>
      {rt.paused
        ? <Button size="sm" disabled={ended} onClick={() => void run(() => client.debate.resume(sessionId))}>▶</Button>
        : <Button size="sm" disabled={ended} onClick={() => void run(() => client.debate.pause(sessionId))}>❚❚</Button>}
      <Button size="sm" variant="secondary" disabled={ended} onClick={() => void run(() => client.debate.next(sessionId))}>Next</Button>
      <Button size="sm" variant="secondary" disabled={ended} onClick={() => openOverlay("O12", { sessionId, kind: "ask" })}>Ask…</Button>
      <Button size="sm" variant="secondary" disabled={ended} onClick={() => openOverlay("O12", { sessionId, kind: "interject" })}>Interject</Button>
      <Button size="sm" variant="ghost" disabled={ended} onClick={() => void run(() => client.debate.extendRound(sessionId))}>Extend round</Button>
      <Button size="sm" variant="ghost" disabled={ended} onClick={() => void run(() => client.debate.skipToClosing(sessionId))}>Skip to closing</Button>
      <Button size="sm" variant="danger" disabled={ended} onClick={() => openOverlay("O26", { sessionId })}>End</Button>
    </div>
  );
}

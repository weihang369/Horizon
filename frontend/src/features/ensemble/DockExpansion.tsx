// O12 DockExpansion (Ask… / Interject / Director's note / Step in, R5): foundation stub (Builder D replaces it).
// Rendered by the dock while ui.dockExpansion is set; Esc step 2 collapses it (draft kept by the builder). Owner: EE (stub).
import { client } from "../../client";
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { Composer } from "../session/Composer";

export function DockExpansion({ sessionId, kind, characterId, close }: OverlayComponentProps<"O12">) {
  const send = (text: string) => {
    const p = kind === "ask" && characterId ? client.debate.askCharacter(sessionId, characterId, text)
      : kind === "ask" || kind === "interject" ? client.debate.interject(sessionId, text)
        : kind === "direction" ? client.watch.direct(sessionId, text)
          : client.watch.stepIn(sessionId, text);
    return p.then(close);
  };
  return (
    <div data-overlay="O12" data-kind={kind}>
      <Composer sessionId={sessionId} onSend={send} placeholder={`O12 · ${kind}${characterId ? ` → ${characterId}` : ""}`} />
    </div>
  );
}

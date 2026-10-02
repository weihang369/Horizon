// O03 Destructive confirmation (typed or simple): foundation stub (Builder A replaces it). Owner: EE (stub).
import { useState } from "react";
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { Button } from "../../ui/Button";
import { TextField } from "../../ui/Fields";
import { Modal } from "../../ui/Panels";

export function ConfirmDialog({ close, title, body, confirmLabel, typed, onConfirm }: OverlayComponentProps<"O03">) {
  const [text, setText] = useState("");
  const ok = !typed || text === typed;
  return (
    <Modal
      title={title}
      tape="CONFIRM"
      tone="danger"
      onClose={close}
      actions={
        <>
          <Button variant="ghost" onClick={close}>Cancel</Button>
          <Button variant="danger" disabled={!ok} onClick={async () => { await onConfirm(); close(); }}>{confirmLabel ?? "Delete"}</Button>
        </>
      }
    >
      {body && <p>{body}</p>}
      {typed && <TextField label={`Type "${typed}" to confirm`} value={text} onChange={(e) => setText(e.target.value)} autoFocus />}
    </Modal>
  );
}

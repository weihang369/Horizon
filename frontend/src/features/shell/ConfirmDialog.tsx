// O03 Destructive confirmation (doc 03 §2): typed (delete world / character permanently / all data) or simple
// (delete a session). Cancel is focused first; Esc cancels; errors stay in the dialog. Owner: Builder A.
import { useState } from "react";
import type { OverlayComponentProps } from "../../app/overlayTypes";
import type { HorizonErrorShape } from "../../contract/errors";
import { Button } from "../../ui/Button";
import { TextField } from "../../ui/Fields";
import { ErrorTape, Modal } from "../../ui/Panels";
import s from "./Overlays.module.css";

export function ConfirmDialog({ close, title, body, confirmLabel, typed, onConfirm }: OverlayComponentProps<"O03">) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ok = !typed || text.trim() === typed;
  const confirm = async () => {
    if (!ok || busy) return;
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
      close();
    } catch (e) {
      setError((e as HorizonErrorShape)?.message ?? "That didn't work. Nothing was deleted.");
      setBusy(false);
    }
  };
  return (
    <Modal
      title={title}
      tape={typed ? "CAN'T BE UNDONE" : "CONFIRM"}
      tone="danger"
      size="sm"
      onClose={close}
      actions={
        <>
          <Button variant="ghost" onClick={close} autoFocus={!typed}>Cancel</Button>
          <Button variant="danger" disabled={!ok || busy} onClick={() => void confirm()}>{busy ? "Deleting…" : confirmLabel ?? "Delete"}</Button>
        </>
      }
    >
      <form className={s.confirm} onSubmit={(e) => { e.preventDefault(); void confirm(); }}>
        {body && <p className={s.confirmBody}>{body}</p>}
        {typed && (
          <TextField
            label={`Type “${typed}” to confirm`}
            value={text}
            onChange={(e) => setText(e.target.value)}
            autoFocus
            autoComplete="off"
            spellCheck={false}
            hint={ok ? "Ready." : undefined}
          />
        )}
        {error && <ErrorTape message={error} />}
      </form>
    </Modal>
  );
}

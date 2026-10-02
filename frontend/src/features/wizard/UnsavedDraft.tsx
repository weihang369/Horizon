// O13 Unsaved draft prompt (CHR-01 AC2): Save as draft / Discard / Cancel when leaving mid-wizard. Owner: Builder B.
import { useState } from "react";
import type { OverlayComponentProps } from "@/app/overlayTypes";
import { useCharacter } from "@/client/hooks";
import { PortraitCard } from "@/character";
import { Button, Modal, Tape } from "@/ui";
import { STEP_LABEL } from "./gates";
import s from "./overlays.module.css";

export function UnsavedDraft({ close, characterId, onSave, onDiscard }: OverlayComponentProps<"O13">) {
  const c = useCharacter(characterId).data;
  const [busy, setBusy] = useState(false);
  const editing = c?.status === "approved";
  const name = c?.profile.name || "This character";
  return (
    <Modal
      title={editing ? "Unsaved changes" : "Leave the wizard?"}
      tape={editing ? "O13 · EDIT" : "O13 · UNSAVED DRAFT"}
      size="sm"
      onClose={close}
      actions={
        <>
          <Button variant="ghost" onClick={close}>Cancel</Button>
          <Button variant="danger" disabled={busy} onClick={() => { close(); onDiscard(); }}>
            {editing ? "Discard changes" : "Discard"}
          </Button>
          <Button variant="primary" autoFocus disabled={busy} onClick={async () => { setBusy(true); try { await onSave(); } finally { close(); } }}>
            {editing ? "Save changes" : "Save as draft"}
          </Button>
        </>
      }
    >
      <div className={s.draft}>
        {c && <PortraitCard character={c} emotion="neutral" size="thumb" parallax={false} />}
        <div className={s.draftText}>
          <p className={s.draftName}>{name}</p>
          {c?.creationStep && !editing && <Tape tone="ink" size="sm">Stopped at {STEP_LABEL[c.creationStep]}</Tape>}
          <p className={s.draftBody}>
            {editing
              ? "Save keeps your edits. They apply to new messages only."
              : "Save as draft keeps everything. It waits in the roster with a DRAFT tape and reopens where you left off. Running generations keep going."}
          </p>
        </div>
      </div>
    </Modal>
  );
}

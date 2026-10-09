// O29 Paste text (knowledge-sources "Paste text", design D20): a title and up to 200 KB of text become a `text`
// source that starts indexing. Validation and conflict errors stay in the dialog; anything else goes to reportError.
// Built from the existing Modal, field and button primitives. Owner: Builder B.
import { useState } from "react";
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { reportError } from "../../app/errors";
import { client } from "../../client";
import { toHorizonError } from "../../contract/errors";
import { Button } from "../../ui/Button";
import { TextArea, TextField } from "../../ui/Fields";
import { ErrorTape, Modal } from "../../ui/Panels";
import { PASTE_MAX_BYTES, pasteBytes, pasteCounter, pasteProblem } from "./knowledge";
import s from "../shell/Overlays.module.css";

export function PasteText({ characterId, name, close }: OverlayComponentProps<"O29">) {
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bytes = pasteBytes(text);
  const problem = pasteProblem(title, text);
  const submit = async () => {
    if (problem || busy) return;
    setBusy(true);
    setError(null);
    try {
      await client.characters.addKnowledge(characterId, { type: "text", title: title.trim(), text });
      close();
    } catch (err) {
      const e = toHorizonError(err);
      if (e.code === "validation" || e.code === "conflict") setError(e.message);
      else reportError(e);
      setBusy(false);
    }
  };
  return (
    <Modal
      tape="Knowledge"
      title={`Teach ${name} from pasted text`}
      onClose={close}
      actions={
        <>
          <Button variant="ghost" onClick={close}>Cancel</Button>
          <Button onClick={() => void submit()} disabled={!!problem || busy}>{busy ? "Adding…" : "Add"}</Button>
        </>
      }
    >
      <form className={s.confirm} onSubmit={(e) => { e.preventDefault(); void submit(); }}>
        <TextField label="Title" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} autoFocus autoComplete="off" />
        <TextArea
          label="Text"
          value={text}
          rows={12}
          onChange={(e) => setText(e.target.value)}
          hint={pasteCounter(bytes)}
          error={bytes > PASTE_MAX_BYTES ? `Pasted text can be at most 200 KB (${pasteCounter(bytes)}).` : null}
        />
        {error && <ErrorTape message={error} />}
      </form>
    </Modal>
  );
}

// O02 Create / Edit World (WLD-02/03, D-43): name (1–40, unique), cover (8 presets or an uploaded image) and the
// optional "You in this world" card. Live preview card on the left. Create lands in the new hub's empty state.
// rev 1.3 / M4: a picked image is kept as a File (previewed with an object URL) and uploaded through
// `worlds.uploadCover` after the world is saved; no data URL goes into the world record (worldSave.ts).
// Owner: Builder A.
import { useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import type { OverlayComponentProps } from "../../app/overlayTypes";
import { openOverlay, toast } from "../../app/layers";
import { audio } from "../../audio/engine";
import { client } from "../../client";
import { useWorld, useWorlds } from "../../client/hooks";
import type { HorizonErrorShape } from "../../contract/errors";
import type { World } from "../../contract/types";
import { navigate } from "../../router";
import { COVER_PRESETS } from "../../vfx/covers";
import { Button } from "../../ui/Button";
import { TextArea, TextField } from "../../ui/Fields";
import { ErrorTape, Modal } from "../../ui/Panels";
import { WorldCover } from "../../ui/WorldCover";
import { validateWorldName } from "./worldValidation";
import { COVER_TYPES, coverFileError, saveWorld } from "./worldSave";
import s from "./WorldEditor.module.css";

export function WorldEditor({ close, worldId }: OverlayComponentProps<"O02">) {
  const existing = useWorld(worldId).data;
  const worlds = useWorlds().data ?? [];
  const editing = !!worldId;
  if (editing && !existing) return <Modal title="Edit world" tape="WORLD" onClose={close}><p>Loading…</p></Modal>;
  return <EditorForm close={close} world={existing} worlds={worlds} />;
}

function EditorForm({ close, world: initial, worlds }: { close: () => void; world?: World; worlds: World[] }) {
  // After a create whose cover upload failed, the editor keeps editing that world (saving again never duplicates it).
  const [world, setWorld] = useState<World | undefined>(initial);
  const [createdHere, setCreatedHere] = useState(false);
  const [name, setName] = useState(initial?.name ?? "");
  const [cover, setCover] = useState<World["cover"]>(initial?.cover ?? { kind: "preset", presetId: COVER_PRESETS[0].id });
  const [picked, setPicked] = useState<{ file: File; url: string } | null>(null);
  const [youName, setYouName] = useState(world?.you?.displayName ?? "");
  const [youAbout, setYouAbout] = useState(world?.you?.about ?? "");
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const file = useRef<HTMLInputElement>(null);

  const nameError = useMemo(() => validateWorldName(name, worlds, world?.id), [name, worlds, world?.id]);
  const showNameError = touched ? nameError : null;

  useEffect(() => () => { if (picked) URL.revokeObjectURL(picked.url); }, [picked]);
  const shown: World["cover"] = picked ? { kind: "upload", url: picked.url } : cover;

  const onUpload = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    const problem = coverFileError(f);
    if (problem) return setError(problem);
    setPicked({ file: f, url: URL.createObjectURL(f) });
    setError(null);
  };

  const pickPreset = (presetId: string) => {
    setPicked(null);
    setCover({ kind: "preset", presetId });
  };

  const save = async () => {
    setTouched(true);
    if (nameError || busy) return;
    setBusy(true);
    setError(null);
    const you = youName.trim() ? { displayName: youName.trim().slice(0, 30), ...(youAbout.trim() ? { about: youAbout.trim().slice(0, 160) } : {}) } : undefined;
    try {
      const r = await saveWorld(client, { existing: world, name: name.trim(), cover, you, file: picked?.file });
      if (r.uploadError) {
        // The world is saved; only the cover failed. Stay open on that world, showing why.
        setWorld(r.world);
        setCover(r.world.cover);
        if (r.created) setCreatedHere(true);
        setError(r.uploadError);
        setBusy(false);
        return;
      }
      if (r.created || createdHere) {
        audio.playSfx("ui_confirm");
        close();
        navigate({ name: "hub", worldId: r.world.id });
        toast({ variant: "success", text: `${r.world.name} is ready. Summon someone.` });
      } else {
        toast({ variant: "success", text: "World updated." });
        close();
      }
    } catch (e) {
      setError((e as HorizonErrorShape)?.message ?? "Couldn't save the world.");
      setBusy(false);
    }
  };

  const del = () => {
    if (!world) return;
    close();
    openOverlay("O03", {
      title: `Delete ${world.name}?`,
      body: `Every character (${world.characterCount}) and session in this world will be deleted. Other worlds are untouched.`,
      typed: world.name,
      confirmLabel: "Delete world",
      onConfirm: async () => {
        await client.worlds.delete(world.id);
        navigate({ name: "worlds" }, { transition: "slash-back" });
        toast({ variant: "info", text: `Deleted ${world.name}.` });
      },
    });
  };

  return (
    <Modal
      title={world ? "Edit world" : "New world"}
      tape={world ? "WORLD" : "CREATE"}
      size="lg"
      onClose={close}
      actions={
        <>
          {world && <Button variant="ghost" className={s.del} onClick={del}>Delete world…</Button>}
          <Button variant="ghost" onClick={close}>Cancel</Button>
          <Button disabled={busy} onClick={() => void save()}>{busy ? "Saving…" : world ? "Save" : "Create world ▸"}</Button>
        </>
      }
    >
      <form className={s.editor} onSubmit={(e) => { e.preventDefault(); void save(); }}>
        <div className={s.preview} aria-hidden="true">
          <div className={s.previewCard}>
            <WorldCover cover={shown} className={s.previewCover} />
            <span className={s.previewShade} />
            <span className={s.previewName}>{name.trim() || "Your world"}</span>
            {youName.trim() && <span className={s.previewYou}><b>YOU</b> {youName.trim()}</span>}
          </div>
        </div>
        <div className={s.fields}>
          <TextField
            label="Name"
            value={name}
            maxLength={40}
            counter
            autoFocus
            placeholder="e.g. Harbour Street"
            onChange={(e) => setName(e.target.value)}
            onBlur={() => setTouched(true)}
            error={showNameError}
          />
          <fieldset className={s.covers}>
            <legend className={s.legend}>Cover</legend>
            <div className={s.coverGrid} role="radiogroup" aria-label="Cover">
              {COVER_PRESETS.map((p) => {
                const on = !picked && cover.kind === "preset" && cover.presetId === p.id;
                return (
                  <button
                    key={p.id}
                    type="button"
                    role="radio"
                    aria-checked={on}
                    aria-label={p.name}
                    title={p.name}
                    className={s.coverOpt}
                    onClick={() => pickPreset(p.id)}
                  >
                    <WorldCover presetId={p.id} chrome={false} className={s.coverThumb} />
                  </button>
                );
              })}
              <button
                type="button"
                role="radio"
                aria-checked={shown.kind !== "preset"}
                className={`${s.coverOpt} ${s.upload}`}
                onClick={() => file.current?.click()}
              >
                {shown.kind !== "preset" && shown.url ? <img src={shown.url} alt="" className={s.coverThumb} /> : <span>Upload<br />image</span>}
              </button>
              <input ref={file} type="file" accept={COVER_TYPES.join(",")} hidden onChange={onUpload} />
            </div>
          </fieldset>
          <fieldset className={s.you}>
            <legend className={s.legend}>You in this world <span className={s.optional}>optional</span></legend>
            <p className={s.youHint}>Characters here will know you by this. Other worlds never see it.</p>
            <TextField label="Your name here" value={youName} maxLength={30} counter placeholder="You" onChange={(e) => setYouName(e.target.value)} />
            <TextArea label="One line about you" value={youAbout} maxLength={160} counter rows={2} placeholder="e.g. Hana's boyfriend, works in IT" onChange={(e) => setYouAbout(e.target.value)} />
          </fieldset>
          {error && <ErrorTape message={error} />}
          <button type="submit" hidden />
        </div>
      </form>
    </Modal>
  );
}
